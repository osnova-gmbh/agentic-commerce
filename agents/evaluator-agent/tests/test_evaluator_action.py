"""The bound ``handle_message`` action on the local run-handle stand-in."""

from __future__ import annotations

from pathlib import Path

import pytest
from agent_helpers import configured_evaluator_agent
from cogit_agent_sdk.types import Context
from cogit_finance_seams import LocalArtifacts
from cogit_finance_seams.cogit_host import LocalRunHandle, invoke_action
from cogit_messaging_shim import AgentKey, verify_envelope
from finance_fakes import (
    DEAL_ID,
    REQUIRED_FILES,
    FakeModules,
    evaluation_request,
    make_zip,
)


def _handle(modules: FakeModules, artifacts: LocalArtifacts) -> LocalRunHandle:
    context = Context(tenant_id="local", correlation_id="run-1", agent_id="evaluator")
    return LocalRunHandle("run-1", context, modules=modules, artifacts=artifacts)


def test_handle_message_action_sends_a_signed_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    key_file = tmp_path / "keys" / "evaluator-agent.key"
    monkeypatch.setenv("AGENT_KEY_FILE", str(key_file))
    monkeypatch.delenv("ESCROW_DID", raising=False)
    escrow = AgentKey.generate()
    modules, artifacts = FakeModules(escrow_did=escrow.did), LocalArtifacts()
    artifact = artifacts.put(make_zip(["report.md", "data.csv"]), "application/zip")
    agent = configured_evaluator_agent()
    # The evaluator's own DID is not needed to build the request: any recipient works.
    request = evaluation_request(
        escrow,
        AgentKey.generate().did,
        artifact,
        "required-files",
        {"required_files": REQUIRED_FILES},
    )

    for _ in range(2):  # the same message twice: one verdict ID
        output = invoke_action(
            agent,
            "handle_message",
            {"envelope": request},
            _handle(modules, artifacts),
            idempotency_key=f"msg:{request['message_id']}",
        )
        assert output == {"status": "processed", "reason": None}

    first, second = modules.sent()
    assert first["message_id"] == second["message_id"]
    assert verify_envelope(first)
    assert first["sender_did"] == AgentKey.load_or_create(key_file).did
    assert first["recipient_did"] == escrow.did
    assert first["conversation_id"] == DEAL_ID
    assert first["causation_id"] == request["message_id"]
    assert first["body"]["outcome"] == "fail"
    assert first["body"]["reasons"] == ["missing_file: summary.json"]
    assert (
        modules.queries
        == [("cogit-messaging", "identity.resolve", {"role": "escrow"})] * 2
    )
    assert modules.commands[0][3] == f"send:{first['message_id']}"


def test_handle_message_action_takes_the_escrow_did_from_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    escrow, stranger = AgentKey.generate(), AgentKey.generate()
    monkeypatch.setenv("AGENT_KEY_FILE", str(tmp_path / "evaluator-agent.key"))
    monkeypatch.setenv("ESCROW_DID", escrow.did)
    modules, artifacts = FakeModules(), LocalArtifacts()
    artifact = artifacts.put(make_zip(REQUIRED_FILES), "application/zip")
    request = evaluation_request(
        escrow, AgentKey.generate().did, artifact, "integrity", sender_key=stranger
    )

    output = invoke_action(
        configured_evaluator_agent(),
        "handle_message",
        {"envelope": request},
        _handle(modules, artifacts),
    )

    assert output == {"status": "rejected", "reason": "unexpected_sender"}
    assert modules.queries == []
    assert modules.sent() == []
