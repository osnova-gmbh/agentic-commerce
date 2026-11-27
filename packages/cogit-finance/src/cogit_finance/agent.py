"""Resident agent implementation for the cloneable template."""

from __future__ import annotations

import argparse
import asyncio
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
from cogit_agent_sdk.types import AgentLoopConfig, Context, RunBudget, RunRequest
from cogit_tool_core.providers import ProviderBundle

from cogit_finance.capabilities import (
    configuration,
    prepare_capabilities,
)
from cogit_finance.dependencies import (
    AgentDependencies,
    build_dependencies,
)
from cogit_finance.lifecycle import close_all
from cogit_finance.operations import (
    InternalOperations,
    build_internal_operations,
    register_domain_action_bindings,
    register_domain_tool_bindings,
)
from cogit_finance.resources import load_prompt


class Agent(CogitAgent):
    """Minimal agent that demonstrates lifecycle, tools, and gated writes."""

    def __init__(self) -> None:
        super().__init__()
        from .identity import create_runtime
        self.identity_runtime = create_runtime()
        self.dependencies: AgentDependencies = build_dependencies()
        self.internal_operations: InternalOperations | None = None
        self.capability_configuration = configuration(self.descriptor)
        self.capabilities: ProviderBundle | None = None

    def configure(self, services: AgentServices) -> None:
        from .database_example import persist_request_binding
        from .escrow_operations import handle_message
        from .schemas import HandleMessageInput
        from cogit_finance_seams.inbox import inbox_binding
        from .bootstrap import bootstrap_binding

        super().configure(services)
        self.internal_operations = build_internal_operations(self)
        action_bindings = register_domain_action_bindings(self)
        self.register_action(inbox_binding(handle_message, HandleMessageInput))
        self.register_action(bootstrap_binding())
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
        await asyncio.to_thread(self.identity_runtime.startup)
        if self.capabilities is not None:
            await self.capabilities.start()

    def handle_run(self, request: RunRequest, context: Context, handle: Any) -> Any:
        from cogit_finance_seams.commands import run_commerce_command
        return run_commerce_command(self, request, context, handle, frozenset({"bootstrap", "tick", "drain_inbox"}))

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
            "identity": self.identity_runtime.status(),
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
        from .identity import identity_commands

        return [
            identity_commands(),
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
        "agent": "cogit-finance",
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
