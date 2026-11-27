"""A published route can bind only the exact prepared worker artifact bytes."""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import shutil
import sys
import tomllib
from pathlib import Path
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "buyer_agent"
sys.path.insert(0, str(ROOT / "scripts"))

from worker_cohort import prepare, read_prepared, receipt, wheel_identity  # noqa: E402


def agent_wheel(directory: Path) -> Path:
    """Make a small valid wheel with the project's current identity."""
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]
    version = project["version"]
    stem = project["name"].replace("-", "_")
    dist_info = f"{stem}-{version}.dist-info"
    files = {
        f"{PACKAGE_NAME}/__init__.py": b"# fixture package\n",
        f"{PACKAGE_NAME}/agent.py": b"class Agent: pass\n",
        f"{PACKAGE_NAME}/database_example.py": b"class DatabaseAgent: pass\n",
        f"{dist_info}/METADATA": (
            f"Metadata-Version: 2.3\nName: {project['name']}\nVersion: {version}\n"
        ).encode(),
        f"{dist_info}/WHEEL": (
            b"Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
        ),
    }
    record = io.StringIO(newline="")
    writer = csv.writer(record)
    for name, body in files.items():
        sha = base64.urlsafe_b64encode(hashlib.sha256(body).digest()).rstrip(b"=")
        writer.writerow([name, f"sha256={sha.decode()}", len(body)])
    writer.writerow([f"{dist_info}/RECORD", "", ""])
    files[f"{dist_info}/RECORD"] = record.getvalue().encode()
    directory.mkdir()
    path = directory / f"{stem}-{version}-py3-none-any.whl"
    with ZipFile(path, "w") as archive:
        for name, body in files.items():
            archive.writestr(name, body)
    return path


def prepared(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    root = tmp_path / "source"
    root.mkdir()
    shutil.copyfile(ROOT / "pyproject.toml", root / "pyproject.toml")
    shutil.copytree(ROOT / "vendor", root / "vendor")
    manifest = tmp_path / "cogit.database.yaml"
    entrypoint = f"{PACKAGE_NAME}.database_example:DatabaseAgent"
    manifest.write_bytes(
        b"id: exact-worker\nname: Exact worker\nversion: 0.1.11\n"
        b"description: Fixture\nmetadata:\n" + f"  entrypoint: {entrypoint}\n".encode()
    )
    wheel_dir = tmp_path / "agent-wheel"
    agent_wheel(wheel_dir)
    cohort = tmp_path / "cohort"
    hashes = prepare(root, manifest, wheel_dir, cohort)
    return cohort, hashes


def route_ids() -> dict[str, str]:
    return {
        name: str(uuid4())
        for name in (
            "tenantId",
            "installationId",
            "definitionId",
            "versionId",
            "deploymentId",
            "poolId",
            "agentPrincipalId",
        )
    }


def test_receipt_binds_exact_prepared_bytes_and_published_route(tmp_path: Path) -> None:
    cohort, hashes = prepared(tmp_path)
    assert not (cohort / "receipt.json").exists()
    assert read_prepared(cohort) == (
        hashes["executableSha256"],
        hashes["manifestSha256"],
    )
    ids = route_ids()
    path = receipt(
        cohort,
        ids,
        {
            "executableSha256": hashes["executableSha256"],
            "manifestSha256": hashes["manifestSha256"],
        },
    )
    saved = json.loads(path.read_bytes())
    assert saved["tenantId"] == ids["tenantId"]
    assert saved["route"]["poolId"] == ids["poolId"]
    assert saved["route"]["executableSha256"] == hashes["executableSha256"]
    assert saved["manifest"] == "cogit.yaml"
    with pytest.raises(FileExistsError):
        receipt(
            cohort,
            ids,
            {
                "executableSha256": hashes["executableSha256"],
                "manifestSha256": hashes["manifestSha256"],
            },
        )


def test_wrong_published_hash_cannot_create_receipt(tmp_path: Path) -> None:
    cohort, hashes = prepared(tmp_path)
    with pytest.raises(ValueError, match="Published manifestSha256 differs"):
        receipt(
            cohort,
            route_ids(),
            {
                "executableSha256": hashes["executableSha256"],
                "manifestSha256": "0" * 64,
            },
        )
    assert not (cohort / "receipt.json").exists()


def test_published_hashes_cannot_override_validated_route_ids(tmp_path: Path) -> None:
    cohort, hashes = prepared(tmp_path)
    with pytest.raises(ValueError, match="only the two artifact hashes"):
        receipt(
            cohort,
            route_ids(),
            {**hashes, "poolId": str(uuid4())},
        )
    assert not (cohort / "receipt.json").exists()


def test_changed_wheel_cannot_receive_published_route(tmp_path: Path) -> None:
    cohort, hashes = prepared(tmp_path)
    descriptor = json.loads((cohort / "executable.json").read_bytes())
    wheel = cohort / descriptor["wheels"][0]["path"]
    wheel.write_bytes(wheel.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="Prepared wheel differs"):
        receipt(
            cohort,
            route_ids(),
            {
                "executableSha256": hashes["executableSha256"],
                "manifestSha256": hashes["manifestSha256"],
            },
        )
    assert not (cohort / "receipt.json").exists()


def test_additional_provider_wheel_is_committed_and_verified(tmp_path: Path) -> None:
    root = tmp_path / "source"
    root.mkdir()
    shutil.copyfile(ROOT / "pyproject.toml", root / "pyproject.toml")
    shutil.copytree(ROOT / "vendor", root / "vendor")
    manifest = tmp_path / "cogit.yaml"
    entrypoint = f"{PACKAGE_NAME}.agent:Agent"
    manifest.write_bytes(
        b"id: tool-worker\nname: Tool worker\nversion: 0.1.13\n"
        b"description: Fixture\nmetadata:\n" + f"  entrypoint: {entrypoint}\n".encode()
    )
    wheel_dir = tmp_path / "agent-wheel"
    agent_wheel(wheel_dir)
    provider = root / "vendor/wheels/cogit_tool_shell-0.1.2-py3-none-any.whl"
    output = tmp_path / "cohort"
    hashes = prepare(
        root,
        manifest,
        wheel_dir,
        output,
        entrypoint=entrypoint,
        additional_wheels=(provider,),
    )
    descriptor = json.loads((output / "executable.json").read_bytes())
    assert descriptor["entrypoint"] == f"{PACKAGE_NAME}.agent:Agent"
    assert "cogit-tool-core" in {item["distribution"] for item in descriptor["wheels"]}
    assert "cogit-tool-shell" in {item["distribution"] for item in descriptor["wheels"]}
    assert read_prepared(output)[0] == hashes["executableSha256"]
    copied = output / "wheels" / provider.name
    copied.write_bytes(copied.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="Prepared wheel differs"):
        read_prepared(output)


def test_duplicate_prepared_distribution_is_rejected(tmp_path: Path) -> None:
    output, _ = prepared(tmp_path)
    path = output / "executable.json"
    descriptor = json.loads(path.read_bytes())
    descriptor["wheels"].append(descriptor["wheels"][0])
    path.write_text(json.dumps(descriptor))
    with pytest.raises(ValueError, match="Duplicate prepared wheel"):
        read_prepared(output)


@pytest.mark.parametrize("member", ["METADATA", "WHEEL"])
def test_compressed_metadata_is_bounded_before_expansion(
    tmp_path: Path, member: str
) -> None:
    path = tmp_path / "review-1.0.0-py3-none-any.whl"
    entries = {
        "review-1.0.0.dist-info/METADATA": b"Name: review\nVersion: 1.0.0\n",
        "review-1.0.0.dist-info/WHEEL": b"Root-Is-Purelib: true\n",
        "review-1.0.0.dist-info/RECORD": b"",
    }
    entries[f"review-1.0.0.dist-info/{member}"] += b"A" * (256 * 1024)
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        for name, value in entries.items():
            archive.writestr(name, value)
    assert path.stat().st_size < 4096
    with pytest.raises(ValueError, match="metadata exceeds"):
        wheel_identity(path)


def test_duplicate_zip_member_is_rejected(tmp_path: Path) -> None:
    path = agent_wheel(tmp_path / "wheel")
    with ZipFile(path, "a") as archive:
        name = next(item for item in archive.namelist() if item.endswith("/WHEEL"))
        with pytest.warns(UserWarning, match="Duplicate name"):
            archive.writestr(name, b"Root-Is-Purelib: true\n")
    with pytest.raises(ValueError, match="invalid distribution metadata"):
        wheel_identity(path)
