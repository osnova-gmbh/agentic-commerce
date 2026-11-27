"""Row shapes of the catalog tables: validation of incoming objects and the JSON codec.

A field is ``(kind, required, default)``. Kinds: ``text``, ``int`` (not negative, never a
float or a bool), ``bool``, ``texts`` (list of strings) and ``object``. Lists and objects are stored
as JSON text, booleans as 0 or 1; ``decode`` turns a stored row back into JSON values.
"""

from __future__ import annotations

import copy
import sqlite3
from typing import Any

from cogit_finance_seams import ModuleError, dumps, loads

Spec = dict[str, tuple[str, bool, Any]]

COMPANY: Spec = {
    "org_id": ("text", True, None),
    "legal_name": ("text", True, None),
    "register_id": ("text", False, None),
    "address": ("text", False, None),
    "roles": ("texts", False, []),
    "categories": ("texts", False, []),
    "iban": ("text", False, None),
    "kyb_verified": ("bool", False, False),
    "kyb_verified_by": ("text", False, None),
    "spending_limit_minor": ("int", False, 0),
    "profile": ("object", False, {}),
}

OFFER: Spec = {
    "seller_org_id": ("text", True, None),
    "offer_id": ("text", True, None),
    "title": ("text", True, None),
    "description": ("text", False, None),
    "category": ("text", True, None),
    "price_minor": ("int", True, None),
    "currency": ("text", True, None),
    "delivery_time_s": ("int", True, None),
    "input_schema": ("object", False, {}),
    "deliverable": ("object", False, {}),
    "default_acceptance": ("object", False, {}),
    "active": ("bool", False, True),
}

EVALUATOR: Spec = {
    "evaluator_id": ("text", True, None),
    "version": ("int", True, None),
    "org_id": ("text", True, None),
    "did": ("text", False, None),
    "description": ("text", False, None),
    "deterministic": ("bool", False, False),
    "accepts": ("texts", False, []),
    "params_schema": ("object", False, {}),
}


def invalid(message: str) -> ModuleError:
    return ModuleError("invalid_argument", message)


def _is_kind(kind: str, value: Any, required: bool) -> bool:
    if kind == "text":
        return isinstance(value, str) and (value != "" or not required)
    if kind == "int":
        return type(value) is int and value >= 0
    if kind == "bool":
        return isinstance(value, bool)
    if kind == "texts":
        return isinstance(value, list) and all(isinstance(item, str) and item for item in value)
    return isinstance(value, dict)


def clean(value: Any, spec: Spec, what: str) -> dict:
    """Validate one incoming object against ``spec`` and fill the defaults."""
    if not isinstance(value, dict):
        raise invalid(f"{what} must be an object")
    unknown = sorted(set(value) - set(spec))
    if unknown:
        raise invalid(f"{what} has unknown fields: {', '.join(unknown)}")
    row: dict = {}
    for name, (kind, required, default) in spec.items():
        item = value.get(name)
        if item is None:
            if required:
                raise invalid(f"{what}.{name} is required")
            row[name] = copy.deepcopy(default)
        elif not _is_kind(kind, item, required):
            raise invalid(f"{what}.{name} must be {_DESCRIPTIONS[kind]}")
        else:
            row[name] = item
    return row


_DESCRIPTIONS = {
    "text": "a string (not empty when the field is required)",
    "int": "a non-negative integer",
    "bool": "a boolean",
    "texts": "a list of non-empty strings",
    "object": "an object",
}


def encode(row: dict, spec: Spec) -> list:
    """Column values in ``spec`` order."""
    values = []
    for name, (kind, _required, _default) in spec.items():
        item = row[name]
        if item is not None and kind == "bool":
            item = 1 if item else 0
        elif item is not None and kind in ("texts", "object"):
            item = dumps(item)
        values.append(item)
    return values


def decode(stored: sqlite3.Row, spec: Spec) -> dict:
    row: dict = {}
    for name, (kind, _required, _default) in spec.items():
        item = stored[name]
        if item is not None and kind == "bool":
            item = bool(item)
        elif item is not None and kind in ("texts", "object"):
            item = loads(item)
        row[name] = item
    return row
