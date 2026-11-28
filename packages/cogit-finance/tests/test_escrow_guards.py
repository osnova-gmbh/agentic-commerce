"""Guards of E, each on a fresh in-memory world: a refusal leaves no trace."""

from __future__ import annotations

import copy
from typing import Any

import pytest
from escrow_checks import frozen, refused
from escrow_data import FILES, HAPPY_DEAL
from escrow_world import World

Row = dict[str, Any]
DEAL = HAPPY_DEAL


def test_a_message_illegal_in_the_state_changes_nothing() -> None:
    world = World()
    world.open_deal(DEAL)  # FUNDED
    before = frozen(world)
    proposed = world.inbox(world.buyer, DEAL, "terms_proposed")[-1]["body"]
    again = world.send(
        world.buyer, "accept_terms", DEAL, {"terms_hash": proposed["terms_hash"]}
    )
    refused(world, again, "illegal_in_state", before)
    refused(world, world.request(DEAL), "illegal_in_state", before)
    late_quote = world.send(world.seller, "quote", DEAL, world.quote_body())
    refused(world, late_quote, "illegal_in_state", before)
    assert world.state(DEAL) == "FUNDED"


def test_a_duplicate_message_yields_one_event_and_the_same_answer() -> None:
    world = World()
    body = {
        "seller_org_id": "seller-co",
        "offer_id": "offer-1",
        "inputs": {"topic": "demo"},
        "max_price_minor": 60000,
        "currency": "EUR",
    }
    envelope = world.envelope(world.buyer, "service_request", DEAL, body)
    first = world.handle(envelope)
    after_first = frozen(world)
    assert world.handle(copy.deepcopy(envelope)) == first
    assert first == {"status": "processed", "reason": None}
    assert frozen(world) == after_first
    assert world.event_types(DEAL) == ["service_request"]
    assert len(world.inbox(world.seller, DEAL, "relay")) == 1


def test_a_duplicate_of_the_deciding_verdict_pays_once() -> None:
    world = World()
    world.open_deal(DEAL)
    world.deliver(DEAL)
    requests = world.requests(DEAL, 1)
    for request in requests[:2]:
        world.judge(request)
    last = world.envelope(
        world.evaluator,
        "verdict",
        DEAL,
        world.verdict_body(requests[2]),
        requests[2]["message_id"],
    )
    assert world.handle(last)["status"] == "processed"
    settled = frozen(world)
    assert world.state(DEAL) == "SETTLED"
    assert world.handle(last) == {"status": "processed", "reason": None}
    assert frozen(world) == settled
    assert world.event_types(DEAL).count("verdict") == 3


def test_a_stale_verdict_is_rejected_and_leaves_no_event() -> None:
    world = World()
    world.open_deal(DEAL)
    world.deliver(DEAL, 1, FILES[:2])
    first = world.requests(DEAL, 1)
    assert world.judge(first[1])["status"] == "processed"  # required-files fails
    assert world.state(DEAL) == "REJECTED"
    before = frozen(world)
    # after the decision
    refused(world, world.judge(first[0]), "stale_verdict", before)
    # for a superseded delivery, while the next one is being evaluated
    world.deliver(DEAL, 2)
    assert world.state(DEAL) == "EVALUATING"
    during = frozen(world)
    refused(world, world.judge(first[2]), "stale_verdict", during)
    # after the deal is settled
    world.evaluate(DEAL, 2)
    assert world.state(DEAL) == "SETTLED"
    refused(world, world.judge(first[0]), "stale_verdict", frozen(world))
    assert world.event_types(DEAL).count("verdict") == 4


@pytest.mark.parametrize("party", ["seller-co", "buyer-co"])
def test_an_evaluator_from_a_partys_company_is_refused(party: str) -> None:
    world = World()
    world.modules.evaluators[2] = world.evaluator_row("deadline", org_id=party)
    world.request(DEAL)
    before = frozen(world)
    refused(world, world.quote(DEAL), "evaluator_not_independent", before)
    assert world.state(DEAL) == "REQUESTED"


def test_an_evaluator_whose_agent_belongs_to_a_party_is_refused() -> None:
    world = World()
    world.modules.identities[world.evaluator.did]["org_id"] = "buyer-co"
    world.request(DEAL)
    refused(world, world.quote(DEAL), "evaluator_not_independent", frozen(world))


def test_an_unregistered_evaluator_is_refused() -> None:
    world = World()
    world.request(DEAL)
    body = world.quote_body()
    body["acceptance"]["evaluators"][0]["evaluator_id"] = "taste"
    refused(world, world.quote(DEAL, body), "unknown_evaluator", frozen(world))


def test_a_bad_signature_is_rejected() -> None:
    world = World()
    body = {
        "seller_org_id": "seller-co",
        "offer_id": "offer-1",
        "inputs": {},
        "max_price_minor": 60000,
        "currency": "EUR",
    }
    before = frozen(world)
    forged = world.envelope(world.buyer, "service_request", DEAL, body)
    forged["body"]["max_price_minor"] = 1
    refused(world, world.handle(forged), "bad_signature", before)
    # signed by someone else in the buyer's name
    stolen = world.envelope(world.seller, "service_request", DEAL, body)
    stolen["sender_did"] = world.buyer.did
    refused(world, world.handle(stolen), "bad_signature", before)
    refused(
        world, world.handle({"type_key": "finance.quote"}), "invalid_envelope", before
    )
    assert world.read(DEAL)["deal"] is None


def test_request_guards() -> None:
    world = World()
    before = frozen(world)
    refused(world, world.request(DEAL, 49999), "max_price_below_offer", before)
    world.modules.companies["buyer-co"]["spending_limit_minor"] = 49999
    refused(world, world.request(DEAL), "over_spending_limit", before)
    world.modules.companies["buyer-co"]["roles"] = []
    refused(world, world.request(DEAL), "buyer_not_registered", before)
    as_seller = {
        "seller_org_id": "seller-co",
        "offer_id": "offer-9",
        "inputs": {},
        "max_price_minor": 60000,
        "currency": "EUR",
    }
    sent = world.send(world.seller, "service_request", DEAL, as_seller)
    refused(world, sent, "unexpected_sender", before)
    refused(world, world.request("deal-1"), "invalid_deal_id", before)


def test_malformed_and_unknown_messages_are_rejected_with_a_reason() -> None:
    world = World()
    world.request(DEAL)
    before = frozen(world)
    for name in ("decline", "cancel", "dispute", "ruling"):
        refused(world, world.send(world.buyer, name, DEAL, {}), "invalid_body", before)
    own = world.send(world.buyer, "receipt", DEAL, {})
    refused(world, own, "unexpected_type", before)
    refused(world, world.send(world.buyer, "hello", DEAL, {}), "unknown_type", before)
    bad = world.send(world.seller, "quote", DEAL, {"price_minor": 1})
    refused(world, bad, "invalid_body", before)


def test_terms_are_accepted_by_hash_once_per_party() -> None:
    world = World()
    world.request(DEAL)
    world.quote(DEAL)
    before = frozen(world)
    wrong = world.send(world.buyer, "accept_terms", DEAL, {"terms_hash": "0" * 64})
    refused(world, wrong, "terms_hash_mismatch", before)
    proposed = world.inbox(world.buyer, DEAL, "terms_proposed")[-1]["body"]
    body = {"terms_hash": proposed["terms_hash"]}
    outsider = world.send(world.evaluator, "accept_terms", DEAL, body)
    refused(world, outsider, "unexpected_sender", before)
    assert world.accept(world.buyer, DEAL)["status"] == "processed"
    once = frozen(world)
    refused(
        world,
        world.send(world.buyer, "accept_terms", DEAL, body),
        "already_accepted",
        once,
    )
    assert world.state(DEAL) == "QUOTED"


def test_delivery_guards() -> None:
    world = World()
    world.open_deal(DEAL)
    before = frozen(world)
    artifact = world.artifacts.put(b"zip", "application/zip")
    cases = [
        (world.buyer, 1, artifact, "unexpected_sender"),
        (world.seller, 2, artifact, "unexpected_attempt"),
        (
            world.seller,
            1,
            {**artifact, "artifact_id": "art_missing"},
            "artifact_not_found",
        ),
        (world.seller, 1, {**artifact, "byte_length": 4}, "artifact_mismatch"),
        (world.seller, 1, {**artifact, "sha256": "0" * 64}, "artifact_mismatch"),
    ]
    for key, attempt, ref, reason in cases:
        sent = world.send(key, "delivery", DEAL, {"attempt": attempt, "artifact": ref})
        refused(world, sent, reason, before)


def test_no_third_attempt_when_max_attempts_is_two() -> None:
    world = World()
    world.open_deal(DEAL)
    for attempt in (1, 2):
        world.deliver(DEAL, attempt, FILES[:2])
        world.evaluate(DEAL, attempt)
    assert world.state(DEAL) == "REJECTED"
    decision = world.inbox(world.seller, DEAL, "decision")[-1]["body"]
    assert (decision["attempts_left"], decision["rework_deadline"]) == (0, None)
    refused(world, world.deliver(DEAL, 3), "no_attempts_left", frozen(world))


def test_verdict_correlation() -> None:
    world = World()
    world.open_deal(DEAL)
    world.deliver(DEAL)
    request = world.requests(DEAL, 1)[0]
    before = frozen(world)

    def answer(key: Any = None, **changes: Any) -> Row:
        body = {**world.verdict_body(request), **changes}
        return world.send(key or world.evaluator, "verdict", DEAL, body)

    refused(world, answer(world.seller), "unexpected_sender", before)
    refused(world, answer(terms_hash="0" * 64), "terms_hash_mismatch", before)
    refused(world, answer(artifact_sha256="0" * 64), "artifact_sha256_mismatch", before)
    refused(world, answer(evaluator_id="deadline"), "evaluator_mismatch", before)
    unknown = answer(evaluation_request_id=f"{DEAL}:d1:taste@1")
    refused(world, unknown, "unknown_evaluation_request", before)
    # Error recovery is covered by test_escrow_lifecycle.

    assert answer()["status"] == "processed"
    recorded = frozen(world)
    # the same judgement in a new message is a no-op; a different one conflicts
    assert answer() == {"status": "processed", "reason": None}
    assert frozen(world) == recorded
    refused(
        world, answer(outcome="fail", reasons=["no"]), "conflicting_verdict", recorded
    )
    assert world.event_types(DEAL).count("verdict") == 1


def test_a_recorded_message_id_with_other_content_is_refused() -> None:
    world = World()
    world.open_deal(DEAL)
    cause = world.inbox(world.seller, DEAL, "funding_confirmed")[-1]["message_id"]
    world.deliver(DEAL, 1, FILES[:2])
    world.evaluate(DEAL, 1)
    assert world.state(DEAL) == "REJECTED"
    # a redelivery that answers the same message gets the ID of attempt 1
    artifact = world.artifacts.put(b"second", "application/zip")
    body = {"attempt": 2, "artifact": artifact}
    reused = world.send(world.seller, "delivery", DEAL, body, cause)
    refused(world, reused, "message_id_reused", frozen(world))


def test_a_message_for_someone_else_is_refused() -> None:
    world = World()
    envelope = world.envelope(
        world.buyer, "accept_terms", DEAL, {"terms_hash": "0" * 64}
    )
    envelope["recipient_did"] = world.seller.did
    assert world.handle(envelope)["reason"] == "bad_signature"
    other = World()
    mine = other.envelope(other.buyer, "accept_terms", DEAL, {"terms_hash": "0" * 64})
    assert world.handle(mine) == {"status": "rejected", "reason": "wrong_recipient"}
