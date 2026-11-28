"""Row shapes of the tables that ``deal.commit`` and ``intent.update`` fill from arguments.

A field is ``(check, mode)``. ``REQUIRED`` fields must be given when a row is inserted,
``NULLABLE`` fields default to null, any other mode is the default value. Rows carry
scalars only; money is an integer in minor units and never a float.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeGuard

from cogit_finance_seams import ModuleError

Check = Callable[[Any], bool]
REQUIRED: Any = object()
NULLABLE: Any = object()

ZERO_HASH = "0" * 64
INTENT_KINDS = ("payout", "fee", "refund", "return_unmatched")
INTENT_STATUSES = ("prepared", "submitted", "unknown", "confirmed", "failed")
ACTIVE_STATUSES = ("prepared", "submitted", "unknown")
SINGLE_ACTIVE_KINDS = ("payout", "refund")
ACCOUNTS = ("held", "seller", "fee", "buyer_refund", "returned")
_HASH = re.compile(r"[0-9a-f]{64}")


def invalid(message: str) -> ModuleError:
    return ModuleError("invalid_argument", message)


def is_text(value: Any) -> TypeGuard[str]:
    return isinstance(value, str) and value != ""


def is_integer(value: Any) -> TypeGuard[int]:
    return type(value) is int


def is_natural(value: Any) -> TypeGuard[int]:
    return type(value) is int and value >= 0


def is_positive(value: Any) -> TypeGuard[int]:
    return type(value) is int and value >= 1


def is_object(value: Any) -> bool:
    return isinstance(value, dict)


def is_hash(value: Any) -> bool:
    return isinstance(value, str) and _HASH.fullmatch(value) is not None


def one_of(*allowed: str) -> Check:
    return lambda value: isinstance(value, str) and value in allowed


@dataclass(frozen=True)
class Table:
    name: str
    key: str
    fields: dict[str, tuple[Check, Any]]
    columns: tuple[str, ...]  # what a row object shows, in order


DELIVERIES = Table(
    "deal_deliveries",
    "delivery_id",
    {
        "attempt": (is_positive, REQUIRED),
        "artifact_id": (is_text, REQUIRED),
        "sha256": (is_text, REQUIRED),
        "byte_length": (is_natural, REQUIRED),
        "media_type": (is_text, REQUIRED),
        "delivered_at": (is_text, REQUIRED),
        "status": (is_text, "delivered"),
    },
    (
        "delivery_id",
        "deal_id",
        "attempt",
        "artifact_id",
        "sha256",
        "byte_length",
        "media_type",
        "delivered_at",
        "status",
    ),
)

EVALUATIONS = Table(
    "deal_evaluations",
    "evaluation_request_id",
    {
        "delivery_id": (is_text, REQUIRED),
        "evaluator_id": (is_text, REQUIRED),
        "evaluator_version": (is_natural, REQUIRED),
        "evaluator_did": (is_text, REQUIRED),
        "respond_by": (is_text, REQUIRED),
        "resends": (is_natural, 0),
        "verdict_message_id": (is_text, NULLABLE),
        "outcome": (one_of("pass", "fail", "error"), NULLABLE),
    },
    (
        "evaluation_request_id",
        "delivery_id",
        "evaluator_id",
        "evaluator_version",
        "evaluator_did",
        "respond_by",
        "resends",
        "verdict_message_id",
        "outcome",
    ),
)

INTENTS = Table(
    "deal_payment_intents",
    "intent_id",
    {
        "kind": (one_of(*INTENT_KINDS), REQUIRED),
        "amount_minor": (is_natural, REQUIRED),
        "currency": (is_text, REQUIRED),
        "to_iban": (is_text, REQUIRED),
        "status": (one_of(*INTENT_STATUSES), "prepared"),
        "bank_ref": (is_text, NULLABLE),
    },
    (
        "intent_id",
        "deal_id",
        "kind",
        "amount_minor",
        "currency",
        "to_iban",
        "status",
        "bank_ref",
        "created_at",
        "updated_at",
    ),
)

CREDITS = Table(
    "deal_bank_credits",
    "bank_event_id",
    {
        "reference": (is_text, REQUIRED),
        "amount_minor": (is_natural, REQUIRED),
        "from_iban": (is_text, REQUIRED),
        "received_at": (is_text, REQUIRED),
        "disposition": (one_of("funded", "returned"), REQUIRED),
    },
    (
        "bank_event_id",
        "deal_id",
        "reference",
        "amount_minor",
        "from_iban",
        "received_at",
        "disposition",
    ),
)

POSTINGS = Table(
    "deal_ledger_postings",
    "posting_id",
    {
        "source_id": (is_text, REQUIRED),
        "account": (one_of(*ACCOUNTS), REQUIRED),
        "amount_minor": (is_integer, REQUIRED),
    },
    ("posting_id", "deal_id", "source_id", "account", "amount_minor", "created_at"),
)


def clean(table: Table, item: Any, deal_id: str | None, where: str) -> tuple[str, dict]:
    """Validate one row argument. Returns its key and the fields it names."""
    if not isinstance(item, dict):
        raise invalid(f"{where} must be an object")
    unknown = sorted(set(item) - set(table.fields) - {table.key, "deal_id"})
    if unknown:
        raise invalid(f"{where} has unknown fields: {', '.join(unknown)}")
    if item.get("deal_id") not in (None, deal_id):
        raise invalid(f"{where}.deal_id differs from the deal of this call")
    key = item.get(table.key)
    if not is_text(key):
        raise invalid(f"{where}.{table.key} must be a non-empty string")
    given: dict = {}
    for column, (check, mode) in table.fields.items():
        if column not in item:
            continue
        value = item[column]
        if value is None:
            if mode is REQUIRED:
                raise invalid(f"{where}.{column} must not be null")
        elif not check(value):
            raise invalid(f"{where}.{column} is not valid: {value!r}")
        given[column] = value
    return key, given


def insert(
    db: sqlite3.Connection,
    table: Table,
    deal_id: str | None,
    key: str,
    given: dict,
    where: str,
    stamps: dict | None = None,
) -> None:
    """Insert a new row; ``sqlite3.IntegrityError`` is left to the caller to name."""
    values: dict = {table.key: key, "deal_id": deal_id}
    for column, (_check, mode) in table.fields.items():
        value = given.get(column)
        if value is None:
            if mode is REQUIRED:
                raise invalid(f"{where}.{column} is required")
            value = None if mode is NULLABLE else mode
        values[column] = value
    values.update(stamps or {})
    marks = ", ".join("?" for _ in values)
    db.execute(
        f"INSERT INTO {table.name} ({', '.join(values)}) VALUES ({marks})",
        list(values.values()),
    )


def upsert(
    db: sqlite3.Connection, table: Table, deal_id: str, item: Any, where: str
) -> None:
    """Insert the row, or change the fields the argument names on the existing row."""
    key, given = clean(table, item, deal_id, where)
    existing = db.execute(
        f"SELECT deal_id FROM {table.name} WHERE {table.key} = ?", (key,)
    ).fetchone()
    if existing is None:
        insert(db, table, deal_id, key, given, where)
        return
    if existing["deal_id"] != deal_id:
        raise invalid(f"{where}: {key} belongs to another deal")
    changes = {
        column: value
        for column, value in given.items()
        if value is not None or table.fields[column][1] is NULLABLE
    }
    if changes:
        assignments = ", ".join(f"{column} = ?" for column in changes)
        db.execute(
            f"UPDATE {table.name} SET {assignments} WHERE {table.key} = ?",
            [*changes.values(), key],
        )


def select(
    db: sqlite3.Connection, table: Table, where: str, params: tuple, order_by: str
) -> list[dict]:
    columns = ", ".join(f"t.{column}" for column in table.columns)
    rows = db.execute(
        f"SELECT {columns} FROM {table.name} t WHERE {where} ORDER BY {order_by}",
        params,
    ).fetchall()
    return [dict(row) for row in rows]
