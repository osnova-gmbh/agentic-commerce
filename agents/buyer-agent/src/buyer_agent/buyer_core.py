# pyright: basic
# The shared ports ship without type stubs and pass JSON as plain dicts.
"""Buyer behaviour of the escrow demo (SPEC §8), free of SDK and transport imports.

The ports come in through the constructor, so the class runs unchanged on the run
handle of a Cogit worker and on fakes in the unit tests. The buyer keeps no state
between messages: every reply is derived from the inbound message alone, and the
bank payment is idempotent by its key.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Literal, TypeGuard

from cogit_finance_seams import BankPort, ModulePort
from cogit_messaging_shim import (
    MESSAGING_MODULE,
    MessagingSeams,
    canonical_hash,
    verify_envelope,
)

CATALOG_MODULE = "cogit-finance-catalog"
TYPE_VERSION = 1
CURRENCY = "EUR"
REQUEST_INPUTS: dict[str, Any] = {"topic": "Agentic commerce"}

SERVICE_REQUEST = "finance.service_request"
TERMS_PROPOSED = "finance.terms_proposed"
ACCEPT_TERMS = "finance.accept_terms"
PAYMENT_REQUEST = "finance.payment_request"
RELAY = "finance.relay"
# Messages the buyer only takes note of. It never disputes (SPEC §8).
NO_ACTION_TYPES = frozenset(
    {
        "finance.terms_countersigned",
        "finance.funding_confirmed",
        "finance.decision",
        "finance.payout_confirmed",
        "finance.receipt",
    }
)
# What E relays to the buyer (SPEC §6.3, build guide §5.4).
RELAYED_TYPES = frozenset({"finance.quote", "finance.delivery"})

Json = dict[str, Any]


class EscrowUnknownError(RuntimeError):
    """No escrow DID is configured or registered yet. Worth retrying later."""


@dataclass(frozen=True)
class BuyerSettings:
    org_id: str = "buyer-co"
    iban: str = "DE00EXAMPLE0000000010"
    category: str = "reports"
    max_price_minor: int = 60000
    escrow_did: str | None = None  # None: resolved with identity.resolve


@dataclass(frozen=True)
class PurchaseResult:
    """Outcome of ``start_purchase``; the counts are the discovery evidence."""

    status: Literal["requested", "no_offer"]
    sellers_seen: int
    offers_seen: int
    deal_id: str | None = None
    seller_org_id: str | None = None
    offer_id: str | None = None


@dataclass(frozen=True)
class MessageResult:
    status: Literal["processed", "rejected"]
    reason: str | None = None


PROCESSED = MessageResult("processed")


def rejected(reason: str) -> MessageResult:
    return MessageResult("rejected", reason)


def _is_amount(value: object) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool)


class BuyerCore:
    def __init__(
        self,
        modules: ModulePort,
        messaging: MessagingSeams,
        bank: BankPort,
        settings: BuyerSettings | None = None,
    ) -> None:
        self._modules = modules
        self._messaging = messaging
        self._bank = bank
        self.settings = settings or BuyerSettings()
        self._escrow_did = self.settings.escrow_did

    def escrow_did(self) -> str:
        """E's DID: the configured one, else the registered escrow identity."""
        if self._escrow_did is None:
            found = self._query(
                MESSAGING_MODULE, "identity.resolve", {"role": "escrow"}
            )
            identity = found.get("identity")
            if not isinstance(identity, dict) or not identity.get("did"):
                raise EscrowUnknownError("No escrow identity is registered")
            self._escrow_did = str(identity["did"])
        return self._escrow_did

    def start_purchase(
        self, category: str | None = None, max_price_minor: int | None = None
    ) -> PurchaseResult:
        """Discover one offer and request it from E. Arguments override the settings."""
        wanted = category or self.settings.category
        ceiling = (
            self.settings.max_price_minor
            if max_price_minor is None
            else max_price_minor
        )
        listed = self._query(CATALOG_MODULE, "sellers.list", {"category": wanted})
        sellers = sorted(_rows(listed, "sellers"), key=lambda row: str(row["org_id"]))
        if not sellers:
            return PurchaseResult("no_offer", sellers_seen=0, offers_seen=0)
        seller_org_id = str(sellers[0]["org_id"])
        catalog = self._query(
            CATALOG_MODULE, "catalog.read", {"seller_org_id": seller_org_id}
        )
        offers = _rows(catalog, "offers")
        sellers_seen, offers_seen = len(sellers), len(offers)
        offer = next((o for o in offers if _fits(o, wanted, ceiling)), None)
        if offer is None:
            return PurchaseResult("no_offer", sellers_seen, offers_seen)
        offer_id = str(offer["offer_id"])
        deal_id = str(uuid.uuid4())
        self._messaging.send(
            SERVICE_REQUEST,
            TYPE_VERSION,
            self.escrow_did(),
            deal_id,
            {
                "seller_org_id": seller_org_id,
                "offer_id": offer_id,
                "inputs": dict(REQUEST_INPUTS),
                "max_price_minor": ceiling,
                "currency": CURRENCY,
            },
        )
        return PurchaseResult(
            "requested", sellers_seen, offers_seen, deal_id, seller_org_id, offer_id
        )

    def handle_message(self, envelope: Json) -> MessageResult:
        """Act on one inbound envelope. Raises only for failures worth retrying."""
        if not verify_envelope(envelope):
            return rejected("bad_signature")
        if envelope["sender_did"] != self.escrow_did():
            return rejected("unexpected_sender")
        type_key = envelope["type_key"]
        if envelope["type_version"] != TYPE_VERSION:
            return rejected("unsupported_type")
        if type_key == TERMS_PROPOSED:
            return self._on_terms_proposed(envelope)
        if type_key == PAYMENT_REQUEST:
            return self._on_payment_request(envelope)
        if type_key == RELAY:
            return self._on_relay(envelope)
        if type_key in NO_ACTION_TYPES:
            return PROCESSED
        return rejected("unsupported_type")

    def _on_terms_proposed(self, envelope: Json) -> MessageResult:
        body: Json = envelope["body"]
        terms, terms_hash = body.get("terms"), body.get("terms_hash")
        if not isinstance(terms, dict) or not isinstance(terms_hash, str):
            return rejected("invalid_body")
        deal_id = str(envelope["conversation_id"])
        objection = self._objection_to(terms, terms_hash, deal_id)
        if objection is not None:
            return rejected(objection)
        self._messaging.send(
            ACCEPT_TERMS,
            TYPE_VERSION,
            self.escrow_did(),
            deal_id,
            {"terms_hash": terms_hash},
            causation_id=str(envelope["message_id"]),
        )
        return PROCESSED

    def _objection_to(self, terms: Json, terms_hash: str, deal_id: str) -> str | None:
        """Why the buyer refuses these terms, or None when it accepts them."""
        price = terms.get("price_minor")
        if not _is_amount(price):
            return "invalid_body"
        if terms.get("deal_id") != deal_id:
            return "deal_id_mismatch"
        if canonical_hash(terms) != terms_hash:
            return "terms_hash_mismatch"
        if terms.get("buyer_org_id") != self.settings.org_id:
            return "wrong_buyer_org"
        if terms.get("currency") != CURRENCY:
            return "unsupported_currency"
        if price > self.settings.max_price_minor:
            return "price_above_maximum"
        acceptance = terms.get("acceptance")
        evaluators = (
            acceptance.get("evaluators") if isinstance(acceptance, dict) else None
        )
        if not isinstance(evaluators, list) or not evaluators:
            return "no_evaluator"
        return None

    def _on_payment_request(self, envelope: Json) -> MessageResult:
        body: Json = envelope["body"]
        to_iban, reference = body.get("to_iban"), body.get("reference")
        amount, currency = body.get("amount_minor"), body.get("currency")
        if not (isinstance(to_iban, str) and isinstance(reference, str)):
            return rejected("invalid_body")
        if not _is_amount(amount) or amount < 1:
            return rejected("invalid_body")
        if currency != CURRENCY:
            return rejected("unsupported_currency")
        if amount > self.settings.max_price_minor:
            return rejected("amount_above_maximum")
        # A bank error propagates: the delivery loop releases the message and the
        # retry repeats the call under the same key, so the money moves once.
        self._bank.transfer(
            from_iban=self.settings.iban,
            to_iban=to_iban,
            amount_minor=amount,
            currency=CURRENCY,
            reference=reference,
            idempotency_key=f"pay:{envelope['conversation_id']}",
        )
        return PROCESSED

    def _on_relay(self, envelope: Json) -> MessageResult:
        relayed = envelope["body"].get("relayed")
        if not verify_envelope(relayed):
            return rejected("bad_relayed_signature")
        if relayed["type_key"] not in RELAYED_TYPES:
            return rejected("unsupported_type")
        return PROCESSED

    def _query(self, module: str, export: str, args: Json) -> Json:
        return self._modules.module_query(module, export, args)


def _rows(result: Json, name: str) -> list[Json]:
    return list(result.get(name) or [])


def _fits(offer: Json, category: str, ceiling: int) -> bool:
    """An active offer of the wanted category, in EUR, at or under the ceiling."""
    price = offer.get("price_minor")
    return (
        bool(offer.get("active"))
        and _is_amount(price)
        and price <= ceiling
        and offer.get("currency", CURRENCY) == CURRENCY
        and offer.get("category", category) == category
    )
