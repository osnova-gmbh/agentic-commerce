"""The signed message envelope (SPEC §6.1)."""

from __future__ import annotations

import base64
import uuid
from datetime import datetime, timedelta, timezone

from .canonical import canonical_bytes
from .keys import AgentKey, verify_signature

ENVELOPE_VERSION = 1
SIGNED_FIELDS = (
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
)
ENVELOPE_FIELDS = (*SIGNED_FIELDS, "signature")


def to_ts(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def now_ts() -> str:
    return to_ts(datetime.now(timezone.utc))


def parse_ts(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def reply_message_id(causation_id: str, type_key: str, recipient_did: str) -> str:
    """Stable ID of a reply, so that processing a message twice sends the same reply."""
    return str(uuid.uuid5(uuid.UUID(causation_id), f"{type_key}|{recipient_did}"))


def _b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64u_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def signing_bytes(envelope: dict) -> bytes:
    return canonical_bytes({name: envelope[name] for name in SIGNED_FIELDS})


def build_envelope(
    key: AgentKey,
    sender_did: str,
    type_key: str,
    type_version: int,
    recipient_did: str,
    conversation_id: str,
    body: dict,
    causation_id: str | None = None,
    *,
    message_id: str | None = None,
    created_at: str | None = None,
) -> dict:
    """Build and sign one envelope.

    Without ``message_id``: a reply (``causation_id`` given) gets the stable
    ``reply_message_id``; anything else gets a random UUID.
    """
    if message_id is None:
        message_id = reply_message_id(causation_id, type_key, recipient_did) if causation_id else str(uuid.uuid4())
    envelope = {
        "envelope_version": ENVELOPE_VERSION,
        "message_id": message_id,
        "type_key": type_key,
        "type_version": type_version,
        "sender_did": sender_did,
        "recipient_did": recipient_did,
        "conversation_id": conversation_id,
        "causation_id": causation_id,
        "created_at": created_at or now_ts(),
        "body": body,
    }
    envelope["signature"] = _b64u(key.sign(signing_bytes(envelope)))
    return envelope


def freshness_error(envelope: dict, now: datetime) -> str | None:
    """Admission freshness, separate from archival signature verification."""
    try:
        created = parse_ts(envelope["created_at"])
    except (KeyError, TypeError, ValueError):
        return "invalid_timestamp"
    if created < now - timedelta(hours=24):
        return "message_expired"
    if created > now + timedelta(minutes=2):
        return "message_from_future"
    return None


def verify_envelope(envelope: object) -> bool:
    """True when the envelope is complete and signed by its ``sender_did``."""
    if not isinstance(envelope, dict) or set(envelope) != set(ENVELOPE_FIELDS):
        return False
    try:
        if envelope["envelope_version"] != ENVELOPE_VERSION or not isinstance(envelope["body"], dict):
            return False
        return verify_signature(envelope["sender_did"], signing_bytes(envelope), _b64u_decode(envelope["signature"]))
    except (TypeError, ValueError, KeyError):
        return False
