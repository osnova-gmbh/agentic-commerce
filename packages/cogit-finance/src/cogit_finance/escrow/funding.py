"""Record every bank credit once, funding or durably returning it in full."""

from __future__ import annotations

from typing import Any

from cogit_finance_seams import ModuleError
from cogit_messaging_shim import parse_ts

from cogit_finance.escrow import followups, guards, ids, messages, payout
from cogit_finance.escrow.store import DEALS, EscrowContext

Row = dict[str, Any]


def collect(ctx: EscrowContext) -> tuple[int, int]:
    events = ctx.bank.credits(ctx.config["rail"]["escrow_iban"], "0")
    funded = 0
    for credit in events:
        known = ctx.store.modules.module_query(
            DEALS, "credit.read", {"bank_event_id": credit["event_id"]}
        )
        if known.get("credit"):
            continue  # replayed event, not a second bank transfer
        deal_id = ids.deal_id_from_reference(credit.get("reference"))
        view = ctx.store.read(deal_id) if deal_id else None
        allowed = (
            view is not None and view.exists and guards.funding(view, credit) is None
        )
        if allowed:
            assert view is not None
            requested = view.last_event("payment_request")
            assert requested is not None
            allowed = parse_ts(credit["booked_at"]) < parse_ts(
                requested["body"]["funding_due_by"]
            )
        try:
            if allowed:
                assert view is not None
                followups.fund(ctx, view, credit)
                funded += 1
            else:
                return_credit(ctx, credit, deal_id if view and view.exists else None)
        except ModuleError as error:
            if error.code not in ("duplicate_credit", "head_mismatch"):
                raise
            # The winner committed this credit, or the next tick rechecks its state.
    return len(events), funded


def return_credit(ctx: EscrowContext, credit: Row, deal_id: str | None) -> None:
    event_id = str(credit["event_id"])
    row = {
        "bank_event_id": event_id,
        "reference": credit["reference"],
        "amount_minor": credit["amount_minor"],
        "from_iban": credit["from_iban"],
        "received_at": credit["booked_at"],
        "disposition": "returned",
    }
    intent = {
        "intent_id": f"credit:{event_id}:return_unmatched",
        "kind": payout.RETURN,
        "amount_minor": credit["amount_minor"],
        "currency": credit["currency"],
        "to_iban": credit["from_iban"],
        "status": "prepared",
    }
    posting = {
        "posting_id": ids.posting_id(f"credit:{event_id}", "held"),
        "source_id": event_id,
        "account": "held",
        "amount_minor": credit["amount_minor"],
    }
    if deal_id is None:
        # There is no deal log for an unknown reference. This command atomically
        # persists the bank event, return intent and held posting with no deal ID.
        ctx.store.modules.module_command(
            DEALS,
            "credit.return",
            {"credit": row, "intent": intent, "posting": posting},
            idempotency_key=f"credit:{event_id}:return",
        )
    else:
        view = ctx.store.read(deal_id)
        ctx.store.record_own(
            view,
            "credit_returned",
            view.state,
            {"bank_event_id": event_id, "received_at": messages.later(ctx.clock(), 0)},
            credits=[row],
            intents=[intent],
            postings=[posting],
        )


def reconcile_returns(ctx: EscrowContext) -> None:
    rows = ctx.store.modules.module_query(DEALS, "intents.unresolved", {})["intents"]
    for intent in rows:
        if intent["kind"] == payout.RETURN:
            payout.settle_intent(ctx, intent)
