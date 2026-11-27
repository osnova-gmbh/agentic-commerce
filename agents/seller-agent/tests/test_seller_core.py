"""Unit tests of the seller core on fake ports: publish, quote and terms."""

from __future__ import annotations

from typing import Any

import pytest
from cogit_messaging_shim import AgentKey, canonical_hash, verify_envelope
from finance_fakes import (
    DEAL_ID,
    Rig,
    from_escrow,
    relay,
    service_request,
    terms_proposed,
)

PROCESSED = {"status": "processed", "reason": None}


def rejected(reason: str) -> dict[str, Any]:
    return {"status": "rejected", "reason": reason}


@pytest.fixture
def rig() -> Rig:
    return Rig()


def test_publish_catalog_sends_the_offers_file(rig: Rig) -> None:
    assert rig.core.publish_catalog() == 1

    ((args, key),) = rig.modules.published()
    assert args["seller_org_id"] == "seller-co"
    (offer,) = args["offers"]
    assert offer["offer_id"] == "offer-1"
    assert offer["price_minor"] == 50000
    assert offer["deliverable"]["required_files"] == [
        "report.md",
        "data.csv",
        "summary.json",
    ]
    assert key == f"catalog.publish:seller-co:{canonical_hash(args['offers'])}"

    rig.core.publish_catalog(run_key="run-7")
    assert rig.modules.published()[1][1] == "catalog.publish:seller-co:run-7"


def test_relayed_service_request_is_quoted(rig: Rig) -> None:
    inbound = relay(rig.escrow, rig.did, service_request(rig.buyer, rig.escrow.did))

    assert rig.core.handle_message(inbound) == PROCESSED

    (quote,) = rig.messaging.sent
    assert verify_envelope(quote)
    assert quote["type_key"] == "finance.quote"
    assert quote["recipient_did"] == rig.escrow.did
    assert quote["conversation_id"] == DEAL_ID
    assert quote["causation_id"] == inbound["message_id"]
    assert quote["body"] == {
        "price_minor": 50000,
        "currency": "EUR",
        "delivery_deadline": "2026-11-27T10:01:00Z",
        "valid_until": "2026-11-27T10:10:00Z",
        "acceptance": {
            "evaluators": [
                {"evaluator_id": "integrity", "version": 1, "params": {}},
                {
                    "evaluator_id": "required-files",
                    "version": 1,
                    "params": {
                        "required_files": ["report.md", "data.csv", "summary.json"]
                    },
                },
                {
                    "evaluator_id": "deadline",
                    "version": 1,
                    "params": {"delivery_deadline": "2026-11-27T10:01:00Z"},
                },
            ],
            "policy": "all",
            "max_attempts": 2,
        },
    }
    # Quoting leaves the offers file's default acceptance spec untouched.
    defaults = rig.catalog["offers"][0]["default_acceptance"]["evaluators"]
    assert defaults[2]["params"] == {}


def test_relay_with_a_broken_inner_signature_is_rejected(rig: Rig) -> None:
    request = service_request(rig.buyer, rig.escrow.did)
    request["body"]["max_price_minor"] = 1
    inbound = relay(rig.escrow, rig.did, request)

    assert rig.core.handle_message(inbound) == rejected("bad_relayed_signature")
    assert rig.messaging.sent == []


def test_relay_for_an_unknown_offer_is_rejected(rig: Rig) -> None:
    request = service_request(rig.buyer, rig.escrow.did, offer_id="offer-9")
    inbound = relay(rig.escrow, rig.did, request)

    assert rig.core.handle_message(inbound) == rejected("unknown_offer")
    assert rig.messaging.sent == []


def test_matching_terms_are_accepted(rig: Rig) -> None:
    inbound = terms_proposed(rig.escrow, rig.did)

    assert rig.core.handle_message(inbound) == PROCESSED

    (accept,) = rig.messaging.sent
    assert verify_envelope(accept)
    assert accept["type_key"] == "finance.accept_terms"
    assert accept["recipient_did"] == rig.escrow.did
    assert accept["causation_id"] == inbound["message_id"]
    assert accept["body"] == {"terms_hash": inbound["body"]["terms_hash"]}


@pytest.mark.parametrize(
    "changes",
    [
        {"price_minor": 49999},
        {"currency": "USD"},
        {"offer_id": "offer-9"},
        {"seller_org_id": "other-co"},
    ],
)
def test_terms_that_differ_from_the_offer_are_refused(
    rig: Rig, changes: dict[str, Any]
) -> None:
    inbound = terms_proposed(rig.escrow, rig.did, **changes)

    assert rig.core.handle_message(inbound) == rejected("terms_mismatch")
    assert rig.messaging.sent == []


def test_terms_with_a_wrong_hash_are_refused(rig: Rig) -> None:
    body = terms_proposed(rig.escrow, rig.did)["body"]
    body["terms_hash"] = "0" * 64
    inbound = from_escrow(rig.escrow, rig.did, "finance.terms_proposed", body)

    assert rig.core.handle_message(inbound) == rejected("terms_hash_mismatch")
    assert rig.messaging.sent == []


def test_messages_not_from_escrow_are_rejected(rig: Rig) -> None:
    stranger = AgentKey.generate()
    body = terms_proposed(rig.escrow, rig.did)["body"]
    inbound = from_escrow(
        rig.escrow, rig.did, "finance.terms_proposed", body, sender=stranger
    )

    assert rig.core.handle_message(inbound) == rejected("unexpected_sender")
    assert rig.messaging.sent == []


def test_informational_messages_need_no_action(rig: Rig) -> None:
    # Our own quote, signed by us, as E relays it to the buyer.
    quote = from_escrow(
        rig.escrow, rig.escrow.did, "finance.quote", {}, sender=rig.messaging.key
    )
    for inbound in (
        from_escrow(rig.escrow, rig.did, "finance.terms_countersigned", {}),
        from_escrow(rig.escrow, rig.did, "finance.payout_confirmed", {}),
        from_escrow(rig.escrow, rig.did, "finance.receipt", {}),
        relay(rig.escrow, rig.did, quote, state="QUOTED"),
    ):
        assert rig.core.handle_message(inbound) == PROCESSED
    assert rig.messaging.sent == []


def test_unsupported_types_and_bad_signatures_are_rejected(rig: Rig) -> None:
    payment = from_escrow(rig.escrow, rig.did, "finance.payment_request", {})
    assert rig.core.handle_message(payment) == rejected("unsupported_type")

    tampered = terms_proposed(rig.escrow, rig.did)
    tampered["body"]["terms"]["price_minor"] = 1
    assert rig.core.handle_message(tampered) == rejected("bad_signature")
    assert rig.messaging.sent == []
