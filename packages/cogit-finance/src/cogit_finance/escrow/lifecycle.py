"""Participant cancellation/disputes and authenticated operator rulings."""

from __future__ import annotations

from typing import Any

from cogit_messaging_shim import parse_ts

from cogit_finance.escrow import messages, payout
from cogit_finance.escrow import reasons as r
from cogit_finance.escrow import transitions as t
from cogit_finance.escrow.messages import Outgoing
from cogit_finance.escrow.recovery import dispute_due
from cogit_finance.escrow.store import EscrowContext
from cogit_finance.escrow.view import DealView

Row = dict[str, Any]


def record(ctx: EscrowContext, view: DealView, envelope: Row) -> DealView:
    trigger = envelope["type_key"].removeprefix("finance.")
    sender = envelope["sender_did"]
    seller = ctx.directory.identity_for("seller", view.seller_org_id)
    parties = {view.buyer_did, str(seller["did"]) if seller else ""}
    parts: dict[str, Any] = {}
    if trigger == "ruling":
        # A DID in the tenant, a buyer, or a worker is not operator authority.
        if sender != ctx.config["operator"].get("ruling_did"):
            raise r.Rejected(r.UNEXPECTED_SENDER)
        release = envelope["body"]["outcome"] == "release"
        target = t.RELEASING if release else t.REFUNDING
        parts["intents"] = (
            payout.payout_intents if release else payout.refund_intents
        )(ctx, view)
    else:
        if sender not in parties or (trigger == "cancel" and sender != view.buyer_did):
            raise r.Rejected(r.UNEXPECTED_SENDER)
        if trigger == "dispute" and ctx.clock() >= parse_ts(dispute_due(view)):
            raise r.Rejected("dispute_window_passed")
        if trigger == "cancel" and any(
            c["disposition"] == "funded" for c in view.credits
        ):
            raise r.Rejected("credit_received")
        target = {"cancel": t.CANCELLED, "decline": t.DECLINED, "dispute": t.DISPUTED}[
            trigger
        ]
    body = messages.relay(envelope, view.deal_id, view.head_seq + 1, target)
    outbox = [
        Outgoing(messages.RELAY, did, body, envelope["message_id"])
        for did in sorted(parties - {sender, ""})
    ]
    return ctx.store.record_message(view, envelope, target, outbox=outbox, **parts)
