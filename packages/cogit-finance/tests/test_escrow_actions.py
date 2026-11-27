"""E's bound actions, run the way a run host runs them.

``handle_message`` and ``tick`` are invoked through ``invoke_action`` on a
``LocalRunHandle`` whose database and artifact seams end in the test fakes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from agent_helpers import configured_cogit_finance
from cogit_agent_sdk.types import Context
from cogit_finance_seams.cogit_host import LocalRunHandle, invoke_action
from cogit_messaging_shim import AgentKey
from escrow_checks import assert_chain, assert_sequence, load_sequence
from escrow_data import HAPPY_DEAL
from escrow_world import World
from pydantic import ValidationError

from cogit_finance import escrow_operations
from cogit_finance.escrow import settings

Row = dict[str, Any]


@pytest.fixture
def hosted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> World:
    """A world whose E is reached only through the agent's bound actions."""
    key_file = tmp_path / "keys" / "cogit-finance.key"
    monkeypatch.setenv(escrow_operations.AGENT_KEY_FILE_ENV, str(key_file))
    monkeypatch.delenv(settings.OPERATOR_CONFIG_ENV, raising=False)
    monkeypatch.delenv(settings.CONTRACTS_DIR_ENV, raising=False)
    world = World(escrow_key=AgentKey.load_or_create(key_file))
    monkeypatch.setattr(escrow_operations, "bank_factory", lambda config: world.bank)
    monkeypatch.setattr(escrow_operations, "clock", world.clock.now)
    agent = configured_cogit_finance()
    runs = {"n": 0}

    def invoke(action: str, payload: Row) -> Row:
        runs["n"] += 1
        run_id = f"cogit-finance-{runs['n']:05d}"
        context = Context(
            tenant_id="local", correlation_id=run_id, agent_id="cogit-finance"
        )
        handle = LocalRunHandle(
            run_id, context, modules=world.modules, artifacts=world.artifacts
        )
        return invoke_action(agent, action, payload, handle, idempotency_key=run_id)

    world.handle = lambda envelope: invoke("handle_message", {"envelope": envelope})
    world.run_tick = lambda: invoke("tick", {})
    world.invoke = invoke  # type: ignore[attr-defined]
    return world


def test_the_happy_path_runs_through_the_bound_actions(hosted: World) -> None:
    assert hosted.run_tick() == {
        "types_registered": 14,
        "credits_seen": 0,
        "deals_funded": 0,
        "outbox_sent": 0,
    }
    hosted.happy_path()
    deal = hosted.read(HAPPY_DEAL)
    assert_sequence(deal, load_sequence("happy-path.events.json"))
    assert_chain(deal)
    assert deal["deal"]["terms"]["escrow_did"] == hosted.escrow.did
    assert hosted.bank.transfers[f"{HAPPY_DEAL}:payout"]["amount_minor"] == 49500
    assert hosted.bank.transfers[f"{HAPPY_DEAL}:fee"]["amount_minor"] == 500


def test_handle_message_reports_a_refusal_as_output(hosted: World) -> None:
    forged = hosted.envelope(hosted.buyer, "accept_terms", HAPPY_DEAL, {})
    forged["signature"] = "AAAA"
    assert hosted.handle(forged) == {"status": "rejected", "reason": "bad_signature"}
    unknown = hosted.send(
        hosted.buyer, "accept_terms", HAPPY_DEAL, {"terms_hash": "0" * 64}
    )
    assert unknown == {"status": "rejected", "reason": "illegal_in_state"}


def test_the_action_contracts_forbid_extra_fields(hosted: World) -> None:
    with pytest.raises(ValidationError):
        hosted.invoke("tick", {"force": True})  # type: ignore[attr-defined]
    with pytest.raises(ValidationError):
        hosted.invoke("handle_message", {})  # type: ignore[attr-defined]


def test_settings_come_from_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    default = settings.load_operator_config()
    assert default["escrow"]["fee_bps"] == 100
    assert default["rail"]["sim"]["base_url"] == "http://sim-bank:8080"
    text = settings.PACKAGED_OPERATOR_CONFIG.read_text(encoding="utf-8")
    custom = tmp_path / "operator.yaml"
    custom.write_text(text.replace("fee_bps: 100", "fee_bps: 250"), encoding="utf-8")
    monkeypatch.setenv(settings.OPERATOR_CONFIG_ENV, str(custom))
    assert settings.load_operator_config()["escrow"]["fee_bps"] == 250
    custom.write_text(text.replace("fee_bps: 100", "fee_bps: 1.5"), encoding="utf-8")
    with pytest.raises(ValueError, match="fee_bps"):
        settings.load_operator_config()

    monkeypatch.setenv(settings.CONTRACTS_DIR_ENV, str(tmp_path / "schemas"))
    assert settings.contracts_dir() == tmp_path / "schemas"
    monkeypatch.setenv(escrow_operations.SIM_BANK_URL_ENV, "http://localhost:8080")
    bank = escrow_operations.sim_bank(default)
    assert bank is escrow_operations.sim_bank(default)  # one client per URL
