# pyright: basic
"""Seller core: publish offers, quote, accept terms, deliver and redeliver.

Plain Python. The ports come in through the constructor and nothing here imports
the Cogit SDK, so the behaviour is unit-tested with fakes. The core keeps no state
between messages: what it needs is in the message and in the offers file. Every
reply passes the inbound ``message_id`` as ``causation_id``, which gives the reply
a stable ID, so handling the same message twice queues one reply.
"""

from __future__ import annotations

import copy
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from cogit_finance_seams import ArtifactPort, ModulePort
from cogit_messaging_shim import (
    MessagingSeams,
    canonical_hash,
    to_ts,
    verify_envelope,
)

from seller_agent.deliverable import MEDIA_TYPE, build_deliverable
from seller_agent.offers import find_offer

CATALOG_MODULE = "cogit-finance-catalog"
RELAY = "finance.relay"
SERVICE_REQUEST = "finance.service_request"
QUOTE = "finance.quote"
TERMS_PROPOSED = "finance.terms_proposed"
ACCEPT_TERMS = "finance.accept_terms"
FUNDING_CONFIRMED = "finance.funding_confirmed"
DELIVERY = "finance.delivery"
DECISION = "finance.decision"
INFORMATIONAL = (
    "finance.terms_countersigned",
    "finance.payout_confirmed",
    "finance.receipt",
)
QUOTE_VALID_S = 600
MODES = ("ok", "broken")


class RefusalError(Exception):
    """The message is refused; ``reason`` goes into the acknowledgement."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _fields(body: Any, *names: str) -> list[Any]:
    if not isinstance(body, dict) or any(name not in body for name in names):
        raise RefusalError("invalid_body")
    return [body[name] for name in names]


def publish_offers(
    modules: ModulePort,
    seller_org_id: str,
    offers: list[dict[str, Any]],
    run_key: str | None = None,
) -> int:
    """Replace this seller's offers in the catalog; return how many it now has.

    The command key is the run's key when there is one (a retried run publishes
    once), otherwise the hash of the offers (the same offers publish once).
    """
    result = modules.module_command(
        CATALOG_MODULE,
        "catalog.publish",
        {"seller_org_id": seller_org_id, "offers": offers},
        idempotency_key=(
            f"catalog.publish:{seller_org_id}:{run_key or canonical_hash(offers)}"
        ),
    )
    return int(result["count"])


def quoted_acceptance(offer: dict[str, Any], delivery_deadline: str) -> dict[str, Any]:
    """The offer's default acceptance spec with the quoted deadline filled in."""
    default = offer["default_acceptance"]
    evaluators: list[dict[str, Any]] = []
    for item in default["evaluators"]:
        params = copy.deepcopy(item.get("params") or {})
        if item["evaluator_id"] == "deadline":
            params["delivery_deadline"] = delivery_deadline
        evaluators.append(
            {
                "evaluator_id": item["evaluator_id"],
                "version": item["version"],
                "params": params,
            }
        )
    return {
        "evaluators": evaluators,
        "policy": default["policy"],
        "max_attempts": default["max_attempts"],
    }


class SellerCore:
    """The seller's side of a deal, driven by finance messages from E."""

    def __init__(
        self,
        *,
        modules: ModulePort,
        artifacts: ArtifactPort,
        messaging: MessagingSeams,
        escrow_did: str,
        seller_org_id: str,
        offers: list[dict[str, Any]],
        mode: str = "ok",
        delay_s: float = 0,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], datetime] = _utcnow,
    ) -> None:
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}, not {mode!r}")
        self._modules = modules
        self._artifacts = artifacts
        self._messaging = messaging
        self._escrow_did = escrow_did
        self._seller_org_id = seller_org_id
        self._offers = offers
        self._mode = mode
        self._delay_s = delay_s
        self._sleep = sleep
        self._now = now
        self._handlers: dict[str, Callable[[dict[str, Any]], None]] = {
            RELAY: self._on_relay,
            TERMS_PROPOSED: self._on_terms_proposed,
            FUNDING_CONFIRMED: self._on_funding_confirmed,
            DECISION: self._on_decision,
            **dict.fromkeys(INFORMATIONAL, self._nothing_to_do),
        }

    def publish_catalog(self, run_key: str | None = None) -> int:
        """Publish the offers file to the catalog module; return the count."""
        return publish_offers(self._modules, self._seller_org_id, self._offers, run_key)

    def handle_message(self, envelope: dict[str, Any]) -> dict[str, Any]:
        """Process one inbound envelope; return ``{"status", "reason"}``."""
        if not verify_envelope(envelope):
            return {"status": "rejected", "reason": "bad_signature"}
        if envelope["sender_did"] != self._escrow_did:
            return {"status": "rejected", "reason": "unexpected_sender"}
        handler = self._handlers.get(envelope["type_key"])
        if handler is None or envelope["type_version"] != 1:
            return {"status": "rejected", "reason": "unsupported_type"}
        try:
            handler(envelope)
        except RefusalError as refusal:
            return {"status": "rejected", "reason": refusal.reason}
        return {"status": "processed", "reason": None}

    def _reply(self, envelope: dict[str, Any], type_key: str, body: dict) -> None:
        self._messaging.send(
            type_key,
            1,
            self._escrow_did,
            envelope["conversation_id"],
            body,
            envelope["message_id"],
        )

    def _own_offer(self, seller_org_id: Any, offer_id: Any) -> dict[str, Any] | None:
        if seller_org_id != self._seller_org_id:
            return None
        return find_offer(self._offers, offer_id)

    def _nothing_to_do(self, envelope: dict[str, Any]) -> None:
        del envelope

    def _on_relay(self, envelope: dict[str, Any]) -> None:
        (relayed,) = _fields(envelope["body"], "relayed")
        if not verify_envelope(relayed):
            raise RefusalError("bad_relayed_signature")
        if relayed["conversation_id"] != envelope["conversation_id"]:
            raise RefusalError("relay_mismatch")
        if relayed["type_key"] in (QUOTE, DELIVERY):
            return  # our own messages on their way to the buyer
        if relayed["type_key"] != SERVICE_REQUEST or relayed["type_version"] != 1:
            raise RefusalError("unsupported_type")
        seller_org_id, offer_id = _fields(relayed["body"], "seller_org_id", "offer_id")
        offer = self._own_offer(seller_org_id, offer_id)
        if offer is None:
            raise RefusalError("unknown_offer")
        now = self._now()
        deadline = to_ts(now + timedelta(seconds=offer["delivery_time_s"]))
        quote = {
            "price_minor": offer["price_minor"],
            "currency": offer["currency"],
            "delivery_deadline": deadline,
            "valid_until": to_ts(now + timedelta(seconds=QUOTE_VALID_S)),
            "acceptance": quoted_acceptance(offer, deadline),
        }
        self._reply(envelope, QUOTE, quote)

    def _on_terms_proposed(self, envelope: dict[str, Any]) -> None:
        terms, terms_hash = _fields(envelope["body"], "terms", "terms_hash")
        seller_org_id, offer_id, price_minor, currency = _fields(
            terms, "seller_org_id", "offer_id", "price_minor", "currency"
        )
        try:
            computed = canonical_hash(terms)
        except TypeError as exc:
            raise RefusalError("invalid_body") from exc
        if computed != terms_hash:
            raise RefusalError("terms_hash_mismatch")
        offer = self._own_offer(seller_org_id, offer_id)
        if (
            offer is None
            or price_minor != offer["price_minor"]
            or currency != offer["currency"]
        ):
            raise RefusalError("terms_mismatch")
        self._reply(envelope, ACCEPT_TERMS, {"terms_hash": terms_hash})

    def _on_funding_confirmed(self, envelope: dict[str, Any]) -> None:
        if self._delay_s > 0:
            self._sleep(self._delay_s)
        self._deliver(envelope, 1)

    def _on_decision(self, envelope: dict[str, Any]) -> None:
        delivery_id, outcome, attempts_left = _fields(
            envelope["body"], "delivery_id", "outcome", "attempts_left"
        )
        if not isinstance(delivery_id, str) or not isinstance(attempts_left, int):
            raise RefusalError("invalid_body")
        if outcome != "reject" or attempts_left <= 0:
            return  # approved, or rejected for good: nothing to deliver
        _, separator, suffix = delivery_id.rpartition(":d")
        if not separator or not suffix.isdecimal():
            raise RefusalError("invalid_body")
        self._deliver(envelope, int(suffix) + 1)

    def _deliver(self, envelope: dict[str, Any], attempt: int) -> None:
        complete = not (self._mode == "broken" and attempt == 1)
        data = build_deliverable(envelope["conversation_id"], include_summary=complete)
        stored = self._artifacts.put(data, MEDIA_TYPE)
        artifact = {
            "artifact_id": stored["artifact_id"],
            "sha256": stored["sha256"],
            "byte_length": stored["byte_length"],
            "media_type": stored["media_type"],
        }
        self._reply(envelope, DELIVERY, {"attempt": attempt, "artifact": artifact})
