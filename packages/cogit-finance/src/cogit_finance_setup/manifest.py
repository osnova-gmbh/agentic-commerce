"""Runtime composition helpers; agent domain code never imports this package."""

from __future__ import annotations

import os
import re
import stat
import tempfile
from importlib import import_module
from pathlib import Path
from typing import Any, cast

import yaml
from cogit_agent_sdk import AgentServices, CogitAgent
from cogit_runtime.config import RuntimeEnvironment
from cogit_runtime.manifest import parse_manifest
from cogit_runtime.readiness import prepare_model_profile

from cogit_finance.capabilities import configuration

from .errors import SetupError
from .policy import require_policy_package

POLICY_CONTRACT = {"authority": "agentdb", "contract": "runtime.checkpoint.v1"}


def read_manifest(path: Path) -> dict[str, Any]:
    """Read bounded YAML using the Runtime's actual manifest schema and aliases."""
    try:
        if path.stat().st_size > 2 * 1024 * 1024:
            raise SetupError("Manifest exceeds the 2 MiB bound")
        raw: object = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise SetupError("Cannot read the manifest as YAML") from exc
    if not isinstance(raw, dict):
        raise SetupError("Manifest must be an object with text keys")
    mapping = cast(dict[object, object], raw)
    if not all(isinstance(key, str) for key in mapping):
        raise SetupError("Manifest must be an object with text keys")
    result: dict[str, Any] = {cast(str, key): value for key, value in mapping.items()}
    parse_manifest(result)
    return result


def _agent_class(entrypoint: object) -> type[CogitAgent]:
    if (
        not isinstance(entrypoint, str)
        or len(entrypoint) > 200
        or re.fullmatch(
            r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*:[A-Za-z_]\w*", entrypoint, re.ASCII
        )
        is None
    ):
        raise SetupError("Manifest metadata.entrypoint must be module:ClassName")
    module, name = entrypoint.split(":")
    try:
        selected: object = getattr(import_module(module), name, None)
    except Exception as exc:
        raise SetupError("Manifest metadata.entrypoint could not be imported") from exc
    if not isinstance(selected, type) or not issubclass(selected, CogitAgent):
        raise SetupError("Manifest metadata.entrypoint must name a CogitAgent class")
    return selected


def configured_agent(payload: dict[str, Any]) -> CogitAgent:
    """Validate declarations, then prepare providers without acquiring resources."""
    manifest = parse_manifest(payload)
    if any(isinstance(item, str) for item in manifest.config.model.fallbacks or ()):
        raise SetupError("Canonical model fallbacks require structured token bounds")
    descriptor = manifest.descriptor
    agent_class = _agent_class((descriptor.metadata or {}).get("entrypoint"))
    settings = configuration(descriptor)
    if settings.providers:
        metadata = dict(descriptor.metadata or {})
        if metadata.get("cogit_policy", POLICY_CONTRACT) != POLICY_CONTRACT:
            raise SetupError(
                "Selected providers require the AgentDB lifecycle policy contract"
            )
        metadata["cogit_policy"] = dict(POLICY_CONTRACT)
        descriptor = descriptor.model_copy(update={"metadata": metadata})
        descriptor = require_policy_package(descriptor)
    # This checks declared provider/model capability consistency, without contacting
    # a model or admitting work. Production admission stays with Runtime/AgentDB.
    profile = prepare_model_profile(
        descriptor, manifest.config, RuntimeEnvironment(dev_mode=True), agent_class
    )
    for ready in profile.models:
        selected = ready.descriptor()
        if selected.provider != "runtime":
            if any(
                type(bound) is not int or not 0 < bound <= 1_000_000_000
                for bound in (selected.context_window, selected.max_output_tokens)
            ):
                raise SetupError(
                    "Model context_window and max_output_tokens must be positive "
                    "bounded "
                    "integers before canonical worker deployment"
                )
    agent = agent_class()
    agent.descriptor = descriptor
    agent.configure(AgentServices())
    return agent


def resolved_manifest(payload: dict[str, Any]) -> dict[str, Any]:
    """Return canonical declarations while preserving operator-owned configuration."""
    agent = configured_agent(payload)
    result: dict[str, Any] = {
        **payload,
        "metadata": agent.descriptor.metadata,
        "actions": [
            binding.descriptor.model_dump(mode="json", by_alias=False)
            for binding in agent.action_bindings()
        ],
        "tools": [
            binding.descriptor.model_dump(mode="json", by_alias=False)
            for binding in agent.tool_bindings()
        ],
    }
    if agent.descriptor.database_packages:
        result.pop("databasePackages", None)
        result["database_packages"] = [
            item.model_dump(mode="json", by_alias=False)
            for item in agent.descriptor.database_packages
        ]
    return result


def write_manifest(path: Path, payload: dict[str, Any]) -> None:
    """Replace validated YAML without changing an existing POSIX access mode."""
    pending: Path | None = None
    try:
        mode = (
            stat.S_IMODE(path.stat().st_mode)
            if os.name != "nt" and path.exists()
            else None
        )
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as output:
            pending = Path(output.name)
            yaml.safe_dump(payload, output, sort_keys=False)
        if mode is not None:
            pending.chmod(mode)
        pending.replace(path)
    except (OSError, yaml.YAMLError) as exc:
        raise SetupError("Could not write the validated manifest") from exc
    finally:
        if pending is not None:
            pending.unlink(missing_ok=True)
