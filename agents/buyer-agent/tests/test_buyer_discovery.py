# pyright: basic
"""Buyer discovery and ``service_request`` (SPEC §8, §13.1), on fake ports."""

from __future__ import annotations

import uuid

import pytest
from buyer_fakes import (
    BUYER_KEY,
    CATALOG,
    ESCROW_KEY,
    MESSAGING,
    FakeModules,
    offer,
    rig,
    seller,
)
from cogit_messaging_shim import verify_envelope

from buyer_agent.buyer_core import EscrowUnknownError, PurchaseResult


def one_offer() -> FakeModules:
    return FakeModules(sellers=[seller()], offers={"seller-co": [offer()]})


def test_picks_the_first_seller_and_the_first_affordable_active_offer() -> None:
    test = rig(
        FakeModules(
            sellers=[seller("zeta-co"), seller("seller-co")],
            offers={
                "seller-co": [
                    offer("offer-0", 10000, active=False),
                    offer("offer-1", 70000),
                    offer("offer-2", 50000),
                    offer("offer-3", 40000),
                ],
                "zeta-co": [offer("offer-9", 100)],
            },
        )
    )

    result = test.buyer.start_purchase()

    assert result.status == "requested"
    assert (result.seller_org_id, result.offer_id) == ("seller-co", "offer-2")
    assert (result.sellers_seen, result.offers_seen) == (2, 4)
    assert result.deal_id is not None
    assert str(uuid.UUID(result.deal_id)) == result.deal_id
    # Discovery read the category's sellers and only the first seller's catalog.
    assert test.modules.queries == [
        (CATALOG, "sellers.list", {"category": "reports"}),
        (CATALOG, "catalog.read", {"seller_org_id": "seller-co"}),
    ]
    (request,) = test.messaging.sent
    assert verify_envelope(request)
    assert request["sender_did"] == BUYER_KEY.did
    assert request["type_key"] == "finance.service_request"
    assert request["type_version"] == 1
    assert request["recipient_did"] == ESCROW_KEY.did
    assert request["conversation_id"] == result.deal_id
    assert request["causation_id"] is None
    assert request["body"] == {
        "seller_org_id": "seller-co",
        "offer_id": "offer-2",
        "inputs": {"topic": "Agentic commerce"},
        "max_price_minor": 60000,
        "currency": "EUR",
    }


def test_every_purchase_gets_a_new_deal_id() -> None:
    test = rig(one_offer())

    first, second = test.buyer.start_purchase(), test.buyer.start_purchase()

    assert first.deal_id != second.deal_id
    assert len(test.messaging.sent) == 2


def test_inactive_and_too_expensive_offers_are_skipped() -> None:
    test = rig(
        FakeModules(
            sellers=[seller()],
            offers={
                "seller-co": [
                    offer("offer-1", 100, active=False),
                    offer("offer-2", 60001),
                ]
            },
        )
    )

    result = test.buyer.start_purchase()

    assert result == PurchaseResult("no_offer", sellers_seen=1, offers_seen=2)
    assert test.messaging.sent == []


@pytest.mark.parametrize(
    "max_price_minor,expected", [(50000, "requested"), (49999, "no_offer")]
)
def test_an_offer_at_the_maximum_price_is_affordable(
    max_price_minor: int, expected: str
) -> None:
    test = rig(one_offer(), max_price_minor=max_price_minor)

    assert test.buyer.start_purchase().status == expected


def test_an_empty_catalog_gives_no_offer_and_sends_nothing() -> None:
    test = rig(FakeModules())

    result = test.buyer.start_purchase()

    assert result == PurchaseResult("no_offer", sellers_seen=0, offers_seen=0)
    assert (result.deal_id, result.seller_org_id, result.offer_id) == (None,) * 3
    assert test.modules.exports_called() == ["sellers.list"]
    assert test.messaging.sent == []


def test_a_seller_without_offers_gives_no_offer() -> None:
    test = rig(FakeModules(sellers=[seller()]))

    result = test.buyer.start_purchase()

    assert result == PurchaseResult("no_offer", sellers_seen=1, offers_seen=0)
    assert test.messaging.sent == []


def test_arguments_override_the_configured_category_and_maximum() -> None:
    test = rig(
        FakeModules(
            sellers=[seller("audit-co", ("audits",)), seller("seller-co")],
            offers={
                "audit-co": [
                    offer("report-1", 100),
                    offer("audit-1", 900, category="audits"),
                    offer("audit-2", 700, category="audits", currency="USD"),
                    offer("audit-3", 600, category="audits"),
                ]
            },
        )
    )

    result = test.buyer.start_purchase(category="audits", max_price_minor=800)

    assert test.modules.queries[0] == (
        CATALOG,
        "sellers.list",
        {"category": "audits"},
    )
    # Offers of another category or currency are not what the buyer asked for.
    assert (result.seller_org_id, result.offer_id) == ("audit-co", "audit-3")
    assert (result.sellers_seen, result.offers_seen) == (1, 4)
    assert test.messaging.sent[0]["body"]["max_price_minor"] == 800


def test_the_escrow_did_is_resolved_when_it_is_not_configured() -> None:
    modules = one_offer()
    modules.escrow_did = ESCROW_KEY.did
    test = rig(modules, escrow_did=None)

    assert test.buyer.start_purchase().status == "requested"
    assert (MESSAGING, "identity.resolve", {"role": "escrow"}) in modules.queries
    assert test.messaging.sent[0]["recipient_did"] == ESCROW_KEY.did


def test_a_configured_escrow_did_needs_no_identity_query() -> None:
    test = rig(one_offer())

    test.buyer.start_purchase()

    assert "identity.resolve" not in test.modules.exports_called()


def test_without_a_registered_escrow_the_request_fails_and_sends_nothing() -> None:
    test = rig(one_offer(), escrow_did=None)

    with pytest.raises(EscrowUnknownError):
        test.buyer.start_purchase()
    assert test.messaging.sent == []
