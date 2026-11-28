# pyright: basic
"""Sim payment adapter (SPEC §10.3): prepare, submit, reconcile and confirm.

An intent is committed with the deal event that needs it, submitted to the bank
under its own ID as idempotency key, and confirmed together with its ledger
postings. Running a step twice pays once: the bank and the modules de-duplicate.
"""

from __future__ import annotations

from typing import Any

import httpx
from cogit_finance_seams import BankError

from cogit_finance.escrow import ids, messages, money
from cogit_finance.escrow import transitions as t
from cogit_finance.escrow.messages import Outgoing
from cogit_finance.escrow.store import EscrowContext, EscrowError
from cogit_finance.escrow.view import DealView

Row = dict[str, Any]
PAYOUT = "payout"
FEE = "fee"
REFUND = "refund"
RETURN = "return_unmatched"
CREDITED_ACCOUNT = {
    PAYOUT: "seller",
    FEE: "fee",
    REFUND: "buyer_refund",
    RETURN: "returned",
}
REFERENCE_PREFIX = {
    PAYOUT: "PAYOUT-",
    FEE: "FEE-",
    REFUND: "REFUND-",
    RETURN: "RETURN-",
}


def _deciding_verdict(view: DealView) -> str:
    """The message every payout notification answers: the verdict that decided."""
    event = (
        view.last_event("ruling")
        or view.last_event("verdict")
        or view.last_event("service_request")
    )
    assert event is not None
    return str(event["source_message_id"])


def _both(view: DealView, type_key: str, body: Row) -> list[Outgoing]:
    cause = _deciding_verdict(view)
    terms = view.terms
    return [
        Outgoing(type_key, terms["buyer_did"], body, cause),
        Outgoing(type_key, terms["seller_did"], body, cause),
    ]


def _intent(view: DealView, kind: str, amount_minor: int, to_iban: str) -> Row:
    return {
        "intent_id": ids.intent_id(view.deal_id, kind),
        "kind": kind,
        "amount_minor": amount_minor,
        "currency": view.terms["currency"],
        "to_iban": to_iban,
        "status": "prepared",
    }


def payout_intents(ctx: EscrowContext, view: DealView) -> list[Row]:
    """Prepare exactly the same transfers for approval and a release ruling."""
    terms = view.terms
    payout_minor, fee = money.split(terms["price_minor"], terms["fee_bps"])
    seller = ctx.directory.company(terms["seller_org_id"])
    if seller is None or not seller.get("iban"):
        raise EscrowError(f"company {terms['seller_org_id']} has no IBAN to pay out to")
    planned = (
        (PAYOUT, payout_minor, str(seller["iban"])),
        (FEE, fee, str(ctx.config["rail"]["fee_iban"])),
    )
    return [
        _intent(view, kind, amount, iban)
        for kind, amount, iban in planned
        if amount > 0
    ]


def refund_intents(ctx: EscrowContext, view: DealView) -> list[Row]:
    # Refund the account that actually funded the deal, not a mutable catalog IBAN.
    credit = next(row for row in view.credits if row["disposition"] == "funded")
    return [_intent(view, REFUND, view.terms["price_minor"], credit["from_iban"])]


def submit_payout(ctx: EscrowContext, view: DealView) -> DealView:
    """Row 16: prepare intents atomically with the release decision."""
    terms = view.terms
    payout_minor, fee = money.split(terms["price_minor"], terms["fee_bps"])
    intents = payout_intents(ctx, view)
    body = {
        "payout_minor": payout_minor,
        "fee_minor": fee,
        "currency": terms["currency"],
        "intents": [
            {
                name: row[name]
                for name in ("intent_id", "kind", "amount_minor", "to_iban")
            }
            for row in intents
        ],
    }
    return ctx.store.record_own(
        view, "payout_submitted", t.RELEASING, body, intents=intents
    )


def _postings(intent: Row) -> list[Row]:
    """Money leaves ``held`` and reaches the seller's or the fee account."""
    intent_id = str(intent["intent_id"])
    amount = int(intent["amount_minor"])
    moves = (("held", -amount), (CREDITED_ACCOUNT[intent["kind"]], amount))
    return [
        {
            "posting_id": ids.posting_id(intent_id, account),
            "source_id": intent_id,
            "account": account,
            "amount_minor": signed,
        }
        for account, signed in moves
    ]


def settle_intent(ctx: EscrowContext, intent: Row) -> bool:
    """Never resubmit an ambiguous transfer until lookup proves it absent."""
    intent_id = str(intent["intent_id"])
    try:
        transfer = None
        if intent["status"] != "prepared":
            transfer = ctx.bank.lookup(intent_id)
        if transfer is None:
            if intent["status"] == "prepared":
                ctx.store.update_intent(intent_id, "submitted")
            reference = REFERENCE_PREFIX[intent["kind"]] + (
                intent.get("deal_id") or intent_id
            )
            transfer = ctx.bank.transfer(
                from_iban=ctx.config["rail"]["escrow_iban"],
                to_iban=intent["to_iban"],
                amount_minor=intent["amount_minor"],
                currency=intent["currency"],
                reference=reference,
                idempotency_key=intent_id,
            )
        if transfer.get("status") != "booked" or not transfer.get("transfer_id"):
            ctx.store.update_intent(intent_id, "unknown")
            return False
    except (BankError, httpx.HTTPError, OSError, ValueError):
        ctx.store.update_intent(intent_id, "unknown")
        return False
    ctx.store.update_intent(
        intent_id,
        "confirmed",
        bank_ref=str(transfer["transfer_id"]),
        postings=_postings(intent),
    )
    return True


def release(ctx: EscrowContext, view: DealView) -> DealView:
    """Row 21: once the bank has booked every intent, the deal is settled."""
    kinds = (REFUND,) if view.state == t.REFUNDING else (PAYOUT, FEE)
    complete = True
    for intent in view.intents:
        if intent["kind"] in kinds and intent["status"] != "confirmed":
            complete = settle_intent(ctx, intent) and complete
    view = ctx.store.read(view.deal_id)
    if not complete:
        return view
    if view.state == t.REFUNDING:
        refund = view.intent(ids.intent_id(view.deal_id, REFUND))
        assert refund is not None and refund["status"] == "confirmed"
        body = {
            "amount_minor": refund["amount_minor"],
            "currency": refund["currency"],
            "bank_ref": refund["bank_ref"],
        }
        return ctx.store.record_own(
            view,
            "refund_confirmed",
            t.REFUNDED,
            body,
            outbox=_both(view, "finance.refund_confirmed", body),
        )
    refs = [
        row.get("bank_ref")
        for kind in (PAYOUT, FEE)
        if (row := view.intent(ids.intent_id(view.deal_id, kind))) is not None
    ]
    body = messages.payout_confirmed(view.terms, str(next(filter(None, refs), "none")))
    return ctx.store.record_own(
        view,
        "payout_confirmed",
        t.SETTLED,
        body,
        outbox=_both(view, messages.PAYOUT_CONFIRMED, body),
    )


def send_receipt(ctx: EscrowContext, view: DealView) -> DealView:
    """Row 23: the receipt attests the deal head it is written on."""
    body = messages.receipt(
        view.terms, str(view.terms_hash), view.head_seq, view.head_hash
    )
    if view.state == t.REFUNDED:
        body.update(outcome="refunded", fee_minor=0, payout_minor=0)
    return ctx.store.record_own(
        view, "receipt", view.state, body, outbox=_both(view, messages.RECEIPT, body)
    )
