# pyright: basic
"""Fakes and builders for the buyer tests: module port, bank and signed envelopes."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from cogit_finance_seams import BankError, ModuleError
from cogit_messaging_shim import AgentKey, build_envelope, canonical_hash
from cogit_messaging_shim.testing import RecordingMessaging

from buyer_agent.buyer_core import BuyerCore, BuyerSettings

CATALOG = "cogit-finance-catalog"
MESSAGING = "cogit-messaging"
DEAL_ID = "0b0e7c4e-6f0a-4c56-9c3e-2f1f0a8d4b11"
BUYER_IBAN = "DE00EXAMPLE0000000010"
ESCROW_IBAN = "DE00EXAMPLE0000000001"

# Fresh keys per test session; no key material lives in the repository.
ESCROW_KEY = AgentKey.generate()
SELLER_KEY = AgentKey.generate()
BUYER_KEY = AgentKey.generate()


def seller(org_id: str = "seller-co", categories: tuple[str, ...] = ("reports",)):
    return {
        "org_id": org_id,
        "legal_name": f"{org_id} GmbH",
        "roles": ["seller"],
        "categories": list(categories),
    }


def offer(offer_id: str = "offer-1", price_minor: int = 50000, **changes: Any):
    row = {
        "seller_org_id": "seller-co",
        "offer_id": offer_id,
        "title": "Market report",
        "category": "reports",
        "price_minor": price_minor,
        "currency": "EUR",
        "delivery_time_s": 60,
        "active": True,
    }
    return {**row, **changes}


class FakeModules:
    """ModulePort with a catalog, an escrow identity and a recording queue."""

    def __init__(
        self,
        sellers: list[dict] | None = None,
        offers: dict[str, list[dict]] | None = None,
        escrow_did: str | None = None,
    ) -> None:
        self.sellers = sellers or []
        self.offers = offers or {}
        self.escrow_did = escrow_did
        self.queries: list[tuple[str, str, dict]] = []
        self.commands: list[tuple[str, str, dict, str]] = []
        self.queued: dict[str, dict] = {}

    def module_query(self, module: str, export: str, args: dict | None = None) -> dict:
        args = dict(args or {})
        self.queries.append((module, export, args))
        if (module, export) == (CATALOG, "sellers.list"):
            wanted = args.get("category")
            # Deliberately unsorted: the buyer must not rely on the list order.
            return {
                "sellers": [
                    row
                    for row in self.sellers
                    if wanted is None or wanted in row["categories"]
                ]
            }
        if (module, export) == (CATALOG, "catalog.read"):
            return {"offers": list(self.offers.get(args["seller_org_id"], []))}
        if (module, export) == (MESSAGING, "identity.resolve"):
            if self.escrow_did is None or args != {"role": "escrow"}:
                return {"identity": None}
            return {"identity": {"did": self.escrow_did, "role": "escrow"}}
        raise ModuleError("unknown_export", f"{module}.{export}")

    def module_command(
        self,
        module: str,
        export: str,
        args: dict | None = None,
        *,
        idempotency_key: str,
    ) -> dict:
        args = dict(args or {})
        self.commands.append((module, export, args, idempotency_key))
        if (module, export) != (MESSAGING, "message.send"):
            raise ModuleError("unknown_export", f"{module}.{export}")
        envelope = args["envelope"]
        status = "duplicate" if envelope["message_id"] in self.queued else "queued"
        self.queued.setdefault(envelope["message_id"], envelope)
        return {"message_id": envelope["message_id"], "status": status}

    def exports_called(self) -> list[str]:
        return [export for _, export, _ in self.queries]


class FakeBank:
    """BankPort that books one transfer per idempotency key, like the sim bank."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.booked: dict[str, dict] = {}
        self.error: BankError | None = None

    def transfer(self, **call: Any) -> dict:
        self.calls.append(dict(call))
        if self.error is not None:
            raise self.error
        key = call.pop("idempotency_key")
        first = self.booked.get(key)
        if first is None:
            number = len(self.booked) + 1
            first = {**call, "transfer_id": f"tr_{number}", "event_id": str(number)}
            self.booked[key] = first
        elif {name: first[name] for name in call} != call:
            raise BankError(409, "idempotency_conflict")
        return dict(first)

    def lookup(self, idempotency_key: str) -> dict | None:
        return self.booked.get(idempotency_key)

    def credits(self, iban: str, after: str = "0") -> list[dict]:
        return []

    def accounts(self) -> list[dict]:
        return []


@dataclass
class Rig:
    """A buyer core on fakes, with the fakes at hand for assertions."""

    buyer: BuyerCore
    modules: FakeModules
    messaging: RecordingMessaging
    bank: FakeBank


def rig(modules: FakeModules | None = None, **settings: Any) -> Rig:
    """Default settings with E's DID configured; ``settings`` override them."""
    modules = modules or FakeModules()
    messaging, bank = RecordingMessaging(BUYER_KEY), FakeBank()
    configured = replace(BuyerSettings(escrow_did=ESCROW_KEY.did), **settings)
    buyer = BuyerCore(modules, messaging, bank, configured)
    return Rig(buyer, modules, messaging, bank)


def signed(
    type_key: str,
    body: dict,
    *,
    key: AgentKey = ESCROW_KEY,
    recipient_did: str = BUYER_KEY.did,
    deal_id: str = DEAL_ID,
) -> dict:
    """An envelope signed by ``key``; by default from E to the buyer."""
    return build_envelope(key, key.did, type_key, 1, recipient_did, deal_id, body)


def terms(**changes: Any) -> dict:
    base = {
        "deal_id": DEAL_ID,
        "buyer_org_id": "buyer-co",
        "seller_org_id": "seller-co",
        "buyer_did": BUYER_KEY.did,
        "seller_did": SELLER_KEY.did,
        "escrow_did": ESCROW_KEY.did,
        "offer_id": "offer-1",
        "inputs": {"topic": "Agentic commerce"},
        "price_minor": 50000,
        "currency": "EUR",
        "fee_bps": 100,
        "delivery_deadline": "2026-11-27T12:01:00Z",
        "acceptance": {
            "evaluators": [
                {"evaluator_id": "integrity", "version": 1, "params": {}},
                {"evaluator_id": "deadline", "version": 1, "params": {}},
            ],
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
    }
    return {**base, **changes}


def terms_proposed(proposed: dict | None = None, **envelope_args: Any) -> dict:
    proposed = terms() if proposed is None else proposed
    body = {"terms": proposed, "terms_hash": canonical_hash(proposed)}
    return signed("finance.terms_proposed", body, **envelope_args)


def payment_request(amount_minor: int = 50000, **envelope_args: Any) -> dict:
    deal_id = envelope_args.get("deal_id", DEAL_ID)
    body = {
        "to_iban": ESCROW_IBAN,
        "amount_minor": amount_minor,
        "currency": "EUR",
        "reference": f"ESCROW-{deal_id}",
        "funding_due_by": "2026-11-27T12:15:00Z",
    }
    return signed("finance.payment_request", body, **envelope_args)


def relay(relayed: dict, seq: int = 2, state: str = "QUOTED") -> dict:
    deal = {"deal_id": relayed["conversation_id"], "seq": seq, "state": state}
    return signed("finance.relay", {"relayed": relayed, "deal": deal})


def quote() -> dict:
    """A quote as the seller sends it to E."""
    body = {
        "price_minor": 50000,
        "currency": "EUR",
        "delivery_deadline": "2026-11-27T12:01:00Z",
        "valid_until": "2026-11-27T12:10:00Z",
        "acceptance": terms()["acceptance"],
    }
    return signed("finance.quote", body, key=SELLER_KEY, recipient_did=ESCROW_KEY.did)
