"""Boundary tests for immutable schemas, time admission and bank outages."""

from __future__ import annotations

from datetime import timedelta

import pytest
from cogit_messaging_shim import build_envelope
from escrow_data import HAPPY_DEAL
from escrow_world import World

from cogit_finance.escrow import policy


@pytest.mark.parametrize(
    "value,outcomes,expected",
    [
        ("quorum 2", ["pass", "pass", None], "approve"),
        ("quorum 2", ["fail", "fail", None], "reject"),
        ("quorum 2", ["pass", "error", None], None),
        ("quorum 1", [None, "pass", "fail"], "approve"),
    ],
)
def test_quorum_decides_as_soon_as_certain(
    value: str, outcomes: list[str | None], expected: str | None
) -> None:
    assert policy.decide(value, outcomes) == expected


def test_quorum_uses_v2_without_changing_v1() -> None:
    w = World()
    w.request(HAPPY_DEAL)
    quote = w.quote_body()
    quote["acceptance"]["policy"] = "quorum 2"
    assert w.send(w.seller, "quote", HAPPY_DEAL, quote)["reason"] == "invalid_body"
    envelope = build_envelope(
        w.seller,
        w.seller.did,
        "finance.quote",
        2,
        w.escrow.did,
        HAPPY_DEAL,
        quote,
        created_at=w.clock.ts(),
    )
    assert w.handle(envelope)["status"] == "processed"
    assert w.inbox(w.buyer, HAPPY_DEAL, "terms_proposed")[-1]["type_version"] == 2
    w.accept(w.buyer, HAPPY_DEAL)
    w.accept(w.seller, HAPPY_DEAL)
    w.pay(HAPPY_DEAL)
    w.deliver(HAPPY_DEAL)
    for request in w.requests(HAPPY_DEAL, 1)[:2]:
        w.judge(request)
    assert w.state(HAPPY_DEAL) == "SETTLED"
    assert len(w.read(HAPPY_DEAL)["events"]) == 16  # decision after 2 of 3


@pytest.mark.parametrize(
    "seconds,reason", [(-86401, "message_expired"), (121, "message_from_future")]
)
def test_escrow_rejects_signed_but_stale_messages(seconds: int, reason: str) -> None:
    w = World()
    w.request(HAPPY_DEAL)
    body = w.quote_body()
    from cogit_messaging_shim import to_ts

    envelope = build_envelope(
        w.seller,
        w.seller.did,
        "finance.quote",
        1,
        w.escrow.did,
        HAPPY_DEAL,
        body,
        created_at=to_ts(w.clock.now() + timedelta(seconds=seconds)),
    )
    before = w.read(HAPPY_DEAL)
    assert w.handle(envelope) == {"status": "rejected", "reason": reason}
    assert w.read(HAPPY_DEAL) == before


def test_bank_outage_does_not_prevent_durable_refund_preparation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    w = World()
    w.open_deal(HAPPY_DEAL)
    w.clock.tick(61)

    def offline(*args: object, **kwargs: object) -> None:
        raise TimeoutError("bank offline")

    with monkeypatch.context() as patch:
        patch.setattr(w.bank, "credits", offline)
        patch.setattr(w.bank, "transfer", offline)
        w.run_tick()
    assert w.state(HAPPY_DEAL) == "REFUNDING"
    assert w.read(HAPPY_DEAL)["intents"][0]["status"] == "unknown"
    w.run_tick()
    assert w.state(HAPPY_DEAL) == "REFUNDED"
    assert len(w.bank.transfers) == 2
