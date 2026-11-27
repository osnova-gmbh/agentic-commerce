"""Canonical JSON (SPEC §6.1): UTF-8, sorted keys, no insignificant whitespace, no floats."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def _reject_floats(value: Any) -> None:
    if isinstance(value, float):
        raise TypeError("Canonical JSON carries no floating-point values; use integers")
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("Canonical JSON object keys must be strings")
            _reject_floats(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reject_floats(item)


def canonical_bytes(value: Any) -> bytes:
    _reject_floats(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_hex(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def canonical_hash(value: Any) -> str:
    """Lower-case hex SHA-256 of the canonical bytes, e.g. ``terms_hash``."""
    return sha256_hex(canonical_bytes(value))


ZERO_HASH = "0" * 64


def event_hash(event: dict) -> str:
    """Hash of one deal event: SHA-256 over ``prev_hash`` followed by the canonical event."""
    fields = ("deal_id", "seq", "prev_hash", "event_type", "source_message_id", "actor_did", "body", "state_after")
    return sha256_hex(event["prev_hash"].encode("ascii") + canonical_bytes({name: event[name] for name in fields}))
