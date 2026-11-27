"""Resident agent implementation for the cloneable template."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from cogit_agent_sdk import (
    AgentServices,
    CliArgument,
    CliCommand,
    CliCommandGroup,
    CogitAgent,
)
from cogit_agent_sdk.types import AgentLoopConfig, Context, RunBudget
from cogit_tool_core.providers import ProviderBundle

from seller_agent.capabilities import (
    configuration,
    prepare_capabilities,
)
from seller_agent.dependencies import (
    AgentDependencies,
    build_dependencies,
)
from seller_agent.lifecycle import close_all
from seller_agent.operations import (
    InternalOperations,
    build_internal_operations,
    register_domain_action_bindings,
    register_domain_tool_bindings,
)
from seller_agent.resources import load_prompt


class Agent(CogitAgent):
    """Minimal agent that demonstrates lifecycle, tools, and gated writes."""

    def __init__(self) -> None:
        super().__init__()
        self.dependencies: AgentDependencies = build_dependencies()
        self.internal_operations: InternalOperations | None = None
        self.capability_configuration = configuration(self.descriptor)
        self.capabilities: ProviderBundle | None = None

    def configure(self, services: AgentServices) -> None:
        from .database_example import persist_request_binding

        super().configure(services)
        self.internal_operations = build_internal_operations(self)
        action_bindings = register_domain_action_bindings(self)
        self.register_action(persist_request_binding())
        register_domain_tool_bindings(self, action_bindings)
        functions = self.dependencies.functions
        self.register_tool(functions.as_dispatch_tool_binding())
        self.register_tool(functions.as_describe_tool_binding())
        self.capability_configuration = configuration(self.descriptor)
        self.capabilities = prepare_capabilities(
            self.descriptor, self.capability_configuration
        )
        if self.capabilities is not None:
            for binding in self.capabilities.bindings:
                self.register_tool(binding)

    async def startup(self) -> None:
        if self.capabilities is not None:
            await self.capabilities.start()

    async def shutdown(self) -> None:
        resources = self.dependencies.closeables
        if self.capabilities is not None:
            resources = (*resources, self.capabilities)
        await close_all(resources)

    async def execution_finished(self, context: Context) -> None:
        """Release ended execution resources after Runtime drains their operations."""
        if self.capabilities is not None:
            await self.capabilities.release_scope(context)

    def health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "records": len(self.dependencies.records.records),
            "sessions": len(self.dependencies.session_store.sessions),
        }

    def system_prompt(self, context: Context) -> str:
        del context
        base = (
            "workspace.md"
            if self.capability_configuration.profile == "workspace"
            else "system.md"
        )
        fragments = self.capabilities.prompt_fragments if self.capabilities else ()
        return "\n\n".join((load_prompt(base), *fragments))

    def loop_config(self, context: Context) -> AgentLoopConfig:
        config = super().loop_config(context)
        if not self.capability_configuration.providers:
            return config
        bounds = self.capability_configuration.budget
        return config.model_copy(
            update={
                "max_turns": bounds.turns,
                "wall_clock_timeout_seconds": bounds.seconds,
                "budget": RunBudget(
                    max_iterations=bounds.turns,
                    max_tool_calls=bounds.tools,
                    max_duration_seconds=bounds.seconds,
                ),
            }
        )

    def commands(self) -> list[CliCommandGroup]:
        return [
            CliCommandGroup(
                name="reference-report",
                help="Synthetic reference-agent report utilities",
                commands=[
                    CliCommand(
                        name="emit",
                        help="Write a synthetic case summary report to disk",
                        arguments=[
                            CliArgument(("--output",), default="report.json"),
                        ],
                        handler=_emit_report,
                    ),
                ],
            ),
        ]


def _emit_report(services: AgentServices, args: argparse.Namespace) -> int:
    del services
    dependencies = build_dependencies()
    records = dependencies.records.records
    summary = {
        "agent": "seller-agent",
        "record_count": len(records),
        "records": [
            {"record_id": record_id, "status": status}
            for record_id, status in sorted(records.items())
        ],
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0
