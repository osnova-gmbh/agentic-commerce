"""Offline tests for the reference agent's function registry integration."""

from __future__ import annotations

from typing import Any, cast

import pytest
from agent_helpers import (
    configured_buyer_agent,
    tool_result_payload,
)
from cogit_agent_sdk.loop import NoopCancellation
from cogit_agent_sdk.types import Context
from cogit_runtime import CogitRuntimeApp

from buyer_agent.dependencies import (
    build_dependencies,
)
from buyer_agent.functions.scoring import (
    score_record_risk,
)


def test_registry_loads_scoring_function() -> None:
    registry = build_dependencies().functions

    assert registry.list_functions() == ["score_record_risk"]


def test_registry_call_returns_expected_result() -> None:
    registry = build_dependencies().functions

    result = registry.call(
        "score_record_risk",
        record_id="record-open",
        factors=["late", "unverified"],
    )

    assert result == score_record_risk(
        record_id="record-open",
        factors=["late", "unverified"],
    )
    body = cast(dict[str, Any], result)
    assert body["record_id"] == "record-open"
    assert body["factors"] == ["late", "unverified"]
    assert isinstance(body["score"], int)
    assert body["level"] in {"low", "medium", "high"}


@pytest.mark.asyncio
async def test_dispatch_tool_returns_result(runtime: CogitRuntimeApp) -> None:
    host = runtime.state.loop_host
    result = await host.tool_broker.execute(
        "run_function",
        {
            "function_name": "score_record_risk",
            "parameters": {"record_id": "record-open", "factors": ["late"]},
        },
        Context(
            tenant_id="test-tenant",
            correlation_id="function-registry-dispatch",
            agent_id="buyer-agent",
        ),
        tool_call_id="dispatch-tool",
        execution_id="dispatch-tool",
        cancellation=NoopCancellation(),
    )

    assert result.is_error is False
    body = tool_result_payload(result)
    assert body["result"] == score_record_risk(
        record_id="record-open",
        factors=["late"],
    )


@pytest.mark.asyncio
async def test_dispatch_tool_unknown_function_returns_error_not_exception(
    runtime: CogitRuntimeApp,
) -> None:
    host = runtime.state.loop_host
    result = await host.tool_broker.execute(
        "run_function",
        {"function_name": "does_not_exist"},
        Context(
            tenant_id="test-tenant",
            correlation_id="function-registry-not-found",
            agent_id="buyer-agent",
        ),
        tool_call_id="dispatch-tool-missing",
        execution_id="dispatch-tool-missing",
        cancellation=NoopCancellation(),
    )

    assert result.is_error is False
    body = tool_result_payload(result)
    assert "error" in body
    error = cast(dict[str, Any], body["error"])
    assert error["code"] == "FUNCTION_NOT_FOUND"
    assert "does_not_exist" in error["message"]


@pytest.mark.asyncio
async def test_describe_tool_returns_metadata_for_known_function(
    runtime: CogitRuntimeApp,
) -> None:
    host = runtime.state.loop_host
    result = await host.tool_broker.execute(
        "describe_function",
        {"function_name": "score_record_risk"},
        Context(
            tenant_id="test-tenant",
            correlation_id="function-registry-describe",
            agent_id="buyer-agent",
        ),
        tool_call_id="describe-tool",
        execution_id="describe-tool",
        cancellation=NoopCancellation(),
    )

    assert result.is_error is False
    body = tool_result_payload(result)
    assert body["name"] == "score_record_risk"
    assert body["category"] == "risk"
    assert any(param["name"] == "record_id" for param in body["parameters"])


@pytest.mark.asyncio
async def test_describe_tool_unknown_function_lists_available(
    runtime: CogitRuntimeApp,
) -> None:
    host = runtime.state.loop_host
    result = await host.tool_broker.execute(
        "describe_function",
        {"function_name": "does_not_exist"},
        Context(
            tenant_id="test-tenant",
            correlation_id="function-registry-describe-missing",
            agent_id="buyer-agent",
        ),
        tool_call_id="describe-tool-missing",
        execution_id="describe-tool-missing",
        cancellation=NoopCancellation(),
    )

    assert result.is_error is False
    body = tool_result_payload(result)
    assert "error" in body
    error = cast(dict[str, Any], body["error"])
    assert error["code"] == "FUNCTION_NOT_FOUND"
    assert "score_record_risk" in error["available_functions"]


def test_function_registry_tools_are_absent_from_action_inventory() -> None:
    agent = configured_buyer_agent()
    action_names = {binding.descriptor.name for binding in agent.action_bindings()}
    tool_names = {binding.descriptor.name for binding in agent.tool_bindings()}
    assert "run_function" not in action_names
    assert "describe_function" not in action_names
    assert {"run_function", "describe_function"}.issubset(tool_names)
