"""Gate G2: the happy path and the broken run, replayed in memory.

Buyer, seller and evaluator are played with their own keys; E runs on fakes of
the modules and the bank. Both deals live in one world, so the dumped fixtures
show them side by side. Set ``ESCROW_WRITE_FIXTURES=1`` to rewrite the files in
``tests/fixtures/escrow`` from this run.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest
from escrow_checks import (
    assert_chain,
    assert_envelopes,
    assert_sequence,
    load_sequence,
)
from escrow_data import (
    BROKEN_DEAL,
    BUYER_IBAN,
    ESCROW_IBAN,
    FEE_IBAN,
    HAPPY_DEAL,
    SELLER_IBAN,
)
from escrow_world import World

Row = dict[str, Any]
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "escrow"
DEALS = {"happy-path": HAPPY_DEAL, "broken-run": BROKEN_DEAL}
SETTLED_BALANCES = {
    "held": 0,
    "seller": 49500,
    "fee": 500,
    "buyer_refund": 0,
    "returned": 0,
}


@pytest.fixture(scope="module")
def world() -> World:
    world = World()
    world.happy_path()
    world.first_verdicts = world.broken_run()  # type: ignore[attr-defined]
    return world


def query(world: World, export: str, args: Row | None = None) -> Row:
    return world.modules.module_query("cogit-finance-deals", export, args or {})


def snapshot(world: World) -> dict[str, Row]:
    """Both runs the way the dashboard reads them: file name -> query result."""
    files = {
        "deal.list.json": query(world, "deal.list"),
        "ledger.balances.json": query(world, "ledger.balances"),
        "bank.accounts.json": {"accounts": world.bank.accounts()},
    }
    for name, deal_id in DEALS.items():
        files[f"deal.read.{name}.json"] = world.read(deal_id)
        files[f"ledger.balances.{name}.json"] = query(
            world, "ledger.balances", {"deal_id": deal_id}
        )
    return files


def test_happy_path_is_the_spec_event_sequence(world: World) -> None:
    deal = world.read(HAPPY_DEAL)
    assert_sequence(deal, load_sequence("happy-path.events.json"))
    assert len(deal["events"]) == 17
    assert deal["deal"]["state"] == "SETTLED"
    assert_chain(deal)
    assert_envelopes(deal)
    assert [row["status"] for row in deal["deliveries"]] == ["approved"]
    assert [row["outcome"] for row in deal["evaluations"]] == ["pass"] * 3


def test_broken_run_is_rejected_redelivered_and_settled(world: World) -> None:
    deal = world.read(BROKEN_DEAL)
    assert_sequence(deal, load_sequence("broken-run.events.json"))
    assert deal["deal"]["state"] == "SETTLED"
    assert_chain(deal)
    assert_envelopes(deal)
    # Attempt 1: integrity passes, required-files fails and decides, and the
    # deadline verdict arrives after the decision.
    assert world.first_verdicts == [  # type: ignore[attr-defined]
        {"status": "processed", "reason": None},
        {"status": "processed", "reason": None},
        {"status": "rejected", "reason": "stale_verdict"},
    ]
    assert [row["status"] for row in deal["deliveries"]] == ["rejected", "approved"]
    outcomes = {
        row["evaluation_request_id"].split(":", 1)[1]: row["outcome"]
        for row in deal["evaluations"]
    }
    assert outcomes == {
        "d1:integrity@1": "pass",
        "d1:required-files@1": "fail",
        "d1:deadline@1": None,
        "d2:integrity@1": "pass",
        "d2:required-files@1": "pass",
        "d2:deadline@1": "pass",
    }
    reject, approve = (
        event["body"] for event in deal["events"] if event["event_type"] == "decision"
    )
    assert reject["outcome"] == "reject" and reject["attempts_left"] == 1
    assert reject["reasons"] == ["required-files@1: missing file: summary.json"]
    assert reject["rework_deadline"] == deal["deal"]["terms"]["delivery_deadline"]
    assert approve == {
        "decided_at": "2026-11-27T10:00:21Z",
        "delivery_id": f"{BROKEN_DEAL}:d2",
        "outcome": "approve",
        "attempts_left": 0,
        "rework_deadline": None,
        "reasons": [],
    }


@pytest.mark.parametrize("deal_id", [HAPPY_DEAL, BROKEN_DEAL])
def test_money_moves_once_and_the_ledger_balances(world: World, deal_id: str) -> None:
    transfers = world.bank.transfers
    assert transfers[f"pay:{deal_id}"]["amount_minor"] == 50000
    payout, fee = transfers[f"{deal_id}:payout"], transfers[f"{deal_id}:fee"]
    assert (payout["from_iban"], payout["to_iban"]) == (ESCROW_IBAN, SELLER_IBAN)
    assert (fee["from_iban"], fee["to_iban"]) == (ESCROW_IBAN, FEE_IBAN)
    assert (payout["amount_minor"], fee["amount_minor"]) == (49500, 500)
    assert query(world, "ledger.balances", {"deal_id": deal_id}) == SETTLED_BALANCES

    deal = world.read(deal_id)
    intents = {row["kind"]: row for row in deal["intents"]}
    assert {kind: row["status"] for kind, row in intents.items()} == {
        "payout": "confirmed",
        "fee": "confirmed",
    }
    assert intents["payout"]["bank_ref"] == payout["transfer_id"]
    assert [row["disposition"] for row in deal["credits"]] == ["funded"]
    postings = sorted(
        (row["source_id"], row["account"], row["amount_minor"])
        for row in world.modules.postings.values()
        if row["deal_id"] == deal_id
    )
    credit = deal["credits"][0]["bank_event_id"]
    assert postings == sorted(
        [
            (credit, "held", 50000),
            (f"{deal_id}:payout", "held", -49500),
            (f"{deal_id}:payout", "seller", 49500),
            (f"{deal_id}:fee", "held", -500),
            (f"{deal_id}:fee", "fee", 500),
        ]
    )
    receipt = deal["events"][-1]["body"]
    confirmed = deal["events"][-2]
    assert receipt == {
        "outcome": "settled",
        "price_minor": 50000,
        "fee_minor": 500,
        "payout_minor": 49500,
        "currency": "EUR",
        "terms_hash": deal["deal"]["terms_hash"],
        "head_seq": confirmed["seq"],
        "head_hash": confirmed["hash"],
    }


def test_bank_accounts_after_both_deals(world: World) -> None:
    assert world.bank.balances == {
        ESCROW_IBAN: 0,
        FEE_IBAN: 1000,
        BUYER_IBAN: 900000,
        SELLER_IBAN: 99000,
    }
    assert len(world.bank.transfers) == 6  # per deal: funding, payout, fee


def test_every_notification_went_out_once_and_is_linked(world: World) -> None:
    assert all(row["status"] == "sent" for row in world.modules.outbox.values())
    assert set(world.modules.outbox) == set(world.modules.messages)
    for envelope in world.modules.messages.values():
        assert envelope["sender_did"] == world.escrow.did
        assert envelope["causation_id"] is not None
    sent = [
        envelope["type_key"].removeprefix("finance.")
        for envelope in world.inbox(world.buyer, HAPPY_DEAL)
    ]
    assert sent == [
        "relay",  # the quote
        "terms_proposed",
        "terms_countersigned",
        "payment_request",
        "funding_confirmed",
        "relay",  # the delivery
        "decision",
        "payout_confirmed",
        "receipt",
    ]
    keys = {key for _, export, key in world.modules.commands if export == "deal.commit"}
    quote = world.read(HAPPY_DEAL)["events"][1]["source_message_id"]
    assert f"evt:{quote}" in keys
    assert f"own:{HAPPY_DEAL}:3:terms_proposed" in keys


def test_fixture_files_show_both_runs(world: World) -> None:
    """The committed dashboard fixtures have the shape and content of this run."""
    files = snapshot(world)
    if os.environ.get("ESCROW_WRITE_FIXTURES") == "1":
        FIXTURES.mkdir(parents=True, exist_ok=True)
        for name, content in files.items():
            text = json.dumps(content, indent=2, sort_keys=True, ensure_ascii=False)
            (FIXTURES / name).write_text(text + "\n", encoding="utf-8")
    assert sorted(path.name for path in FIXTURES.glob("*.json")) == sorted(files)
    stored = {name: json.loads((FIXTURES / name).read_text("utf-8")) for name in files}
    for name in DEALS:
        deal = stored[f"deal.read.{name}.json"]
        assert_sequence(deal, load_sequence(f"{name}.events.json"))
        assert_chain(deal)
        assert_envelopes(deal)
        assert set(deal) == set(files[f"deal.read.{name}.json"])
        assert stored[f"ledger.balances.{name}.json"] == SETTLED_BALANCES
    listed = stored["deal.list.json"]["deals"]
    assert [row["deal_id"] for row in listed] == [BROKEN_DEAL, HAPPY_DEAL]
    assert {row["state"] for row in listed} == {"SETTLED"}
    assert set(listed[0]) == set(files["deal.list.json"]["deals"][0])
    assert stored["ledger.balances.json"] == {
        **SETTLED_BALANCES,
        "seller": 99000,
        "fee": 1000,
    }
    assert stored["bank.accounts.json"] == files["bank.accounts.json"]
