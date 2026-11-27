"""Delivery selection requires the actual seller's signed agreement."""

import pytest

from cogit_messaging_shim import AgentKey, build_envelope
from finance_fakes import DEAL_ID, FakeModules, terms_proposed
from seller_agent.offers import load_catalog
from seller_agent.seller import RefusalError
from seller_agent.service_delivery import build_agreed_delivery


@pytest.mark.parametrize("invalid", ["missing_acceptance", "other_seller", "tampered_terms"])
def test_delivery_rejects_unaccepted_or_tampered_terms(invalid):
    escrow, seller = AgentKey.generate(), AgentKey.generate()
    proposal = terms_proposed(escrow, seller.did)
    signer = AgentKey.generate() if invalid == "other_seller" else seller
    acceptance = build_envelope(
        signer, signer.did, "finance.accept_terms", 1, escrow.did, DEAL_ID,
        {"terms_hash": proposal["body"]["terms_hash"]},
    )
    if invalid == "tampered_terms":
        proposal["body"]["terms"]["offer_id"] = "ai-training"
    modules = FakeModules()
    modules.received = [proposal] + ([] if invalid == "missing_acceptance" else [acceptance])
    with pytest.raises(RefusalError, match="missing_accepted_terms"):
        build_agreed_delivery(
            modules, DEAL_ID, True, escrow_did=escrow.did, seller_did=seller.did,
            seller_org_id="seller-co", offers=load_catalog()["offers"],
        )
