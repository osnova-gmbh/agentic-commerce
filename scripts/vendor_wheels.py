"""Vendor the two shared packages into Cogit agent projects, the way the template
vendors its framework cohort.

For every project given: build cogit-finance-seams and cogit-messaging-shim as wheels,
copy them into <project>/vendor/wheels/, record their SHA-256 in
vendor/wheels/cohort.json and make pyproject.toml depend on them. Then lock and
reinstall:

    python scripts/vendor_wheels.py packages/cogit-finance agents/buyer-agent
    (cd <project> && uv lock) && cogit install --project <project>

Safe to run again after the shared packages change (bump their version first).
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHARED = ("cogit-finance-seams", "cogit-messaging-shim")
EXTRA_DEPENDENCIES = ('"cryptography>=42"', '"httpx>=0.27"')


def build_wheels(out: Path) -> dict[str, Path]:
    wheels: dict[str, Path] = {}
    for name in SHARED:
        subprocess.run(["uv", "build", "--quiet", "--wheel", "--out-dir", str(out)], cwd=ROOT / "packages" / name, check=True)
        (wheel,) = out.glob(name.replace("-", "_") + "-*.whl")
        wheels[name] = wheel
    return wheels


def vendor(project: Path, wheels: dict[str, Path]) -> None:
    vendor_dir = project / "vendor" / "wheels"
    receipt_path = vendor_dir / "cohort.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    pyproject_path = project / "pyproject.toml"
    pyproject = pyproject_path.read_text(encoding="utf-8")
    for name, wheel in wheels.items():
        prefix = name.replace("-", "_") + "-"
        version = wheel.name[len(prefix) :].split("-")[0]
        for old in vendor_dir.glob(prefix + "*.whl"):
            old.unlink()
        receipt["wheelSha256"] = {k: v for k, v in receipt["wheelSha256"].items() if not k.startswith(prefix)}
        shutil.copy2(wheel, vendor_dir / wheel.name)
        receipt["wheelSha256"][wheel.name] = hashlib.sha256(wheel.read_bytes()).hexdigest()
        dependency = f'"{name}=={version}"'
        source = f'{name} = {{ path = "vendor/wheels/{wheel.name}" }}'
        if re.search(rf'"{name}==[^"]+"', pyproject):
            pyproject = re.sub(rf'"{name}==[^"]+"', dependency, pyproject)
            pyproject = re.sub(rf"^{name} = \{{ path = [^\n]+\}}$", source, pyproject, flags=re.M)
        else:
            pyproject = _add_dependency(pyproject, dependency)
            pyproject = pyproject.replace("[tool.uv.sources]\n", f"[tool.uv.sources]\n{source}\n", 1)
    for dependency in EXTRA_DEPENDENCIES:
        if dependency.split(">=")[0].strip('"') + ">=" not in pyproject.split("[project.scripts]")[0]:
            pyproject = _add_dependency(pyproject, dependency)
    pyproject_path.write_text(pyproject, encoding="utf-8")
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(f"vendored {', '.join(w.name for w in wheels.values())} into {project}")


def _add_dependency(pyproject: str, dependency: str) -> str:
    match = re.search(r"^dependencies = \[\n(.*?)^\]", pyproject, flags=re.M | re.S)
    if match is None:
        raise SystemExit("pyproject.toml has no [project] dependencies list")
    return pyproject[: match.end(1)] + f"    {dependency},\n" + pyproject[match.end(1) :]


def main() -> int:
    projects = [Path(arg).resolve() for arg in sys.argv[1:]]
    if not projects:
        print(__doc__)
        return 2
    with tempfile.TemporaryDirectory() as tmp:
        wheels = build_wheels(Path(tmp))
        for project in projects:
            vendor(project, wheels)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
