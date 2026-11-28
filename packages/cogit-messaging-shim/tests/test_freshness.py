"""Freshness is an admission check, not a restriction on archival verification."""

from datetime import datetime, timedelta, timezone

import pytest

from cogit_messaging_shim import AgentKey, build_envelope, to_ts, verify_envelope
from cogit_messaging_shim.envelope import freshness_error
from cogit_messaging_shim.loop import DeliveryLoop


@pytest.mark.parametrize(
    "seconds,reason",
    [
        (-86401, "message_expired"),
        (-86400, None),
        (120, None),
        (121, "message_from_future"),
    ],
)
def test_signed_envelope_freshness_boundaries(seconds: int, reason: str | None) -> None:
    now = datetime(2026, 11, 28, tzinfo=timezone.utc)
    key = AgentKey.generate()
    envelope = build_envelope(
        key,
        key.did,
        "test.note",
        1,
        key.did,
        "conversation",
        {},
        created_at=to_ts(now + timedelta(seconds=seconds)),
    )
    assert verify_envelope(envelope)
    assert freshness_error(envelope, now) == reason


def test_delivery_loop_rejects_stale_message_before_work_admission() -> None:
    now = datetime(2026, 11, 28, tzinfo=timezone.utc)
    key = AgentKey.generate()
    envelope = build_envelope(
        key,
        key.did,
        "test.note",
        1,
        key.did,
        "c",
        {},
        created_at=to_ts(now - timedelta(days=2)),
    )

    class Port:
        def __init__(self) -> None:
            self.acks: list[dict] = []

        def module_command(
            self, module: str, export: str, args: dict, *, idempotency_key: str
        ) -> dict:
            if export == "message.claim":
                return {
                    "messages": [
                        {
                            "message_id": envelope["message_id"],
                            "envelope": envelope,
                            "attempts": 1,
                        }
                    ]
                }
            assert export == "message.ack"
            self.acks.append(args)
            return {}

        def module_query(
            self, module: str, export: str, args: dict | None = None
        ) -> dict:
            return {}

    class Work:
        def admit(self, *args: object, **kwargs: object) -> str:
            pytest.fail("stale messages must not be admitted")

    port = Port()
    DeliveryLoop("agent", port, Work(), clock=lambda: now).run_once()
    assert port.acks == [
        {
            "message_id": envelope["message_id"],
            "outcome": "rejected",
            "reason": "message_expired",
        }
    ]
