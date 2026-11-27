"""Load immutable reference database resources from an installed distribution."""

from __future__ import annotations

import hashlib
import json
from importlib.resources import files
from typing import Any, Literal, cast


def load_database_bundle(
    *,
    historical: bool = False,
    historical_version: Literal[
        "1.0.0", "1.1.0", "1.1.1", "1.1.2", "1.1.3", "1.1.4", "1.1.5", "1.1.6"
    ]
    | None = None,
) -> tuple[dict[str, Any], str]:
    """Verify the active or explicitly retained bundle and return its digest."""
    if historical and historical_version is not None:
        raise ValueError("Select only one historical bundle selector")
    retained = "1.0.0" if historical else historical_version
    if retained not in {
        None,
        "1.0.0",
        "1.1.0",
        "1.1.1",
        "1.1.2",
        "1.1.3",
        "1.1.4",
        "1.1.5",
        "1.1.6",
    }:
        raise ValueError("Unknown retained database bundle")
    package = files("seller_agent")
    root = package.joinpath("database")
    if retained is not None:
        root = root.joinpath("historical", f"module-{retained}")
    try:
        manifest_bytes = root.joinpath("manifest.json").read_bytes()
        manifest = cast(dict[str, Any], json.loads(manifest_bytes))
        paths: set[str] = set()
        for item in [*manifest["files"], *manifest["migrations"]]:
            path = item["path"]
            if not isinstance(path, str):
                raise ValueError("Invalid database resource path")
            parts = path.split("/")
            if (
                path in paths
                or any(part in ("", ".", "..") for part in parts)
                or "\\" in path
                or ":" in path
            ):
                raise ValueError("Invalid or duplicate database resource path")
            paths.add(path)
            content = root.joinpath(*parts).read_bytes()
            if hashlib.sha256(content).hexdigest() != item["sha256"]:
                raise ValueError(f"Database resource hash mismatch: {path}")
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Database bundle could not be loaded") from exc
    canonical = json.dumps(
        manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return manifest, hashlib.sha256(canonical).hexdigest()
