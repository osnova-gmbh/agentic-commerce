"""Manifest validation and export use the YAML-selected executable agent."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, ClassVar

import pytest
import yaml
from cogit_agent_sdk import (
    AgentServices,
    CogitAgent,
    OperationInvocation,
    bind_action,
    operation,
)
from cogit_agent_sdk.operations import export_action_contract
from cogit_runtime.readiness import RuntimeModelProfile
from pydantic import BaseModel

from cogit_finance.database_example import (
    DatabaseAgent,
)
from cogit_finance_setup import (
    configured_agent,
    read_manifest,
)
from cogit_finance_setup.errors import SetupError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import export_action_contract as export_script  # noqa: E402
import manifest_sync  # noqa: E402
import validate_manifest  # noqa: E402
from enable_database import database_manifest  # noqa: E402


class SelectedInput(BaseModel):
    value: str


@operation
def selected_action(
    request: SelectedInput, invocation: OperationInvocation
) -> SelectedInput:
    del invocation
    return request


class SelectedAgent(CogitAgent):
    calls: ClassVar[list[str]] = []

    def __init__(self) -> None:
        self.calls.append("construct")
        super().__init__()

    @classmethod
    def runtime_model_readiness(cls, profile: RuntimeModelProfile) -> bool:
        cls.calls.append("readiness")
        return profile.kind == "external"

    def configure(self, services: AgentServices) -> None:
        super().configure(services)
        self.calls.append("configure")
        self.register_action(
            bind_action(
                selected_action,
                name="selected_action",
                description="Return the selected test input.",
            )
        )


class EmptyAgent(CogitAgent):
    calls: ClassVar[int] = 0

    def __bool__(self) -> bool:
        return False

    def configure(self, services: AgentServices) -> None:
        super().configure(services)
        type(self).calls += 1
        if type(self).calls > 1:
            raise RuntimeError("Agent configured more than once")


def save_manifest(tmp_path: Path, payload: dict[str, Any]) -> Path:
    path = tmp_path / "cogit.yaml"
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def database_profile(tmp_path: Path) -> Path:
    return save_manifest(tmp_path, database_manifest(ROOT / "cogit.yaml"))


def contract(path: Path, agent: CogitAgent) -> None:
    path.write_text(
        json.dumps(export_action_contract(agent.action_bindings())), encoding="utf-8"
    )


def test_database_profile_validator_uses_selected_agent_without_rewriting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = database_profile(tmp_path)
    expected = DatabaseAgent()
    expected.configure(AgentServices())
    artifact = tmp_path / "action-contract.v1.json"
    contract(artifact, expected)
    before = (path.read_bytes(), artifact.read_bytes())
    monkeypatch.setattr(validate_manifest, "ROOT", tmp_path)
    monkeypatch.setattr(manifest_sync, "ROOT", tmp_path)
    assert validate_manifest.main() == 0
    assert (path.read_bytes(), artifact.read_bytes()) == before


def test_export_and_explicit_database_instance_keep_action_only_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_profile(tmp_path)
    monkeypatch.setattr(manifest_sync, "ROOT", tmp_path)
    artifact = tmp_path / "action-contract.v1.json"
    manifest_sync.export_action_contract_file(artifact)
    expected = DatabaseAgent()
    expected.configure(AgentServices())
    assert json.loads(artifact.read_bytes()) == export_action_contract(
        expected.action_bindings()
    )
    assert manifest_sync.validate_manifest_file(tmp_path / "cogit.yaml", expected) == []
    assert manifest_sync.validate_action_contract_file(artifact, expected) == []


def test_database_profile_still_rejects_stale_default_action_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = database_profile(tmp_path)
    artifact = tmp_path / "action-contract.v1.json"
    artifact.write_bytes((ROOT / "action-contract.v1.json").read_bytes())
    before = (path.read_bytes(), artifact.read_bytes())
    monkeypatch.setattr(validate_manifest, "ROOT", tmp_path)
    monkeypatch.setattr(manifest_sync, "ROOT", tmp_path)
    assert validate_manifest.main() == 1
    assert "Action contract artifact is stale" in capsys.readouterr().err
    assert (path.read_bytes(), artifact.read_bytes()) == before


def test_selected_database_binding_mismatch_is_not_skipped(tmp_path: Path) -> None:
    payload = database_manifest(ROOT / "cogit.yaml")
    payload["actions"] = []
    path = save_manifest(tmp_path, payload)
    assert any(
        "persist_reference_request" in error
        for error in manifest_sync.validate_manifest_file(path)
    )


def test_other_cogit_agent_controls_readiness_and_bindings() -> None:
    payload = read_manifest(ROOT / "cogit.yaml")
    payload["metadata"]["entrypoint"] = f"{__name__}:SelectedAgent"
    payload["runtime"]["model"] = {
        "profile": "external",
        "allowed_models": [
            {
                "provider": "openai",
                "model": "fixture-model",
                "context_window": 32000,
                "max_output_tokens": 1024,
            }
        ],
    }
    SelectedAgent.calls = []
    selected = configured_agent(payload)
    assert isinstance(selected, SelectedAgent)
    assert SelectedAgent.calls == ["readiness", "construct", "configure"]
    assert [binding.descriptor.name for binding in selected.action_bindings()] == [
        "selected_action"
    ]


def test_validator_configures_an_empty_registry_agent_only_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = read_manifest(ROOT / "cogit.yaml")
    payload["metadata"]["entrypoint"] = f"{__name__}:EmptyAgent"
    payload.update(actions=[], tools=[], pipelines=[])
    save_manifest(tmp_path, payload)
    contract(tmp_path / "action-contract.v1.json", CogitAgent())
    EmptyAgent.calls = 0
    monkeypatch.setattr(validate_manifest, "ROOT", tmp_path)
    monkeypatch.setattr(manifest_sync, "ROOT", tmp_path)
    assert validate_manifest.main() == 0
    assert EmptyAgent.calls == 1


@pytest.mark.parametrize(
    "entrypoint",
    [
        None,
        "",
        "not-a-class",
        "../escape:Agent",
        "os:system",
        "pathlib:Path",
        "missing_fixture_module:Agent",
        "cogit_finance.agent:MissingAgent",
    ],
)
def test_invalid_entrypoint_cannot_fall_back_to_demo(entrypoint: object) -> None:
    payload = read_manifest(ROOT / "cogit.yaml")
    if entrypoint is None:
        del payload["metadata"]["entrypoint"]
    else:
        payload["metadata"]["entrypoint"] = entrypoint
    with pytest.raises(SetupError, match="entrypoint"):
        configured_agent(payload)


def test_validator_import_failure_is_safe_and_read_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    payload = read_manifest(ROOT / "cogit.yaml")
    payload["metadata"]["entrypoint"] = "fixture_sensitive_import.module:Agent"
    path = save_manifest(tmp_path, payload)
    before = path.read_bytes()
    monkeypatch.setattr(validate_manifest, "ROOT", tmp_path)
    monkeypatch.setattr(manifest_sync, "ROOT", tmp_path)
    assert validate_manifest.main() == 1
    output = capsys.readouterr()
    assert "fixture_sensitive_import" not in output.err + output.out
    assert "entrypoint" in output.err
    assert path.read_bytes() == before


def test_export_failure_redacts_sensitive_configuration_without_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    payload = read_manifest(ROOT / "cogit.yaml")
    payload["metadata"]["cogit_tools"] = {
        "fixture_sensitive_credential": "fixture-sensitive-export-value"
    }
    path = save_manifest(tmp_path, payload)
    artifact = tmp_path / "action-contract.v1.json"
    artifact.write_bytes(b"prior exported artifact\n")
    before = (path.read_bytes(), artifact.read_bytes())
    monkeypatch.setattr(export_script, "ROOT", tmp_path)
    monkeypatch.setattr(manifest_sync, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["export_action_contract.py"])
    assert export_script.main() == 1
    output = capsys.readouterr()
    assert "fixture-sensitive-export-value" not in output.err + output.out
    assert "Action contract export failed" in output.err
    assert (path.read_bytes(), artifact.read_bytes()) == before
