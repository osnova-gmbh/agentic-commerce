"""Vendored installation fails closed when selected wheel bytes change."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from verify_framework_wheels import verify_framework_wheels  # noqa: E402


def prepared_cohort(tmp_path: Path) -> Path:
    shutil.copy2(ROOT / "pyproject.toml", tmp_path / "pyproject.toml")
    shutil.copytree(ROOT / "vendor", tmp_path / "vendor")
    return tmp_path


def selected_wheel(root: Path, package: str) -> Path:
    receipt = json.loads((root / "vendor/wheels/cohort.json").read_text())
    filename = next(
        name for name in receipt["wheelSha256"] if name.startswith(package + "-")
    )
    return root / "vendor" / "wheels" / filename


def test_reviewed_wheels_match_the_selected_metadata(tmp_path: Path) -> None:
    verify_framework_wheels(prepared_cohort(tmp_path))


def test_changed_wheel_bytes_fail_verification(tmp_path: Path) -> None:
    root = prepared_cohort(tmp_path)
    wheel = selected_wheel(root, "agentdb_client")
    wheel.write_bytes(wheel.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="hash mismatch"):
        verify_framework_wheels(root)


def test_missing_wheel_fails_verification(tmp_path: Path) -> None:
    root = prepared_cohort(tmp_path)
    selected_wheel(root, "agentdb_client").unlink()
    with pytest.raises(ValueError, match="Missing or linked"):
        verify_framework_wheels(root)


@pytest.mark.parametrize(
    "selection",
    ['editable = "../cogit-agent-sdk"', 'index = "pypi"'],
)
def test_sibling_or_index_selection_fails_verification(
    tmp_path: Path, selection: str
) -> None:
    root = prepared_cohort(tmp_path)
    metadata = root / "pyproject.toml"
    sdk_wheel = selected_wheel(root, "cogit_agent_sdk").name
    metadata.write_text(
        metadata.read_text(encoding="utf-8").replace(
            f'path = "vendor/wheels/{sdk_wheel}"', selection
        ),
        encoding="utf-8",
    )
    with pytest.raises(KeyError):
        verify_framework_wheels(root)


def test_unreceipted_metadata_selection_fails_verification(tmp_path: Path) -> None:
    root = prepared_cohort(tmp_path)
    metadata = root / "pyproject.toml"
    sdk_wheel = selected_wheel(root, "cogit_agent_sdk").name
    metadata.write_text(
        metadata.read_text(encoding="utf-8").replace(
            sdk_wheel, "cogit_agent_sdk-9.9.9-py3-none-any.whl"
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="metadata does not match"):
        verify_framework_wheels(root)
