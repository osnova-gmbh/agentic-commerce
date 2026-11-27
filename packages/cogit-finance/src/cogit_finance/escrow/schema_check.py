# pyright: basic
"""Validator for AgentDb's assertion dialect of JSON Schema (SPEC §6.1).

The message schemas use only ``type`` (also as a nullable union), ``properties``,
``required``, ``additionalProperties: false``, ``items``, ``enum``, ``minLength``,
``maxLength``, ``minimum``, ``maximum``, ``minItems``, ``maxItems`` and
``description``. The messaging module validates bodies on ``message.send``; E checks
again before it relies on a body.
"""

from __future__ import annotations

from typing import Any

_TYPES: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "object": (dict,),
    "array": (list,),
    "boolean": (bool,),
}


def _is(value: Any, name: str) -> bool:
    if name == "null":
        return value is None
    if isinstance(value, bool):
        return name == "boolean"
    return isinstance(value, _TYPES.get(name, ()))


def validate(schema: dict[str, Any], value: Any, path: str = "body") -> str | None:
    """The first violation as text, or None when the value fits the schema."""
    declared = schema.get("type")
    if declared is not None:
        names = declared if isinstance(declared, list) else [declared]
        if not any(_is(value, name) for name in names):
            return f"{path}: expected {' or '.join(names)}"
    if value is None:
        return None
    if "enum" in schema and value not in schema["enum"]:
        return f"{path}: not one of the allowed values"
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            return f"{path}: shorter than minLength"
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            return f"{path}: longer than maxLength"
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            return f"{path}: below minimum"
        if "maximum" in schema and value > schema["maximum"]:
            return f"{path}: above maximum"
    elif isinstance(value, list):
        return _array(schema, value, path)
    elif isinstance(value, dict):
        return _object(schema, value, path)
    return None


def _array(schema: dict[str, Any], value: list[Any], path: str) -> str | None:
    if len(value) < schema.get("minItems", 0):
        return f"{path}: fewer than minItems"
    if "maxItems" in schema and len(value) > schema["maxItems"]:
        return f"{path}: more than maxItems"
    items = schema.get("items")
    if isinstance(items, dict):
        for index, item in enumerate(value):
            error = validate(items, item, f"{path}[{index}]")
            if error:
                return error
    return None


def _object(schema: dict[str, Any], value: dict[str, Any], path: str) -> str | None:
    for name in schema.get("required", []):
        if name not in value:
            return f"{path}.{name}: required"
    properties = schema.get("properties", {})
    for name, item in value.items():
        if name in properties:
            error = validate(properties[name], item, f"{path}.{name}")
            if error:
                return error
        elif schema.get("additionalProperties") is False:
            return f"{path}.{name}: not allowed"
    return None
