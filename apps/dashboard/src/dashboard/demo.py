"""Opt-in local demo. Runs the real agent cores on reference modules and a sim bank.

The normal dashboard remains read-only. Only ``create_demo_app`` adds the demo
controls, and the launcher binds them to loopback.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import asdict
from pathlib import Path
from typing import Literal

import yaml
from buyer_agent.buyer_core import BuyerCore
from cogit_finance.escrow import EscrowCore, settings
from cogit_finance_catalog_module import CatalogModule
from cogit_finance_deals_module import DealsModule
from cogit_finance_seams import SimBankClient
from cogit_messaging_shim import DeliveryLoop
from cogit_messaging_shim.seams import ShimMessaging
from cogit_messaging_shim.testing import LocalBus
from evaluator_agent.evaluator import EvaluatorCore
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from seller_agent.seller import SellerCore

from .app import STATIC, create_app
from .boris import BorisBankPort, BorisGateway, BorisModulePort, offline_report
from .sources import ModuleSource

log = logging.getLogger(__name__)
AGENTS = (
    ("cogit-finance", "operator-co", "escrow"),
    ("seller-agent", "seller-co", "seller"),
    ("buyer-agent", "buyer-co", "buyer"),
    ("evaluator-agent", "operator-co", "evaluator"),
)


class DemoEngine:
    def __init__(self, root: Path, *, bank_url: str = "http://127.0.0.1:8080", bank=None,
                 step_delay: float = 1.0, boris: BorisGateway | None = None):
        self.boris = boris
        self.bank = bank if bank is not None else SimBankClient.from_url(bank_url)
        self.bank.accounts()  # fail at startup if the bank is unreachable
        self.step_delay = step_delay
        self.bus = LocalBus()
        self.bus.host.install(CatalogModule())
        self.bus.host.install(DealsModule())
        self.keys = {name: self.bus.add_agent(name, org, role,
                                            boris.agent_keys.get(name) if boris else None)
                     for name, org, role in AGENTS}
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.worker: threading.Thread | None = None
        self.requests: dict[str, dict] = {}
        self.current: dict = {"running": False, "deal_id": None, "scenario": None, "error": None}

        operator = self.bus.host.port("operator", "operator")
        data = root / "data/demo"
        for company in yaml.safe_load((data / "companies.yaml").read_text(encoding="utf-8"))["companies"]:
            operator.module_command(
                "cogit-finance-catalog", "company.upsert", {"company": company},
                idempotency_key=f"seed:company:{company['org_id']}",
            )
        for evaluator in yaml.safe_load((data / "evaluators.yaml").read_text(encoding="utf-8"))["evaluators"]:
            evaluator["did"] = self.keys["evaluator-agent"].did
            operator.module_command(
                "cogit-finance-catalog", "evaluator.upsert", {"evaluator": evaluator},
                idempotency_key=f"seed:evaluator:{evaluator['evaluator_id']}",
            )
        self.offers = yaml.safe_load((data / "offers.seller-co.yaml").read_text(encoding="utf-8"))["offers"]
        self.buyer = BuyerCore(self._modules("buyer-agent"), self._messaging("buyer-agent"), self._bank("buyer-agent"))
        self.escrow = EscrowCore(
            self._modules("cogit-finance"), self._bank("cogit-finance"), self.bus.artifacts,
            self.keys["cogit-finance"], settings.load_operator_config(), settings.PACKAGED_CONTRACTS_DIR,
        )
        self.bus.runtime.register("buyer-agent", self._invoke_buyer)
        self.bus.runtime.register("cogit-finance", self.escrow)
        self.bus.runtime.register("evaluator-agent", EvaluatorCore(
            messaging=self.bus.messaging("evaluator-agent"), artifacts=self.bus.artifacts,
            escrow_did=self.keys["cogit-finance"].did,
        ))
        self._set_seller("happy")
        self.escrow.register_types()
        self.source = ModuleSource(self.bus.host.port("dashboard", "operator_ro"), self.bank)

    def _modules(self, name: str):
        port = self.bus.host.port(name)
        if self.boris and name in {"buyer-agent", "seller-agent", "cogit-finance"}:
            return BorisModulePort(port, self.boris, name, self.keys[name].did)
        return port

    def _messaging(self, name: str):
        return ShimMessaging(self.keys[name], self._modules(name))

    def _bank(self, name: str):
        return BorisBankPort(self.bank, self.boris, name) if self.boris else self.bank

    def boris_report(self, deal_id: str | None = None) -> dict:
        return self.boris.report(deal_id) if self.boris else offline_report(deal_id)

    def _invoke_buyer(self, action: str, payload: dict, request_key: str) -> dict:
        return asdict(getattr(self.buyer, action)(**payload))

    def _set_seller(self, scenario: str) -> None:
        seller = SellerCore(
            modules=self._modules("seller-agent"), artifacts=self.bus.artifacts,
            messaging=self._messaging("seller-agent"), escrow_did=self.keys["cogit-finance"].did,
            seller_org_id="seller-co", offers=self.offers, mode="broken" if scenario == "rework" else "ok",
        )
        seller.publish_catalog()
        self.bus.runtime.register("seller-agent", seller)

    def status(self) -> dict:
        with self.lock:
            result = {**self.current, "mode": "local-simulation"}
        result["state"] = None
        if result["deal_id"]:
            read = self.source.deal(result["deal_id"])
            result["state"] = (read.get("deal") or {}).get("state")
        result["boris"] = self.boris_report(result["deal_id"])
        return result

    def start(self, scenario: str, request_key: str, *, background: bool = True) -> dict:
        with self.lock:
            if request_key in self.requests:
                previous = self.requests[request_key]
                if previous["scenario"] != scenario:
                    raise ValueError("This request key belongs to a different scenario")
                return dict(previous)
            if self.current["running"]:
                raise RuntimeError("A purchase is already running")
            self._set_seller(scenario)
            result = asdict(self.buyer.start_purchase())
            if result["status"] != "requested":
                raise RuntimeError("No eligible offer was found")
            self.current = {"running": True, "deal_id": result["deal_id"], "scenario": scenario, "error": None}
            receipt = {**result, "scenario": scenario}
            self.requests[request_key] = receipt
            if background:
                self.worker = threading.Thread(target=self.run, daemon=True, name="demo-purchase")
                self.worker.start()
            return dict(receipt)

    def run(self) -> None:
        """Deliver signed messages through the existing admission/ack loop."""
        idle = 0
        deal_id = self.current["deal_id"]
        try:
            for _ in range(120):
                if self.stop.is_set():
                    raise RuntimeError("Demo stopped before completion")
                handled = sum(
                    DeliveryLoop(name, self.bus.host.port(name), self.bus.runtime, limit=1).run_once()
                    for name, _, _ in AGENTS
                )
                self.escrow.tick()
                runs = [
                    run for run in self.bus.runtime.runs.values()
                    if run.input.get("envelope", {}).get("conversation_id") == deal_id
                ]
                failures = [run for run in runs if run.status == "failed"]
                if failures:
                    raise RuntimeError(failures[-1].error or "An agent run failed")
                state = self.status()["state"]
                if state == "SETTLED":
                    self.bus.pump()  # deliver the final payout notices and receipts
                    return
                idle = idle + 1 if handled == 0 else 0
                if idle >= 5 or state in {"DISPUTED", "REFUNDED", "EXPIRED", "CANCELLED", "DECLINED"}:
                    rejected = [run.output for run in runs if (run.output or {}).get("status") == "rejected"]
                    raise RuntimeError(f"Purchase stopped in {state or 'no deal'}; {rejected[-1:]}")
                self.stop.wait(self.step_delay)
            raise RuntimeError("Purchase did not complete within 120 delivery rounds")
        except Exception as exc:
            log.exception("Local demo purchase failed")
            with self.lock:
                self.current["error"] = str(exc)
        finally:
            with self.lock:
                self.current["running"] = False

    def close(self) -> None:
        self.stop.set()
        if self.worker is not None:
            self.worker.join(timeout=10)


class PurchaseRequest(BaseModel):
    scenario: Literal["happy", "rework"] = "happy"


def create_demo_app(engine: DemoEngine) -> FastAPI:
    app = create_app(engine.source)
    app.state.demo = engine

    @app.get("/demo")
    def controls():
        return FileResponse(STATIC / "demo.html", media_type="text/html")

    @app.get("/api/demo/status")
    def status():
        return engine.status()

    @app.get("/api/demo/boris")
    def boris_evidence(deal_id: str | None = None):
        return engine.boris_report(deal_id)

    @app.post("/api/demo/purchases", status_code=202)
    def purchase(request: PurchaseRequest, idempotency_key: str = Header(min_length=1, max_length=200)):
        try:
            return engine.start(request.scenario, idempotency_key)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.get("/api/demo/deals/{deal_id}/delivery")
    def download_delivery(deal_id: str):
        read = engine.source.deal(deal_id)
        deliveries = read.get("deliveries") or []
        if not deliveries:
            archived = getattr(engine, "archived_delivery", lambda _: None)(deal_id)
            if archived is not None:
                return Response(archived, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="delivery-{deal_id}.zip"'})
            raise HTTPException(404, "No delivery exists for this deal")
        delivery = max(deliveries, key=lambda item: item["attempt"])
        return Response(
            engine.bus.artifacts.get(delivery["artifact_id"]), media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="report-{deal_id}.zip"'},
        )

    return app
