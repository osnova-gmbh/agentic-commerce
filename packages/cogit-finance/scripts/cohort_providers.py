"""Resolve selected entry-point owners to explicit local wheel artifacts."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from email.parser import BytesParser
from importlib.metadata import entry_points
from pathlib import Path
from typing import cast
from zipfile import ZipFile

import yaml


def _name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def selected_provider_names(manifest: Path) -> set[str]:
    if manifest.stat().st_size > 1024 * 1024:
        raise ValueError("Manifest exceeds the artifact size limit")
    payload: object = yaml.safe_load(manifest.read_bytes())
    if not isinstance(payload, dict):
        raise ValueError("Manifest must be an object")
    metadata: object = cast(dict[str, object], payload).get("metadata", {})
    if not isinstance(metadata, dict):
        raise ValueError("Manifest metadata must be an object")
    settings: object = cast(dict[str, object], metadata).get("cogit_tools", {})
    if not isinstance(settings, dict):
        raise ValueError("Tool settings must be an object")
    providers: object = cast(dict[str, object], settings).get("providers", [])
    if not isinstance(providers, list):
        raise ValueError("Provider selection must be a list")
    result: set[str] = set()
    installed = entry_points(group="cogit.tool_providers.v1")
    for selection in cast(list[object], providers):
        if not isinstance(selection, dict):
            raise ValueError("Provider selection must be an object")
        provider = cast(dict[str, object], selection).get("provider")
        if not isinstance(provider, str):
            raise ValueError("Provider selection requires a name")
        matches = [entry for entry in installed if entry.name == provider]
        if len(matches) != 1 or matches[0].dist is None:
            raise ValueError("Selected provider must have one installed distribution")
        result.add(_name(matches[0].dist.name))
    return result


def provider_wheels(
    manifest: Path,
    sources: Mapping[str, Path],
    additional: Sequence[Path],
    required: Mapping[str, Path],
) -> tuple[Path, ...]:
    """Select metadata only; never import provider code during artifact preparation."""
    candidates = dict(sources)
    dependencies: dict[str, set[str]] = {}
    for path in (*sources.values(), *additional):
        if path.stat().st_size > 32 * 1024 * 1024:
            raise ValueError("Provider wheel exceeds the artifact size limit")
        with ZipFile(path) as archive:
            names = archive.namelist()
            if len(names) > 4096 or len(names) != len(set(names)):
                raise ValueError("Provider wheel has excessive members")
            entries = [
                item
                for item in archive.namelist()
                if item.endswith(".dist-info/METADATA")
            ]
            if len(entries) != 1:
                raise ValueError(
                    "Provider wheel requires one distribution metadata file"
                )
            if archive.getinfo(entries[0]).file_size > 256 * 1024:
                raise ValueError("Provider wheel metadata exceeds the size limit")
            metadata = BytesParser().parsebytes(archive.read(entries[0]))
        name = _name(str(metadata.get("Name", "")))
        if name in candidates and candidates[name].resolve() != path.resolve():
            raise ValueError("Ambiguous wheel source for selected distribution")
        candidates[name] = path
        dependencies[name] = {
            _name(match.group(0))
            for item in metadata.get_all("Requires-Dist", [])
            if (match := re.match(r"[A-Za-z0-9_.-]+", str(item)))
        }
    pending = selected_provider_names(manifest)
    selected: set[str] = set()
    while pending:
        name = pending.pop()
        if name in selected or name in required:
            continue
        if name not in candidates:
            raise ValueError("Selected provider has no explicit local wheel artifact")
        selected.add(name)
        # External dependencies remain pinned by uv.lock/container installation.
        # Every dependency with a supplied local artifact joins this commitment.
        pending.update(dependencies[name] & candidates.keys() - selected)
    return tuple(candidates[name] for name in sorted(selected))
