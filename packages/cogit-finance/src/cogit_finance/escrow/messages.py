# pyright: basic
"""Bodies of the messages E sends, and the receipt. No I/O."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from cogit_messaging_shim import parse_ts, to_ts

from cogit_finance.escrow import ids, money, policy

Body = dict[str, Any]

RELAY = "finance.relay"
TERMS_PROPOSED = "finance.terms_proposed"
TERMS_COUNTERSIGNED = "finance.terms_countersigned"
PAYMENT_REQUEST = "finance.payment_request"
FUNDING_CONFIRMED = "finance.funding_confirmed"
EVALUATION_REQUEST = "finance.evaluation_request"
DECISION = "finance.decision"
PAYOUT_CONFIRMED = "finance.payout_confirmed"
RECEIPT = "finance.receipt"
# Types only E sends; receiving one is refused.
OWN_TYPES = frozenset(
    {
        RELAY,
        TERMS_PROPOSED,
        TERMS_COUNTERSIGNED,
        PAYMENT_REQUEST,
        FUNDING_CONFIRMED,
        EVALUATION_REQUEST,
        DECISION,
        PAYOUT_CONFIRMED,
        RECEIPT,
        "finance.refund_confirmed",
    }
)
TYPE_VERSION = 1
MAX_REASONS = 50
MAX_REASON_LENGTH = 500


@dataclass(frozen=True)
class Outgoing:
    """One message E queues with a commit; the store signs and numbers it."""

    type_key: str
    recipient_did: str
    body: Body
    causation_id: str | None
    type_version: int = TYPE_VERSION


def later(moment: datetime, seconds: int) -> str:
    return to_ts(moment + timedelta(seconds=seconds))


def relay(envelope: Body, deal_id: str, seq: int, state: str) -> Body:
    """SPEC §6.3: the original signed envelope plus the deal head after it."""
    return {
        "relayed": envelope,
        "deal": {"deal_id": deal_id, "seq": seq, "state": state},
    }


def terms_proposed(terms: Body, terms_hash: str) -> Body:
    return {"terms": terms, "terms_hash": terms_hash}


def terms_countersigned(terms_hash: str, accepted_by: list[str]) -> Body:
    return {"terms_hash": terms_hash, "accepted_by": list(accepted_by)}


def payment_request(terms: Body, escrow_iban: str, now: datetime) -> Body:
    return {
        "to_iban": escrow_iban,
        "amount_minor": terms["price_minor"],
        "currency": terms["currency"],
        "reference": ids.payment_reference(terms["deal_id"]),
        "funding_due_by": later(now, terms["timers"]["funding_due_s"]),
    }


def funding_confirmed(terms: Body, bank_event_id: str) -> Body:
    return {
        "amount_minor": terms["price_minor"],
        "currency": terms["currency"],
        "bank_event_id": bank_event_id,
        "delivery_deadline": terms["delivery_deadline"],
    }


def artifact_ref(delivery: Body) -> Body:
    return {
        "artifact_id": delivery["artifact_id"],
        "sha256": delivery["sha256"],
        "byte_length": delivery["byte_length"],
        "media_type": delivery["media_type"],
    }


def evaluation_request(
    terms_hash: str, delivery: Body, evaluator: Body, respond_by: str
) -> Body:
    """``evaluator`` is one entry of the acceptance spec."""
    return {
        "evaluation_request_id": ids.evaluation_request_id(
            delivery["delivery_id"], evaluator["evaluator_id"], evaluator["version"]
        ),
        "terms_hash": terms_hash,
        "delivery_id": delivery["delivery_id"],
        "artifact": artifact_ref(delivery),
        "evaluator_id": evaluator["evaluator_id"],
        "evaluator_version": evaluator["version"],
        "params": evaluator["params"],
        "delivered_at": delivery["delivered_at"],
        "respond_by": respond_by,
    }


def rework_deadline(terms: Body, now: datetime) -> str:
    """min(delivery deadline, rejection time + rework window), SPEC §5.3."""
    window = now + timedelta(seconds=terms["timers"]["rework_window_s"])
    return to_ts(min(parse_ts(terms["delivery_deadline"]), window))


def decision(
    terms: Body, delivery: Body, outcome: str, reasons: list[str], now: datetime
) -> Body:
    left = policy.attempts_left(
        terms["acceptance"]["max_attempts"], delivery["attempt"]
    )
    rework = outcome == policy.REJECT and left > 0
    return {
        "delivery_id": delivery["delivery_id"],
        "outcome": outcome,
        "attempts_left": left,
        "rework_deadline": rework_deadline(terms, now) if rework else None,
        "reasons": [reason[:MAX_REASON_LENGTH] for reason in reasons[:MAX_REASONS]],
    }


def payout_confirmed(terms: Body, bank_ref: str) -> Body:
    payout, fee = money.split(terms["price_minor"], terms["fee_bps"])
    return {
        "payout_minor": payout,
        "fee_minor": fee,
        "currency": terms["currency"],
        "bank_ref": bank_ref,
    }


def receipt(terms: Body, terms_hash: str, head_seq: int, head_hash: str) -> Body:
    """Receipt of a settled deal. It attests the deal head it was written on."""
    payout, fee = money.split(terms["price_minor"], terms["fee_bps"])
    return {
        "outcome": "settled",
        "price_minor": terms["price_minor"],
        "fee_minor": fee,
        "payout_minor": payout,
        "currency": terms["currency"],
        "terms_hash": terms_hash,
        "head_seq": head_seq,
        "head_hash": head_hash,
    }
