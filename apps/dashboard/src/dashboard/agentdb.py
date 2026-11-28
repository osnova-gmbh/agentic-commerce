"""Persistent AgentDb-backed dashboard and scheduler for four external workers."""

from __future__ import annotations

import json
import logging
import threading
import uuid
from pathlib import Path
from urllib.parse import quote, urlparse

import httpx
from pydantic import BaseModel

from cogit_finance_seams import SimBankClient
from cogit_finance_seams.native import decode_result, encode_args
from .sources import ModuleSource

log = logging.getLogger(__name__)
ROLES = ("buyer-agent", "seller-agent", "evaluator-agent", "cogit-finance")


class PurchaseRequest(BaseModel):
    scenario: str = "happy"


class AgentDbClient:
    def __init__(self, url: str, token: str, tenant_id: str, *, transport=None):
        parsed = urlparse(url)
        if parsed.scheme != "https" and not (
            parsed.scheme == "http"
            and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
        ):
            raise ValueError(
                "AgentDb needs HTTPS, or loopback HTTP for the local stack"
            )
        self.tenant_id = str(uuid.UUID(tenant_id))
        self.http = httpx.Client(
            base_url=url.rstrip("/"),
            headers={"Authorization": f"Bearer {token}"},
            timeout=20,
            follow_redirects=False,
            transport=transport,
        )

    def close(self):
        self.http.close()

    def request(self, method, path, payload=None, *, key=None):
        headers = {"x-agentdb-correlation-id": str(uuid.uuid4())}
        if key:
            headers["Idempotency-Key"] = key
        response = self.http.request(method, path, json=payload, headers=headers)
        response.raise_for_status()
        return response.json()

    def admit(self, installation_id, command, payload, key):
        return self.request(
            "POST",
            "/v1/queries",
            {
                "installationId": installation_id,
                "input": {
                    "text": json.dumps(
                        {"command": command, "payload": payload}, separators=(",", ":")
                    )
                },
            },
            key=key,
        )["runId"]

    def run(self, run_id):
        return self.request("GET", f"/v1/runs/{uuid.UUID(run_id)}")

    def output(self, run_id):
        result = self.request("GET", f"/v1/runs/{uuid.UUID(run_id)}/result")
        artifact = result["resultArtifactId"]
        response = self.http.get(f"/v1/artifacts/{uuid.UUID(artifact)}/content")
        response.raise_for_status()
        value = response.json()
        if isinstance(value, dict) and isinstance(value.get("content"), str):
            value = json.loads(value["content"])
        return value.get("output", value) if isinstance(value, dict) else value

    def module_query(self, module, export, args=None):
        path = f"/v1/tenants/{self.tenant_id}/modules/{quote(module, safe='')}/queries/{quote(export, safe='')}"
        response = self.request(
            "POST",
            path,
            {
                "moduleVersion": "1.1.0",
                "exportVersion": "1.1.0",
                "contractId": f"{module}.{export}.v1",
                "input": encode_args(args),
            },
            key=f"read:{uuid.uuid4()}",
        )
        return decode_result(response)


class PersistentScheduler:
    """A persisted outbox for admission; retries reuse exactly the same request key."""

    TERMINAL = {"completed", "succeeded", "failed", "cancelled", "rejected", "expired"}

    def __init__(self, client: AgentDbClient, routes: dict, journal: Path):
        self.client, self.routes, self.journal = client, routes, journal
        self.lock = threading.RLock()
        self.pending = (
            json.loads(journal.read_text(encoding="utf-8")) if journal.exists() else {}
        )
        self.failures_path = journal.with_name("scheduler-failures.json")
        self.failures = (json.loads(self.failures_path.read_text(encoding="utf-8"))
                         if self.failures_path.exists() else {})

    def save(self):
        self.journal.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.journal.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.pending, indent=2) + "\n", encoding="utf-8")
        tmp.replace(self.journal)

    def schedule(self, slot, role, command, payload=None):
        with self.lock:
            current = self.pending.get(slot)
            if current is None:
                current = {
                    "key": f"commerce:{uuid.uuid4()}",
                    "role": role,
                    "command": command,
                    "payload": payload or {},
                    "run_id": None,
                }
                self.pending[slot] = current
                self.save()  # committed before admission can have an external effect
            if current["run_id"] is None:
                current["run_id"] = self.client.admit(
                    self.routes[role]["installationId"],
                    current["command"],
                    current["payload"],
                    current["key"],
                )
                self.save()
            return current["run_id"]

    def poll(self):
        with self.lock:
            for slot, current in list(self.pending.items()):
                try:
                    run_id = self.schedule(
                        slot, current["role"], current["command"], current["payload"]
                    )
                    state = self.client.run(run_id).get("lifecycle")
                except (httpx.HTTPError, OSError, ValueError):
                    log.exception("Unable to poll %s; retaining its admission key", slot)
                    continue
                if state in self.TERMINAL:
                    if state not in {"completed", "succeeded"}:
                        self.failures[run_id] = {**current, "slot": slot, "state": state}
                        tmp = self.failures_path.with_suffix(".tmp")
                        tmp.write_text(json.dumps(self.failures, indent=2) + "\n", encoding="utf-8")
                        tmp.replace(self.failures_path)  # preserve evidence before releasing the slot
                        log.error("AgentDb job %s ended %s: %s", slot, state, run_id)
                    del self.pending[slot]
                    self.save()
            for role in ROLES:
                try:
                    self.schedule(f"inbox:{role}", role, "drain_inbox")
                except (httpx.HTTPError, OSError):
                    log.exception("Inbox admission unavailable for %s", role)
            try:
                self.schedule("escrow:tick", "cogit-finance", "tick")
            except (httpx.HTTPError, OSError):
                log.exception("Escrow tick admission unavailable")


class AgentDbEngine:
    def __init__(
        self,
        client,
        routes,
        state_dir: Path,
        *,
        reader,
        bank_url="http://127.0.0.1:8080",
        interval=2,
    ):
        self.client, self.routes, self.state_dir, self.interval = (
            client,
            routes,
            state_dir,
            interval,
        )
        state_dir.mkdir(parents=True, exist_ok=True)
        self.bank = SimBankClient.from_url(bank_url)
        self.reader = reader
        self.source = ModuleSource(self.reader, self.bank)
        self.scheduler = PersistentScheduler(
            client, routes, state_dir / "scheduler.json"
        )
        self.stop = threading.Event()
        self.error = None
        self.purchases_path = state_dir / "purchases.json"
        self.purchases = (
            json.loads(self.purchases_path.read_text())
            if self.purchases_path.exists()
            else {}
        )
        self.worker = None

    def start_scheduler(self):
        self.worker = threading.Thread(
            target=self.run, daemon=True, name="agentdb-admission"
        )
        self.worker.start()

    def run(self):
        while not self.stop.is_set():
            try:
                self.scheduler.poll()
                self.error = None
            except Exception as exc:
                self.error = str(exc)
                log.exception("AgentDb scheduler failed; preserving admission records")
            self.stop.wait(self.interval)

    def start(self, scenario, request_key):
        if scenario != "happy":
            raise ValueError(
                "This AgentDb deployment runs the successful-delivery scenario"
            )
        if not request_key or len(request_key) > 200:
            raise ValueError("A bounded request key is required")
        if request_key not in self.purchases:
            run_id = self.client.admit(
                self.routes["buyer-agent"]["installationId"],
                "start_purchase",
                {},
                f"purchase:{request_key}",
            )
            self.purchases[request_key] = {"run_id": run_id, "scenario": scenario}
            tmp = self.purchases_path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(self.purchases, indent=2) + "\n", encoding="utf-8"
            )
            tmp.replace(self.purchases_path)
        return self.purchases[request_key]

    def status(self):
        latest = (
            next(reversed(self.purchases.values()), None) if self.purchases else None
        )
        status = {
            "mode": "agentdb",
            "running": False,
            "deal_id": None,
            "scenario": "happy",
            "state": None,
            "error": self.error,
            "failed_runs": list(self.scheduler.failures.values()),
            "supported_scenarios": ["happy"],
        }
        if latest:
            run = self.client.run(latest["run_id"])
            status["running"] = run.get("lifecycle") not in PersistentScheduler.TERMINAL
            if run.get("lifecycle") in {"completed", "succeeded"}:
                output = self.client.output(latest["run_id"])
                status["deal_id"] = output.get("deal_id")
                if status["deal_id"]:
                    status["state"] = self.source.deal(status["deal_id"])["deal"][
                        "state"
                    ]
                    status["running"] = status["state"] not in {
                        "SETTLED",
                        "REFUNDED",
                        "DISPUTED",
                        "CANCELLED",
                        "DECLINED",
                        "EXPIRED",
                    }
        return status

    def close(self):
        self.stop.set()
        if self.worker:
            self.worker.join(timeout=25)
        self.client.close()
        if self.reader is not self.client:
            self.reader.close()


def create_agentdb_app(engine):
    from fastapi import Header, HTTPException
    from fastapi.responses import FileResponse
    from .app import STATIC, create_app

    app = create_app(engine.source)

    @app.get("/demo")
    def page():
        return FileResponse(STATIC / "agentdb.html")

    @app.get("/api/demo/status")
    def status():
        return engine.status()

    @app.post("/api/demo/purchases", status_code=202)
    def purchase(
        request: PurchaseRequest,
        idempotency_key: str = Header(min_length=1, max_length=200),
    ):
        try:
            return engine.start(request.scenario, idempotency_key)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.get("/api/demo/deals/{deal_id}/delivery")
    def download(deal_id: str):
        from fastapi.responses import Response

        deliveries = engine.source.deal(deal_id).get("deliveries") or []
        if not deliveries:
            raise HTTPException(404, "No delivery exists for this deal")
        artifact = max(deliveries, key=lambda row: row["attempt"])["artifact_id"]
        result = engine.reader.http.get(f"/v1/artifacts/{uuid.UUID(artifact)}/bytes")
        result.raise_for_status()
        return Response(
            result.content,
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="report-{uuid.UUID(deal_id)}.zip"'
            },
        )

    return app
