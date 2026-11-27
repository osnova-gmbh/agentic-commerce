"""Wheel packaging and distribution asset tests."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = ROOT / "dist"
PACKAGE_NAME = "buyer_agent"
DATABASE_PREFIX = f"{PACKAGE_NAME}/database"


def _build_wheel() -> Path:
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    subprocess.run(  # noqa: S603
        ["uv", "build", "--wheel", "--out-dir", str(DIST_DIR), str(ROOT)],  # noqa: S607
        cwd=ROOT,
        check=True,
    )
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]
    distribution = project["name"].replace("-", "_")
    wheel = DIST_DIR / f"{distribution}-{project['version']}-py3-none-any.whl"
    assert wheel.is_file()
    return wheel


def test_wheel_includes_prompts_py_typed_and_no_lock() -> None:
    wheel = _build_wheel()
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        root = ROOT / "src" / PACKAGE_NAME / "database"
        for version in ("1.1.0", "1.1.1", "1.1.2", "1.1.3", "1.1.4", "1.1.6"):
            retained_root = root / "historical" / f"module-{version}"
            retained = json.loads((retained_root / "manifest.json").read_bytes())
            for relative in [
                "manifest.json",
                *[item["path"] for item in retained["migrations"]],
                *[item["path"] for item in retained["files"]],
            ]:
                member = f"{DATABASE_PREFIX}/historical/module-{version}/{relative}"
                assert archive.read(member) == (retained_root / relative).read_bytes()
        old_root = (
            ROOT / "src" / PACKAGE_NAME / "database" / "historical" / "module-1.0.0"
        )
        for relative in (
            "manifest.json",
            "catalog/resources.v1.json",
            "contracts/requests.v1.json",
            "contracts/settings.v1.json",
            "migrations/000001__reference_domain.sql",
            "migrations/000002__reference_commands.sql",
        ):
            assert (
                archive.read(f"{DATABASE_PREFIX}/historical/module-1.0.0/{relative}")
                == (old_root / relative).read_bytes()
            )
    assert f"{PACKAGE_NAME}/py.typed" in names
    assert f"{PACKAGE_NAME}/prompts/system.md" in names
    assert f"{DATABASE_PREFIX}/manifest.json" in names
    assert f"{DATABASE_PREFIX}/migrations/000001__reference_domain.sql" in names
    assert f"{DATABASE_PREFIX}/migrations/000002__reference_commands.sql" in names
    assert f"{DATABASE_PREFIX}/migrations/000003__reference_list_v2.sql" in names
    assert f"{DATABASE_PREFIX}/contracts/requests.v1.json" in names
    assert f"{DATABASE_PREFIX}/contracts/requests.v2.json" in names
    assert f"{DATABASE_PREFIX}/catalog/resources.v1.json" in names
    assert f"{DATABASE_PREFIX}/catalog/resources.v2.json" in names
    assert f"{DATABASE_PREFIX}/historical/module-1.0.0/manifest.json" in names
    assert (
        f"{DATABASE_PREFIX}/historical/module-1.0.0/migrations/"
        "000001__reference_domain.sql"
    ) in names
    assert (
        f"{DATABASE_PREFIX}/historical/module-1.0.0/migrations/"
        "000002__reference_commands.sql"
    ) in names
    assert not any(name.endswith("uv.lock") for name in names)


def test_installed_wheel_loads_active_and_historical_bundles(tmp_path: Path) -> None:
    wheel = _build_wheel()
    target = tmp_path / "installed"
    subprocess.run(  # noqa: S603
        [  # noqa: S607
            "uv",
            "pip",
            "install",
            "--python",
            sys.executable,
            "--target",
            str(target),
            "--no-deps",
            str(wheel),
        ],
        cwd=tmp_path,
        check=True,
    )
    outside = tmp_path / "outside-checkout"
    outside.mkdir()
    script = (
        f"import json,{PACKAGE_NAME} as agent_package; "
        f"from {PACKAGE_NAME}.database_bundle "
        "import load_database_bundle; "
        "current, current_digest = load_database_bundle(); "
        "old, old_digest = load_database_bundle(historical=True); "
        "retained, retained_digest = load_database_bundle(historical_version='1.1.0'); "
        "previous, previous_digest = load_database_bundle(historical_version='1.1.1'); "
        "latest, latest_digest = load_database_bundle(historical_version='1.1.2'); "
        "released, released_digest = load_database_bundle(historical_version='1.1.3'); "
        "print(json.dumps({'path':agent_package.__file__, "
        "'current':current['version'], 'current_digest':current_digest, "
        "'old':old['version'], 'old_digest':old_digest, "
        "'retained':retained['version'], 'retained_digest':retained_digest, "
        "'latest':latest['version'], 'latest_digest':latest_digest, "
        "'released':released['version'], 'released_digest':released_digest, "
        "'previous':previous['version'], 'previous_digest':previous_digest}))"
    )
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", script],
        cwd=outside,
        env={**os.environ, "PYTHONPATH": str(target)},
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(result.stdout)
    assert Path(payload["path"]).is_relative_to(target)
    assert payload["current"] == "1.1.7"
    assert payload["current_digest"] == (
        "f63a2e2ac613e3c12ec7bbb1f71bfa2df04b08cc532fbfe0a62abaa0faa02efa"
    )
    assert payload["released"] == "1.1.3"
    assert payload["released_digest"] == (
        "3bbcfcdee737d0875cc5f8f7986e39d6b1e39b1c7ce858e5a276f199749decf6"
    )
    assert payload["latest"] == "1.1.2"
    assert payload["latest_digest"] == (
        "a6790747cbc73f36b9c2d7c9e5003412ac9f3bc7b20443fc53cb944fb58da499"
    )
    assert payload["previous"] == "1.1.1"
    assert payload["previous_digest"] == (
        "3d58744d7e47380b349d34cf8821a4dc3ae77d5486d8e6a91d2b313c437dae50"
    )
    assert payload["retained"] == "1.1.0"
    assert payload["retained_digest"] == (
        "618f39aa1587ad5b5ac6132386c4bef829fadb5b90051855d16716f1c0b7f548"
    )
    assert payload["old"] == "1.0.0"
    assert payload["old_digest"] == (
        "15714d0a37fbea9938514f3ab61f445b6a4cfe1ab4db1ad3f8b5fbd4002c4bd9"
    )
