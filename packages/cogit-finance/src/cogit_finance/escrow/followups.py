# pyright: basic
"""What E does on its own once a deal allows it. Every step is one commit.

``advance`` looks only at the recorded deal, never at the message being handled,
so a run that died between two commits is continued by the next one: by the same
message delivered again, or by ``tick``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from cogit_finance.escrow import guards, ids, messages, payout, policy
from cogit_finance.escrow import transitions as t
from cogit_finance.escrow.inbound import DELIVERY_FIELDS
from cogit_finance.escrow.messages import Outgoing
from cogit_finance.escrow.store import EscrowContext, EscrowError
from cogit_finance.escrow.terms import build_terms, terms_hash
from cogit_finance.escrow.view import DealView

Row = dict[str, Any]
Step = Callable[[EscrowContext, DealView], DealView]
MAX_STEPS = 32  # up to 16 evaluator retries plus lifecycle follow-ups


def advance(ctx: EscrowContext, view: DealView) -> DealView:
    """Carry out E's own steps until the deal waits for someone else."""
    for _ in range(MAX_STEPS):
        # The local checkout can hold an approved deal for an explicit release.
        # All normal agent deployments retain automatic settlement by default.
        if view.state == t.APPROVED and not ctx.release_authorized(view.deal_id):
            return view
        step = next_step(view)
        if step is None:
            return view
        advanced = step(ctx, view)
        if advanced.head_seq == view.head_seq:
            return advanced
        view = advanced
    raise EscrowError(f"deal {view.deal_id} does not come to rest")


def next_step(view: DealView) -> Step | None:
    state = view.state
    if state == t.QUOTED:
        if view.last_event("terms_proposed") is None:
            return propose_terms
        return countersign if guards.both_accepted(view) else None
    if state == t.EVALUATING:
        from cogit_finance.escrow.recovery import evaluation_timer

        return decide if _outcome(view) else evaluation_timer
    if state in (t.SETTLED, t.REFUNDED):
        return None if view.last_event("receipt") else payout.send_receipt
    return _ALWAYS.get(state)


def _parties(view: DealView, type_key: str, body: Row, cause: str) -> list[Outgoing]:
    terms = view.terms
    return [
        Outgoing(type_key, terms["buyer_did"], body, cause),
        Outgoing(type_key, terms["seller_did"], body, cause),
    ]


def propose_terms(ctx: EscrowContext, view: DealView) -> DealView:
    quote = view.message_of("quote")
    offer = ctx.directory.offer(view.seller_org_id, view.offer_id)
    if offer is None:
        raise EscrowError(f"offer {view.offer_id} is gone; cannot build the terms")
    terms = build_terms(
        deal_id=view.deal_id,
        buyer_org_id=view.buyer_org_id,
        seller_org_id=view.seller_org_id,
        buyer_did=view.buyer_did,
        seller_did=quote["sender_did"],
        escrow_did=ctx.escrow_did,
        offer=offer,
        request=view.request["body"],
        quote=quote["body"],
        escrow_config=ctx.config["escrow"],
    )
    digest = terms_hash(terms)
    body = messages.terms_proposed(terms, digest)
    cause = quote["message_id"]
    version = 2 if terms["acceptance"]["policy"].startswith("quorum ") else 1
    outbox = [
        Outgoing(messages.TERMS_PROPOSED, terms["buyer_did"], body, cause, version),
        Outgoing(messages.TERMS_PROPOSED, terms["seller_did"], body, cause, version),
    ]
    return ctx.store.record_own(
        view,
        "terms_proposed",
        t.QUOTED,
        body,
        deal={"terms": terms, "terms_hash": digest},
        outbox=outbox,
    )


def _last_acceptance(view: DealView) -> str:
    event = view.last_event("accept_terms")
    assert event is not None
    return str(event["source_message_id"])


def countersign(ctx: EscrowContext, view: DealView) -> DealView:
    accepted_by = list(view.acceptances.values())
    body = messages.terms_countersigned(str(view.terms_hash), accepted_by)
    outbox = _parties(view, messages.TERMS_COUNTERSIGNED, body, _last_acceptance(view))
    return ctx.store.record_own(
        view, "terms_countersigned", t.ACCEPTED, body, outbox=outbox
    )


def request_payment(ctx: EscrowContext, view: DealView) -> DealView:
    terms = view.terms
    iban = ctx.config["rail"]["escrow_iban"]
    body = messages.payment_request(terms, iban, ctx.clock())
    outbox = [
        Outgoing(
            messages.PAYMENT_REQUEST, terms["buyer_did"], body, _last_acceptance(view)
        )
    ]
    return ctx.store.record_own(
        view, "payment_request", t.FUNDING_REQUESTED, body, outbox=outbox
    )


def fund(ctx: EscrowContext, view: DealView, credit: Row) -> DealView:
    """Row 9: a matching bank credit funds the deal. The caller checked the guard."""
    terms = view.terms
    event_id = str(credit["event_id"])
    row = {
        "bank_event_id": event_id,
        "reference": credit["reference"],
        "amount_minor": credit["amount_minor"],
        "from_iban": credit.get("from_iban"),
        "received_at": credit.get("booked_at") or messages.later(ctx.clock(), 0),
        "disposition": "funded",
    }
    posting = {
        "posting_id": ids.posting_id(f"credit:{event_id}", "held"),
        "source_id": event_id,
        "account": "held",
        "amount_minor": credit["amount_minor"],
    }
    requested = view.last_event("payment_request")
    assert requested is not None
    cause = ids.own_message_id(
        view.deal_id,
        int(requested["seq"]),
        messages.PAYMENT_REQUEST,
        terms["buyer_did"],
        0,
    )
    confirmed = messages.funding_confirmed(terms, event_id)
    body = {**row, "currency": terms["currency"]}
    return ctx.store.record_own(
        view,
        "funding_received",
        t.FUNDED,
        body,
        outbox=_parties(view, messages.FUNDING_CONFIRMED, confirmed, cause),
        credits=[row],
        postings=[posting],
    )


def request_evaluation(ctx: EscrowContext, view: DealView) -> DealView:
    terms = view.terms
    delivery = view.current_delivery
    delivered = view.last_event("delivery")
    assert delivery is not None and delivered is not None
    registry = ctx.directory.evaluators()
    respond_by = messages.later(ctx.clock(), terms["timers"]["evaluator_respond_s"])
    rows: list[Row] = []
    outbox: list[Outgoing] = []
    for named in terms["acceptance"]["evaluators"]:
        evaluator = registry.get((named["evaluator_id"], named["version"]))
        if evaluator is None or not evaluator.get("did"):
            raise EscrowError(f"evaluator {named['evaluator_id']} is not registered")
        body = messages.evaluation_request(
            str(view.terms_hash), delivery, named, respond_by
        )
        rows.append(
            {
                "evaluation_request_id": body["evaluation_request_id"],
                "delivery_id": delivery["delivery_id"],
                "evaluator_id": named["evaluator_id"],
                "evaluator_version": named["version"],
                "evaluator_did": evaluator["did"],
                "respond_by": respond_by,
                "resends": 0,
                "verdict_message_id": None,
                "outcome": None,
            }
        )
        outbox.append(
            Outgoing(
                messages.EVALUATION_REQUEST,
                evaluator["did"],
                body,
                str(delivered["source_message_id"]),
            )
        )
    event_body = {
        "delivery_id": delivery["delivery_id"],
        "respond_by": respond_by,
        "requests": [
            {
                "evaluation_request_id": row["evaluation_request_id"],
                "evaluator_id": row["evaluator_id"],
                "evaluator_version": row["evaluator_version"],
                "evaluator_did": row["evaluator_did"],
            }
            for row in rows
        ],
    }
    return ctx.store.record_own(
        view,
        "evaluation_requested",
        t.EVALUATING,
        event_body,
        outbox=outbox,
        evaluations=rows,
    )


def _current_evaluations(view: DealView) -> list[Row]:
    delivery = view.current_delivery
    return [] if delivery is None else view.evaluations_for(delivery["delivery_id"])


def _outcome(view: DealView) -> str | None:
    outcomes = [row.get("outcome") for row in _current_evaluations(view)]
    return policy.decide(view.terms["acceptance"]["policy"], outcomes)


def _fail_reasons(view: DealView) -> list[str]:
    reasons: list[str] = []
    for row in _current_evaluations(view):
        if row.get("outcome") != policy.FAIL:
            continue
        name = f"{row['evaluator_id']}@{row['evaluator_version']}"
        event = view.event_for_message(str(row.get("verdict_message_id")))
        given = event["body"]["envelope"]["body"]["reasons"] if event else []
        reasons += [f"{name}: {reason}" for reason in given] or [f"{name}: fail"]
    return reasons


def decide(ctx: EscrowContext, view: DealView) -> DealView:
    """The policy is decided: record it and tell both parties."""
    outcome = _outcome(view)
    delivery = view.current_delivery
    verdict = view.last_event("verdict")
    assert outcome is not None and delivery is not None and verdict is not None
    approved = outcome == policy.APPROVE
    reasons = [] if approved else _fail_reasons(view)
    body = messages.decision(view.terms, delivery, outcome, reasons, ctx.clock())
    row = {name: delivery.get(name) for name in DELIVERY_FIELDS}
    row["status"] = "approved" if approved else "rejected"
    return ctx.store.record_own(
        view,
        "decision",
        t.APPROVED if approved else t.REJECTED,
        {**body, "decided_at": messages.later(ctx.clock(), 0)},
        outbox=_parties(
            view, messages.DECISION, body, str(verdict["source_message_id"])
        ),
        deliveries=[row],
    )


_ALWAYS: dict[str, Step] = {
    t.ACCEPTED: request_payment,
    t.DELIVERED: request_evaluation,
    t.APPROVED: payout.submit_payout,
    t.RELEASING: payout.release,
    t.REFUNDING: payout.release,
}
