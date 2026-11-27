"""Exercise the actual worker launch flags against Python's isolated mode."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_worker_flags_prevent_generated_caches_in_isolated_mode(tmp_path: Path) -> None:
    launcher = (ROOT / "scripts/start_database_worker.sh").read_text(encoding="utf-8")
    command = next(
        line for line in launcher.splitlines() if line.startswith("exec python ")
    )
    arguments = shlex.split(command.rstrip("\\"))
    flags = arguments[2 : arguments.index("-m")]
    code = (
        "import importlib.util,json,pathlib,sys; "
        "path=pathlib.Path(sys.argv[1]); "
        "spec=importlib.util.spec_from_file_location('bytecode_probe',path); "
        "module=importlib.util.module_from_spec(spec); "
        "spec.loader.exec_module(module); "
        "print(json.dumps({'disabled':sys.dont_write_bytecode,'value':module.value}))"
    )
    environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "0"}
    source = tmp_path / "bytecode_probe.py"
    source.write_text("value = 42\n", encoding="utf-8")
    completed = subprocess.run(  # noqa: S603 - reviewed launcher flags and owned fixture
        [sys.executable, *flags, "-c", code, str(source)],
        env=environment,
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert json.loads(completed.stdout) == {"disabled": True, "value": 42}
    assert not (tmp_path / "__pycache__").exists()

    # Control: isolation ignores the environment even when it requests suppression.
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    control = subprocess.run(  # noqa: S603 - the same owned fixture, without -B
        [
            sys.executable,
            *[flag for flag in flags if flag != "-B"],
            "-c",
            code,
            str(source),
        ],
        env=environment,
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert json.loads(control.stdout) == {"disabled": False, "value": 42}
    assert list((tmp_path / "__pycache__").glob("bytecode_probe.*.pyc"))
