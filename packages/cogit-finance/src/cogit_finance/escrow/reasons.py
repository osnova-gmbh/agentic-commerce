"""Reason codes of a refused message. They are part of E's observable behaviour."""

from __future__ import annotations

from cogit_finance.escrow.transitions import ILLEGAL_IN_STATE as ILLEGAL_IN_STATE
from cogit_finance.escrow.transitions import NOT_IN_DEMO as NOT_IN_DEMO

# Envelope
INVALID_ENVELOPE = "invalid_envelope"
BAD_SIGNATURE = "bad_signature"
WRONG_RECIPIENT = "wrong_recipient"
UNKNOWN_TYPE = "unknown_type"
UNEXPECTED_TYPE = "unexpected_type"  # a type only E sends
INVALID_BODY = "invalid_body"
INVALID_DEAL_ID = "invalid_deal_id"
MESSAGE_ID_REUSED = "message_id_reused"  # a recorded ID with other content

# Sender
UNKNOWN_SENDER = "unknown_sender"
UNEXPECTED_SENDER = "unexpected_sender"

# service_request and quote
BUYER_NOT_REGISTERED = "buyer_not_registered"
OFFER_NOT_FOUND = "offer_not_found"
OFFER_INACTIVE = "offer_inactive"
UNSUPPORTED_CURRENCY = "unsupported_currency"
MAX_PRICE_BELOW_OFFER = "max_price_below_offer"
OVER_SPENDING_LIMIT = "over_spending_limit"
SELLER_UNREACHABLE = "seller_unreachable"
PRICE_ABOVE_MAX = "price_above_max"
TOO_MANY_ATTEMPTS = "too_many_attempts"
DUPLICATE_EVALUATOR = "duplicate_evaluator"
UNKNOWN_EVALUATOR = "unknown_evaluator"
EVALUATOR_NOT_ALLOWED = "evaluator_not_allowed"
EVALUATOR_NOT_INDEPENDENT = "evaluator_not_independent"
EVALUATOR_UNREACHABLE = "evaluator_unreachable"

# accept_terms
TERMS_HASH_MISMATCH = "terms_hash_mismatch"
ALREADY_ACCEPTED = "already_accepted"

# delivery
NO_ATTEMPTS_LEFT = "no_attempts_left"
UNEXPECTED_ATTEMPT = "unexpected_attempt"
ARTIFACT_NOT_FOUND = "artifact_not_found"
ARTIFACT_MISMATCH = "artifact_mismatch"

# verdict
UNKNOWN_EVALUATION_REQUEST = "unknown_evaluation_request"
STALE_VERDICT = "stale_verdict"
DELIVERY_ID_MISMATCH = "delivery_id_mismatch"
ARTIFACT_SHA256_MISMATCH = "artifact_sha256_mismatch"
EVALUATOR_MISMATCH = "evaluator_mismatch"
CONFLICTING_VERDICT = "conflicting_verdict"


class Rejected(Exception):  # noqa: N818 - a refusal, not an error
    """E refuses the message. Nothing was recorded; ``reason`` goes to the sender."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason
