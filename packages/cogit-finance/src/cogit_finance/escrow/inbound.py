# pyright: basic
"""Inbound messages: check the guard, then record the message as one deal event."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from cogit_finance_seams import ModuleError
from cogit_messaging_shim import to_ts

from cogit_finance.escrow import guards, ids, messages, policy
from cogit_finance.escrow import reasons as r
from cogit_finance.escrow import transitions as t
from cogit_finance.escrow.messages import RELAY, Outgoing
from cogit_finance.escrow.store import EscrowContext
from cogit_finance.escrow.view import DealView

Row = dict[str, Any]
DELIVERY_FIELDS = (
    "delivery_id",
    "attempt",
    "artifact_id",
    "sha256",
    "byte_length",
    "media_type",
    "delivered_at",
    "status",
)
EVALUATION_FIELDS = (
    "evaluation_request_id",
    "delivery_id",
    "evaluator_id",
    "evaluator_version",
    "evaluator_did",
    "respond_by",
    "resends",
    "verdict_message_id",
    "outcome",
)


def _require(refused: str | None) -> None:
    if refused:
        raise r.Rejected(refused)


def record(ctx: EscrowContext, view: DealView, trigger: str, envelope: Row) -> DealView:
    """Record one admitted message, or raise ``Rejected`` and change nothing."""
    if trigger == "verdict" and guards.stale_verdict(view, envelope["body"]):
        raise r.Rejected(r.STALE_VERDICT)
    _require(t.refuse_message(view.state, trigger))
    return _RECORDERS[trigger](ctx, view, envelope)


def _relay(view: DealView, envelope: Row, to_did: str, state_after: str) -> Outgoing:
    body = messages.relay(envelope, view.deal_id, view.head_seq + 1, state_after)
    return Outgoing(RELAY, to_did, body, envelope["message_id"])


def _service_request(ctx: EscrowContext, view: DealView, envelope: Row) -> DealView:
    body = envelope["body"]
    identity = ctx.directory.identity(envelope["sender_did"])
    company = ctx.directory.company(identity["org_id"]) if identity else None
    seller = ctx.directory.identity_for("seller", body["seller_org_id"])
    _require(
        guards.service_request(
            body,
            identity=identity,
            company=company,
            offer=ctx.directory.offer(body["seller_org_id"], body["offer_id"]),
            seller_identity=seller,
        )
    )
    assert identity is not None and seller is not None
    deal = {
        "buyer_org_id": identity["org_id"],
        "seller_org_id": body["seller_org_id"],
        "offer_id": body["offer_id"],
        "terms": None,
        "terms_hash": None,
    }
    outbox = [_relay(view, envelope, seller["did"], t.REQUESTED)]
    return ctx.store.record_message(
        view, envelope, t.REQUESTED, deal=deal, outbox=outbox
    )


def _quote(ctx: EscrowContext, view: DealView, envelope: Row) -> DealView:
    body = envelope["body"]
    registry = ctx.directory.evaluators()
    named = [
        (e["evaluator_id"], e["version"]) for e in body["acceptance"]["evaluators"]
    ]
    dids = {str(registry[key].get("did")) for key in named if key in registry}
    _require(
        guards.quote(
            view,
            body,
            identity=ctx.directory.identity(envelope["sender_did"]),
            buyer_company=ctx.directory.company(view.buyer_org_id),
            offer=ctx.directory.offer(view.seller_org_id, view.offer_id),
            registry=registry,
            identities={did: ctx.directory.identity(did) for did in sorted(dids)},
            config=ctx.config,
        )
    )
    outbox = [_relay(view, envelope, view.buyer_did, t.QUOTED)]
    return ctx.store.record_message(view, envelope, t.QUOTED, outbox=outbox)


def _accept_terms(ctx: EscrowContext, view: DealView, envelope: Row) -> DealView:
    _require(guards.accept_terms(view, envelope))
    return ctx.store.record_message(view, envelope, t.QUOTED)


def _stored(ctx: EscrowContext, artifact_id: str) -> bytes | None:
    """The artifact's bytes, or None when the store does not have it."""
    try:
        if ctx.artifacts.stat(artifact_id) is None:
            return None
        return ctx.artifacts.get(artifact_id)
    except (ModuleError, LookupError):
        return None


def _delivery(ctx: EscrowContext, view: DealView, envelope: Row) -> DealView:
    body = envelope["body"]
    artifact = body["artifact"]
    _require(guards.delivery(view, envelope, _stored(ctx, artifact["artifact_id"])))
    row = {
        "delivery_id": ids.delivery_id(view.deal_id, body["attempt"]),
        "attempt": body["attempt"],
        "artifact_id": artifact["artifact_id"],
        "sha256": artifact["sha256"],
        "byte_length": artifact["byte_length"],
        "media_type": artifact["media_type"],
        "delivered_at": to_ts(ctx.clock()),
        "status": "delivered",
    }
    outbox = [_relay(view, envelope, view.terms["buyer_did"], t.DELIVERED)]
    return ctx.store.record_message(
        view, envelope, t.DELIVERED, outbox=outbox, deliveries=[row]
    )


def _verdict(ctx: EscrowContext, view: DealView, envelope: Row) -> DealView:
    body = envelope["body"]
    _require(guards.verdict(view, envelope))
    evaluation = view.evaluation(body["evaluation_request_id"])
    assert evaluation is not None
    earlier = view.event_for_message(str(evaluation.get("verdict_message_id")))
    recorded = earlier["body"]["envelope"]["body"] if earlier else None
    kind = policy.classify_verdict(evaluation, recorded, body)
    if kind == policy.DUPLICATE:
        return view  # the same judgement again: a no-op
    if kind == policy.CONFLICT:
        raise r.Rejected(r.CONFLICTING_VERDICT)
    if body["outcome"] == policy.ERROR:
        # An error verdict leads to a re-request and then a dispute; neither is built.
        raise r.Rejected(r.NOT_IN_DEMO)
    row = {name: evaluation.get(name) for name in EVALUATION_FIELDS}
    row["verdict_message_id"] = envelope["message_id"]
    row["outcome"] = body["outcome"]
    return ctx.store.record_message(view, envelope, t.EVALUATING, evaluations=[row])


_RECORDERS: dict[str, Callable[[EscrowContext, DealView, Row], DealView]] = {
    "service_request": _service_request,
    "quote": _quote,
    "accept_terms": _accept_terms,
    "delivery": _delivery,
    "verdict": _verdict,
}
