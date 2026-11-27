"""Lossless carrier for commerce's native AgentDb export contracts."""

from __future__ import annotations

import json

from .protocols import ModuleError

NATIVE_MODULES = frozenset(
    {"cogit-messaging", "cogit-finance-catalog", "cogit-finance-deals"}
)
MAX_CARRIER_CHARS = 65536


def encode_args(args: dict | None) -> dict:
    value = json.dumps(
        args or {},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    if len(value) > MAX_CARRIER_CHARS:
        raise ModuleError(
            "payload_too_large", "Native module payload exceeds 65536 characters"
        )
    return {"payload": value}


def decode_result(response: dict) -> dict:
    if not isinstance(response, dict) or not isinstance(response.get("result"), str):
        raise ModuleError(
            "invalid_module_response", "Expected the native result carrier"
        )
    result = json.loads(response["result"])
    if not isinstance(result, dict):
        raise ModuleError("invalid_module_response", "Module results must be objects")
    if "_module_error" in result:
        raise ModuleError(result["_module_error"])
    return result
