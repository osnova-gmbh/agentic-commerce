"""Argument and envelope shape checks. No signature cryptography here (SPEC §6.2)."""

from __future__ import annotations

import re
from typing import Any

from cogit_finance_seams import ModuleError

ENVELOPE_VERSION = 1
ENVELOPE_FIELDS = frozenset(
    {
        "envelope_version",
        "message_id",
        "type_key",
        "type_version",
        "sender_did",
        "recipient_did",
        "conversation_id",
        "causation_id",
        "created_at",
        "body",
        "signature",
    }
)
_TEXT_FIELDS = ("message_id", "type_key", "sender_did", "recipient_did", "conversation_id", "signature")
_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
MAX_TEXT = 512


def is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def text_arg(args: dict, name: str) -> str:
    value = args.get(name)
    if not isinstance(value, str) or not value:
        raise ModuleError("invalid_argument", f"{name} must be a non-empty string")
    return value


def int_arg(args: dict, name: str, *, default: int | None = None, minimum: int = 0) -> int:
    value = args.get(name, default)
    if value is None and default is not None:
        value = default
    if not is_int(value) or value < minimum:
        raise ModuleError("invalid_argument", f"{name} must be an integer of at least {minimum}")
    return value


def has_float(value: Any) -> bool:
    if isinstance(value, float):
        return True
    if isinstance(value, dict):
        return any(has_float(item) for item in value.values())
    if isinstance(value, list):
        return any(has_float(item) for item in value)
    return False


def check_envelope(envelope: Any) -> dict:
    """Return the envelope if it has the SPEC §6.1 shape, else raise ``invalid_envelope``."""

    def invalid(problem: str) -> ModuleError:
        return ModuleError("invalid_envelope", problem)

    if not isinstance(envelope, dict):
        raise invalid("envelope must be a JSON object")
    if set(envelope) != ENVELOPE_FIELDS:
        unknown = sorted(set(envelope) - ENVELOPE_FIELDS)
        missing = sorted(ENVELOPE_FIELDS - set(envelope))
        raise invalid(f"missing fields {missing}, unknown fields {unknown}")
    if not is_int(envelope["envelope_version"]) or envelope["envelope_version"] != ENVELOPE_VERSION:
        raise invalid(f"envelope_version must be {ENVELOPE_VERSION}")
    for name in _TEXT_FIELDS:
        value = envelope[name]
        if not isinstance(value, str) or not value or len(value) > MAX_TEXT:
            raise invalid(f"{name} must be a non-empty string of at most {MAX_TEXT} characters")
    if not is_int(envelope["type_version"]) or envelope["type_version"] < 1:
        raise invalid("type_version must be a positive integer")
    causation_id = envelope["causation_id"]
    if causation_id is not None and (not isinstance(causation_id, str) or not causation_id):
        raise invalid("causation_id must be a message_id or null")
    created_at = envelope["created_at"]
    if not isinstance(created_at, str) or not _TIMESTAMP.fullmatch(created_at):
        raise invalid("created_at must be a UTC timestamp, YYYY-MM-DDTHH:MM:SSZ")
    if not isinstance(envelope["body"], dict):
        raise invalid("body must be a JSON object")
    if has_float(envelope):
        raise invalid("canonical JSON carries no floating-point values")
    return envelope
