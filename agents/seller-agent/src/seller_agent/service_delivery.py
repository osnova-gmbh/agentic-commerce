"""Build the agreed service from signed, accepted conversation terms."""

from __future__ import annotations

from cogit_finance_seams import ModulePort
from cogit_messaging_shim import canonical_hash, verify_envelope

from seller_agent.deliverable import build_service_deliverable
from seller_agent.offers import find_offer
from seller_agent.seller import RefusalError


def build_agreed_delivery(
    modules: ModulePort,
    deal_id: str,
    complete: bool,
    *,
    escrow_did: str,
    seller_did: str,
    seller_org_id: str,
    offers: list[dict],
) -> bytes:
    """Use only terms signed by escrow and countersigned by this seller."""
    history = modules.module_query(
        "cogit-messaging", "conversation.read", {"conversation_id": deal_id}
    )["messages"]
    messages = [row["envelope"] for row in history]
    accepted = {
        message["body"].get("terms_hash")
        for message in messages
        if message.get("type_key") == "finance.accept_terms"
        and message.get("type_version") == 1
        and message.get("conversation_id") == deal_id
        and message.get("sender_did") == seller_did
        and message.get("recipient_did") == escrow_did
        and verify_envelope(message)
    }
    for message in reversed(messages):
        if not (
            message.get("type_key") == "finance.terms_proposed"
            and message.get("type_version") == 1
            and message.get("conversation_id") == deal_id
            and message.get("sender_did") == escrow_did
            and message.get("recipient_did") == seller_did
            and verify_envelope(message)
        ):
            continue
        terms = message["body"].get("terms")
        terms_hash = message["body"].get("terms_hash")
        if not isinstance(terms, dict) or terms_hash not in accepted:
            continue
        if canonical_hash(terms) != terms_hash or terms.get("deal_id") != deal_id:
            continue
        offer = find_offer(offers, terms.get("offer_id"))
        if (
            offer is None
            or terms.get("seller_org_id") != seller_org_id
            or terms.get("seller_did") != seller_did
            or terms.get("escrow_did") != escrow_did
            or terms.get("currency") != offer["currency"]
            or terms.get("price_minor") != offer["price_minor"]
            or not isinstance(terms.get("inputs"), dict)
        ):
            raise RefusalError("terms_mismatch")
        return build_service_deliverable(
            deal_id, offer, terms["inputs"], include_summary=complete
        )
    raise RefusalError("missing_accepted_terms")
