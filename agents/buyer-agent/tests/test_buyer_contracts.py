# pyright: basic
"""What the buyer sends, and what its tests feed it, match the frozen schemas."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
from buyer_fakes import (
    FakeModules,
    offer,
    payment_request,
    quote,
    relay,
    rig,
    seller,
    terms_proposed,
)

CONTRACTS = Path(__file__).resolve().parents[3] / "contracts" / "messages"

pytestmark = pytest.mark.skipif(
    not CONTRACTS.is_dir(), reason="the repository's message contracts are absent"
)


def assert_valid(envelope: dict) -> None:
    name = f"{envelope['type_key']}.v{envelope['type_version']}.json"
    schema = json.loads((CONTRACTS / name).read_text(encoding="utf-8"))
    jsonschema.validate(envelope["body"], schema)


def test_the_messages_the_buyer_sends_match_their_schemas() -> None:
    test = rig(FakeModules(sellers=[seller()], offers={"seller-co": [offer()]}))

    test.buyer.start_purchase()
    test.buyer.handle_message(terms_proposed())

    request, accept = test.messaging.sent
    assert request["type_key"] == "finance.service_request"
    assert accept["type_key"] == "finance.accept_terms"
    assert_valid(request)
    assert_valid(accept)


@pytest.mark.parametrize(
    "build", [terms_proposed, payment_request, quote, lambda: relay(quote())]
)
def test_the_inbound_messages_of_the_tests_match_their_schemas(build) -> None:
    assert_valid(build())
