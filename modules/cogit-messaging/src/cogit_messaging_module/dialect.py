"""The schema dialect a message type may use (SPEC §6.1).

AgentDb's assertion dialect: ``type``, ``properties``, ``required``,
``additionalProperties: false``, ``items``, ``enum``, ``minLength``, ``maxLength``,
``minimum``, ``maximum``, ``minItems``, ``maxItems``, ``description`` and nullable
unions (``"type": [T, "null"]``). Anything else is refused at registration.
"""

from __future__ import annotations

from typing import Any

from cogit_finance_seams import ModuleError

KEYWORDS = frozenset(
    {
        "type",
        "properties",
        "required",
        "additionalProperties",
        "items",
        "enum",
        "minLength",
        "maxLength",
        "minimum",
        "maximum",
        "minItems",
        "maxItems",
        "description",
    }
)
TYPES = frozenset({"object", "array", "string", "integer", "number", "boolean", "null"})
_SIZES = ("minLength", "maxLength", "minItems", "maxItems")
_BOUNDS = ("minimum", "maximum")


def _unsupported(path: str, problem: str) -> ModuleError:
    return ModuleError("unsupported_schema", f"{path}: {problem}")


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _check_type(value: Any, path: str) -> None:
    if isinstance(value, str):
        if value not in TYPES:
            raise _unsupported(path, f"unknown type {value!r}")
        return
    names = value if isinstance(value, list) else []
    if len(names) != 2 or "null" not in names or names[0] == names[1] or any(name not in TYPES for name in names):
        raise _unsupported(path, 'type must be a type name or a nullable union [T, "null"]')


def check_dialect(schema: Any, path: str = "$") -> None:
    """Raise ``ModuleError("unsupported_schema")`` unless ``schema`` stays inside the dialect."""
    if not isinstance(schema, dict):
        raise _unsupported(path, "a schema must be a JSON object")
    for keyword in schema:
        if keyword not in KEYWORDS:
            raise _unsupported(path, f"keyword {keyword!r} is outside the supported dialect")
    if "type" in schema:
        _check_type(schema["type"], path)
    if "description" in schema and not isinstance(schema["description"], str):
        raise _unsupported(path, "description must be a string")
    if "additionalProperties" in schema and schema["additionalProperties"] is not False:
        raise _unsupported(path, "additionalProperties may only be false")
    if "required" in schema:
        names = schema["required"]
        if not isinstance(names, list) or any(not isinstance(name, str) for name in names):
            raise _unsupported(path, "required must be a list of property names")
    if "enum" in schema:
        values = schema["enum"]
        if not isinstance(values, list) or not values:
            raise _unsupported(path, "enum must be a non-empty list")
        if any(not (value is None or isinstance(value, (str, bool)) or _is_int(value)) for value in values):
            raise _unsupported(path, "enum values must be strings, integers, booleans or null")
    for keyword in _SIZES:
        if keyword in schema and not (_is_int(schema[keyword]) and schema[keyword] >= 0):
            raise _unsupported(path, f"{keyword} must be a non-negative integer")
    for keyword in _BOUNDS:
        if keyword in schema and not _is_int(schema[keyword]):
            raise _unsupported(path, f"{keyword} must be an integer")
    if "properties" in schema:
        properties = schema["properties"]
        if not isinstance(properties, dict):
            raise _unsupported(path, "properties must be an object")
        for name, child in properties.items():
            check_dialect(child, f"{path}.properties.{name}")
    if "items" in schema:
        check_dialect(schema["items"], f"{path}.items")
