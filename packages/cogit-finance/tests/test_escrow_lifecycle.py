"""SPEC §5/§9/§10 regression tests with an injected clock and bank failures."""

from __future__ import annotations

from typing import Any

import pytest
from cogit_messaging_shim import AgentKey
from escrow_data import BUYER_IBAN, ESCROW_IBAN, FILES, HAPPY_DEAL, PRICE
from escrow_world import World

DEAL = HAPPY_DEAL


def test_delivery_timeout_refunds_once_and_sends_receipt() -> None:
    w = World()
    w.open_deal(DEAL)
    w.clock.tick(61)
    assert w.deliver(DEAL)["reason"] == "delivery_deadline_passed"
    for _ in range(3):
        w.run_tick()
    assert w.state(DEAL) == "REFUNDED"
    assert w.bank.balances[BUYER_IBAN] == 1000000
    assert w.bank.balances[ESCROW_IBAN] == 0
    assert len(w.bank.transfers) == 2
    assert w.event_types(DEAL)[-3:] == [
        "delivery_deadline",
        "refund_confirmed",
        "receipt",
    ]
    assert w.inbox(w.buyer, DEAL, "receipt")[-1]["body"]["outcome"] == "refunded"


@pytest.mark.parametrize("quoted", [False, True])
def test_unaccepted_deals_expire(quoted: bool) -> None:
    w = World()
    w.request(DEAL)
    if quoted:
        w.quote(DEAL)
    w.clock.tick(601)
    w.run_tick()
    assert w.state(DEAL) == "EXPIRED"
    before = w.read(DEAL)
    w.run_tick()
    assert w.read(DEAL) == before


def test_funding_timeout_cancels_and_late_credit_is_returned() -> None:
    w = World()
    w.request(DEAL)
    w.quote(DEAL)
    w.accept(w.buyer, DEAL)
    w.accept(w.seller, DEAL)
    w.clock.tick(901)
    # Credit arrives before the timer runs, but after the funding deadline.
    assert w.pay(DEAL)["deals_funded"] == 0
    assert w.state(DEAL) == "CANCELLED"
    assert w.bank.balances[BUYER_IBAN] == 1000000
    assert w.read(DEAL)["credits"][0]["disposition"] == "returned"


@pytest.mark.parametrize(
    "trigger,target", [("cancel", "CANCELLED"), ("decline", "DECLINED")]
)
def test_participants_can_close_unfunded_deals(trigger: str, target: str) -> None:
    w = World()
    w.request(DEAL)
    assert (
        w.send(w.evaluator, trigger, DEAL, {"reason": "stop"})["reason"]
        == "unexpected_sender"
    )
    assert w.send(w.buyer, trigger, DEAL, {"reason": "stop"})["status"] == "processed"
    assert w.state(DEAL) == target


@pytest.mark.parametrize("errors", [False, True])
def test_evaluator_retry_then_dispute_never_moves_money(errors: bool) -> None:
    w = World()
    w.open_deal(DEAL)
    w.deliver(DEAL)
    request = w.requests(DEAL, 1)[0]
    if errors:
        body = {**w.verdict_body(request), "outcome": "error"}
        w.send(w.evaluator, "verdict", DEAL, body, request["message_id"])
    else:
        w.clock.tick(61)
        w.run_tick()
    retries = [
        e
        for e in w.requests(DEAL, 1)
        if e["body"]["evaluation_request_id"]
        == request["body"]["evaluation_request_id"]
    ]
    assert len(retries) == 2
    if errors:
        w.send(w.evaluator, "verdict", DEAL, body, retries[-1]["message_id"])
    else:
        w.clock.tick(61)
        w.run_tick()
    assert w.state(DEAL) == "DISPUTED"
    assert len(w.bank.transfers) == 1
    assert len(w.read(DEAL)["deliveries"]) == 1
    assert w.read(DEAL)["intents"] == []
    assert w.read(DEAL)["events"][-1]["body"]["reason"] == "evaluator_unavailable"


@pytest.mark.parametrize(
    "outcome,target", [("release", "SETTLED"), ("refund", "REFUNDED")]
)
def test_dispute_stops_timers_until_authenticated_ruling(
    outcome: str, target: str
) -> None:
    w = World()
    operator = AgentKey.generate()
    w.config["operator"]["ruling_did"] = operator.did
    w.open_deal(DEAL)
    w.deliver(DEAL, names=FILES[:2])
    w.evaluate(DEAL)
    assert w.state(DEAL) == "REJECTED"
    assert (
        w.send(w.seller, "dispute", DEAL, {"reason": "review"})["status"] == "processed"
    )
    w.clock.tick(7200)
    w.run_tick()
    assert w.state(DEAL) == "DISPUTED"
    ruling = {"outcome": outcome, "reason": "reviewed evidence"}
    assert w.send(w.buyer, "ruling", DEAL, ruling)["reason"] == "unexpected_sender"
    assert w.send(operator, "ruling", DEAL, ruling)["status"] == "processed"
    assert w.state(DEAL) == target
    assert {i["kind"] for i in w.read(DEAL)["intents"]} == (
        {"refund"} if outcome == "refund" else {"payout", "fee"}
    )


def test_rejection_refunds_after_rework_and_dispute_windows() -> None:
    w = World()
    w.open_deal(DEAL)
    w.deliver(DEAL, names=FILES[:2])
    w.evaluate(DEAL)
    w.clock.tick(61)
    assert w.deliver(DEAL, 2)["reason"] == "delivery_deadline_passed"
    w.run_tick()
    assert w.state(DEAL) == "REJECTED"  # dispute window still open
    w.clock.tick(3601)
    w.run_tick()
    assert w.state(DEAL) == "REFUNDED"


@pytest.mark.parametrize("point", ["before_submit", "after_bank", "ambiguous"])
def test_payment_crash_matrix_looks_up_before_resubmission(
    point: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    w = World()
    original = w.bank.transfer
    lookups: list[str] = []
    lookup = w.bank.lookup
    monkeypatch.setattr(
        w.bank, "lookup", lambda key: (lookups.append(key), lookup(key))[1]
    )

    def transfer(**kwargs: Any) -> dict[str, Any]:
        if kwargs["idempotency_key"] == f"{DEAL}:payout":
            monkeypatch.setattr(w.bank, "transfer", original)
            if point == "before_submit":
                raise TimeoutError("request lost")
            result = original(**kwargs)
            if point == "after_bank":
                raise TimeoutError("response lost")
            return {**result, "status": "pending"}
        return original(**kwargs)

    monkeypatch.setattr(w.bank, "transfer", transfer)
    w.happy_path()
    assert w.state(DEAL) == "RELEASING"
    intent = next(i for i in w.read(DEAL)["intents"] if i["kind"] == "payout")
    assert intent["status"] == "unknown"
    w.run_tick()
    assert w.state(DEAL) == "SETTLED"
    assert f"{DEAL}:payout" in lookups
    assert len(w.bank.transfers) == 3
    assert w.bank.balances[ESCROW_IBAN] == 0
    balances = w.modules.module_query("cogit-finance-deals", "ledger.balances", {})
    assert balances["seller"] + balances["fee"] == PRICE
