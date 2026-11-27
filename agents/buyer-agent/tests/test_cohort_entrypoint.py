"""The authored YAML selects exactly the executable class shipped in the wheel."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from cohort_entrypoint import (  # noqa: E402
    manifest_entrypoint,
    verify_wheel_entrypoint,
)
from test_worker_cohort import prepared  # noqa: E402
from worker_cohort import read_prepared  # noqa: E402


def manifest(tmp_path: Path, metadata: str = "") -> Path:
    path = tmp_path / "cogit.yaml"
    path.write_text(
        "id: owned-agent\nname: Owned Agent\nversion: 0.1.0\ndescription: Fixture\n"
        + metadata,
        encoding="utf-8",
    )
    return path


def test_native_yaml_selects_class_without_another_manifest(tmp_path: Path) -> None:
    path = manifest(tmp_path, "metadata:\n  entrypoint: owned_agent.agent:OwnedAgent\n")
    assert manifest_entrypoint(path) == "owned_agent.agent:OwnedAgent"
    assert not (tmp_path / "agent.json").exists()


def test_explicit_selector_cannot_override_authored_yaml(tmp_path: Path) -> None:
    path = manifest(tmp_path, "metadata:\n  entrypoint: owned_agent.agent:OwnedAgent\n")
    with pytest.raises(ValueError, match="differs from manifest"):
        manifest_entrypoint(path, "another.agent:AnotherAgent")


def test_legacy_yaml_requires_explicit_selector(tmp_path: Path) -> None:
    path = manifest(tmp_path)
    with pytest.raises(ValueError, match=r"metadata\.entrypoint"):
        manifest_entrypoint(path)
    assert manifest_entrypoint(path, "owned_agent.agent:OwnedAgent").endswith(
        ":OwnedAgent"
    )


@pytest.mark.parametrize("entrypoint", ["../escape:Agent", "os:system", "a.b:Missing"])
def test_wheel_must_declare_selected_class(tmp_path: Path, entrypoint: str) -> None:
    path = tmp_path / "agent.whl"
    with ZipFile(path, "w") as archive:
        archive.writestr(
            "a/b.py", "raise RuntimeError('never execute')\nclass Agent: pass\n"
        )
    with pytest.raises(ValueError, match="entrypoint"):
        verify_wheel_entrypoint(path, entrypoint)


def test_inspection_does_not_import_wheel_code(tmp_path: Path) -> None:
    path = tmp_path / "agent.whl"
    with ZipFile(path, "w") as archive:
        archive.writestr(
            "a/b.py", "raise RuntimeError('never execute')\nclass Agent: pass\n"
        )
    verify_wheel_entrypoint(path, "a.b:Agent")


def test_package_init_can_declare_the_entrypoint_class(tmp_path: Path) -> None:
    path = tmp_path / "agent.whl"
    with ZipFile(path, "w") as archive:
        archive.writestr("a/b/__init__.py", "class Agent: pass\n")
    verify_wheel_entrypoint(path, "a.b:Agent")


def test_duplicate_entrypoint_source_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "agent.whl"
    with ZipFile(path, "w") as archive:
        archive.writestr("a/b.py", "class Agent: pass\n")
        with pytest.warns(UserWarning, match="Duplicate name"):
            archive.writestr("a/b.py", "class Agent: pass\n")
    with pytest.raises(ValueError, match="ambiguous entrypoint"):
        verify_wheel_entrypoint(path, "a.b:Agent")


def test_compressed_entrypoint_source_is_bounded_before_read(tmp_path: Path) -> None:
    path = tmp_path / "agent.whl"
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("a/b.py", "#" * (1024 * 1024 + 1))
    with pytest.raises(ValueError, match="source exceeds"):
        verify_wheel_entrypoint(path, "a.b:Agent")


def test_receipt_refuses_descriptor_manifest_disagreement(tmp_path: Path) -> None:
    output, _ = prepared(tmp_path)
    path = output / "executable.json"
    descriptor = json.loads(path.read_bytes())
    package_name = "buyer_agent"
    descriptor["entrypoint"] = f"{package_name}.agent:Agent"
    path.write_text(json.dumps(descriptor), encoding="utf-8")
    with pytest.raises(ValueError, match="differs from manifest"):
        read_prepared(output)
