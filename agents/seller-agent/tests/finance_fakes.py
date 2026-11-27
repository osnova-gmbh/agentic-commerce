"""Fakes and message builders shared by the seller's product tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jsonschema
from cogit_finance_seams import LocalArtifacts, ModuleError
from cogit_messaging_shim import AgentKey, build_envelope, canonical_hash
from cogit_messaging_shim.testing import RecordingMessaging

from seller_agent.offers import load_catalog
from seller_agent.seller import SellerCore

DEAL_ID = "5f0c7a52-3d0b-4a3e-9d55-0c1f4d0a7e11"
NOW = datetime(2026, 11, 27, 10, 0, 0, tzinfo=UTC)
REQUIRED_FILES = ["report.md", "data.csv", "summary.json"]
CONTRACTS = Path(__file__).resolve().parents[3] / "contracts" / "messages"


def assert_contract(envelope: dict[str, Any]) -> None:
    """Validate a message body against its frozen schema in ``contracts/messages``."""
    name = f"{envelope['type_key']}.v{envelope['type_version']}.json"
    schema = json.loads((CONTRACTS / name).read_text(encoding="utf-8"))
    jsonschema.validate(envelope["body"], schema)


class FakeModules:
    """Tiny ``ModulePort``: escrow identity, message queue and catalog."""

    def __init__(self, escrow_did: str | None = None) -> None:
        self.escrow_did = escrow_did
        self.queries: list[tuple[str, str, dict[str, Any]]] = []
        self.commands: list[tuple[str, str, dict[str, Any], str]] = []

    def module_query(
        self, module: str, export: str, args: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        self.queries.append((module, export, args or {}))
        if (module, export) == ("cogit-messaging", "identity.resolve"):
            if self.escrow_did is None:
                return {"identity": None}
            return {"identity": {"did": self.escrow_did, "role": "escrow"}}
        raise ModuleError("unknown_export", f"{module}.{export}")

    def module_command(
        self,
        module: str,
        export: str,
        args: dict[str, Any] | None = None,
        *,
        idempotency_key: str,
    ) -> dict[str, Any]:
        payload = args or {}
        self.commands.append((module, export, payload, idempotency_key))
        if (module, export) == ("cogit-messaging", "message.send"):
            return {"message_id": payload["envelope"]["message_id"], "status": "queued"}
        if (module, export) == ("cogit-finance-catalog", "catalog.publish"):
            return {"count": len(payload["offers"])}
        raise ModuleError("unknown_export", f"{module}.{export}")

    def sent(self) -> list[dict[str, Any]]:
        return [
            args["envelope"]
            for _, export, args, _ in self.commands
            if export == "message.send"
        ]

    def published(self) -> list[tuple[dict[str, Any], str]]:
        return [
            (args, key)
            for _, export, args, key in self.commands
            if export == "catalog.publish"
        ]


def from_escrow(
    escrow: AgentKey,
    seller_did: str,
    type_key: str,
    body: dict[str, Any],
    *,
    sender: AgentKey | None = None,
) -> dict[str, Any]:
    """A signed finance message to the seller, from E unless ``sender`` is given."""
    key = sender or escrow
    return build_envelope(key, key.did, type_key, 1, seller_did, DEAL_ID, body)


def service_request(
    buyer: AgentKey, escrow_did: str, *, offer_id: str = "offer-1"
) -> dict[str, Any]:
    body = {
        "seller_org_id": "seller-co",
        "offer_id": offer_id,
        "inputs": {"topic": "bicycles"},
        "max_price_minor": 60000,
        "currency": "EUR",
    }
    return build_envelope(
        buyer, buyer.did, "finance.service_request", 1, escrow_did, DEAL_ID, body
    )


def relay(
    escrow: AgentKey, seller_did: str, relayed: dict[str, Any], state: str = "REQUESTED"
) -> dict[str, Any]:
    body = {"relayed": relayed, "deal": {"deal_id": DEAL_ID, "seq": 1, "state": state}}
    return from_escrow(escrow, seller_did, "finance.relay", body)


def terms_proposed(escrow: AgentKey, seller_did: str, **changes: Any) -> dict[str, Any]:
    """``finance.terms_proposed`` for offer-1 as quoted; ``changes`` alter the terms."""
    deadline = "2026-11-27T10:01:00Z"
    terms = {
        "deal_id": DEAL_ID,
        "buyer_org_id": "buyer-co",
        "seller_org_id": "seller-co",
        "buyer_did": AgentKey.generate().did,
        "seller_did": seller_did,
        "escrow_did": escrow.did,
        "offer_id": "offer-1",
        "inputs": {"topic": "bicycles"},
        "price_minor": 50000,
        "currency": "EUR",
        "fee_bps": 100,
        "delivery_deadline": deadline,
        "acceptance": {
            "evaluators": [{"evaluator_id": "integrity", "version": 1, "params": {}}],
            "policy": "all",
            "max_attempts": 2,
        },
        "timers": {
            "quote_ttl_s": 600,
            "funding_due_s": 900,
            "delivery_time_s": 60,
            "rework_window_s": 600,
            "dispute_window_s": 3600,
            "evaluator_respond_s": 60,
        },
        **changes,
    }
    body = {"terms": terms, "terms_hash": canonical_hash(terms)}
    return from_escrow(escrow, seller_did, "finance.terms_proposed", body)


def funding_confirmed(escrow: AgentKey, seller_did: str) -> dict[str, Any]:
    body = {
        "amount_minor": 50000,
        "currency": "EUR",
        "bank_event_id": "7",
        "delivery_deadline": "2026-11-27T10:01:00Z",
    }
    return from_escrow(escrow, seller_did, "finance.funding_confirmed", body)


def decision(
    escrow: AgentKey, seller_did: str, outcome: str, attempts_left: int, attempt: int
) -> dict[str, Any]:
    body = {
        "delivery_id": f"{DEAL_ID}:d{attempt}",
        "outcome": outcome,
        "attempts_left": attempts_left,
        "rework_deadline": "2026-11-27T10:01:00Z" if outcome == "reject" else None,
        "reasons": ["missing_file: summary.json"] if outcome == "reject" else [],
    }
    return from_escrow(escrow, seller_did, "finance.decision", body)


class Rig:
    """A seller core on fake ports, with the packaged offers file."""

    def __init__(self, mode: str = "ok", delay_s: float = 0) -> None:
        self.escrow = AgentKey.generate()
        self.buyer = AgentKey.generate()
        self.modules = FakeModules()
        self.artifacts = LocalArtifacts()
        self.messaging = RecordingMessaging()
        self.did = self.messaging.did
        self.slept: list[float] = []
        self.catalog = load_catalog()
        self.core = SellerCore(
            modules=self.modules,
            artifacts=self.artifacts,
            messaging=self.messaging,
            escrow_did=self.escrow.did,
            seller_org_id=self.catalog["seller_org_id"],
            offers=self.catalog["offers"],
            mode=mode,
            delay_s=delay_s,
            sleep=self.slept.append,
            now=lambda: NOW,
        )
