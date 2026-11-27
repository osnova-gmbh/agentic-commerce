"""Provider selection must use the same pure inventory in setup and Runtime."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from cogit_agent_sdk import AgentServices
from cogit_agent_sdk.operations import OperationInvocation, ToolBinding
from cogit_agent_sdk.types import Context, ToolDescriptor
from cogit_tool_core import Model
from cogit_tool_core.providers import PreparedTools, ToolProvider
from pydantic import ValidationError

from cogit_finance.agent import Agent
from cogit_finance.capabilities import (
    CapabilityConfiguration,
)
from cogit_finance_setup import (
    configured_agent,
    main,
    read_manifest,
    resolved_manifest,
)

ROOT = Path(__file__).resolve().parents[1]


class Request(Model):
    customer: str


class Response(Model):
    found: bool


class Settings(Model):
    label: str = "customer-directory"


class Lookup:
    input_model = Request
    output_model = Response

    def __call__(self, request: Request, invocation: OperationInvocation) -> Response:
        del invocation
        return Response(found=request.customer == "fixture-customer")


def selected_provider(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """An unrelated API provider, without any browser or application dependency."""
    events: list[str] = []

    async def start() -> None:
        events.append("start")

    async def close() -> None:
        events.append("close")

    async def release(context: Context) -> None:
        events.append("release:" + (context.execution_id or "missing"))

    def prepare(
        settings: Settings, host: object, dependencies: object
    ) -> PreparedTools:
        del host, dependencies
        events.append("prepare")
        binding = ToolBinding(
            operation=Lookup(),
            descriptor=ToolDescriptor(
                name="customer_lookup",
                description=settings.label,
                input_schema=Request.model_json_schema(),
                output_schema=Response.model_json_schema(),
                risk="read",
                idempotency="inherent",
            ),
        )
        return PreparedTools(
            (binding,),
            ("Inspect the customer directory.",),
            start,
            close,
            release_scope=release,
        )

    provider = ToolProvider(Settings, prepare)

    class Entry:
        name = "fixture-api"

        def load(self) -> ToolProvider[Settings]:
            return provider

    monkeypatch.setattr(
        "cogit_tool_core.providers.entry_points", lambda **kwargs: [Entry()]
    )
    return events


def manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    monkeypatch.setenv("COGIT_WORKSPACE_ROOT", str(tmp_path / "not-created"))
    monkeypatch.setenv("COGIT_TENANT_ID", "fixture-tenant")
    payload = read_manifest(ROOT / "cogit.yaml")
    payload["model"] = {
        "provider": "openai",
        "model": "fixture-model",
        "context_window": 32000,
        "max_output_tokens": 1024,
        "supports_tools": True,
    }
    payload["runtime"]["model"] = {"profile": "sdk"}
    payload["metadata"]["cogit_tools"] = {
        "version": 1,
        "profile": "workspace",
        "providers": [{"id": "customers", "provider": "fixture-api"}],
    }
    return payload


def test_reference_profile_never_discovers_external_providers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(**kwargs: object) -> object:
        raise AssertionError("Reference profile must not discover external tools")

    monkeypatch.setattr("cogit_tool_core.providers.entry_points", forbidden)
    agent = Agent()
    agent.configure(AgentServices())
    assert agent.capabilities is None
    assert "customer_lookup" not in {
        tool.descriptor.name for tool in agent.tool_bindings()
    }


@pytest.mark.parametrize("version", [True, "1", 2])
def test_version_rejects_coercion(version: object) -> None:
    with pytest.raises(ValidationError):
        CapabilityConfiguration.model_validate({"version": version})


@pytest.mark.parametrize("names", [["PATH", "PATH"], ["BAD=NAME"], [""]])
def test_environment_references_are_names_not_values(names: list[str]) -> None:
    with pytest.raises(ValidationError):
        CapabilityConfiguration(environment_names=names)


def test_setup_exports_selected_typed_tools_without_starting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events = selected_provider(monkeypatch)
    payload = manifest(tmp_path, monkeypatch)
    exported = resolved_manifest(payload)
    tool = next(item for item in exported["tools"] if item["name"] == "customer_lookup")
    assert tool["input_schema"] == Request.model_json_schema()
    assert tool["output_schema"] == Response.model_json_schema()
    assert tool["risk"] == "read"
    assert exported["metadata"]["cogit_policy"] == {
        "authority": "agentdb",
        "contract": "runtime.checkpoint.v1",
    }
    runtime_policy = next(
        item
        for item in exported["database_packages"]
        if item["module_key"] == "cogit.runtime-policy"
    )
    assert runtime_policy["exports"][0]["key"] == "checkpoint.evaluate"
    current_policy = next(
        item
        for item in exported["database_packages"]
        if item["module_key"] == "cogit.universal-policy"
    )
    assert current_policy["exports"][0]["contract_id"] == "universal-policy.v1"
    assert current_policy["artifact_sha256"] == (
        "490032710ff6c013b334ad6e38f89dc76b2529390a070934c844fae09f1dcc14"
    )
    assert events == ["prepare"]
    assert not (tmp_path / "not-created").exists()
    assert resolved_manifest(exported) == exported


@pytest.mark.asyncio
async def test_agent_starts_and_closes_selected_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events = selected_provider(monkeypatch)
    agent = configured_agent(manifest(tmp_path, monkeypatch))
    assert events == ["prepare"]
    await agent.startup()
    assert events == ["prepare", "start"]
    assert "customer directory" in agent.system_prompt(None)  # type: ignore[arg-type]
    await agent.execution_finished(
        Context(
            tenant_id="fixture-tenant",
            agent_id=agent.descriptor.id,
            execution_id="first",
            correlation_id="scope-proof",
        )
    )
    assert events == ["prepare", "start", "release:first"]
    await agent.shutdown()
    assert events == ["prepare", "start", "release:first", "close"]


def test_manifest_sync_honors_configured_inventory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import yaml

    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    from manifest_sync import sync_manifest_payload, validate_manifest_file

    events = selected_provider(monkeypatch)
    payload = manifest(tmp_path, monkeypatch)
    path = tmp_path / "agent.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    assert validate_manifest_file(path), (
        "The undeclared selected provider must fail parity"
    )
    exported = sync_manifest_payload(path)
    path.write_text(yaml.safe_dump(exported), encoding="utf-8")
    assert validate_manifest_file(path) == []
    assert all(item == "prepare" for item in events)


def test_setup_check_detects_stale_inventory_without_mutating(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import yaml

    selected_provider(monkeypatch)
    path = tmp_path / "agent.yaml"
    path.write_text(yaml.safe_dump(manifest(tmp_path, monkeypatch)), encoding="utf-8")
    before = path.read_bytes()
    with pytest.raises(SystemExit) as error:
        main(["--manifest", str(path), "--check"])
    assert error.value.code == 1
    assert path.read_bytes() == before
    assert main(["--manifest", str(path)]) == 0
    assert main(["--manifest", str(path), "--check"]) == 0


def test_setup_rejects_conflicting_policy_without_starting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events = selected_provider(monkeypatch)
    payload = manifest(tmp_path, monkeypatch)
    payload["metadata"]["cogit_policy"] = {"authority": "agent-local"}
    with pytest.raises(ValueError, match="AgentDB lifecycle"):
        resolved_manifest(payload)
    assert events == []


def test_setup_rejects_a_conflicting_policy_service_pin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selected_provider(monkeypatch)
    exported = resolved_manifest(manifest(tmp_path, monkeypatch))
    runtime_policy = next(
        item
        for item in exported["database_packages"]
        if item["module_key"] == "cogit.runtime-policy"
    )
    runtime_policy["artifact_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="Policy service package differs"):
        resolved_manifest(exported)


def test_setup_rejects_a_conflicting_complete_set_policy_pin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selected_provider(monkeypatch)
    exported = resolved_manifest(manifest(tmp_path, monkeypatch))
    policy = next(
        item
        for item in exported["database_packages"]
        if item["module_key"] == "cogit.universal-policy"
    )
    policy["artifact_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="Policy service package differs"):
        resolved_manifest(exported)


@pytest.mark.parametrize("field", ["authority", "package"])
@pytest.mark.parametrize("explicit_agent", [False, True])
def test_parity_rejects_removed_central_policy_declarations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    explicit_agent: bool,
) -> None:
    import yaml

    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    from manifest_sync import validate_manifest_file

    selected_provider(monkeypatch)
    exported = resolved_manifest(manifest(tmp_path, monkeypatch))
    if field == "authority":
        del exported["metadata"]["cogit_policy"]
    else:
        exported["database_packages"] = []
    path = tmp_path / "stale.yaml"
    path.write_text(yaml.safe_dump(exported), encoding="utf-8")
    selected = configured_agent(exported) if explicit_agent else None
    assert any(
        "AgentDB policy" in error for error in validate_manifest_file(path, selected)
    )


@pytest.mark.parametrize("field", ["context_window", "max_output_tokens"])
@pytest.mark.parametrize("value", [None, 0, -1, 1_000_000_001])
def test_token_bounds_fail_before_provider_preparation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str, value: int | None
) -> None:
    events = selected_provider(monkeypatch)
    payload = manifest(tmp_path, monkeypatch)
    payload["model"][field] = value
    with pytest.raises(ValueError, match="context_window and max_output_tokens"):
        configured_agent(payload)
    assert events == []


@pytest.mark.parametrize(
    "bounds", [{}, {"context_window": 32000}, {"max_output_tokens": 1024}]
)
def test_fallback_token_bounds_fail_before_provider_preparation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bounds: dict[str, int]
) -> None:
    events = selected_provider(monkeypatch)
    payload = manifest(tmp_path, monkeypatch)
    payload["runtime"]["model"]["fallbacks"] = [
        {
            "adapter": "openai",
            "model": "fallback-fixture",
            "supports_tools": True,
            "supports_streaming": False,
            **bounds,
        }
    ]
    with pytest.raises(ValueError, match="context_window and max_output_tokens"):
        configured_agent(payload)
    assert events == []


def test_complete_fallback_bounds_preserve_inventory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events = selected_provider(monkeypatch)
    payload = manifest(tmp_path, monkeypatch)
    payload["runtime"]["model"]["fallbacks"] = [
        {
            "adapter": "openai",
            "model": "fallback-fixture",
            "supports_tools": True,
            "supports_streaming": False,
            "context_window": 32000,
            "max_output_tokens": 1024,
        }
    ]
    configured_agent(payload)
    assert events == ["prepare"]


def test_legacy_fallback_fails_before_provider_preparation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events = selected_provider(monkeypatch)
    payload = manifest(tmp_path, monkeypatch)
    payload["runtime"]["model"]["fallbacks"] = ["unbounded-alias"]
    with pytest.raises(ValueError, match="structured token bounds"):
        configured_agent(payload)
    assert events == []
