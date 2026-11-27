"""Shared helpers for configuring the reference agent in tests."""

from __future__ import annotations

import json
from typing import Any, cast

from cogit_agent_sdk import AgentServices
from cogit_agent_sdk.types import TextContent, ToolResult

from seller_agent import Agent


def configured_seller_agent() -> Agent:
    """Return a reference agent after runtime-equivalent configure()."""

    agent = Agent()
    agent.configure(AgentServices())
    return agent


def tool_result_payload(result: ToolResult) -> dict[str, Any]:
    """Decode a model-facing tool result payload from broker output."""

    assert result.content
    block = result.content[0]
    assert isinstance(block, TextContent)
    return cast(dict[str, Any], json.loads(block.text))
