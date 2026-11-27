"""Declare the central policy service dependency; no policy content lives here."""

from __future__ import annotations

import hashlib
import json
from importlib.resources import files

from cogit_agent_sdk.types import AgentDescriptor
from cogit_agent_sdk.types.database import DatabasePackageRequirement
from pydantic import ValidationError

from .errors import SetupError

_LEGACY_PIN = "d8af77ff5c9041b437e929682322fb537529a20d3dab226dc7ead5e0c5167687"
_CURRENT_PIN = "a0d0339c8df28e8e3e9e86dc986a6a915b6bf22e941ab769c504d5b9ad04d8b8"
_POLICY_RESOURCE_SHA256 = {
    "runtime-policy-package.json": _LEGACY_PIN,
    "universal-policy-package.json": _CURRENT_PIN,
}


def _selected_requirement(name: str) -> DatabasePackageRequirement:
    try:
        package = files("seller_agent_setup")
        with package.joinpath(name).open("rb") as stream:
            encoded: bytes = stream.read(4097)
    except OSError as exc:
        raise SetupError("Selected policy service package is unavailable") from exc
    if len(encoded) > 4096:
        raise SetupError("Selected policy package exceeds its bound")
    try:
        raw = json.loads(encoded)
        canonical = json.dumps(
            raw, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise SetupError("Selected policy service package is invalid") from exc
    if hashlib.sha256(canonical).hexdigest() != _POLICY_RESOURCE_SHA256[name]:
        raise SetupError("Selected policy service package integrity differs")
    try:
        return DatabasePackageRequirement.model_validate(raw)
    except ValidationError as exc:
        raise SetupError("Selected policy service package is invalid") from exc


def require_policy_package(descriptor: AgentDescriptor) -> AgentDescriptor:
    """Pin the AgentDB export whose operator-installed policies authorize work."""
    packages = list(descriptor.database_packages)
    for name in _POLICY_RESOURCE_SHA256:
        requirement = _selected_requirement(name)
        existing = next(
            (item for item in packages if item.module_key == requirement.module_key),
            None,
        )
        if existing is None:
            packages.append(requirement)
        elif existing != requirement:
            raise SetupError(
                "Policy service package differs from the selected template cohort"
            )
    # AgentDescriptor also validates cardinality and duplicate package identities.
    values = descriptor.model_dump()
    values["database_packages"] = [item.model_dump() for item in packages]
    return AgentDescriptor.model_validate(values)
