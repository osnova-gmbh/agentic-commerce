"""Published workers must carry the reviewed source, not stale shared wheels."""

from __future__ import annotations

import hashlib
import json
import tomllib
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PROJECTS = (
    "packages/cogit-finance",
    "agents/buyer-agent",
    "agents/seller-agent",
    "agents/evaluator-agent",
)
SHARED = ("cogit-finance-seams", "cogit-messaging-shim")


@pytest.mark.parametrize("project", PROJECTS)
@pytest.mark.parametrize("package", SHARED)
def test_shared_wheel_matches_source_and_lock(project: str, package: str) -> None:
    directory = ROOT / project
    source = ROOT / "packages" / package
    metadata = tomllib.loads((source / "pyproject.toml").read_text(encoding="utf-8"))
    project_config = tomllib.loads(
        (directory / "pyproject.toml").read_text(encoding="utf-8")
    )
    version = metadata["project"]["version"]
    assert f"{package}=={version}" in project_config["project"]["dependencies"]
    wheel = directory / project_config["tool"]["uv"]["sources"][package]["path"]
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    cohort = json.loads(
        (directory / "vendor/wheels/cohort.json").read_text(encoding="utf-8")
    )
    assert cohort["wheelSha256"][wheel.name] == digest
    lock = tomllib.loads((directory / "uv.lock").read_text(encoding="utf-8"))
    locked = next(entry for entry in lock["package"] if entry["name"] == package)
    assert locked["version"] == version
    assert locked["wheels"] == [{"filename": wheel.name, "hash": f"sha256:{digest}"}]
    with zipfile.ZipFile(wheel) as archive:
        files = {
            p.relative_to(source / "src").as_posix(): p
            for p in (source / "src").rglob("*.py")
        }
        assert {name for name in archive.namelist() if name.endswith(".py")} == set(
            files
        )
        for name, path in files.items():
            # Git may check Python sources out as CRLF on Windows.
            assert archive.read(name).replace(
                b"\r\n", b"\n"
            ) == path.read_bytes().replace(b"\r\n", b"\n"), name


@pytest.mark.parametrize(
    "module", ("cogit-finance-catalog", "cogit-finance-deals", "cogit-messaging")
)
def test_native_migration_bytes_match_manifest(module: str) -> None:
    directory = ROOT / "modules" / module / "agentdb"
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    for migration in manifest["migrations"]:
        data = (directory / migration["path"]).read_bytes()
        assert b"\r\n" not in data, migration["path"]
        assert hashlib.sha256(data).hexdigest() == migration["sha256"]
