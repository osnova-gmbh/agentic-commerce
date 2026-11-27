from datetime import datetime, timezone
from pathlib import Path

import pytest

pytest.importorskip("cogit_messaging_module")

from cogit_finance_seams import ModuleError  # noqa: E402

from cogit_messaging_shim import AgentKey, DeliveryLoop, ShimMessaging, verify_envelope  # noqa: E402
from cogit_messaging_shim.testing import LocalBus  # noqa: E402

CONTRACTS = Path(__file__).resolve().parents[3] / "contracts"
NOTE = {"type": "object", "properties": {"n": {"type": "integer"}}, "required": ["n"], "additionalProperties": False}


class Counter:
    """Answers every note below ``stop_at`` with the next number."""

    def __init__(self, bus: LocalBus, installation_id: str, stop_at: int) -> None:
        self.messaging = bus.messaging(installation_id)
        self.stop_at = stop_at
        self.seen: list[int] = []

    def handle_message(self, envelope: dict) -> dict:
        assert verify_envelope(envelope)
        n = envelope["body"]["n"]
        self.seen.append(n)
        if n < self.stop_at:
            reply = {"n": n + 1}
            self.messaging.send("test.count", 1, envelope["sender_did"], "conv-1", reply, envelope["message_id"])
        return {"status": "processed", "reason": None}


def test_pump_runs_every_loop_until_the_bus_is_quiet():
    bus = LocalBus()
    ping_key = bus.add_agent("ping-agent", "ping-co", "buyer")
    pong_key = bus.add_agent("pong-agent", "pong-co", "seller", AgentKey.from_seed(bytes(range(32))))
    assert pong_key.did == AgentKey.from_seed(bytes(range(32))).did
    bus.register_type("test.count", 1, NOTE)
    bus.register_type("test.count", 1, NOTE)
    ping, pong = Counter(bus, "ping-agent", 4), Counter(bus, "pong-agent", 4)
    bus.runtime.register("ping-agent", ping)
    bus.runtime.register("pong-agent", pong)
    assert isinstance(bus.messaging("ping-agent"), ShimMessaging) and bus.messaging("ping-agent").did == ping_key.did
    assert isinstance(bus.loop("ping-agent"), DeliveryLoop)
    bus.messaging("ping-agent").send("test.count", 1, pong_key.did, "conv-1", {"n": 1})
    assert bus.pump() == 4
    assert (pong.seen, ping.seen) == ([1, 3], [2, 4])
    assert bus.pump() == 0
    identity = bus.host.port("ping-agent").module_query("cogit-messaging", "identity.resolve", {"role": "seller"})
    assert identity["identity"]["did"] == pong_key.did


def test_pump_leaves_messages_of_installations_without_an_agent_queued():
    bus = LocalBus(clock=lambda: datetime(2026, 11, 27, 12, 0, 0, tzinfo=timezone.utc))
    bus.add_agent("ping-agent", "ping-co", "buyer")
    inbox_key = bus.add_agent("inbox-agent", "inbox-co", "seller")
    bus.register_type("test.count", 1, NOTE)
    bus.messaging("ping-agent").send("test.count", 1, inbox_key.did, "conv-1", {"n": 1})
    assert bus.pump() == 0
    claimed = bus.host.port("inbox-agent").module_command("cogit-messaging", "message.claim", {}, idempotency_key="c1")
    assert [message["attempts"] for message in claimed["messages"]] == [1]


def test_register_type_reports_conflicts_and_uses_the_configured_escrow_installation():
    bus = LocalBus(settings={"escrow_installation_id": "escrow-x"})
    bus.register_type("test.count", 1, NOTE)
    with pytest.raises(ModuleError) as caught:
        bus.register_type("test.count", 1, {"type": "object"})
    assert caught.value.code == "type_conflict"
    with pytest.raises(ModuleError) as caught:
        bus.register_type("test.bad", 1, {"$ref": "#/x"})
    assert caught.value.code == "unsupported_schema"


def test_register_finance_types_registers_every_frozen_schema():
    if not (CONTRACTS / "messages").is_dir():
        pytest.skip("contracts/messages is not part of this checkout")
    expected = len(list((CONTRACTS / "messages").glob("finance.*.v1.json")))
    assert expected >= 14
    bus = LocalBus()
    assert bus.register_finance_types(CONTRACTS) == expected
    assert bus.register_finance_types(CONTRACTS / "messages") == expected
    count = bus.host.db.execute("SELECT COUNT(*) FROM msg_message_types WHERE type_key LIKE 'finance.%'").fetchone()[0]
    assert count == expected
