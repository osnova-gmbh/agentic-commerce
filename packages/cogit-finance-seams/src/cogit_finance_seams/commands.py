"""Deterministic root commands for admitted commerce work; no model loop."""

from __future__ import annotations

import json

from cogit_agent_sdk import OperationInvocation
from cogit_agent_sdk.loop import NoopCancellation


def run_commerce_command(
    agent, request, context, handle, allowed: frozenset[str]
) -> dict:
    value = request.input or {}
    # AgentDb's query admission carries text; processing admissions can carry
    # the object directly. Both enter the same strict command allowlist.
    if isinstance(value, dict) and "command" not in value:
        text = value.get("text") or value.get("instruction") or request.instruction
        try:
            value = json.loads(text)
        except (TypeError, ValueError) as exc:
            raise ValueError("Commerce admission must contain a JSON command") from exc
    if not isinstance(value, dict) or set(value) - {
        "command",
        "payload",
        "instruction",
    }:
        raise ValueError("Commerce work needs command and payload")
    command = value.get("command")
    if command not in allowed:
        raise ValueError(f"Unsupported commerce command: {command!r}")
    payload = value.get("payload", {})
    if not isinstance(payload, dict):
        raise ValueError("Command payload must be an object")
    binding = next(
        (b for b in agent.action_bindings() if b.descriptor.name == command), None
    )
    if binding is None:
        raise ValueError(f"Commerce action is not registered: {command}")
    invocation = OperationInvocation(
        context=context,
        handle=handle,
        cancellation=NoopCancellation(),
        idempotency_key=str(
            (context.metadata or {}).get("run_id") or context.correlation_id
        ),
    )
    result = binding.invoke(
        binding.operation.input_model.model_validate(payload), invocation
    )
    return (
        result.model_dump(mode="json")
        if hasattr(result, "model_dump")
        else dict(result)
    )
