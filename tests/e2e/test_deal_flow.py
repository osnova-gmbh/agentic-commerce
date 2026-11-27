"""End to end, offline: discovery to payout through the real agents, modules and bank."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from world import BUYER, REPO, SELLER, DemoWorld, chain_is_valid, sequence_matches

ESCROW_IBAN, FEE_IBAN = "DE00EXAMPLE0000000001", "DE00EXAMPLE0000000002"
BUYER_IBAN, SELLER_IBAN = "DE00EXAMPLE0000000010", "DE00EXAMPLE0000000020"
PRICE, FEE, PAYOUT = 50000, 500, 49500


def fixture(name: str) -> dict:
    return json.loads((REPO / "contracts" / "fixtures" / name).read_text(encoding="utf-8"))


@pytest.fixture
def world(tmp_path: Path, request: pytest.FixtureRequest):
    demo = DemoWorld(tmp_path, seller_mode=getattr(request, "param", "ok"))
    yield demo
    demo.close()


def start_deal(world: DemoWorld) -> str:
    assert world.tick()["types_registered"] == 14
    assert world.act(SELLER, "publish_catalog") == {"count": 2}
    purchase = world.act(BUYER, "start_purchase")
    assert purchase["status"] == "requested", purchase
    assert (purchase["seller_org_id"], purchase["offer_id"]) == ("seller-co", "offer-1")
    assert (purchase["sellers_seen"], purchase["offers_seen"]) == (1, 2)  # the discovery evidence
    return purchase["deal_id"]


def assert_settled(world: DemoWorld, deal_id: str, fixture_name: str) -> dict:
    deal = world.deal(deal_id)
    types = [event["event_type"] for event in deal["events"]]
    assert sequence_matches(deal["events"], fixture(fixture_name)), types
    assert chain_is_valid(deal["events"])
    assert deal["deal"]["state"] == "SETTLED"
    assert deal["deal"]["head_seq"] == len(deal["events"])
    # Money: the buyer paid the price; nothing stays held; the fee comes out of the payout.
    assert world.balances(deal_id) == {"held": 0, "seller": PAYOUT, "fee": FEE, "buyer_refund": 0, "returned": 0}
    assert world.accounts() == {ESCROW_IBAN: 0, FEE_IBAN: FEE, BUYER_IBAN: 1_000_000 - PRICE, SELLER_IBAN: PAYOUT}
    assert {intent["kind"]: intent["status"] for intent in deal["intents"]} == {"payout": "confirmed", "fee": "confirmed"}
    # Every message of the deal was delivered and handled; only stale verdicts may be refused.
    for message in world.conversation(deal_id):
        assert message["status"] in ("processed", "rejected"), message
        if message["status"] == "rejected":
            assert (message["type_key"], message["reason"]) == ("finance.verdict", "stale_verdict"), message
    return deal


def test_happy_path_settles_with_the_expected_events_and_balances(world: DemoWorld) -> None:
    deal_id = start_deal(world)
    assert world.run(deal_id) == "SETTLED"
    deal = assert_settled(world, deal_id, "happy-path.events.json")
    assert len(deal["events"]) == 17
    assert [(row["attempt"], row["status"]) for row in deal["deliveries"]] == [(1, "approved")]
    assert sorted(row["outcome"] for row in deal["evaluations"]) == ["pass", "pass", "pass"]


@pytest.mark.parametrize("world", ["broken"], indirect=True)
def test_broken_delivery_is_rejected_redelivered_and_settled(world: DemoWorld) -> None:
    deal_id = start_deal(world)
    assert world.run(deal_id) == "SETTLED"
    deal = assert_settled(world, deal_id, "broken-run.events.json")
    deliveries = sorted(deal["deliveries"], key=lambda row: row["attempt"])
    assert [(row["attempt"], row["status"]) for row in deliveries] == [(1, "rejected"), (2, "approved")]
    first = [row for row in deal["evaluations"] if row["delivery_id"].endswith(":d1")]
    second = [row for row in deal["evaluations"] if row["delivery_id"].endswith(":d2")]
    assert "fail" in [row["outcome"] for row in first]
    assert sorted(row["outcome"] for row in second) == ["pass", "pass", "pass"]
    decisions = [event["body"] for event in deal["events"] if event["event_type"] == "decision"]
    assert [body["outcome"] for body in decisions] == ["reject", "approve"]
    assert any("summary.json" in reason for reason in decisions[0]["reasons"])


def test_money_is_held_between_funding_and_payout(world: DemoWorld) -> None:
    deal_id = start_deal(world)
    assert world.run(deal_id, until="FUNDED") == "FUNDED"
    assert world.balances(deal_id)["held"] == PRICE
    assert world.accounts()[ESCROW_IBAN] == PRICE
    assert world.accounts()[SELLER_IBAN] == 0
    assert world.run(deal_id) == "SETTLED"


def test_empty_catalog_gives_no_offer_and_no_deal(world: DemoWorld) -> None:
    world.tick()
    purchase = world.act(BUYER, "start_purchase")
    assert purchase["status"] == "no_offer" and purchase["deal_id"] is None
    assert world.reader.module_query("cogit-finance-deals", "deal.list", {}) == {"deals": []}
