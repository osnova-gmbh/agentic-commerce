"""Manifest sync/export idempotency tests."""

from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from manifest_sync import (  # noqa: E402
    canonical_manifest_actions_json,
    canonical_manifest_tools_json,
    export_manifest_file,
    sync_manifest_payload,
    validate_manifest_file,
)


def test_manifest_sync_preserves_non_binding_fields(tmp_path: Path) -> None:
    source = tmp_path / "cogit.yaml"
    manifest_text = (ROOT / "cogit.yaml").read_text(encoding="utf-8")
    source.write_text(manifest_text, encoding="utf-8")
    original = yaml.safe_load(source.read_text(encoding="utf-8"))

    synced = sync_manifest_payload(source)
    assert synced["id"] == original["id"]
    assert synced["pipelines"] == original["pipelines"]
    assert synced["runtime"]["model"] == original["runtime"]["model"]
    assert synced["runtime"] == original["runtime"]


def test_manifest_sync_is_idempotent(tmp_path: Path) -> None:
    target = tmp_path / "cogit.yaml"
    manifest_text = (ROOT / "cogit.yaml").read_text(encoding="utf-8")
    target.write_text(manifest_text, encoding="utf-8")

    export_manifest_file(target)
    first_actions = canonical_manifest_actions_json()
    first_tools = canonical_manifest_tools_json()

    export_manifest_file(target)
    second_actions = canonical_manifest_actions_json()
    second_tools = canonical_manifest_tools_json()

    assert first_actions == second_actions
    assert first_tools == second_tools
    assert validate_manifest_file(target) == []


def test_live_manifest_matches_canonical_binding_snapshots() -> None:
    manifest = yaml.safe_load((ROOT / "cogit.yaml").read_text(encoding="utf-8"))
    manifest_actions = json.dumps(
        sorted(manifest["actions"], key=lambda item: item["name"]),
        sort_keys=True,
    )
    manifest_tools = json.dumps(
        sorted(manifest["tools"], key=lambda item: item["name"]),
        sort_keys=True,
    )
    assert manifest_actions == json.dumps(
        json.loads(canonical_manifest_actions_json()),
        sort_keys=True,
    )
    assert manifest_tools == json.dumps(
        json.loads(canonical_manifest_tools_json()),
        sort_keys=True,
    )


def test_release_manifest_matches_package_and_serial_worker() -> None:
    manifest = yaml.safe_load((ROOT / "cogit.yaml").read_text(encoding="utf-8"))
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]
    assert manifest["version"] == project["version"]
    assert manifest["metadata"]["template_version"] == project["version"]
    assert manifest["runtime"]["worker"]["concurrency"] == 1
