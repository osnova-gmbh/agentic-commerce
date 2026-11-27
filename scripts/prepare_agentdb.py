"""Build exact worker cohorts and a deployment plan, without touching a server."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from sync_commerce_agents import PROJECTS, synchronize

ROOT = Path(__file__).resolve().parents[1]


def prepare(install: bool = False) -> Path:
    from run_demo import configure_paths

    configure_paths()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    output = ROOT / ".state/agentdb/builds" / stamp
    output.mkdir(parents=True)
    # Package the actual current shared source before committing any worker
    # hashes. A prepared agent must not carry yesterday's messaging adapter.
    from vendor_wheels import SHARED, vendor

    shared_dir = output / "shared"
    shared_dir.mkdir()
    wheels = {}
    for name in SHARED:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "hatchling",
                "build",
                "-t",
                "wheel",
                "-d",
                str(shared_dir),
            ],
            cwd=ROOT / "packages" / name,
            check=True,
        )
        wheels[name] = next(shared_dir.glob(name.replace("-", "_") + "-*.whl"))
    for directory in PROJECTS.values():
        vendor(directory, wheels)
    synchronize()
    helper_path = ROOT / "agents/buyer-agent/scripts/worker_cohort.py"
    spec = importlib.util.spec_from_file_location("commerce_cohort", helper_path)
    helper = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(helper_path.parent))
    spec.loader.exec_module(helper)
    import yaml

    plan = {"root": str(ROOT), "agents": {}, "modules": {}}
    for package, directory in PROJECTS.items():
        name = package.replace("_", "-")
        wheel_dir = output / name / "dist"
        wheel_dir.mkdir(parents=True)
        subprocess.run(
            [
                sys.executable,
                "-m",
                "hatchling",
                "build",
                "-t",
                "wheel",
                "-d",
                str(wheel_dir),
            ],
            cwd=directory,
            check=True,
        )
        cohort = output / name / "cohort"
        helper.prepare(directory, directory / "cogit.yaml", wheel_dir, cohort)
        manifest = yaml.safe_load(
            (directory / "cogit.yaml").read_text(encoding="utf-8")
        )
        plan["agents"][name] = {
            "project": str(directory),
            "cohort": str(cohort),
            "requirements": manifest["database_packages"],
        }
        template = directory / "src" / package / "database"
        if (template / "manifest.json").exists():
            data = json.loads((template / "manifest.json").read_text())
            canonical = json.dumps(
                data, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode()
            plan["modules"][data["moduleKey"]] = {
                "bundlePath": str(template),
                "approvedArtifactSha256": hashlib.sha256(canonical).hexdigest(),
            }
    for directory in sorted((ROOT / "modules").glob("*/agentdb")):
        data = json.loads((directory / "manifest.json").read_text())
        canonical = json.dumps(
            data, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
        plan["modules"][data["moduleKey"]] = {
            "bundlePath": str(directory),
            "approvedArtifactSha256": hashlib.sha256(canonical).hexdigest(),
        }
    destination = output / "plan.json"
    destination.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    print(destination)
    if install:
        for directory in PROJECTS.values():
            subprocess.run(
                ["cogit", "install", "--project", str(directory)], check=True
            )
            subprocess.run(
                ["cogit", "agent", "validate", "--project", str(directory)], check=True
            )
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--install",
        action="store_true",
        help="Install and validate all four workers through Cogit",
    )
    prepare(parser.parse_args().install)
