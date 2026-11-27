"""Catalog checkout with explicit funding, delivery and settlement steps."""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import asdict, replace
from pathlib import Path
from typing import Literal

from cogit_finance.escrow import EscrowCore, settings
from cogit_finance.escrow.money import split
from cogit_messaging_shim import DeliveryLoop
from fastapi import Header, HTTPException
from jsonschema import Draft202012Validator
from pydantic import BaseModel, ConfigDict, Field
from seller_agent.deliverable import build_service_deliverable
from seller_agent.seller import SellerCore

from .demo import AGENTS, DemoEngine, create_demo_app
from .view import deal_view, format_minor

log = logging.getLogger(__name__)
TERMINAL = {"SETTLED", "REFUNDED", "CANCELLED", "DECLINED", "EXPIRED"}


class CatalogDemoEngine(DemoEngine):
    def __init__(self, root: Path, *, history_file: Path | None = None, **kwargs):
        self.orders: dict[str, dict] = {}
        self.release_permissions: set[str] = set()
        self.history_file = history_file
        self.archived_views: dict[str, dict] = {}
        if history_file and history_file.is_file():
            self.archived_views = json.loads(history_file.read_text(encoding="utf-8")).get("views", {})
        super().__init__(root, **kwargs)
        company = self.bus.host.port("buyer-agent").module_query(
            "cogit-finance-catalog", "company.read", {"org_id": self.buyer.settings.org_id},
        )["company"]
        self.buyer.settings = replace(self.buyer.settings, max_price_minor=company["spending_limit_minor"])
        self.escrow = EscrowCore(
            self.bus.host.port("cogit-finance"), self.bank, self.bus.artifacts,
            self.keys["cogit-finance"], settings.load_operator_config(), settings.PACKAGED_CONTRACTS_DIR,
            release_authorized=lambda deal_id: deal_id in self.release_permissions,
        )
        self.bus.runtime.register("cogit-finance", self.escrow)

    def _set_seller(self, scenario: str) -> None:
        seller = SellerCore(
            modules=self.bus.host.port("seller-agent"), artifacts=self.bus.artifacts,
            messaging=self.bus.messaging("seller-agent"), escrow_did=self.keys["cogit-finance"].did,
            seller_org_id="seller-co", offers=self.offers, mode="broken" if scenario == "rework" else "ok",
            build_delivery=self._build_delivery,
        )
        seller.publish_catalog()
        self.bus.runtime.register("seller-agent", seller)

    def _build_delivery(self, deal_id: str, complete: bool) -> bytes:
        read = self.source.deal(deal_id)
        terms = read["deal"]["terms"]
        offer = self._offer(terms["seller_org_id"], terms["offer_id"])
        return build_service_deliverable(deal_id, offer, terms["inputs"], include_summary=complete)

    def _offer(self, seller_org_id: str, offer_id: str) -> dict:
        rows = self.bus.host.port("buyer-agent").module_query(
            "cogit-finance-catalog", "catalog.read", {"seller_org_id": seller_org_id},
        )["offers"]
        offer = next((row for row in rows if row["offer_id"] == offer_id and row["active"]), None)
        if offer is None:
            raise ValueError("This service is no longer available")
        return offer

    def services(self) -> list[dict]:
        port = self.bus.host.port("buyer-agent")
        sellers = port.module_query("cogit-finance-catalog", "sellers.list", {})["sellers"]
        rows = []
        fee_bps = self.escrow.config["escrow"]["fee_bps"]
        for seller in sellers:
            identity = port.module_query("cogit-messaging", "identity.resolve", {"role": "seller", "org_id": seller["org_id"]}).get("identity")
            if not identity:
                continue
            offers = port.module_query("cogit-finance-catalog", "catalog.read", {"seller_org_id": seller["org_id"]})["offers"]
            for offer in offers:
                if not offer["active"] or offer["currency"] != "EUR":
                    continue
                payout, fee = split(offer["price_minor"], fee_bps)
                rows.append({
                    **offer, "seller_name": seller["legal_name"], "demo": True,
                    "price": format_minor(offer["price_minor"]), "payout_minor": payout,
                    "fee_minor": fee, "fee_bps": fee_bps,
                    "payout": format_minor(payout), "fee": format_minor(fee),
                })
        return sorted(rows, key=lambda row: (row["title"].casefold(), row["seller_org_id"], row["offer_id"]))

    def start(self, *args, **kwargs):
        raise ValueError("Select a service from the catalog and review its terms first")

    def _replay(self, action: str, request_key: str, fingerprint: dict) -> dict | None:
        stored = self.requests.get(f"{action}:{request_key}")
        if stored is None:
            return None
        if stored["fingerprint"] != fingerprint:
            raise ValueError("This request key was already used for different details")
        return dict(stored["result"])

    def _launch(self, action: str, request_key: str, fingerprint: dict, deal_id: str, targets: set[str], background: bool) -> dict:
        self.current = {"running": True, "deal_id": deal_id, "scenario": self.orders[deal_id]["scenario"], "error": None, "action": action}
        result = {"deal_id": deal_id, "action": action, "status": "processing"}
        self.requests[f"{action}:{request_key}"] = {"fingerprint": fingerprint, "result": result}
        if background:
            self.worker = threading.Thread(target=self.run_phase, args=(targets,), daemon=True, name=f"checkout-{action}")
            self.worker.start()
        return result

    def prepare(self, seller_org_id: str, offer_id: str, inputs: dict, request_key: str, *, background: bool = True) -> dict:
        fingerprint = {"seller_org_id": seller_org_id, "offer_id": offer_id, "inputs": inputs}
        with self.lock:
            repeated = self._replay("prepare", request_key, fingerprint)
            if repeated:
                return repeated
            if self.current["running"]:
                raise RuntimeError("The agents are still processing the current step")
            if self.current["deal_id"] and self.status()["state"] not in TERMINAL:
                raise RuntimeError("Complete the current checkout before choosing another service")
            service = next((row for row in self.services() if row["seller_org_id"] == seller_org_id and row["offer_id"] == offer_id), None)
            if service is None:
                raise ValueError("Choose an available service from the catalog")
            errors = list(Draft202012Validator(service["input_schema"]).iter_errors(inputs))
            if errors:
                raise ValueError(errors[0].message)
            self._set_seller("happy")
            purchase = self.buyer.request_offer(seller_org_id, offer_id, inputs)
            deal_id = purchase.deal_id
            self.orders[deal_id] = {"service": service, "inputs": dict(inputs), "scenario": "happy"}
            return self._launch("prepare", request_key, fingerprint, deal_id, {"QUOTED"}, background)

    def advance(self, deal_id: str, action: str, request_key: str, *, scenario: str = "happy", background: bool = True) -> dict:
        expected = {"fund": {"QUOTED", "FUNDING_REQUESTED"}, "deliver": {"FUNDED", "REJECTED"}, "release": {"APPROVED"}}
        targets = {"fund": {"FUNDED"}, "deliver": {"APPROVED", "REJECTED"}, "release": {"SETTLED"}}
        fingerprint = {"deal_id": deal_id, "scenario": scenario if action == "deliver" else None}
        with self.lock:
            repeated = self._replay(action, request_key, fingerprint)
            if repeated:
                return repeated
            if action not in expected or deal_id not in self.orders:
                raise ValueError("Unknown checkout or action")
            if self.current["running"]:
                raise RuntimeError("The agents are still processing the current step")
            state = (self.source.deal(deal_id).get("deal") or {}).get("state")
            if state not in expected[action]:
                raise RuntimeError(f"Cannot {action} a deal in {state or 'unknown'} state")
            if action == "deliver":
                if state != "REJECTED":
                    self.orders[deal_id]["scenario"] = scenario
                self._set_seller(self.orders[deal_id]["scenario"])
            if action == "release":
                self.release_permissions.add(deal_id)
            return self._launch(action, request_key, fingerprint, deal_id, targets[action], background)

    def run_phase(self, targets: set[str]) -> None:
        idle = 0
        deal_id = self.current["deal_id"]
        initial = self.source.deal(deal_id).get("deal") or {}
        initial_head = initial.get("head_seq", 0)
        try:
            for _ in range(150):
                if self.stop.is_set():
                    raise RuntimeError("Checkout stopped")
                handled = 0
                for name, _, _ in AGENTS:
                    handled += DeliveryLoop(name, self.bus.host.port(name), self.bus.runtime, limit=1).run_once()
                    self.escrow.tick()
                    runs = [run for run in self.bus.runtime.runs.values() if run.input.get("envelope", {}).get("conversation_id") == deal_id]
                    failures = [run for run in runs if run.status == "failed"]
                    if failures:
                        raise RuntimeError(failures[-1].error or "An agent step failed")
                    deal = self.source.deal(deal_id).get("deal") or {}
                    state = deal.get("state")
                    if state in targets and deal.get("head_seq", 0) > initial_head:
                        return
                    if state in TERMINAL or state == "DISPUTED":
                        raise RuntimeError(f"Checkout stopped in {state}")
                idle = idle + 1 if handled == 0 else 0
                if idle >= 5:
                    raise RuntimeError("The checkout could not advance; no agent message is pending")
                self.stop.wait(self.step_delay)
            raise RuntimeError("The checkout step exceeded its delivery limit")
        except Exception as exc:
            log.exception("Checkout step failed")
            with self.lock:
                self.current["error"] = str(exc)
        finally:
            with self.lock:
                self.current["running"] = False

    def status(self) -> dict:
        result = super().status()
        order = self.orders.get(result["deal_id"])
        result["order"] = order
        result["allowed_actions"] = []
        if order:
            terms = (self.source.deal(result["deal_id"]).get("deal") or {}).get("terms")
            result["terms"] = terms
            if terms:
                payout, fee = split(terms["price_minor"], terms["fee_bps"])
                result["payment"] = {
                    "price": format_minor(terms["price_minor"], terms["currency"]),
                    "payout": format_minor(payout, terms["currency"]),
                    "fee": format_minor(fee, terms["currency"]),
                    "to_iban": self.escrow.config["rail"]["escrow_iban"],
                }
            if not result["running"]:
                result["allowed_actions"] = {
                    "QUOTED": ["fund"], "FUNDING_REQUESTED": ["fund"], "FUNDED": ["deliver"],
                    "REJECTED": ["deliver"], "APPROVED": ["release"], "SETTLED": ["browse"],
                }.get(result["state"], [])
        return result

    def archived_delivery(self, deal_id: str) -> bytes | None:
        if not self.history_file or deal_id not in self.archived_views:
            return None
        path = self.history_file.parent / "deliveries" / f"{deal_id}.zip"
        return path.read_bytes() if path.is_file() else None

    def close(self) -> None:
        super().close()
        if self.history_file:
            views = dict(self.archived_views)
            folder = self.history_file.parent / "deliveries"
            folder.mkdir(parents=True, exist_ok=True)
            for row in self.source.deals():
                read = self.source.deal(row["deal_id"])
                views[row["deal_id"]] = deal_view(read, self.source.balances(row["deal_id"]))
                if read["deliveries"]:
                    delivery = max(read["deliveries"], key=lambda item: item["attempt"])
                    (folder / f"{row['deal_id']}.zip").write_bytes(self.bus.artifacts.get(delivery["artifact_id"]))
            self.history_file.write_text(json.dumps({"views": views}, ensure_ascii=False), encoding="utf-8")


class OrderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    seller_org_id: str = Field(min_length=1, max_length=128)
    offer_id: str = Field(min_length=1, max_length=128)
    inputs: dict = Field(default_factory=dict)


class DeliveryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario: Literal["happy", "rework"] = "happy"


def create_checkout_app(engine: CatalogDemoEngine):
    app = create_demo_app(engine)
    app.state.archived_views = engine.archived_views
    app.state.service_titles = {(row["seller_org_id"], row["offer_id"]): row["title"] for row in engine.services()}

    def execute(function, *args, **kwargs):
        try:
            return function(*args, **kwargs)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.get("/api/demo/services")
    def services():
        return {"services": engine.services()}

    @app.post("/api/demo/orders", status_code=202)
    def prepare(request: OrderRequest, idempotency_key: str = Header(min_length=1, max_length=200)):
        return execute(engine.prepare, request.seller_org_id, request.offer_id, request.inputs, idempotency_key)

    @app.post("/api/demo/orders/{deal_id}/fund", status_code=202)
    def fund(deal_id: str, idempotency_key: str = Header(min_length=1, max_length=200)):
        return execute(engine.advance, deal_id, "fund", idempotency_key)

    @app.post("/api/demo/orders/{deal_id}/deliver", status_code=202)
    def deliver(deal_id: str, request: DeliveryRequest, idempotency_key: str = Header(min_length=1, max_length=200)):
        return execute(engine.advance, deal_id, "deliver", idempotency_key, scenario=request.scenario)

    @app.post("/api/demo/orders/{deal_id}/release", status_code=202)
    def release(deal_id: str, idempotency_key: str = Header(min_length=1, max_length=200)):
        return execute(engine.advance, deal_id, "release", idempotency_key)

    return app
