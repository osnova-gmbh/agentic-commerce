# pyright: basic
"""Guards of the in-scope SPEC §5.2 rows. Pure: every fact is passed in.

Each function returns the reason to refuse, or None when the transition may go
ahead. Whether the trigger is legal in the deal's state is checked before, from
the transition table.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

from cogit_messaging_shim import parse_ts

from cogit_finance.escrow import policy
from cogit_finance.escrow import reasons as r
from cogit_finance.escrow.transitions import EVALUATING, FUNDING_REQUESTED
from cogit_finance.escrow.view import DealView

Row = dict[str, Any]
CURRENCY = "EUR"


def _sender(identity: Row | None, role: str, org_id: str | None = None) -> str | None:
    if identity is None or not identity.get("active", True):
        return r.UNKNOWN_SENDER
    if identity.get("role") != role:
        return r.UNEXPECTED_SENDER
    if org_id is not None and identity.get("org_id") != org_id:
        return r.UNEXPECTED_SENDER
    return None


def service_request(
    body: Row,
    *,
    identity: Row | None,
    company: Row | None,
    offer: Row | None,
    seller_identity: Row | None,
) -> str | None:
    """Row 1. ``identity`` is the sender's; ``company`` is the sender's company."""
    refused = _sender(identity, "buyer")
    if refused:
        return refused
    if company is None or "buyer" not in (company.get("roles") or []):
        return r.BUYER_NOT_REGISTERED
    if body["currency"] != CURRENCY:
        return r.UNSUPPORTED_CURRENCY
    if offer is None:
        return r.OFFER_NOT_FOUND
    if not offer.get("active"):
        return r.OFFER_INACTIVE
    if offer.get("currency") != CURRENCY:
        return r.UNSUPPORTED_CURRENCY
    if body["max_price_minor"] < offer["price_minor"]:
        return r.MAX_PRICE_BELOW_OFFER
    if offer["price_minor"] > int(company.get("spending_limit_minor") or 0):
        return r.OVER_SPENDING_LIMIT
    if seller_identity is None:
        return r.SELLER_UNREACHABLE
    return None


def _timestamps(*values: str) -> bool:
    try:
        for value in values:
            parse_ts(value)
    except ValueError:
        return False
    return True


def evaluators(
    acceptance: Row,
    *,
    parties: set[str],
    registry: dict[tuple[str, int], Row],
    identities: dict[str, Row | None],
    allow: list[str],
) -> str | None:
    """Every named evaluator is registered, reachable and independent of both parties.

    ``registry`` maps ``(evaluator_id, version)`` to the evaluator row;
    ``identities`` maps an evaluator DID to its identity row or None.
    """
    seen: set[tuple[str, int]] = set()
    for named in acceptance["evaluators"]:
        key = (named["evaluator_id"], named["version"])
        if key in seen:
            return r.DUPLICATE_EVALUATOR
        seen.add(key)
        row = registry.get(key)
        if row is None:
            return r.UNKNOWN_EVALUATOR
        if allow and named["evaluator_id"] not in allow:
            return r.EVALUATOR_NOT_ALLOWED
        if row.get("org_id") in parties:
            return r.EVALUATOR_NOT_INDEPENDENT
        identity = identities.get(str(row.get("did")))
        if identity is None or not identity.get("active", True):
            return r.EVALUATOR_UNREACHABLE
        if identity.get("org_id") in parties or identity.get("role") != "evaluator":
            return r.EVALUATOR_NOT_INDEPENDENT
    return None


def quote(
    view: DealView,
    body: Row,
    *,
    identity: Row | None,
    buyer_company: Row | None,
    offer: Row | None,
    registry: dict[tuple[str, int], Row],
    identities: dict[str, Row | None],
    config: Row,
) -> str | None:
    """Row 2. ``identity`` is the sender's; the offer is the one the deal names."""
    refused = _sender(identity, "seller", view.seller_org_id)
    if refused:
        return refused
    request = view.request["body"]
    if body["currency"] != request["currency"]:
        return r.UNSUPPORTED_CURRENCY
    if body["price_minor"] > request["max_price_minor"]:
        return r.PRICE_ABOVE_MAX
    limit = int((buyer_company or {}).get("spending_limit_minor") or 0)
    if body["price_minor"] > limit:
        return r.OVER_SPENDING_LIMIT
    if offer is None:
        return r.OFFER_NOT_FOUND
    if not offer.get("active"):
        return r.OFFER_INACTIVE
    if not _timestamps(body["delivery_deadline"], body["valid_until"]):
        return r.INVALID_BODY
    acceptance = body["acceptance"]
    try:
        policy.decide(acceptance["policy"], [None] * len(acceptance["evaluators"]))
    except ValueError:
        return r.INVALID_BODY
    if acceptance["max_attempts"] > config["escrow"]["max_delivery_attempts"]:
        return r.TOO_MANY_ATTEMPTS
    return evaluators(
        acceptance,
        parties={view.buyer_org_id, view.seller_org_id},
        registry=registry,
        identities=identities,
        allow=list(config["evaluators"]["allow"]),
    )


def accept_terms(view: DealView, envelope: Row) -> str | None:
    """Row 6: the hash of the proposed terms, once per party."""
    if view.terms_hash is None:
        return r.ILLEGAL_IN_STATE  # the quote is recorded, the terms are not yet
    sender = envelope["sender_did"]
    if sender not in (view.terms["buyer_did"], view.terms["seller_did"]):
        return r.UNEXPECTED_SENDER
    if envelope["body"]["terms_hash"] != view.terms_hash:
        return r.TERMS_HASH_MISMATCH
    if sender in view.acceptances:
        return r.ALREADY_ACCEPTED
    return None


def both_accepted(view: DealView) -> bool:
    if view.terms_hash is None:
        return False
    parties = {view.terms["buyer_did"], view.terms["seller_did"]}
    return parties <= set(view.acceptances)


def funding(view: DealView, credit: Row) -> str | None:
    """Row 9: the deal awaits funding and the credit is the exact price."""
    if view.state != FUNDING_REQUESTED:
        return "not_awaiting_funding"
    terms = view.terms
    if credit.get("amount_minor") != terms["price_minor"]:
        return "amount_mismatch"
    if credit.get("currency", terms["currency"]) != terms["currency"]:
        return "currency_mismatch"
    return None


def delivery(
    view: DealView, envelope: Row, stored: bytes | None, now: datetime | None = None
) -> str | None:
    """Rows 11 and 17. ``stored`` holds the artifact's bytes, None when missing."""
    terms = view.terms
    if envelope["sender_did"] != terms["seller_did"]:
        return r.UNEXPECTED_SENDER
    if view.next_attempt > terms["acceptance"]["max_attempts"]:
        return r.NO_ATTEMPTS_LEFT
    moment = now or parse_ts(envelope["created_at"])
    if moment >= parse_ts(terms["delivery_deadline"]):
        return "delivery_deadline_passed"
    if view.state == "REJECTED":
        decision = view.last_event("decision")
        deadline = decision["body"]["rework_deadline"] if decision else None
        if not deadline or moment >= parse_ts(deadline):
            return "rework_deadline_passed"
    body = envelope["body"]
    expected = view.next_attempt
    if body["attempt"] != expected:
        return r.UNEXPECTED_ATTEMPT
    if stored is None:
        return r.ARTIFACT_NOT_FOUND
    artifact = body["artifact"]
    digest = hashlib.sha256(stored).hexdigest()
    if digest != artifact["sha256"] or len(stored) != artifact["byte_length"]:
        return r.ARTIFACT_MISMATCH
    return None


def stale_verdict(view: DealView, body: Row) -> bool:
    """SPEC §9.2: for a superseded delivery, or after the decision."""
    evaluation = view.evaluation(body["evaluation_request_id"])
    if evaluation is None:
        return False
    current = view.current_delivery
    superseded = current is None or evaluation["delivery_id"] != current["delivery_id"]
    return superseded or view.state != EVALUATING


def verdict(view: DealView, envelope: Row) -> str | None:
    """Row 14: the verdict answers a request for the current delivery."""
    body = envelope["body"]
    evaluation = view.evaluation(body["evaluation_request_id"])
    current = view.current_delivery
    if evaluation is None or current is None:
        return r.UNKNOWN_EVALUATION_REQUEST
    if envelope["sender_did"] != evaluation["evaluator_did"]:
        return r.UNEXPECTED_SENDER
    if body["terms_hash"] != view.terms_hash:
        return r.TERMS_HASH_MISMATCH
    if body["delivery_id"] != evaluation["delivery_id"]:
        return r.DELIVERY_ID_MISMATCH
    if body["artifact_sha256"] != current["sha256"]:
        return r.ARTIFACT_SHA256_MISMATCH
    same_evaluator = (
        body["evaluator_id"] == evaluation["evaluator_id"]
        and body["evaluator_version"] == evaluation["evaluator_version"]
    )
    return None if same_evaluator else r.EVALUATOR_MISMATCH
