# pyright: basic
"""The buyer's answers to E's messages (SPEC §8), on fake ports."""

from __future__ import annotations

import copy

import pytest
from buyer_fakes import (
    BUYER_IBAN,
    BUYER_KEY,
    DEAL_ID,
    ESCROW_IBAN,
    ESCROW_KEY,
    SELLER_KEY,
    payment_request,
    quote,
    relay,
    rig,
    signed,
    terms,
    terms_proposed,
)
from cogit_finance_seams import BankError
from cogit_messaging_shim import canonical_hash, reply_message_id, verify_envelope

from buyer_agent.buyer_core import MessageResult

PROCESSED = MessageResult("processed")


def rejected(reason: str) -> MessageResult:
    return MessageResult("rejected", reason)


def test_acceptable_terms_are_accepted_with_their_hash() -> None:
    test = rig()
    proposal = terms_proposed()

    assert test.buyer.handle_message(proposal) == PROCESSED

    (accept,) = test.messaging.sent
    assert verify_envelope(accept)
    assert accept["sender_did"] == BUYER_KEY.did
    assert accept["type_key"] == "finance.accept_terms"
    assert accept["recipient_did"] == ESCROW_KEY.did
    assert accept["conversation_id"] == DEAL_ID
    assert accept["causation_id"] == proposal["message_id"]
    assert accept["body"] == {"terms_hash": canonical_hash(terms())}
    assert test.bank.calls == []


def test_the_same_terms_twice_give_the_same_reply() -> None:
    test = rig()
    proposal = terms_proposed()

    assert test.buyer.handle_message(proposal) == PROCESSED
    assert test.buyer.handle_message(proposal) == PROCESSED

    first, second = test.messaging.sent
    assert first["message_id"] == second["message_id"]
    assert first["message_id"] == reply_message_id(
        proposal["message_id"], "finance.accept_terms", ESCROW_KEY.did
    )


def test_terms_at_the_maximum_price_are_accepted() -> None:
    test = rig(max_price_minor=50000)

    assert test.buyer.handle_message(terms_proposed()) == PROCESSED
    assert len(test.messaging.sent) == 1


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"price_minor": 60001}, "price_above_maximum"),
        ({"currency": "USD"}, "unsupported_currency"),
        ({"buyer_org_id": "other-co"}, "wrong_buyer_org"),
        (
            {"acceptance": {"evaluators": [], "policy": "all", "max_attempts": 2}},
            "no_evaluator",
        ),
        ({"deal_id": "3d2a5f0e-1b7c-4e7a-8a55-6c9d2b1e0f42"}, "deal_id_mismatch"),
    ],
)
def test_unacceptable_terms_are_refused(changes: dict, reason: str) -> None:
    test = rig()

    result = test.buyer.handle_message(terms_proposed(terms(**changes)))

    assert result == rejected(reason)
    assert test.messaging.sent == []


def test_terms_that_do_not_match_their_hash_are_refused() -> None:
    test = rig()
    body = {"terms": terms(), "terms_hash": canonical_hash(terms(price_minor=1))}

    result = test.buyer.handle_message(signed("finance.terms_proposed", body))

    assert result == rejected("terms_hash_mismatch")
    assert test.messaging.sent == []


def test_a_payment_request_is_paid_exactly_as_asked() -> None:
    test = rig()

    assert test.buyer.handle_message(payment_request()) == PROCESSED

    assert test.bank.calls == [
        {
            "from_iban": BUYER_IBAN,
            "to_iban": ESCROW_IBAN,
            "amount_minor": 50000,
            "currency": "EUR",
            "reference": f"ESCROW-{DEAL_ID}",
            "idempotency_key": f"pay:{DEAL_ID}",
        }
    ]
    assert test.messaging.sent == []


def test_the_same_payment_request_twice_is_one_payment() -> None:
    test = rig()
    request = payment_request()

    assert test.buyer.handle_message(request) == PROCESSED
    assert test.buyer.handle_message(request) == PROCESSED

    assert [call["idempotency_key"] for call in test.bank.calls] == [
        f"pay:{DEAL_ID}",
        f"pay:{DEAL_ID}",
    ]
    assert test.bank.calls[0] == test.bank.calls[1]
    assert list(test.bank.booked) == [f"pay:{DEAL_ID}"]


def test_a_bank_error_is_raised_so_the_message_is_retried() -> None:
    test = rig()
    request = payment_request()
    test.bank.error = BankError(409, "insufficient_funds")

    with pytest.raises(BankError):
        test.buyer.handle_message(request)
    assert test.bank.booked == {}

    test.bank.error = None
    assert test.buyer.handle_message(request) == PROCESSED
    assert list(test.bank.booked) == [f"pay:{DEAL_ID}"]


def test_a_payment_above_the_maximum_price_is_refused() -> None:
    test = rig()

    result = test.buyer.handle_message(payment_request(amount_minor=60001))

    assert result == rejected("amount_above_maximum")
    assert test.bank.calls == []


@pytest.mark.parametrize("build", [payment_request, terms_proposed])
def test_a_message_that_is_not_from_the_escrow_is_refused(build) -> None:
    test = rig()

    result = test.buyer.handle_message(build(key=SELLER_KEY))

    assert result == rejected("unexpected_sender")
    assert test.bank.calls == []
    assert test.messaging.sent == []


def test_a_message_with_a_broken_signature_is_refused() -> None:
    test = rig()
    request = payment_request()
    request["body"]["amount_minor"] = 1

    assert test.buyer.handle_message(request) == rejected("bad_signature")
    assert test.bank.calls == []


def test_a_relayed_quote_or_delivery_is_noted_without_action() -> None:
    test = rig()
    artifact = {
        "artifact_id": "art_1",
        "sha256": "0" * 64,
        "byte_length": 1,
        "media_type": "application/zip",
    }
    delivery = signed(
        "finance.delivery",
        {"attempt": 1, "artifact": artifact},
        key=SELLER_KEY,
        recipient_did=ESCROW_KEY.did,
    )

    assert test.buyer.handle_message(relay(quote())) == PROCESSED
    assert test.buyer.handle_message(relay(delivery, 9, "DELIVERED")) == PROCESSED
    assert test.messaging.sent == []
    assert test.bank.calls == []


def test_a_relay_with_a_broken_inner_signature_is_refused() -> None:
    test = rig()
    tampered = copy.deepcopy(quote())
    tampered["body"]["price_minor"] = 1

    result = test.buyer.handle_message(relay(tampered))

    assert result == rejected("bad_relayed_signature")


def test_a_relay_of_a_type_the_buyer_does_not_expect_is_refused() -> None:
    test = rig()
    request = signed(
        "finance.service_request",
        {"seller_org_id": "seller-co", "offer_id": "offer-1"},
        key=BUYER_KEY,
        recipient_did=ESCROW_KEY.did,
    )

    result = test.buyer.handle_message(relay(request, 1, "REQUESTED"))

    assert result == rejected("unsupported_type")


@pytest.mark.parametrize(
    "type_key",
    [
        "finance.terms_countersigned",
        "finance.funding_confirmed",
        "finance.decision",
        "finance.payout_confirmed",
        "finance.receipt",
    ],
)
def test_notifications_are_processed_without_action(type_key: str) -> None:
    test = rig()
    # A rejecting decision too: the buyer never disputes.
    body = {"outcome": "reject", "attempts_left": 1}

    assert test.buyer.handle_message(signed(type_key, body)) == PROCESSED
    assert test.messaging.sent == []
    assert test.bank.calls == []


@pytest.mark.parametrize("type_key", ["finance.quote", "finance.verdict", "x.other"])
def test_an_unknown_type_is_refused(type_key: str) -> None:
    test = rig()

    result = test.buyer.handle_message(signed(type_key, {}))

    assert result == rejected("unsupported_type")
    assert test.messaging.sent == []


def test_the_escrow_is_resolved_from_the_identity_registry() -> None:
    test = rig(escrow_did=None)
    test.modules.escrow_did = ESCROW_KEY.did

    assert test.buyer.handle_message(terms_proposed()) == PROCESSED
    assert test.messaging.sent[0]["recipient_did"] == ESCROW_KEY.did
