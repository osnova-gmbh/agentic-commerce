"""Verify the locally vendored framework cohort before installation."""

from __future__ import annotations

import json
import re
import tomllib
from hashlib import sha256
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[1]


def verify_framework_wheels(root: Path) -> None:
    vendor = root / "vendor" / "wheels"
    receipt = json.loads((vendor / "cohort.json").read_text(encoding="utf-8"))
    hashes = cast(dict[str, str], receipt["wheelSha256"])
    metadata = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    sources = metadata["tool"]["uv"]["sources"]
    selected = {sources[name]["path"] for name in sources}
    if selected != {f"vendor/wheels/{name}" for name in hashes}:
        raise ValueError("Framework metadata does not match the cohort receipt")
    for name, expected in hashes.items():
        if Path(name).name != name or not name.endswith(".whl"):
            raise ValueError("Invalid framework wheel filename")
        if re.fullmatch(r"[0-9a-f]{64}", expected) is None:
            raise ValueError("Invalid framework wheel hash")
        wheel = vendor / name
        if wheel.is_symlink() or not wheel.is_file():
            raise ValueError("Missing or linked framework wheel")
        if sha256(wheel.read_bytes()).hexdigest() != expected:
            raise ValueError(f"Framework wheel hash mismatch: {name}")


def main() -> int:
    try:
        verify_framework_wheels(ROOT)
    except (OSError, ValueError, KeyError, TypeError):
        print("Framework cohort verification failed; inspect its metadata and receipt.")
        return 1
    print("Verified the vendored framework cohort; release approval remains separate.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
