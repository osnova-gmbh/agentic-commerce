"""Typed action surface checks for Proposal 019 explicit bindings."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
import yaml
from agent_helpers import configured_evaluator_agent
from cogit_agent_sdk import (
    AgentServices,
    FunctionParameter,
    OperationInvocation,
    bind_action,
    bind_tool_from_action,
    function,
    operation,
)
from cogit_agent_sdk.contracts import RunHandle
from cogit_agent_sdk.functions import RunFunctionInput
from cogit_agent_sdk.loop import NoopCancellation
from cogit_agent_sdk.resident import CogitAgent
from cogit_agent_sdk.types import Context
from cogit_runtime import CogitRuntimeApp
from cogit_runtime.errors import RuntimeConfigurationError
from fastapi.testclient import TestClient

from evaluator_agent import Agent
from evaluator_agent.schemas import (
    LookupRecordInput,
    LookupRecordOutput,
)

ROOT = Path(__file__).resolve().parents[1]


@function(
    name="probe_after_configure",
    description="Probe function registered after configure.",
    parameters=[
        FunctionParameter(
            name="seen",
            type="bool",
            required=True,
            description="Whether configure-time wiring is visible.",
        ),
    ],
)
def probe_after_configure(seen: bool) -> dict[str, bool]:
    return {"seen": seen}


class ProbeAgent(Agent):
    """Registers a probe function after configure to test handler wiring."""

    def configure(self, services: AgentServices) -> None:
        super().configure(services)
        self.dependencies.functions.register(
            name="probe_after_configure",
            function=probe_after_configure,
            description="Probe function registered after configure.",
            parameters=[
                FunctionParameter(
                    name="seen",
                    type="bool",
                    required=True,
                    description="Whether configure-time wiring is visible.",
                ),
            ],
        )


class BreachLookupAgent(CogitAgent):
    """Returns output that fails post-invocation validation."""

    def configure(self, services: AgentServices) -> None:
        super().configure(services)

        def breach_lookup(
            request: LookupRecordInput,
            invocation: OperationInvocation,
        ) -> LookupRecordOutput:
            del request, invocation
            return cast(LookupRecordOutput, {"broken": True})

        self.register_action(
            bind_action(
                operation(breach_lookup),
                name="lookup_record",
                description="Look up a synthetic service record.",
                risk="read",
                idempotency="inherent",
            ),
        )


class CountingLookupActionAgent(CogitAgent):
    """Counts action-path invocations with action-only exposure."""

    def __init__(self) -> None:
        super().__init__()
        self.invocation_count = 0

    def configure(self, services: AgentServices) -> None:
        super().configure(services)
        agent = self

        def counting_lookup(
            request: LookupRecordInput,
            invocation: OperationInvocation,
        ) -> LookupRecordOutput:
            del invocation
            agent.invocation_count += 1
            return LookupRecordOutput(record_id=request.record_id, status="open")

        self.register_action(
            bind_action(
                operation(counting_lookup),
                name="lookup_record",
                description="Look up a synthetic service record.",
                risk="read",
                idempotency="inherent",
            ),
        )


class CountingLookupDualAgent(CountingLookupActionAgent):
    """Counts invocations with explicit dual-bound lookup exposure."""

    def configure(self, services: AgentServices) -> None:
        super().configure(services)
        lookup_action = next(
            binding
            for binding in self.action_bindings()
            if binding.descriptor.name == "lookup_record"
        )
        self.register_tool(
            bind_tool_from_action(
                lookup_action,
                execution_mode="parallel",
            ),
        )


@pytest.mark.asyncio
async def test_configure_binds_final_function_registry_tools() -> None:
    agent = ProbeAgent()
    agent.configure(AgentServices())
    agent.freeze_tool_registration()

    context = Context(
        tenant_id="test-tenant",
        correlation_id="probe-configure",
        agent_id="evaluator-agent",
    )
    handle = RunHandle("probe-exec", context)
    run_binding = next(
        binding
        for binding in agent.tool_bindings()
        if binding.descriptor.name == "run_function"
    )
    output = run_binding.operation(
        RunFunctionInput(
            function_name="probe_after_configure",
            parameters={"seen": True},
        ),
        OperationInvocation(
            context=context,
            handle=handle,
            cancellation=NoopCancellation(),
        ),
    )
    assert output.error is None
    assert output.result == {"seen": True}


def test_typed_http_action_rejects_invalid_input(client: TestClient) -> None:
    response = client.post("/actions/lookup_record", json={"record_id": ""})
    assert response.status_code == 400

    missing = client.post("/actions/validate_request", json={"request_id": "req-1"})
    assert missing.status_code == 400


@pytest.mark.asyncio
async def test_typed_tool_route_rejects_invalid_input(
    client: TestClient,
    runtime: CogitRuntimeApp,
) -> None:
    del client
    host = runtime.state.loop_host
    result = await host.tool_broker.execute(
        "lookup_record",
        {"record_id": ""},
        Context(
            tenant_id="test-tenant",
            correlation_id="typed-action-test",
            agent_id="evaluator-agent",
        ),
        tool_call_id="typed-tool-invalid",
        execution_id="typed-tool-invalid",
        cancellation=NoopCancellation(),
    )
    assert result.is_error is True


def test_typed_http_action_accepts_valid_input(client: TestClient) -> None:
    response = client.post(
        "/actions/lookup_record",
        json={"record_id": "record-open"},
    )
    assert response.status_code == 200
    assert response.json() == {"record_id": "record-open", "status": "open"}


@pytest.mark.asyncio
async def test_dual_bound_lookup_invokes_operation_exactly_once_via_action(
    tmp_path: Path,
) -> None:
    manifest_path = _counting_lookup_manifest_path(tmp_path, include_tools=False)
    runtime = _counting_runtime(manifest_path, CountingLookupActionAgent)
    host = runtime.state.loop_host
    agent = cast(CountingLookupActionAgent, runtime.state.agent)

    result = await host.execute_bound_action(
        "lookup_record",
        {"record_id": "record-open"},
        Context(
            tenant_id="test-tenant",
            correlation_id="count-action",
            agent_id="count-agent",
        ),
        "exec-count-action",
    )
    assert result.status == "succeeded"
    assert agent.invocation_count == 1


@pytest.mark.asyncio
async def test_dual_bound_lookup_invokes_operation_exactly_once_via_tool(
    tmp_path: Path,
) -> None:
    manifest_path = _counting_lookup_manifest_path(tmp_path, include_tools=True)
    runtime = _counting_runtime(manifest_path, CountingLookupDualAgent)
    host = runtime.state.loop_host
    agent = cast(CountingLookupDualAgent, runtime.state.agent)

    result = await host.tool_broker.execute(
        "lookup_record",
        {"record_id": "record-open"},
        Context(
            tenant_id="test-tenant",
            correlation_id="count-tool",
            agent_id="count-agent",
        ),
        tool_call_id="count-tool",
        execution_id="count-tool",
        cancellation=NoopCancellation(),
    )
    assert result.is_error is False
    assert agent.invocation_count == 1


def _counting_lookup_manifest_path(tmp_path: Path, *, include_tools: bool) -> Path:
    agent: CogitAgent = (
        CountingLookupDualAgent() if include_tools else CountingLookupActionAgent()
    )
    agent.configure(AgentServices())
    lookup_action = next(
        binding
        for binding in agent.action_bindings()
        if binding.descriptor.name == "lookup_record"
    )
    manifest: dict[str, object] = {
        "id": "count-agent",
        "name": "Count Agent",
        "version": "0.1.0",
        "description": "Invocation counting test agent",
        "actions": [lookup_action.descriptor.model_dump(mode="json", by_alias=False)],
        "tools": [],
    }
    if include_tools:
        lookup_tool = next(
            binding
            for binding in agent.tool_bindings()
            if binding.descriptor.name == "lookup_record"
        )
        manifest["tools"] = [
            lookup_tool.descriptor.model_dump(mode="json", by_alias=False),
        ]
    manifest_path = tmp_path / "cogit.yaml"
    manifest_path.write_text(
        yaml.safe_dump(manifest, sort_keys=False),
        encoding="utf-8",
    )
    return manifest_path


def _counting_runtime(
    manifest_path: Path,
    agent_class: type[CogitAgent],
) -> CogitRuntimeApp:
    return CogitRuntimeApp._from_manifest_for_testing(
        manifest_path,
        agent_class=agent_class,
        env={
            "COGIT_DEV_MODE": "1",
            "COGIT_TENANT_ID": "test-tenant",
        },
    )


def _single_lookup_manifest_path(tmp_path: Path) -> Path:
    configured = configured_evaluator_agent()
    lookup_binding = next(
        binding
        for binding in configured.action_bindings()
        if binding.descriptor.name == "lookup_record"
    )
    manifest = {
        "id": "breach-agent",
        "name": "Breach Agent",
        "version": "0.1.0",
        "description": "Typed output breach test agent",
        "actions": [lookup_binding.descriptor.model_dump(mode="json", by_alias=False)],
        "tools": [],
    }
    manifest_path = tmp_path / "cogit.yaml"
    manifest_path.write_text(
        yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8"
    )
    return manifest_path


def test_typed_output_mismatch_returns_contract_breach_http(tmp_path: Path) -> None:
    manifest_path = _single_lookup_manifest_path(tmp_path)

    runtime = CogitRuntimeApp._from_manifest_for_testing(
        manifest_path,
        agent_class=BreachLookupAgent,
        env={
            "COGIT_DEV_MODE": "1",
            "COGIT_TENANT_ID": "test-tenant",
        },
    )
    with TestClient(runtime.build()) as test_client:
        response = test_client.post(
            "/actions/lookup_record",
            json={"record_id": "record-open"},
        )

    assert response.status_code == 500


@pytest.mark.asyncio
async def test_typed_output_mismatch_via_executor(tmp_path: Path) -> None:
    manifest_path = _single_lookup_manifest_path(tmp_path)

    runtime = CogitRuntimeApp._from_manifest_for_testing(
        manifest_path,
        agent_class=BreachLookupAgent,
        env={
            "COGIT_DEV_MODE": "1",
            "COGIT_TENANT_ID": "test-tenant",
        },
    )
    host = runtime.state.loop_host
    result = await host.execute_bound_action(
        "lookup_record",
        {"record_id": "record-open"},
        Context(
            tenant_id="test-tenant",
            correlation_id="breach-test",
            agent_id="breach-agent",
        ),
        "exec-breach",
    )
    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "INVALID_OUTPUT"


def _production_manifest(tmp_path: Path) -> Path:
    """Check binding parity with an explicit model-free production profile."""
    payload = yaml.safe_load((ROOT / "cogit.yaml").read_text(encoding="utf-8"))
    payload["runtime"]["model"] = {"profile": "disabled"}
    manifest = tmp_path / "cogit.yaml"
    manifest.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return manifest


def test_production_boot_requires_configured_agentdb(tmp_path: Path) -> None:
    with pytest.raises(RuntimeConfigurationError, match="COGIT_AGENTDB_URL"):
        CogitRuntimeApp.from_manifest(
            _production_manifest(tmp_path), agent_class=Agent, env={}
        )


def test_production_boot_fails_on_manifest_schema_drift(tmp_path: Path) -> None:
    drift_manifest = _production_manifest(tmp_path)
    drift_manifest.write_text(
        drift_manifest.read_text(encoding="utf-8").replace(
            "LookupRecordInput",
            "DriftedLookupRecordInput",
            1,
        ),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeConfigurationError, match="parity check failed"):
        CogitRuntimeApp._from_manifest_for_testing(
            drift_manifest,
            agent_class=Agent,
            env={
                "COGIT_AGENT_API_KEY": "template-production-test",
                "COGIT_TENANT_ID": "test-tenant",
            },
        )


def test_production_boot_fails_on_unknown_manifest_action_field(tmp_path: Path) -> None:
    drift_manifest = tmp_path / "cogit.yaml"
    drift_manifest.write_text(
        (ROOT / "cogit.yaml")
        .read_text(encoding="utf-8")
        .replace(
            "- name: lookup_record\n",
            "- name: lookup_record\n  unexpected_field: true\n",
            1,
        ),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeConfigurationError, match="unknown manifest field"):
        CogitRuntimeApp._from_manifest_for_testing(
            drift_manifest,
            agent_class=Agent,
            env={
                "COGIT_AGENT_API_KEY": "template-production-test",
                "COGIT_TENANT_ID": "test-tenant",
            },
        )


def test_unconfigured_agent_has_no_bindings() -> None:
    agent = Agent()
    assert len(agent.action_bindings()) == 0
    assert len(agent.tool_bindings()) == 0
    assert agent.internal_operations is None


def test_configured_agent_exposes_final_action_and_tool_inventories() -> None:
    agent = configured_evaluator_agent()
    assert {binding.descriptor.name for binding in agent.action_bindings()} == {
        "lookup_record",
        "validate_request",
        "apply_resolution",
        "lookup_resolution",
        "persist_reference_request",
        "handle_message",
    }
    assert {binding.descriptor.name for binding in agent.tool_bindings()} == {
        "lookup_record",
        "validate_request",
        "run_function",
        "describe_function",
    }
    assert agent.internal_operations is not None
