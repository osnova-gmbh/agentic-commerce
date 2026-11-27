# pyright: basic
"""Deal terms and their hash (build guide §5.5). No I/O."""

from __future__ import annotations

import copy
from typing import Any

from cogit_messaging_shim import canonical_hash

TIMER_KEYS = (
    "quote_ttl_s",
    "funding_due_s",
    "rework_window_s",
    "dispute_window_s",
    "evaluator_respond_s",
)


def build_terms(
    *,
    deal_id: str,
    buyer_org_id: str,
    seller_org_id: str,
    buyer_did: str,
    seller_did: str,
    escrow_did: str,
    offer: dict[str, Any],
    request: dict[str, Any],
    quote: dict[str, Any],
    escrow_config: dict[str, Any],
) -> dict[str, Any]:
    """Terms from the request body, the quote body, the offer and the operator config.

    The operator's timers are frozen into the terms together with the offer's
    ``delivery_time_s`` (SPEC §5.3).
    """
    timers = {name: escrow_config["timers"][name] for name in TIMER_KEYS}
    timers["delivery_time_s"] = offer["delivery_time_s"]
    return {
        "deal_id": deal_id,
        "buyer_org_id": buyer_org_id,
        "seller_org_id": seller_org_id,
        "buyer_did": buyer_did,
        "seller_did": seller_did,
        "escrow_did": escrow_did,
        "offer_id": offer["offer_id"],
        "inputs": copy.deepcopy(request["inputs"]),
        "price_minor": quote["price_minor"],
        "currency": quote["currency"],
        "fee_bps": escrow_config["fee_bps"],
        "delivery_deadline": quote["delivery_deadline"],
        "acceptance": copy.deepcopy(quote["acceptance"]),
        "timers": timers,
    }


def terms_hash(terms: dict[str, Any]) -> str:
    """Lower-case hex SHA-256 of the canonical terms."""
    return canonical_hash(terms)
