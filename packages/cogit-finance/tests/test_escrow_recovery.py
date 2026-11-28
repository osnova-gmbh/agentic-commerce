"""Re-entrancy of E and its tick: interrupted runs, the outbox, bank credits."""

from __future__ import annotations

from typing import Any

import pytest
from cogit_finance_seams import ModuleError
from escrow_data import HAPPY_DEAL
from escrow_world import World

Row = dict[str, Any]
DEAL = HAPPY_DEAL


def test_an_interrupted_run_is_continued_by_the_same_message() -> None:
    world = World()
    world.request(DEAL)
    relayed = world.inbox(world.seller, DEAL, "relay")[-1]["body"]["relayed"]
    quote = world.envelope(
        world.seller, "quote", DEAL, world.quote_body(), relayed["message_id"]
    )
    # the quote is committed, the terms_proposed commit after it fails
    world.modules.fail_once("deal.commit", ModuleError("unavailable"), skip=1)
    with pytest.raises(ModuleError):
        world.handle(quote)
    assert world.event_types(DEAL) == ["service_request", "quote"]
    assert world.handle(quote) == {"status": "processed", "reason": None}
    assert world.event_types(DEAL) == ["service_request", "quote", "terms_proposed"]
    assert len(world.inbox(world.buyer, DEAL, "terms_proposed")) == 1


def test_a_payout_interrupted_after_the_bank_booked_is_finished_by_tick() -> None:
    world = World()
    world.open_deal(DEAL)
    world.deliver(DEAL)
    requests = world.requests(DEAL, 1)
    for request in requests[:2]:
        world.judge(request)
    # prepared -> submitted works, the confirmation after the transfer fails
    world.modules.fail_once("intent.update", ModuleError("unavailable"), skip=1)
    with pytest.raises(ModuleError):
        world.judge(requests[2])
    assert world.state(DEAL) == "RELEASING"
    assert f"{DEAL}:payout" in world.bank.transfers
    world.run_tick()
    assert world.state(DEAL) == "SETTLED"
    assert world.event_types(DEAL)[-3:] == [
        "payout_submitted",
        "payout_confirmed",
        "receipt",
    ]
    assert len(world.bank.transfers) == 3  # funding, one payout, one fee
    assert world.bank.balances["DE00EXAMPLE0000000020"] == 49500
    balances = world.modules.module_query("cogit-finance-deals", "ledger.balances", {})
    assert (balances["held"], balances["seller"], balances["fee"]) == (0, 49500, 500)


def test_tick_resends_an_outbox_entry_that_was_not_sent() -> None:
    world = World()
    world.modules.fail_once("message.send", ModuleError("unavailable"))
    assert world.request(DEAL)["status"] == "processed"
    assert world.inbox(world.seller, DEAL, "relay") == []
    assert [row["status"] for row in world.modules.outbox.values()] == ["pending"]
    result = world.run_tick()
    assert result == {
        "types_registered": 21,
        "credits_seen": 0,
        "deals_funded": 0,
        "outbox_sent": 1,
    }
    assert len(world.inbox(world.seller, DEAL, "relay")) == 1
    assert world.run_tick()["outbox_sent"] == 0


def test_only_the_exact_price_with_the_deal_reference_funds_a_deal() -> None:
    world = World()
    world.request(DEAL)
    world.quote(DEAL)
    world.accept(world.buyer, DEAL)
    world.accept(world.seller, DEAL)
    escrow_iban = world.config["rail"]["escrow_iban"]

    def credit(amount: int, reference: str, key: str) -> Row:
        world.bank.transfer(
            from_iban="DE00EXAMPLE0000000010",
            to_iban=escrow_iban,
            amount_minor=amount,
            currency="EUR",
            reference=reference,
            idempotency_key=key,
        )
        return world.run_tick()

    assert credit(49999, f"ESCROW-{DEAL}", "short")["deals_funded"] == 0
    assert credit(50000, "ESCROW-unknown", "other")["deals_funded"] == 0
    assert world.state(DEAL) == "FUNDING_REQUESTED"
    funded = credit(50000, f"ESCROW-{DEAL}", "exact")
    assert (funded["credits_seen"], funded["deals_funded"]) == (3, 1)
    assert world.state(DEAL) == "FUNDED"
    again = credit(50000, f"ESCROW-{DEAL}", "twice")
    assert (again["credits_seen"], again["deals_funded"]) == (4, 0)
    assert [c["disposition"] for c in world.read(DEAL)["credits"]] == [
        "returned",
        "funded",
        "returned",
    ]
    assert world.bank.balances[escrow_iban] == 50000
    assert world.bank.balances["DE00EXAMPLE0000000010"] == 950000
    intents = list(world.modules.intents.values())
    assert len(intents) == 3
    assert all(
        i["kind"] == "return_unmatched" and i["status"] == "confirmed" for i in intents
    )
    before = dict(world.bank.balances)
    world.run_tick()
    assert world.bank.balances == before
