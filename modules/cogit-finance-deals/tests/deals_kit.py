"""Builders and a thin client for the deals module tests."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

import pytest
from cogit_finance_deals_module import ZERO_HASH
from cogit_finance_seams import LocalModuleHost, ModuleError

MODULE = "cogit-finance-deals"
ESCROW = "cogit-finance"
ESCROW_DID = "did:key:z6MkEscrow"
BUYER_DID = "did:key:z6MkBuyer"
NEW_DEAL = {"buyer_org_id": "buyer-co", "seller_org_id": "seller-co", "offer_id": "offer-1"}
TERMS = {"deal_id": "deal-1", "price_minor": 50000, "currency": "EUR", "fee_bps": 100}
TERMS_HASH = hashlib.sha256(json.dumps(TERMS, sort_keys=True).encode()).hexdigest()


def event_hash(event: dict) -> str:
    """What E does (``cogit_messaging_shim.event_hash``); the module only stores the result."""
    names = ("deal_id", "seq", "prev_hash", "event_type", "source_message_id", "actor_did", "body", "state_after")
    canonical = json.dumps({name: event[name] for name in names}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(event["prev_hash"].encode() + canonical.encode()).hexdigest()


class Clock:
    def __init__(self) -> None:
        self.moment = datetime(2026, 11, 27, 12, 0, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.moment

    def advance(self, seconds: int) -> None:
        self.moment += timedelta(seconds=seconds)

    @property
    def ts(self) -> str:
        return self.moment.strftime("%Y-%m-%dT%H:%M:%SZ")


class Deals:
    """The module as E sees it. Every command gets a fresh idempotency key unless one is
    given, so a repeated call reaches the module and not the host's replay cache."""

    def __init__(self, host: LocalModuleHost, clock: Clock, installation_id: str = ESCROW) -> None:
        self.host, self.clock = host, clock
        self.port = host.port(installation_id)
        self._keys = 0

    def command(self, export: str, args: dict, key: str | None = None) -> dict:
        self._keys += 1
        return self.port.module_command(MODULE, export, args, idempotency_key=key or f"auto-{self._keys}")

    def query(self, export: str, args: dict | None = None) -> dict:
        return self.port.module_query(MODULE, export, args)

    def read(self, deal_id: str = "deal-1") -> dict:
        return self.query("deal.read", {"deal_id": deal_id})

    def head(self, deal_id: str = "deal-1") -> tuple[int, str]:
        deal = self.read(deal_id)["deal"]
        return (0, ZERO_HASH) if deal is None else (deal["head_seq"], deal["head_hash"])

    def event(self, deal_id: str, head: tuple[int, str], event_type: str, state_after: str, **fields) -> dict:
        event = {
            "deal_id": deal_id,
            "seq": head[0] + 1,
            "prev_hash": head[1],
            "event_type": event_type,
            "source_message_id": fields.pop("source_message_id", None),
            "actor_did": fields.pop("actor_did", ESCROW_DID),
            "body": fields.pop("body", {}),
            "state_after": state_after,
        }
        assert not fields, f"unknown event fields {sorted(fields)}"
        return {**event, "hash": event_hash(event)}

    def commit_args(self, event_type: str, state_after: str, *, deal_id: str = "deal-1", head=None, **extra) -> dict:
        """Arguments of the next commit on the current head (or on ``head``, to go stale)."""
        head = self.head(deal_id) if head is None else head
        names = ("source_message_id", "actor_did", "body")
        event = self.event(
            deal_id, head, event_type, state_after, **{name: extra.pop(name) for name in names if name in extra}
        )
        event.pop("deal_id")
        args = {"deal_id": deal_id, "expected_seq": head[0], "expected_hash": head[1], "event": event, **extra}
        if head[0] == 0 and "deal" not in args:
            args["deal"] = dict(NEW_DEAL)
        return args

    def commit(self, event_type: str, state_after: str, **extra) -> dict:
        key = extra.pop("key", None)
        return self.command("deal.commit", self.commit_args(event_type, state_after, **extra), key)

    def fails(self, export: str, args: dict) -> str:
        with pytest.raises(ModuleError) as error:
            self.command(export, args)
        return error.value.code

    def counts(self) -> dict:
        """Row count per table, straight from the database."""
        tables = ("deals", "events", "outbox", "deliveries", "evaluations", "payment_intents", "bank_credits")
        tables += ("ledger_postings",)
        return {name: self.host.db.execute(f"SELECT COUNT(*) FROM deal_{name}").fetchone()[0] for name in tables}


def envelope(message_id: str, type_key: str = "finance.quote") -> dict:
    return {"message_id": message_id, "type_key": type_key, "body": {"n": 1}, "signature": "sig"}


def outbox(*message_ids: str) -> list:
    return [{"outbox_id": message_id, "envelope": envelope(message_id)} for message_id in message_ids]


def delivery(attempt: int = 1, deal_id: str = "deal-1", **extra) -> dict:
    base = {
        "delivery_id": f"{deal_id}:d{attempt}",
        "attempt": attempt,
        "artifact_id": f"art_{attempt}",
        "sha256": "ab" * 32,
        "byte_length": 1234,
        "media_type": "application/zip",
        "delivered_at": "2026-11-27T12:01:00Z",
        "status": "delivered",
    }
    return {**base, **extra}


def evaluation(evaluator_id: str, attempt: int = 1, deal_id: str = "deal-1", **extra) -> dict:
    base = {
        "evaluation_request_id": f"{deal_id}:d{attempt}:{evaluator_id}@1",
        "delivery_id": f"{deal_id}:d{attempt}",
        "evaluator_id": evaluator_id,
        "evaluator_version": 1,
        "evaluator_did": "did:key:z6MkEvaluator",
        "respond_by": "2026-11-27T12:06:00Z",
        "resends": 0,
        "verdict_message_id": None,
        "outcome": None,
    }
    return {**base, **extra}


def intent(kind: str, amount_minor: int, deal_id: str = "deal-1", **extra) -> dict:
    base = {
        "intent_id": f"{deal_id}:{kind}",
        "kind": kind,
        "amount_minor": amount_minor,
        "currency": "EUR",
        "to_iban": "DE00EXAMPLE0000000020",
        "status": "prepared",
    }
    return {**base, **extra}


def credit(bank_event_id: str = "7", amount_minor: int = 50000, deal_id: str = "deal-1") -> dict:
    return {
        "bank_event_id": bank_event_id,
        "reference": f"ESCROW-{deal_id}",
        "amount_minor": amount_minor,
        "from_iban": "DE00EXAMPLE0000000010",
        "received_at": "2026-11-27T12:00:30Z",
        "disposition": "funded",
    }


def posting(source_id: str, account: str, amount_minor: int, posting_id: str | None = None) -> dict:
    return {
        "posting_id": posting_id or f"{source_id}:{account}",
        "source_id": source_id,
        "account": account,
        "amount_minor": amount_minor,
    }
