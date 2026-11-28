"""Freshness is an admission check, not a restriction on archival verification."""

from datetime import datetime, timedelta, timezone

import pytest

from cogit_messaging_shim import AgentKey, build_envelope, to_ts, verify_envelope
from cogit_messaging_shim.envelope import freshness_error


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
