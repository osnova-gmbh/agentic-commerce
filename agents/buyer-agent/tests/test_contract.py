"""Static executable-contract checks for the template."""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

from agent_helpers import configured_buyer_agent
from cogit_agent_sdk import derive_model_schema
from cogit_agent_sdk.manifest import load_manifest

from buyer_agent.schemas import (
    ApplyResolutionInput,
    ApplyResolutionOutput,
    LookupRecordInput,
    LookupRecordOutput,
    LookupResolutionInput,
    LookupResolutionOutput,
    ValidateRequestInput,
    ValidateRequestOutput,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "src" / "buyer_agent"
sys.path.insert(0, str(ROOT / "scripts"))

from manifest_sync import (  # noqa: E402
    canonical_manifest_actions_json,
    canonical_manifest_tools_json,
    validate_manifest_file,
)

REMOVED_SDK_SYMBOLS = {
    "action",
    "collect_actions",
    "collect_action_handlers",
    "legacy_action_binding",
    "bind_legacy_action",
    "handle_action",
    "ExecutableTool",
    "exposed_as_tool",
}


def test_manifest_and_code_bindings_have_exact_parity() -> None:
    agent = configured_buyer_agent()

    assert validate_manifest_file(ROOT / "cogit.yaml") == []

    action_bindings = {item.descriptor.name: item for item in agent.action_bindings()}
    assert set(action_bindings) == {
        "lookup_record",
        "validate_request",
        "apply_resolution",
        "lookup_resolution",
        "persist_reference_request",
        "handle_message",
        "start_purchase",
    }
    assert action_bindings["apply_resolution"].descriptor.requires_approval is True
    assert action_bindings["lookup_record"].descriptor.idempotency == "inherent"
    assert action_bindings["apply_resolution"].descriptor.idempotency == "keyed"
    assert action_bindings["apply_resolution"].descriptor.required_capabilities == [
        "records.write"
    ]
    assert action_bindings["lookup_resolution"].descriptor.required_capabilities == [
        "records.read"
    ]

    tool_bindings = {item.descriptor.name: item for item in agent.tool_bindings()}
    assert set(tool_bindings) == {
        "lookup_record",
        "validate_request",
        "run_function",
        "describe_function",
    }


def test_internal_operation_is_absent_from_manifests() -> None:
    agent = configured_buyer_agent()
    assert agent.internal_operations is not None
    action_names = {binding.descriptor.name for binding in agent.action_bindings()}
    tool_names = {binding.descriptor.name for binding in agent.tool_bindings()}
    assert "refresh_record_index" not in action_names
    assert "refresh_record_index" not in tool_names


def test_domain_action_schemas_are_derived_from_pydantic_models() -> None:
    agent = configured_buyer_agent()
    bindings = {item.descriptor.name: item for item in agent.action_bindings()}

    expected = {
        "lookup_record": (LookupRecordInput, LookupRecordOutput),
        "validate_request": (ValidateRequestInput, ValidateRequestOutput),
        "apply_resolution": (ApplyResolutionInput, ApplyResolutionOutput),
        "lookup_resolution": (LookupResolutionInput, LookupResolutionOutput),
    }
    for name, (input_model, output_model) in expected.items():
        descriptor = bindings[name].descriptor
        assert json.dumps(
            derive_model_schema(input_model),
            sort_keys=True,
        ) == json.dumps(dict(descriptor.input_schema), sort_keys=True)
        assert json.dumps(
            derive_model_schema(output_model),
            sort_keys=True,
        ) == json.dumps(dict(descriptor.output_schema), sort_keys=True)


def test_manifest_action_snapshot_matches_canonical_bindings() -> None:
    manifest = load_manifest(ROOT / "cogit.yaml")
    manifest_payload = sorted(
        (action.model_dump(mode="json", by_alias=False) for action in manifest.actions),
        key=lambda item: item["name"],
    )
    canonical_payload = sorted(
        json.loads(canonical_manifest_actions_json()),
        key=lambda item: item["name"],
    )
    assert json.dumps(manifest_payload, sort_keys=True) == json.dumps(
        canonical_payload,
        sort_keys=True,
    )


def test_manifest_tool_snapshot_matches_canonical_bindings() -> None:
    manifest = load_manifest(ROOT / "cogit.yaml")
    manifest_payload = sorted(
        (tool.model_dump(mode="json", by_alias=False) for tool in manifest.tools or []),
        key=lambda item: item["name"],
    )
    canonical_payload = sorted(
        json.loads(canonical_manifest_tools_json()),
        key=lambda item: item["name"],
    )
    assert json.dumps(manifest_payload, sort_keys=True) == json.dumps(
        canonical_payload,
        sort_keys=True,
    )


def test_dual_bound_tools_share_exact_operation_with_actions() -> None:
    agent = configured_buyer_agent()
    actions = {binding.descriptor.name: binding for binding in agent.action_bindings()}
    tools = {binding.descriptor.name: binding for binding in agent.tool_bindings()}

    for name in ("lookup_record", "validate_request"):
        assert actions[name].operation is tools[name].operation
        assert (
            actions[name].descriptor.requirements == tools[name].descriptor.requirements
        )


def test_agent_source_has_no_template_owned_action_schema_constants() -> None:
    forbidden_names = {
        "LOOKUP_INPUT_SCHEMA",
        "LOOKUP_OUTPUT_SCHEMA",
        "VALIDATE_INPUT_SCHEMA",
        "VALIDATE_OUTPUT_SCHEMA",
        "APPLY_INPUT_SCHEMA",
        "APPLY_OUTPUT_SCHEMA",
        "INPUT_SCHEMA",
        "OUTPUT_SCHEMA",
    }
    violations: list[str] = []

    for source_path in SOURCE_ROOT.rglob("*.py"):
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id in forbidden_names:
                        violations.append(
                            f"{source_path.relative_to(ROOT)}:{target.id}"
                        )
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                if node.target.id in forbidden_names:
                    violations.append(
                        f"{source_path.relative_to(ROOT)}:{node.target.id}",
                    )

    assert violations == []


def test_agent_source_does_not_import_runtime_or_web_frameworks() -> None:
    forbidden = {
        "alembic",
        "anthropic",
        "cogit_runtime",
        "fastapi",
        "openai",
        "sqlalchemy",
        "starlette",
        "uvicorn",
    }
    forbidden_sdk_private = (
        "cogit_agent_sdk.operations.legacy",
        "cogit_agent_sdk.types._immutable",
    )
    violations: list[str] = []

    for source_path in SOURCE_ROOT.glob("*.py"):
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            imported: list[str] = []
            if isinstance(node, ast.Import):
                imported = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported = [node.module]
            for module in imported:
                root_module = module.partition(".")[0]
                if root_module in forbidden or module in forbidden_sdk_private:
                    violations.append(f"{source_path.name}: {module}")
                if module == "cogit_agent_sdk.providers" or module.startswith(
                    "cogit_agent_sdk.providers."
                ):
                    violations.append(f"{source_path.name}: {module}")

    assert violations == []


def test_agent_source_does_not_use_removed_sdk_symbols() -> None:
    violations: list[str] = []

    for source_path in SOURCE_ROOT.rglob("*.py"):
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                for alias in node.names:
                    if alias.name in REMOVED_SDK_SYMBOLS:
                        violations.append(
                            f"{source_path.relative_to(ROOT)}: import {alias.name} "
                            f"from {node.module}",
                        )
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in REMOVED_SDK_SYMBOLS:
                        violations.append(
                            f"{source_path.relative_to(ROOT)}: import {alias.name}",
                        )
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                if (
                    node.value.id == "cogit_agent_sdk"
                    and node.attr in REMOVED_SDK_SYMBOLS
                ):
                    violations.append(
                        f"{source_path.relative_to(ROOT)}: cogit_agent_sdk.{node.attr}",
                    )

    assert violations == []


def test_manifest_selects_agentdb_and_deterministic_queue() -> None:
    manifest = load_manifest(ROOT / "cogit.yaml")
    assert manifest.model is None
    assert [pipeline.name for pipeline in manifest.pipelines or []] == [
        "resolve-case",
        "persist-reference-request",
    ]
    (package,) = manifest.database_packages
    assert package.module_key == f"cogit.{manifest.id}"
    assert package.version == "1.1.7"
    assert {export.key for export in package.exports} == {
        "requests.get",
        "requests.put",
        "resolutions.apply",
        "resolutions.list",
    }
