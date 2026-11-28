"""E's pure domain: the transition table, fees, policy, IDs, terms, schemas."""

from __future__ import annotations

import json

import pytest
from escrow_checks import REPO

from cogit_finance.escrow import ids, money, policy, settings, terms
from cogit_finance.escrow import transitions as t
from cogit_finance.escrow.schema_check import validate


@pytest.mark.parametrize(
    ("price", "bps", "fee"),
    [
        (50000, 100, 500),
        (49, 100, 0),  # 0.49 cent rounds down
        (50, 100, 1),  # 0.5 cent rounds half up
        (149, 100, 1),
        (150, 100, 2),
        (1, 5000, 1),
        (33333, 250, 833),  # 833.325
        (0, 100, 0),
        (50000, 0, 0),
        (50000, 10000, 50000),
    ],
)
def test_fee_rounds_half_up_to_the_cent(price: int, bps: int, fee: int) -> None:
    assert money.fee_minor(price, bps) == fee
    assert money.split(price, bps) == (price - fee, fee)


def test_fee_takes_integers_only() -> None:
    with pytest.raises(TypeError):
        money.fee_minor(500.0, 100)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        money.fee_minor(True, 100)
    with pytest.raises(ValueError, match="fee_bps"):
        money.fee_minor(100, 10001)


def test_the_table_holds_every_spec_row() -> None:
    assert {row.row for row in t.TRANSITIONS} == set(range(1, 24))
    assert {row.source for row in t.TRANSITIONS} <= {t.NONE, *t.STATES}
    assert {row.target for row in t.TRANSITIONS} <= set(t.STATES)
    demo = [row for row in t.TRANSITIONS if row.in_demo]
    assert {row.target for row in demo} == set(t.DEMO_STATES)
    assert t.MESSAGE_TRIGGERS == t.DEMO_MESSAGE_TRIGGERS


def test_the_happy_path_is_a_walk_through_the_table() -> None:
    walk = [
        ("service_request", t.REQUESTED),
        ("quote", t.QUOTED),
        ("terms_proposed", t.QUOTED),
        ("accept_terms", t.QUOTED),
        ("accept_terms", t.QUOTED),
        ("terms_countersigned", t.ACCEPTED),
        ("payment_request", t.FUNDING_REQUESTED),
        ("funding_received", t.FUNDED),
        ("delivery", t.DELIVERED),
        ("evaluation_requested", t.EVALUATING),
        ("verdict", t.EVALUATING),
        ("decision", t.REJECTED),
        ("delivery", t.DELIVERED),
        ("evaluation_requested", t.EVALUATING),
        ("decision", t.APPROVED),
        ("payout_submitted", t.RELEASING),
        ("payout_confirmed", t.SETTLED),
        ("receipt", t.SETTLED),
    ]
    state = t.NONE
    for trigger, target in walk:
        assert t.is_legal(state, trigger, target), (state, trigger, target)
        state = target


@pytest.mark.parametrize(
    ("state", "trigger", "reason"),
    [
        (t.NONE, "service_request", None),
        (t.REQUESTED, "service_request", t.ILLEGAL_IN_STATE),
        (t.FUNDED, "quote", t.ILLEGAL_IN_STATE),
        (t.SETTLED, "delivery", t.ILLEGAL_IN_STATE),
        (t.REJECTED, "delivery", None),
        (t.REQUESTED, "decline", None),
        (t.FUNDED, "cancel", t.ILLEGAL_IN_STATE),
        (t.REJECTED, "dispute", None),
        (t.DISPUTED, "ruling", None),
    ],
)
def test_a_message_is_allowed_only_where_the_table_says(
    state: str, trigger: str, reason: str | None
) -> None:
    assert t.refuse_message(state, trigger) == reason


def test_required_recovery_transitions_are_legal() -> None:
    assert t.is_legal(t.REJECTED, "dispute", t.DISPUTED)
    assert t.is_legal(t.FUNDED, "delivery_deadline", t.REFUNDING)
    assert t.is_legal(t.REFUNDED, "receipt", t.REFUNDED)
    assert not t.is_legal(t.APPROVED, "dispute", t.DISPUTED)
    assert not t.is_legal(t.RELEASING, "ruling", t.REFUNDING)


def test_policy_decides_as_soon_as_the_outcome_is_certain() -> None:
    assert policy.decide("all", [None, None, None]) is None
    assert policy.decide("all", ["pass", "pass", None]) is None
    assert policy.decide("all", ["pass", "fail", None]) == "reject"
    assert policy.decide("all", ["pass", "pass", "pass"]) == "approve"
    assert policy.decide("any", ["fail", None]) is None
    assert policy.decide("any", ["fail", "pass"]) == "approve"
    assert policy.decide("any", ["fail", "fail"]) == "reject"
    assert policy.decide("all", ["pass", "error"]) is None  # an error does not count
    with pytest.raises(ValueError, match="quorum"):
        policy.decide("quorum", ["pass"])


def test_identifiers_follow_the_build_guide() -> None:
    deal = "11111111-1111-4111-8111-111111111111"
    delivery = ids.delivery_id(deal, 2)
    assert delivery == f"{deal}:d2"
    assert ids.evaluation_request_id(delivery, "integrity", 1) == (
        f"{deal}:d2:integrity@1"
    )
    assert ids.payment_reference(deal) == f"ESCROW-{deal}"
    assert ids.deal_id_from_reference(f"ESCROW-{deal}") == deal
    assert ids.deal_id_from_reference("ESCROW-not-a-deal") is None
    assert ids.deal_id_from_reference(f"PAYOUT-{deal}") is None
    assert ids.intent_id(deal, "payout") == f"{deal}:payout"
    first = ids.own_message_id(deal, 3, "finance.terms_proposed", "did:key:zA", 0)
    assert first == ids.own_message_id(
        deal, 3, "finance.terms_proposed", "did:key:zA", 0
    )
    assert first != ids.own_message_id(
        deal, 3, "finance.terms_proposed", "did:key:zA", 1
    )
    assert ids.is_uuid(first) and not ids.is_uuid("deal-1")


def test_terms_freeze_the_quote_the_offer_and_the_operator_timers() -> None:
    config = settings.load_operator_config(settings.PACKAGED_OPERATOR_CONFIG)
    quote = {
        "price_minor": 50000,
        "currency": "EUR",
        "delivery_deadline": "2026-11-27T10:01:00Z",
        "valid_until": "2026-11-27T10:10:00Z",
        "acceptance": {
            "evaluators": [{"evaluator_id": "integrity", "version": 1, "params": {}}],
            "policy": "all",
            "max_attempts": 2,
        },
    }
    built = terms.build_terms(
        deal_id="11111111-1111-4111-8111-111111111111",
        buyer_org_id="buyer-co",
        seller_org_id="seller-co",
        buyer_did="did:key:zBuyer",
        seller_did="did:key:zSeller",
        escrow_did="did:key:zEscrow",
        offer={"offer_id": "offer-1", "delivery_time_s": 60},
        request={"inputs": {"topic": "demo"}},
        quote=quote,
        escrow_config=config["escrow"],
    )
    schema = settings.load_message_schemas(settings.PACKAGED_CONTRACTS_DIR)[
        ("finance.terms_proposed", 1)
    ]
    assert validate(schema["properties"]["terms"], built) is None
    assert built["fee_bps"] == 100 and built["timers"]["delivery_time_s"] == 60
    digest = terms.terms_hash(built)
    assert len(digest) == 64 and digest == terms.terms_hash(
        dict(reversed(built.items()))
    )
    assert digest != terms.terms_hash({**built, "price_minor": 50001})


def test_schema_check_covers_the_assertion_dialect() -> None:
    schema = {
        "type": "object",
        "properties": {
            "n": {"type": "integer", "minimum": 1, "maximum": 5},
            "s": {"type": ["string", "null"], "minLength": 2, "maxLength": 3},
            "e": {"type": "string", "enum": ["a", "b"]},
            "l": {"type": "array", "items": {"type": "integer"}, "maxItems": 2},
        },
        "required": ["n"],
        "additionalProperties": False,
    }
    assert validate(schema, {"n": 1, "s": None, "e": "a", "l": [1, 2]}) is None
    for bad in (
        {},
        {"n": 0},
        {"n": 6},
        {"n": True},
        {"n": 1.0},
        {"n": 1, "s": "x"},
        {"n": 1, "s": "xxxx"},
        {"n": 1, "e": "c"},
        {"n": 1, "l": [1, 2, 3]},
        {"n": 1, "l": ["1"]},
        {"n": 1, "other": 1},
        [],
    ):
        assert validate(schema, bad) is not None, bad


def test_packaged_contracts_and_config_equal_the_frozen_originals() -> None:
    schemas = settings.load_message_schemas(settings.PACKAGED_CONTRACTS_DIR)
    assert len(schemas) == 21
    assert all(
        key.startswith("finance.") and version in (1, 2) for key, version in schemas
    )
    originals = REPO / "contracts" / "messages"
    if not originals.is_dir():
        pytest.skip("not inside the monorepo")
    for path in sorted(originals.glob("finance.*.json")):
        packaged = settings.PACKAGED_CONTRACTS_DIR / path.name
        assert json.loads(packaged.read_bytes()) == json.loads(path.read_bytes())
    for name in ("operator.example.yaml", "operator.schema.json"):
        assert (settings.DATA_DIR / name).read_bytes() == (
            REPO / "config" / name
        ).read_bytes()
