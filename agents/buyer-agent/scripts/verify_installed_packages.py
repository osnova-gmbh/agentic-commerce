"""Prove the selected cohort and agent import from installed distributions."""

from __future__ import annotations

import argparse
import importlib
import json
import re
import sys
import tomllib
import zipfile
from importlib import metadata, resources
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from cohort_entrypoint import manifest_entrypoint  # noqa: E402

FRAMEWORK_MODULES = {
    "agentdb-client": "agentdb_client",
    "cogit-agent-sdk": "cogit_agent_sdk",
    "cogit-runtime": "cogit_runtime",
    "cogit-tool-core": "cogit_tool_core",
}
PIN = re.compile(r"([a-z0-9-]+)(?:\[[a-z0-9_,-]+\])?==([^\s]+)")


def verify_installed_packages(
    root: Path, agent_wheel_dir: Path | None = None
) -> dict[str, object]:
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]
    receipt = json.loads((root / "vendor/wheels/cohort.json").read_text())
    versions = {
        match[1]: match[2]
        for requirement in project["dependencies"]
        if (match := PIN.fullmatch(requirement)) and match[1] in FRAMEWORK_MODULES
    }
    if versions.keys() != FRAMEWORK_MODULES.keys():
        raise ValueError("Project must pin the installed framework distributions")
    agent_name = project["name"].replace("_", "-")
    versions[agent_name] = project["version"]
    entrypoint = manifest_entrypoint(root / "cogit.yaml")
    agent_module, agent_class = entrypoint.split(":")
    modules = {**FRAMEWORK_MODULES, agent_name: agent_module}
    installed: dict[str, object] = {}
    prefix = Path(sys.prefix).resolve()
    for name, expected in versions.items():
        module = importlib.import_module(modules[name])
        location = Path(cast(str, module.__file__)).resolve()
        distribution = metadata.distribution(name)
        recorded_module = any(
            Path(str(distribution.locate_file(file))).resolve() == location
            for file in distribution.files or ()
        )
        direct = json.loads(distribution.read_text("direct_url.json") or "{}")
        if (
            distribution.version != expected
            or not location.is_relative_to(prefix)
            or "site-packages" not in location.parts
            or not recorded_module
            or direct.get("dir_info", {}).get("editable", False)
        ):
            raise ValueError(f"Expected installed noneditable distribution: {name}")
        installed[name] = {"version": expected, "modulePath": str(location)}
        if name == agent_name and not isinstance(
            getattr(module, agent_class, None), type
        ):
            raise ValueError("Installed entrypoint class is unavailable")

    wheel_paths = [root / "vendor/wheels" / name for name in receipt["wheelSha256"]]
    if agent_wheel_dir is not None:
        agent_wheels = list(agent_wheel_dir.glob("*.whl"))
        if len(agent_wheels) != 1:
            raise ValueError("Expected exactly one built agent wheel")
        wheel_paths.append(agent_wheels[0])

    # Optional provider wheels are audited when installed. Minimal installations
    # remain valid without importing or installing a browser or model SDK extra.
    compared = 0
    for wheel_path in wheel_paths:
        filename = wheel_path.name
        name = filename.split("-", 1)[0].replace("_", "-")
        try:
            distribution = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            if name in versions:
                raise
            continue
        with zipfile.ZipFile(wheel_path) as archive:
            for member in archive.namelist():
                if member.endswith(("/", ".dist-info/RECORD")):
                    continue
                path = Path(str(distribution.locate_file(member))).resolve()
                if not path.is_relative_to(prefix) or path.read_bytes() != archive.read(
                    member
                ):
                    raise ValueError(f"Installed framework bytes differ: {name}")
                compared += 1

    bundle_hash = None
    package_name, _, _ = agent_module.rpartition(".")
    if (
        package_name
        and resources.files(package_name).joinpath("database_bundle.py").is_file()
    ):
        # The starter agent exposes a bundled database package. Other projects
        # may persist through a different owned contract.
        prompts = resources.files(package_name).joinpath("prompts")
        if not all(
            prompts.joinpath(name).is_file() for name in ("system.md", "workspace.md")
        ):
            raise ValueError("Missing packaged prompt asset")
        bundle_module = importlib.import_module(f"{package_name}.database_bundle")
        _, bundle_hash = bundle_module.load_database_bundle()
    return {
        "python": sys.version.split()[0],
        "installed": installed,
        "frameworkFilesCompared": compared,
        "databaseModuleSha256": bundle_hash,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--agent-wheel-dir", type=Path)
    args = parser.parse_args()
    print(
        json.dumps(verify_installed_packages(args.root, args.agent_wheel_dir), indent=2)
    )


if __name__ == "__main__":
    main()
