"""Bind the executable entrypoint to the native manifest and selected agent wheel."""

from __future__ import annotations

import ast
import re
from pathlib import Path
from zipfile import ZipFile

from cogit_runtime.manifest import load_manifest

ENTRYPOINT = re.compile(
    r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*:[A-Za-z_][A-Za-z0-9_]*\Z"
)
MAX_SOURCE_BYTES = 1024 * 1024


def manifest_entrypoint(manifest: Path, explicit: str | None = None) -> str:
    """Use cogit.yaml; an explicit legacy selector must agree when both exist."""
    descriptor = load_manifest(manifest).descriptor
    authored = (descriptor.metadata or {}).get("entrypoint")
    selected = authored if authored is not None else explicit
    if (
        not isinstance(selected, str)
        or len(selected) > 200
        or not ENTRYPOINT.fullmatch(selected)
    ):
        raise ValueError("Manifest metadata.entrypoint must name an agent class")
    if explicit is not None and selected != explicit:
        raise ValueError("Explicit agent differs from manifest metadata.entrypoint")
    return selected


def verify_wheel_entrypoint(wheel: Path, entrypoint: str) -> None:
    """Check the template's concrete class without importing untrusted wheel code."""
    module, class_name = entrypoint.split(":")
    module_path = module.replace(".", "/")
    with ZipFile(wheel) as archive:
        names = archive.namelist()
        candidates = [
            name
            for name in (module_path + ".py", module_path + "/__init__.py")
            if name in names
        ]
        if not candidates:
            raise ValueError("Agent wheel does not contain the entrypoint module")
        if len(candidates) != 1 or names.count(candidates[0]) != 1:
            raise ValueError("Agent wheel has an ambiguous entrypoint module")
        source_name = candidates[0]
        member = archive.getinfo(source_name)
        if member.file_size > MAX_SOURCE_BYTES:
            raise ValueError("Agent entrypoint source exceeds the size limit")
        try:
            source = ast.parse(archive.read(member), filename=source_name)
        except (SyntaxError, ValueError) as exc:
            raise ValueError("Agent entrypoint source is invalid Python") from exc
        if not any(
            isinstance(node, ast.ClassDef) and node.name == class_name
            for node in source.body
        ):
            raise ValueError("Agent wheel does not declare the entrypoint class")
