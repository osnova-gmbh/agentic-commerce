# pyright: basic
"""Sim payment adapter (SPEC §10.3): prepare, submit, confirm. No reconcile.

An intent is committed with the deal event that needs it, submitted to the bank
under its own ID as idempotency key, and confirmed together with its ledger
postings. Running a step twice pays once: the bank and the modules de-duplicate.
"""

from __future__ import annotations

from typing import Any

from cogit_finance.escrow import ids, messages, money
from cogit_finance.escrow import transitions as t
from cogit_finance.escrow.messages import Outgoing
from cogit_finance.escrow.store import EscrowContext, EscrowError
from cogit_finance.escrow.view import DealView

Row = dict[str, Any]
PAYOUT = "payout"
FEE = "fee"
CREDITED_ACCOUNT = {PAYOUT: "seller", FEE: "fee"}
REFERENCE_PREFIX = {PAYOUT: "PAYOUT-", FEE: "FEE-"}


def _deciding_verdict(view: DealView) -> str:
    """The message every payout notification answers: the verdict that decided."""
    event = view.last_event("verdict")
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


def submit_payout(ctx: EscrowContext, view: DealView) -> DealView:
    """Row 16: prepare the payout and fee intents with the event that needs them."""
    terms = view.terms
    payout_minor, fee = money.split(terms["price_minor"], terms["fee_bps"])
    seller = ctx.directory.company(terms["seller_org_id"])
    if seller is None or not seller.get("iban"):
        raise EscrowError(f"company {terms['seller_org_id']} has no IBAN to pay out to")
    planned = (
        (PAYOUT, payout_minor, str(seller["iban"])),
        (FEE, fee, str(ctx.config["rail"]["fee_iban"])),
    )
    intents = [
        _intent(view, kind, amount, iban)
        for kind, amount, iban in planned
        if amount > 0
    ]
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


def _settle_intent(ctx: EscrowContext, view: DealView, intent: Row) -> None:
    """Submit one intent to the bank and confirm it with its postings."""
    intent_id = str(intent["intent_id"])
    if intent["status"] == "prepared":
        ctx.store.update_intent(intent_id, "submitted")
    transfer = ctx.bank.transfer(
        from_iban=ctx.config["rail"]["escrow_iban"],
        to_iban=intent["to_iban"],
        amount_minor=intent["amount_minor"],
        currency=intent["currency"],
        reference=f"{REFERENCE_PREFIX[intent['kind']]}{view.deal_id}",
        idempotency_key=intent_id,
    )
    if transfer.get("status") != "booked":
        raise EscrowError(f"transfer for intent {intent_id} is not booked")
    ctx.store.update_intent(
        intent_id,
        "confirmed",
        bank_ref=str(transfer["transfer_id"]),
        postings=_postings(intent),
    )


def release(ctx: EscrowContext, view: DealView) -> DealView:
    """Row 21: once the bank has booked every intent, the deal is settled."""
    for intent in view.intents:
        if intent["kind"] in CREDITED_ACCOUNT and intent["status"] != "confirmed":
            _settle_intent(ctx, view, intent)
    view = ctx.store.read(view.deal_id)
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
    return ctx.store.record_own(
        view, "receipt", t.SETTLED, body, outbox=_both(view, messages.RECEIPT, body)
    )
