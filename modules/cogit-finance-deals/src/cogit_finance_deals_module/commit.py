"""``deal.commit``: append one event to a deal's hash chain, with everything it causes.

The five rules of contracts/module-exports.md, in that order. The caller (the module
host) runs this inside one transaction, so raising leaves no partial rows. E computes
the event hash; this code checks the head, the sequence number and ``prev_hash`` and
stores the hash under a unique index.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from cogit_finance_seams import ModuleError, dumps

from .rows import (
    ACTIVE_STATUSES,
    CREDITS,
    DELIVERIES,
    EVALUATIONS,
    INTENTS,
    POSTINGS,
    SINGLE_ACTIVE_KINDS,
    ZERO_HASH,
    clean,
    insert,
    invalid,
    is_hash,
    is_natural,
    is_object,
    is_positive,
    is_text,
    upsert,
)

ROW_LISTS = ("outbox", "deliveries", "evaluations", "intents", "credits", "postings")
ARGUMENTS = {"deal_id", "expected_seq", "expected_hash", "event", "deal", *ROW_LISTS}
EVENT_FIELDS = {
    "seq": is_positive,
    "prev_hash": is_hash,
    "hash": is_hash,
    "event_type": is_text,
    "actor_did": is_text,
    "body": is_object,
    "state_after": is_text,
}
DEAL_IDENTITY = ("buyer_org_id", "seller_org_id", "offer_id")
DEAL_FIELDS = {**dict.fromkeys(DEAL_IDENTITY, is_text), "terms": is_object, "terms_hash": is_hash}


def bad_event(message: str) -> ModuleError:
    return ModuleError("bad_event", message)


def _event(value: Any, deal_id: str) -> dict:
    if not isinstance(value, dict):
        raise bad_event("event must be an object")
    unknown = sorted(set(value) - set(EVENT_FIELDS) - {"source_message_id", "deal_id"})
    if unknown:
        raise bad_event(f"event has unknown fields: {', '.join(unknown)}")
    if value.get("deal_id") not in (None, deal_id):
        raise bad_event("event.deal_id differs from deal_id")
    for name, check in EVENT_FIELDS.items():
        if not check(value.get(name)):
            raise bad_event(f"event.{name} is missing or not valid")
    source_message_id = value.get("source_message_id")
    if source_message_id is not None and not is_text(source_message_id):
        raise bad_event("event.source_message_id must be a non-empty string or null")
    return {**{name: value[name] for name in EVENT_FIELDS}, "source_message_id": source_message_id}


def _deal_fields(value: Any) -> dict:
    """The ``deal`` argument without its nulls: a null field counts as not given."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise invalid("deal must be an object")
    unknown = sorted(set(value) - set(DEAL_FIELDS) - {"deal_id"})
    if unknown:
        raise invalid(f"deal has unknown fields: {', '.join(unknown)}")
    given = {name: value[name] for name in DEAL_FIELDS if value.get(name) is not None}
    for name, item in given.items():
        if not DEAL_FIELDS[name](item):
            raise invalid(f"deal.{name} is not valid")
    return given


def _rows(args: dict, name: str) -> list:
    value = args.get(name)
    if value is None:
        return []
    if not isinstance(value, list):
        raise invalid(f"{name} must be a list")
    return value


def commit(db: sqlite3.Connection, now: str, args: dict) -> dict:
    unknown = sorted(set(args) - ARGUMENTS)
    if unknown:
        raise invalid(f"unknown arguments: {', '.join(unknown)}")
    deal_id, expected_seq, expected_hash = args.get("deal_id"), args.get("expected_seq"), args.get("expected_hash")
    if not is_text(deal_id):
        raise invalid("deal_id must be a non-empty string")
    if not is_natural(expected_seq) or not isinstance(expected_hash, str):
        raise invalid("expected_seq must be a non-negative integer and expected_hash a string")
    event = _event(args.get("event"), deal_id)
    fields = _deal_fields(args.get("deal"))
    lists = {name: _rows(args, name) for name in ROW_LISTS}

    # 1. A message that already produced an event: the original result, nothing written.
    if event["source_message_id"] is not None:
        known = db.execute(
            "SELECT deal_id, seq, hash FROM deal_events WHERE source_message_id = ?", (event["source_message_id"],)
        ).fetchone()
        if known is not None:
            if known["deal_id"] != deal_id:
                raise bad_event("event.source_message_id is recorded for another deal")
            return {"seq": known["seq"], "hash": known["hash"], "duplicate": True}

    # 2. The caller must have seen the current head. A new deal starts at 0 and 64 zeros.
    deal = db.execute(
        "SELECT head_seq, head_hash, buyer_org_id, seller_org_id, offer_id FROM deal_deals WHERE deal_id = ?",
        (deal_id,),
    ).fetchone()
    head_seq, head_hash = (0, ZERO_HASH) if deal is None else (deal["head_seq"], deal["head_hash"])
    if (expected_seq, expected_hash) != (head_seq, head_hash):
        raise ModuleError("head_mismatch", f"the head of {deal_id} is seq {head_seq}, hash {head_hash}")
    if deal is None:
        missing = [name for name in DEAL_IDENTITY if name not in fields]
        if missing:
            raise ModuleError("head_mismatch", f"a new deal needs deal.{', deal.'.join(missing)}")
    else:
        for name in DEAL_IDENTITY:
            if name in fields and fields[name] != deal[name]:
                raise invalid(f"deal.{name} cannot change after the first event")

    # 3. The event must be the next link of the chain.
    if event["seq"] != expected_seq + 1 or event["prev_hash"] != expected_hash:
        raise bad_event(f"expected seq {expected_seq + 1} with prev_hash {expected_hash}")

    # 4. Move the head, then write the event and everything that belongs to it.
    seq, event_hash, state = event["seq"], event["hash"], event["state_after"]
    terms = dumps(fields["terms"]) if "terms" in fields else None
    try:
        if deal is None:
            db.execute(
                "INSERT INTO deal_deals (deal_id, buyer_org_id, seller_org_id, offer_id, state, head_seq, head_hash,"
                " terms, terms_hash, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (deal_id, *(fields[name] for name in DEAL_IDENTITY), state, seq, event_hash)
                + (terms, fields.get("terms_hash"), now, now),
            )
        else:
            # Compare-and-swap on the head, so a concurrent writer cannot append to the same link.
            moved = db.execute(
                "UPDATE deal_deals SET state = ?, head_seq = ?, head_hash = ?, updated_at = ?,"
                " terms = COALESCE(?, terms), terms_hash = COALESCE(?, terms_hash)"
                " WHERE deal_id = ? AND head_seq = ? AND head_hash = ?",
                (state, seq, event_hash, now, terms, fields.get("terms_hash"), deal_id, expected_seq, expected_hash),
            )
            if moved.rowcount != 1:
                raise ModuleError("head_mismatch", f"the head of {deal_id} moved")
    except sqlite3.IntegrityError as error:
        raise ModuleError("head_mismatch", f"{deal_id} was created concurrently") from error
    try:
        db.execute(
            "INSERT INTO deal_events (deal_id, seq, prev_hash, hash, event_type, source_message_id, actor_did, body,"
            " state_after, recorded_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (deal_id, seq, event["prev_hash"], event_hash, event["event_type"], event["source_message_id"])
            + (event["actor_did"], dumps(event["body"]), state, now),
        )
    except sqlite3.IntegrityError as error:
        raise bad_event("event.hash is already recorded") from error

    for position, item in enumerate(lists["outbox"]):
        _insert_outbox(db, now, deal_id, seq, position, item)
    for index, item in enumerate(lists["deliveries"]):
        upsert(db, DELIVERIES, deal_id, item, f"deliveries[{index}]")
    for index, item in enumerate(lists["evaluations"]):
        upsert(db, EVALUATIONS, deal_id, item, f"evaluations[{index}]")

    # 5. Intents, credits and postings are insert-only and guarded by unique indexes.
    for index, item in enumerate(lists["intents"]):
        _insert_intent(db, now, deal_id, item, f"intents[{index}]")
    for index, item in enumerate(lists["credits"]):
        key, given = clean(CREDITS, item, deal_id, f"credits[{index}]")
        if db.execute("SELECT 1 FROM deal_bank_credits WHERE bank_event_id = ?", (key,)).fetchone():
            raise ModuleError("duplicate_credit", f"bank event {key} is already recorded")
        try:
            insert(db, CREDITS, deal_id, key, given, f"credits[{index}]")
        except sqlite3.IntegrityError as error:
            raise ModuleError("duplicate_credit", f"bank event {key} is already recorded") from error
    for index, item in enumerate(lists["postings"]):
        key, given = clean(POSTINGS, item, deal_id, f"postings[{index}]")
        insert_posting(db, now, deal_id, key, given, f"postings[{index}]")
    return {"seq": seq, "hash": event_hash, "duplicate": False}


def _insert_outbox(db: sqlite3.Connection, now: str, deal_id: str, seq: int, position: int, item: Any) -> None:
    where = f"outbox[{position}]"
    if not isinstance(item, dict) or set(item) - {"deal_id"} != {"outbox_id", "envelope"}:
        raise invalid(f"{where} must be an object with outbox_id and envelope")
    if not is_text(item["outbox_id"]) or not is_object(item["envelope"]):
        raise invalid(f"{where} needs a non-empty outbox_id and an envelope object")
    if item.get("deal_id") not in (None, deal_id):
        raise invalid(f"{where}.deal_id differs from the deal of this call")
    try:
        db.execute(
            "INSERT INTO deal_outbox (outbox_id, deal_id, seq, envelope, status, sent_at, created_at, ordinal)"
            " VALUES (?, ?, ?, ?, 'pending', NULL, ?, ?)",
            (item["outbox_id"], deal_id, seq, dumps(item["envelope"]), now, position),
        )
    except sqlite3.IntegrityError as error:
        raise invalid(f"{where}.outbox_id {item['outbox_id']} already exists") from error


def _insert_intent(db: sqlite3.Connection, now: str, deal_id: str, item: Any, where: str) -> None:
    key, given = clean(INTENTS, item, deal_id, where)
    status = given.get("status") or "prepared"
    if given.get("kind") in SINGLE_ACTIVE_KINDS and status in ACTIVE_STATUSES:
        marks = ", ".join("?" for _ in ACTIVE_STATUSES)
        active = db.execute(
            "SELECT intent_id FROM deal_payment_intents WHERE deal_id = ? AND kind IN ('payout', 'refund')"
            f" AND status IN ({marks})",
            (deal_id, *ACTIVE_STATUSES),
        ).fetchone()
        if active is not None:
            raise ModuleError("intent_conflict", f"{deal_id} already has the active intent {active['intent_id']}")
    try:
        insert(db, INTENTS, deal_id, key, given, where, {"created_at": now, "updated_at": now})
    except sqlite3.IntegrityError as error:
        raise ModuleError("intent_conflict", f"intent {key} cannot be added: {error}") from error


def insert_posting(db: sqlite3.Connection, now: str, deal_id: str, key: str, given: dict, where: str) -> None:
    try:
        insert(db, POSTINGS, deal_id, key, given, where, {"created_at": now})
    except sqlite3.IntegrityError as error:
        raise ModuleError("duplicate_posting", f"{where}: {key} or its source and account already exist") from error
