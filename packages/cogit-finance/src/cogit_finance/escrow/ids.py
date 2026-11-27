"""Identifiers and idempotency keys (SPEC §7, §9; build guide §5.1 and §5.3)."""

from __future__ import annotations

import uuid

REFERENCE_PREFIX = "ESCROW-"


def is_uuid(text: object) -> bool:
    if not isinstance(text, str) or len(text) != 36:
        return False
    try:
        return str(uuid.UUID(text)) == text.lower()
    except ValueError:
        return False


def delivery_id(deal_id: str, attempt: int) -> str:
    return f"{deal_id}:d{attempt}"


def evaluation_request_id(delivery: str, evaluator_id: str, version: int) -> str:
    return f"{delivery}:{evaluator_id}@{version}"


def payment_reference(deal_id: str) -> str:
    return f"{REFERENCE_PREFIX}{deal_id}"


def deal_id_from_reference(reference: object) -> str | None:
    """The deal a bank credit names, or None when the reference is not ours."""
    if not isinstance(reference, str) or not reference.startswith(REFERENCE_PREFIX):
        return None
    deal_id = reference[len(REFERENCE_PREFIX) :]
    return deal_id if is_uuid(deal_id) else None


def intent_id(deal_id: str, kind: str) -> str:
    """Also the idempotency key of the transfer at the bank."""
    return f"{deal_id}:{kind}"


def posting_id(source_id: str, account: str) -> str:
    return f"{source_id}:{account}"


def own_message_id(
    deal_id: str, seq: int, type_key: str, recipient_did: str, n: int
) -> str:
    """ID of an envelope E sends: stable, so a repeated run sends the same one."""
    name = f"{seq}:{type_key}:{recipient_did}:{n}"
    return str(uuid.uuid5(uuid.UUID(deal_id), name))


def message_event_key(message_id: str) -> str:
    """``deal.commit`` key of the event that records an inbound message."""
    return f"evt:{message_id}"


def own_event_key(deal_id: str, seq: int, event_type: str) -> str:
    """``deal.commit`` key of an event E originates."""
    return f"own:{deal_id}:{seq}:{event_type}"


def outbox_send_key(outbox_id: str) -> str:
    return f"out:{outbox_id}"


def outbox_sent_key(outbox_id: str) -> str:
    return f"sent:{outbox_id}"


def intent_update_key(intent: str, status: str) -> str:
    return f"intent:{intent}:{status}"


def type_register_key(type_key: str, type_version: int) -> str:
    return f"type:{type_key}:v{type_version}"
