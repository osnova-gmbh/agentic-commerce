# pyright: basic
"""Operator configuration and message schemas, read from files (SPEC §14)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import yaml

from cogit_finance.escrow.schema_check import validate

DATA_DIR = Path(__file__).resolve().parent / "data"
PACKAGED_CONTRACTS_DIR = DATA_DIR / "messages"
PACKAGED_OPERATOR_CONFIG = DATA_DIR / "operator.example.yaml"
OPERATOR_SCHEMA = DATA_DIR / "operator.schema.json"

OPERATOR_CONFIG_ENV = "COGIT_FINANCE_OPERATOR_CONFIG"
CONTRACTS_DIR_ENV = "FINANCE_CONTRACTS_DIR"
TYPE_PREFIX = "finance."


def check_operator_config(config: Any) -> dict[str, Any]:
    """Return the config when it fits ``operator.schema.json``; raise otherwise."""
    schema = json.loads(OPERATOR_SCHEMA.read_text(encoding="utf-8"))
    error = validate(schema, config, "operator config")
    if error:
        raise ValueError(error)
    if config["rail"]["kind"] != "sim":
        raise ValueError("operator config: only the sim rail is built in the demo")
    return config


def load_operator_config(path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    """The YAML at ``path``, else at ``COGIT_FINANCE_OPERATOR_CONFIG``, else the
    packaged copy of ``config/operator.example.yaml``."""
    source = path or os.environ.get(OPERATOR_CONFIG_ENV) or PACKAGED_OPERATOR_CONFIG
    with open(source, encoding="utf-8") as handle:
        return check_operator_config(yaml.safe_load(handle))


def contracts_dir(path: str | os.PathLike[str] | None = None) -> Path:
    """``path``, else ``FINANCE_CONTRACTS_DIR``, else the packaged schemas."""
    return Path(path or os.environ.get(CONTRACTS_DIR_ENV) or PACKAGED_CONTRACTS_DIR)


def load_message_schemas(
    directory: str | os.PathLike[str],
) -> dict[tuple[str, int], dict[str, Any]]:
    """``(type_key, type_version) -> schema`` for every ``finance.*.v<N>.json``."""
    schemas: dict[tuple[str, int], dict[str, Any]] = {}
    for path in sorted(Path(directory).glob(f"{TYPE_PREFIX}*.v*.json")):
        type_key, _, version = path.name.removesuffix(".json").rpartition(".v")
        if not version.isdigit():
            continue
        schemas[(type_key, int(version))] = json.loads(path.read_text("utf-8"))
    if not schemas:
        raise ValueError(f"no finance message schemas in {directory}")
    return schemas
