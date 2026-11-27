"""Prepare exact canonical worker artifacts, then bind published route IDs.

The preparation step is deliberately independent of AgentDb publication. Its
output hashes are inputs to the existing deployment workflow. The receipt step
requires those published hashes and route IDs and never invents an identity.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import stat
import sys
import tomllib
from email.parser import BytesParser
from pathlib import Path
from typing import cast
from uuid import UUID
from zipfile import BadZipFile, ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cohort_entrypoint import manifest_entrypoint, verify_wheel_entrypoint
from cohort_providers import provider_wheels
from verify_framework_wheels import verify_framework_wheels

FRAMEWORK_NAMES = ("cogit-runtime", "cogit-agent-sdk", "agentdb-client")
MAX_WHEEL_BYTES = 32 * 1024 * 1024
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_DESCRIPTOR_BYTES = 65536
MAX_WHEEL_METADATA_BYTES = 256 * 1024
HEX_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


def encode(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def digest(path: Path, maximum: int) -> str:
    plain_file(path, maximum)
    result = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(65536):
            result.update(chunk)
    return result.hexdigest()


def plain_file(path: Path, maximum: int) -> None:
    """Use ordinary bounded files for commitments, never linked artifacts."""
    for member in (path, *path.parents):
        details = member.lstat()
        if stat.S_ISLNK(details.st_mode) or (
            getattr(details, "st_file_attributes", 0)
            & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        ):
            raise ValueError(f"Linked cohort artifact: {path}")
    if not path.is_file() or path.stat().st_size > maximum:
        raise ValueError(f"Missing or oversized cohort artifact: {path}")


def normalized_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def wheel_identity(path: Path) -> tuple[str, str]:
    plain_file(path, MAX_WHEEL_BYTES)
    if path.suffix != ".whl" or not re.fullmatch(r"[A-Za-z0-9_.+-]+\.whl", path.name):
        raise ValueError(f"Unsafe wheel filename: {path.name}")
    with ZipFile(path) as archive:
        names = archive.namelist()
        metadata = [name for name in names if name.endswith(".dist-info/METADATA")]
        if len(metadata) != 1 or len(names) > 4096 or len(names) != len(set(names)):
            raise ValueError(f"Wheel has invalid distribution metadata: {path}")
        dist_info = metadata[0].rsplit("/", 1)[0]
        if f"{dist_info}/WHEEL" not in names or f"{dist_info}/RECORD" not in names:
            raise ValueError(f"Wheel lacks its WHEEL or RECORD: {path}")
        for member in (metadata[0], f"{dist_info}/WHEEL"):
            if archive.getinfo(member).file_size > MAX_WHEEL_METADATA_BYTES:
                raise ValueError("Wheel metadata exceeds the artifact size limit")
        wheel = BytesParser().parsebytes(archive.read(f"{dist_info}/WHEEL"))
        package = BytesParser().parsebytes(archive.read(metadata[0]))
        name = normalized_name(str(package.get("Name", "")))
        version = str(package.get("Version", ""))
        if (
            wheel.get("Root-Is-Purelib") != "true"
            or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name)
            or not re.fullmatch(r"[0-9][A-Za-z0-9.+!-]*", version)
        ):
            raise ValueError(f"Wheel is not a valid pure Python cohort member: {path}")
        return name, version


def wheel_artifact(path: Path) -> dict[str, str]:
    name, version = wheel_identity(path)
    return {
        "distribution": name,
        "version": version,
        "path": f"wheels/{path.name}",
        "sha256": digest(path, MAX_WHEEL_BYTES),
    }


def project_metadata(root: Path) -> tuple[str, str, dict[str, Path]]:
    config = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    project = config["project"]
    sources = config["tool"]["uv"]["sources"]
    selected: dict[str, Path] = {}
    direct = {
        requirement.split("==", 1)[0].split("[", 1)[0]
        for requirement in project["dependencies"]
        if "==" in requirement
    }
    for name in sorted(set(FRAMEWORK_NAMES) | (direct & sources.keys())):
        relative = Path(sources[name]["path"])
        if relative.parent.as_posix() != "vendor/wheels":
            raise ValueError(f"Framework source must be vendored: {name}")
        selected[name] = root / relative
        wheel_name, wheel_version = wheel_identity(selected[name])
        if wheel_name != name:
            raise ValueError(f"Framework wheel identity differs from source: {name}")
        requirement = f"{name}=={wheel_version}"
        plain_requirements = {
            re.sub(r"\[[^]]+\]", "", item) for item in project["dependencies"]
        }
        if requirement not in plain_requirements:
            raise ValueError(f"Framework version differs from project pin: {name}")
    return normalized_name(project["name"]), project["version"], selected


def prepare(
    root: Path,
    manifest: Path,
    agent_wheel_dir: Path,
    output: Path,
    *,
    entrypoint: str | None = None,
    additional_wheels: tuple[Path, ...] = (),
) -> dict[str, str]:
    """Commit the explicit local executable closure and exact manifest."""
    root = root.resolve(strict=True)
    verify_framework_wheels(root)
    agent_name, agent_version, framework = project_metadata(root)
    agent_wheels = list(agent_wheel_dir.glob("*.whl"))
    if len(agent_wheels) != 1:
        raise ValueError("Expected exactly one built agent wheel")
    agent = agent_wheels[0]
    if wheel_identity(agent) != (agent_name, agent_version):
        raise ValueError("Built agent wheel differs from project identity")
    entrypoint = manifest_entrypoint(manifest, entrypoint)
    verify_wheel_entrypoint(agent, entrypoint)
    sources = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))[
        "tool"
    ]["uv"]["sources"]
    candidates = {name: root / config["path"] for name, config in sources.items()}
    discovered = provider_wheels(manifest, candidates, additional_wheels, framework)
    additional_by_path = dict.fromkeys((*additional_wheels, *discovered))
    selected = (agent, *framework.values(), *additional_by_path)
    identities = [wheel_identity(source)[0] for source in selected]
    if len(identities) != len(set(identities)) or not 4 <= len(selected) <= 64:
        raise ValueError("Executable closure has duplicate or excessive packages")
    manifest_hash = digest(manifest, MAX_MANIFEST_BYTES)
    if output.exists():
        raise ValueError("Use a fresh cohort directory; preserve prior artifacts")
    wheels = output / "wheels"
    wheels.mkdir(parents=True)
    copied: list[Path] = []
    for source in selected:
        target = wheels / source.name
        shutil.copyfile(source, target)
        copied.append(target)
    target_manifest = output / "cogit.yaml"
    shutil.copyfile(manifest, target_manifest)
    if digest(target_manifest, MAX_MANIFEST_BYTES) != manifest_hash:
        raise ValueError("Copied manifest differs from source")
    executable = {
        "contractVersion": "cogit.worker-executable.v1",
        "agentDistribution": agent_name,
        "entrypoint": entrypoint,
        "wheels": [wheel_artifact(path) for path in copied],
    }
    descriptor = encode(executable)
    if len(descriptor) > MAX_DESCRIPTOR_BYTES:
        raise ValueError("Executable descriptor exceeds Runtime's size limit")
    (output / "executable.json").write_bytes(descriptor)
    prepared = {
        "contractVersion": "cogit.worker-cohort-prepared.v1",
        "entrypoint": entrypoint,
        "executableSha256": hashlib.sha256(descriptor).hexdigest(),
        "manifestSha256": manifest_hash,
    }
    (output / "prepared.json").write_bytes(encode(prepared))
    return prepared


def read_prepared(cohort: Path) -> tuple[str, str]:
    descriptor_path = cohort / "executable.json"
    manifest_path = cohort / "cogit.yaml"
    executable_hash = digest(descriptor_path, MAX_DESCRIPTOR_BYTES)
    manifest_hash = digest(manifest_path, MAX_MANIFEST_BYTES)
    parsed: object = json.loads(descriptor_path.read_bytes())
    if not isinstance(parsed, dict):
        raise ValueError("Invalid prepared executable descriptor")
    executable = cast(dict[str, object], parsed)
    raw_wheels = executable.get("wheels")
    if (
        set(executable)
        != {"contractVersion", "agentDistribution", "entrypoint", "wheels"}
        or executable["contractVersion"] != "cogit.worker-executable.v1"
        or not isinstance(executable["entrypoint"], str)
        or not isinstance(raw_wheels, list)
        or not 4 <= len(cast(list[object], raw_wheels)) <= 64
    ):
        raise ValueError("Invalid prepared executable descriptor")
    selected_entrypoint = executable["entrypoint"]
    if len(selected_entrypoint) > 200 or not re.fullmatch(
        r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*:[A-Za-z_][A-Za-z0-9_]*",
        selected_entrypoint,
    ):
        raise ValueError("Invalid prepared entrypoint")
    manifest_entrypoint(manifest_path, selected_entrypoint)
    wheel_records = cast(list[object], raw_wheels)
    paths: set[str] = set()
    wheels: set[str] = set()
    for raw_artifact in wheel_records:
        if not isinstance(raw_artifact, dict):
            raise ValueError("Invalid prepared wheel record")
        artifact = cast(dict[str, object], raw_artifact)
        if set(artifact) != {
            "distribution",
            "version",
            "path",
            "sha256",
        }:
            raise ValueError("Invalid prepared wheel record")
        relative = artifact["path"]
        distribution = artifact["distribution"]
        version = artifact["version"]
        wheel_hash = artifact["sha256"]
        if not isinstance(relative, str) or not re.fullmatch(
            r"wheels/[A-Za-z0-9_.+-]+\.whl", relative
        ):
            raise ValueError("Invalid prepared wheel path")
        if not all(
            isinstance(value, str) for value in (distribution, version, wheel_hash)
        ):
            raise ValueError("Invalid prepared wheel identity")
        distribution = cast(str, distribution)
        version = cast(str, version)
        wheel_hash = cast(str, wheel_hash)
        path = cohort / relative
        if (
            wheel_identity(path) != (distribution, version)
            or digest(path, MAX_WHEEL_BYTES) != wheel_hash
        ):
            raise ValueError("Prepared wheel differs from descriptor")
        if distribution in wheels or relative in paths:
            raise ValueError("Duplicate prepared wheel")
        if distribution == executable["agentDistribution"]:
            verify_wheel_entrypoint(path, selected_entrypoint)
        wheels.add(distribution)
        paths.add(relative)
    agent_distribution = executable["agentDistribution"]
    if not isinstance(agent_distribution, str):
        raise ValueError("Invalid prepared agent distribution")
    if agent_distribution in FRAMEWORK_NAMES or not (
        set(FRAMEWORK_NAMES) | {agent_distribution}
    ).issubset(wheels):
        raise ValueError("Prepared wheel closure is incomplete")
    return executable_hash, manifest_hash


def receipt(cohort: Path, ids: dict[str, str], published: dict[str, str]) -> Path:
    """Bind a prepared cohort to IDs and hashes from the published route."""
    executable_hash, manifest_hash = read_prepared(cohort)
    if set(published) != {"executableSha256", "manifestSha256"}:
        raise ValueError("Published hashes must contain only the two artifact hashes")
    for key, actual in (
        ("executableSha256", executable_hash),
        ("manifestSha256", manifest_hash),
    ):
        value = published[key]
        if not HEX_DIGEST.fullmatch(value) or value != actual:
            raise ValueError(f"Published {key} differs from prepared bytes")
    parsed_ids = {key: str(UUID(value)) for key, value in ids.items()}
    if any(UUID(value).int == 0 for value in parsed_ids.values()):
        raise ValueError("Published route IDs cannot be nil UUIDs")
    route = {
        key: parsed_ids[key]
        for key in (
            "installationId",
            "definitionId",
            "versionId",
            "deploymentId",
            "poolId",
            "agentPrincipalId",
        )
    }
    route["executableSha256"] = executable_hash
    route["manifestSha256"] = manifest_hash
    body = encode(
        {
            "contractVersion": "cogit.worker-cohort.v1",
            "tenantId": parsed_ids["tenantId"],
            "route": route,
            "manifest": "cogit.yaml",
            "executable": "executable.json",
        }
    )
    path = cohort / "receipt.json"
    with path.open("xb") as target:
        target.write(body)
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    first = commands.add_parser("prepare", help="Prepare exact local artifact bytes")
    first.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    first.add_argument("--manifest", type=Path, required=True)
    first.add_argument("--agent-wheel-dir", type=Path, required=True)
    first.add_argument("--output", type=Path, required=True)
    first.add_argument("--agent", help="Legacy selector; must agree with cogit.yaml")
    first.add_argument("--additional-wheel", type=Path, action="append", default=[])
    second = commands.add_parser("receipt", help="Bind a real published route")
    second.add_argument("--cohort", type=Path, required=True)
    for name in (
        "tenant-id",
        "installation-id",
        "definition-id",
        "version-id",
        "deployment-id",
        "pool-id",
        "agent-principal-id",
    ):
        second.add_argument(f"--{name}", required=True)
    second.add_argument("--published-executable-sha256", required=True)
    second.add_argument("--published-manifest-sha256", required=True)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            print(
                encode(
                    prepare(
                        args.root,
                        args.manifest,
                        args.agent_wheel_dir,
                        args.output,
                        entrypoint=args.agent,
                        additional_wheels=tuple(args.additional_wheel),
                    )
                ).decode(),
                end="",
            )
        else:
            ids = {
                "tenantId": args.tenant_id,
                "installationId": args.installation_id,
                "definitionId": args.definition_id,
                "versionId": args.version_id,
                "deploymentId": args.deployment_id,
                "poolId": args.pool_id,
                "agentPrincipalId": args.agent_principal_id,
            }
            published = {
                "executableSha256": args.published_executable_sha256,
                "manifestSha256": args.published_manifest_sha256,
            }
            print(receipt(args.cohort, ids, published))
    except (OSError, ValueError, KeyError, TypeError, BadZipFile) as exc:
        parser.exit(1, f"Worker cohort preparation failed: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
