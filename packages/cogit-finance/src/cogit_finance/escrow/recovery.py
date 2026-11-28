"""Durable timers and the single evaluator re-request (SPEC §5, §9)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from cogit_messaging_shim import parse_ts, to_ts

from cogit_finance.escrow import ids, messages, payout
from cogit_finance.escrow import transitions as t
from cogit_finance.escrow.messages import Outgoing
from cogit_finance.escrow.store import EscrowContext
from cogit_finance.escrow.view import DealView

Row = dict[str, Any]


def dispute_due(view: DealView) -> str:
    event = view.last_event("decision")
    assert event is not None
    start = parse_ts(event["body"].get("decided_at", event["recorded_at"]))
    return messages.later(start, view.terms["timers"]["dispute_window_s"])


def timer(ctx: EscrowContext, view: DealView) -> DealView:
    """Only the current state owns a timer; replay cannot repeat a transition."""
    now = ctx.clock()
    trigger, deadline, target = "", "", ""
    if view.state == t.REQUESTED:
        start = parse_ts(view.request["created_at"])
        deadline = messages.later(start, ctx.config["escrow"]["timers"]["quote_ttl_s"])
        trigger, target = "quote_ttl", t.EXPIRED
    elif view.state == t.QUOTED:
        deadline = view.message_of("quote")["body"]["valid_until"]
        trigger, target = "valid_until", t.EXPIRED
    elif view.state == t.FUNDING_REQUESTED:
        event = view.last_event("payment_request")
        assert event is not None
        deadline = event["body"]["funding_due_by"]
        trigger, target = "funding_due_by", t.CANCELLED
    elif view.state == t.FUNDED:
        deadline = view.terms["delivery_deadline"]
        trigger, target = "delivery_deadline", t.REFUNDING
    elif view.state == t.REJECTED:
        event = view.last_event("decision")
        assert event is not None
        rework = event["body"]["rework_deadline"]
        if rework and now < parse_ts(rework):
            return view
        deadline = dispute_due(view)
        trigger, target = "rework_exhausted", t.REFUNDING
    elif view.state == t.EVALUATING:
        return evaluation_timer(ctx, view)
    if not deadline or now < parse_ts(deadline):
        return view
    parts = (
        {"intents": payout.refund_intents(ctx, view)} if target == t.REFUNDING else {}
    )
    return ctx.store.record_own(view, trigger, target, {"deadline": deadline}, **parts)


def evaluation_timer(ctx: EscrowContext, view: DealView) -> DealView:
    delivery = view.current_delivery
    assert delivery is not None
    rows = view.evaluations_for(delivery["delivery_id"])
    for row in rows:
        if row.get("outcome") in ("pass", "fail"):
            continue
        if row.get("outcome") != "error" and ctx.clock() < parse_ts(row["respond_by"]):
            continue
        if row["resends"] >= 1:
            return ctx.store.record_own(
                view,
                "evaluator_unavailable",
                t.DISPUTED,
                {
                    "reason": "evaluator_unavailable",
                    "evaluation_request_id": row["evaluation_request_id"],
                },
            )
        return retry_evaluation(ctx, view, row)
    return view


def retry_evaluation(ctx: EscrowContext, view: DealView, row: Row) -> DealView:
    delivery = view.current_delivery
    assert delivery is not None
    named = next(
        e
        for e in view.terms["acceptance"]["evaluators"]
        if (e["evaluator_id"], e["version"])
        == (row["evaluator_id"], row["evaluator_version"])
    )
    due = ctx.clock() + timedelta(seconds=view.terms["timers"]["evaluator_respond_s"])
    updated = {
        **row,
        "respond_by": to_ts(due),
        "resends": 1,
        "outcome": None,
        "verdict_message_id": None,
    }
    updated.pop("deal_id", None)
    body = messages.evaluation_request(
        str(view.terms_hash), delivery, named, to_ts(due)
    )
    requested = view.last_event("evaluation_requested")
    assert requested is not None
    ordinal = next(
        n
        for n, e in enumerate(requested["body"]["requests"])
        if e["evaluation_request_id"] == row["evaluation_request_id"]
    )
    cause = row.get("verdict_message_id") or ids.own_message_id(
        view.deal_id,
        requested["seq"],
        messages.EVALUATION_REQUEST,
        row["evaluator_did"],
        ordinal,
    )
    return ctx.store.record_own(
        view,
        "evaluation_retried",
        t.EVALUATING,
        {
            "evaluation_request_id": row["evaluation_request_id"],
            "respond_by": to_ts(due),
        },
        evaluations=[updated],
        outbox=[
            Outgoing(messages.EVALUATION_REQUEST, row["evaluator_did"], body, cause)
        ],
    )
