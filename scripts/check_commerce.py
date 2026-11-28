"""Run the commerce acceptance suites against repository sources.

Use --require-native in CI so PostgreSQL acceptance cannot silently skip.
The framework cohort must be installed first (scripts/dev-install.sh).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-native", action="store_true")
    args = parser.parse_args()
    if args.require_native and not os.environ.get("COMMERCE_SQL_TEST_DSN"):
        parser.error("COMMERCE_SQL_TEST_DSN is required; native acceptance must run")
    sources = [
        str(path)
        for group in ("packages", "modules", "apps", "agents")
        for path in (ROOT / group).glob("*/src")
    ]
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(sources), "PYTHONUTF8": "1"}
    suites = [
        str(path / "tests")
        for group in ("packages", "modules", "apps")
        for path in (ROOT / group).iterdir()
        if (path / "tests").is_dir()
        and (path / "pyproject.toml").exists()
        and not (path / "cogit.yaml").exists()
    ]
    suites.append(str(ROOT / "tests/e2e"))
    failures = []
    for suite in suites:
        command = [
            sys.executable,
            "-m",
            "pytest",
            suite,
            "-q",
            "--tb=short",
            "-p",
            "no:cacheprovider",
        ]
        try:
            result = subprocess.run(
                command, cwd=ROOT, env=env, check=False, timeout=300
            )
            if result.returncode:
                failures.append(suite)
        except (OSError, subprocess.TimeoutExpired) as exc:
            print(f"Cannot validate {suite}: {exc}", file=sys.stderr)
            failures.append(suite)
    finance = ROOT / "packages/cogit-finance/tests"
    command = [
        sys.executable,
        "-m",
        "pytest",
        *map(str, finance.glob("test_escrow*.py")),
        str(finance / "test_contract.py"),
        str(finance / "test_typed_actions.py"),
        str(finance / "test_manifest_sync.py"),
        "-q",
        "--tb=short",
        "-p",
        "no:cacheprovider",
    ]
    try:
        result = subprocess.run(command, cwd=ROOT, env=env, check=False, timeout=300)
        if result.returncode:
            failures.append("escrow")
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"Cannot validate escrow: {exc}", file=sys.stderr)
        failures.append("escrow")
    if failures:
        print("Failed suites: " + ", ".join(failures), file=sys.stderr)
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
