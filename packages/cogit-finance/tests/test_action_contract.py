"""Action contract artifact parity tests."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from agent_helpers import configured_cogit_finance
from cogit_agent_sdk.operations import export_action_contract, parse_action_contract

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from manifest_sync import (  # noqa: E402
    canonical_action_contract_json,
    validate_action_contract_file,
)


def test_action_contract_matches_live_bindings() -> None:
    agent = configured_cogit_finance()
    contract_path = ROOT / "action-contract.v1.json"
    assert validate_action_contract_file(contract_path, agent) == []

    loaded = json.loads(contract_path.read_text(encoding="utf-8"))
    parsed = parse_action_contract(loaded)
    expected = parse_action_contract(export_action_contract(agent.action_bindings()))
    assert parsed == expected


def test_canonical_action_contract_json_is_deterministic() -> None:
    first = canonical_action_contract_json()
    second = canonical_action_contract_json()
    assert first == second
