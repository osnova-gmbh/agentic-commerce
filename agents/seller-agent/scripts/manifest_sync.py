"""Deterministic manifest/code parity helpers for the reference template."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, cast

import yaml
from cogit_agent_sdk import CogitAgent
from cogit_agent_sdk.operations import (
    ACTION_CONTRACT_SCHEMA_VERSION,
    export_action_contract,
    export_action_contract_json,
    parse_action_contract,
    write_action_contract_artifact,
)
from cogit_agent_sdk.types import ActionDescriptor, ToolDescriptor
from cogit_runtime.manifest import parse_manifest
from cogit_runtime.operations.parity import (
    validate_action_binding_parity,
    validate_tool_binding_parity,
)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from seller_agent.capabilities import (  # noqa: E402
    configuration,
)
from seller_agent_setup import (  # noqa: E402
    configured_agent,
    read_manifest,
    resolved_manifest,
    write_manifest,
)


def configure_seller_agent(
    agent: CogitAgent | None = None,
) -> CogitAgent:
    """Use a supplied configured agent, otherwise compose the YAML-selected one."""
    return (
        agent
        if agent is not None
        else configured_agent(read_manifest(ROOT / "cogit.yaml"))
    )


def expected_action_descriptors(
    agent: CogitAgent | None = None,
) -> list[ActionDescriptor]:
    configured = configure_seller_agent(agent)
    return [binding.descriptor for binding in configured.action_bindings()]


def expected_tool_descriptors(
    agent: CogitAgent | None = None,
) -> list[ToolDescriptor]:
    configured = configure_seller_agent(agent)
    return [binding.descriptor for binding in configured.tool_bindings()]


def manifest_action_payloads(
    agent: CogitAgent | None = None,
) -> list[dict[str, Any]]:
    return [
        descriptor.model_dump(mode="json", by_alias=False)
        for descriptor in expected_action_descriptors(agent)
    ]


def manifest_tool_payloads(
    agent: CogitAgent | None = None,
) -> list[dict[str, Any]]:
    return [
        descriptor.model_dump(mode="json", by_alias=False)
        for descriptor in expected_tool_descriptors(agent)
    ]


def validate_manifest_actions(
    manifest_actions: list[ActionDescriptor],
    agent: CogitAgent | None = None,
) -> list[str]:
    configured = configure_seller_agent(agent)
    return validate_action_binding_parity(
        manifest_actions,
        configured.action_bindings(),
    )


def validate_manifest_tools(
    manifest_tools: list[ToolDescriptor],
    agent: CogitAgent | None = None,
) -> list[str]:
    configured = configure_seller_agent(agent)
    return validate_tool_binding_parity(
        manifest_tools,
        configured.tool_bindings(),
    )


def load_manifest_actions(manifest_path: Path) -> list[ActionDescriptor]:
    raw: object = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest = cast(dict[str, Any], raw)
    actions_obj = manifest.get("actions")
    if not isinstance(actions_obj, list):
        return []
    actions = cast(list[Any], actions_obj)
    return [ActionDescriptor.model_validate(item) for item in actions]


def load_manifest_tools(manifest_path: Path) -> list[ToolDescriptor]:
    raw: object = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest = cast(dict[str, Any], raw)
    tools_obj = manifest.get("tools")
    if not isinstance(tools_obj, list):
        return []
    tools = cast(list[Any], tools_obj)
    return [ToolDescriptor.model_validate(item) for item in tools]


def validate_manifest_file(
    manifest_path: Path,
    agent: CogitAgent | None = None,
) -> list[str]:
    payload = read_manifest(manifest_path)
    configured = agent if agent is not None else configured_agent(payload)
    errors = validate_manifest_actions(load_manifest_actions(manifest_path), configured)
    errors.extend(
        validate_manifest_tools(load_manifest_tools(manifest_path), configured)
    )
    if configuration(configured.descriptor).providers:
        declared = parse_manifest(payload).descriptor
        if (declared.metadata or {}).get("cogit_policy") != (
            configured.descriptor.metadata or {}
        ).get("cogit_policy"):
            errors.append("AgentDB policy authority declaration is stale")
        if declared.database_packages != configured.descriptor.database_packages:
            errors.append("AgentDB policy package declaration is stale")
    return errors


def canonical_manifest_actions_json(agent: CogitAgent | None = None) -> str:
    return json.dumps(
        manifest_action_payloads(agent),
        sort_keys=True,
        separators=(",", ":"),
    )


def canonical_manifest_tools_json(agent: CogitAgent | None = None) -> str:
    return json.dumps(
        manifest_tool_payloads(agent),
        sort_keys=True,
        separators=(",", ":"),
    )


def canonical_action_contract_payload(
    agent: CogitAgent | None = None,
) -> dict[str, Any]:
    configured = configure_seller_agent(agent)
    return export_action_contract(configured.action_bindings())


def canonical_action_contract_json(agent: CogitAgent | None = None) -> str:
    configured = configure_seller_agent(agent)
    return export_action_contract_json(configured.action_bindings(), indent=0)


def export_action_contract_file(
    output_path: Path,
    agent: CogitAgent | None = None,
) -> Path:
    configured = configure_seller_agent(agent)
    return write_action_contract_artifact(output_path, configured.action_bindings())


def validate_action_contract_file(
    contract_path: Path,
    agent: CogitAgent | None = None,
) -> list[str]:
    raw: object = json.loads(contract_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return [f"Action contract at {contract_path} must be a JSON object."]

    raw_doc = cast(dict[str, Any], raw)
    schema_version = raw_doc.get("schema_version")
    if schema_version != ACTION_CONTRACT_SCHEMA_VERSION:
        return [
            "Action contract schema_version mismatch: "
            f"expected {ACTION_CONTRACT_SCHEMA_VERSION!r}, got {schema_version!r}.",
        ]

    configured = configure_seller_agent(agent)
    try:
        parsed = parse_action_contract(raw_doc)
    except Exception as exc:
        return [f"Action contract parse error: {exc}"]

    expected = export_action_contract(configured.action_bindings())
    expected_descriptors = parse_action_contract(expected)
    if parsed != expected_descriptors:
        return [
            "Action contract artifact is stale. "
            "Run: uv run python scripts/export_action_contract.py",
        ]
    return []


def sync_manifest_payload(
    manifest_path: Path,
    agent: CogitAgent | None = None,
) -> dict[str, Any]:
    """Rewrite actions/tools from live bindings while preserving other fields."""

    manifest = read_manifest(manifest_path)
    if agent is None:
        return resolved_manifest(manifest)
    configured = agent
    manifest["actions"] = manifest_action_payloads(configured)
    manifest["tools"] = manifest_tool_payloads(configured)
    return manifest


def export_manifest_file(
    manifest_path: Path,
    agent: CogitAgent | None = None,
) -> None:
    updated = sync_manifest_payload(manifest_path, agent)
    write_manifest(manifest_path, updated)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync cogit.yaml actions/tools from live agent bindings.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "cogit.yaml",
        help="Manifest path to rewrite (default: cogit.yaml)",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    export_manifest_file(args.manifest)
    print(f"synced manifest bindings to {args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
