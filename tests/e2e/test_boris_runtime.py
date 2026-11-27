"""Real checkout paths must cross Boris before queue delivery or moving money."""

import copy
import json
from pathlib import Path

import pytest
from cogit_finance_seams import SimBankClient
from cogit_messaging_shim import verify_envelope
from cogit_messaging_shim.affinidi.boris import MCPHTTPResponse
from dashboard.boris import BorisConnectionError, BorisGateway
from dashboard.checkout import CatalogDemoEngine, create_checkout_app
from fastapi.testclient import TestClient
from sim_bank import create_app as create_bank_app

ROOT = Path(__file__).resolve().parents[2]


class EchoTransport:
    def __init__(self):
        self.calls = []
        self.fail = lambda arguments: False
        self.mutate = lambda arguments: arguments

    def __call__(self, method, url, envelope, headers):
        assert method == "POST"
        assert headers["x-boris-api-key"] == "test-caller-key"
        self.calls.append(copy.deepcopy(envelope))
        if envelope["method"] == "notifications/initialized":
            return MCPHTTPResponse(202, {}, "")
        if envelope["method"] == "initialize":
            result = {"protocolVersion": "2025-03-26", "capabilities": {"tools": {}},
                      "serverInfo": {"name": "test-echo", "version": "1"}}
        elif envelope["method"] == "tools/list":
            result = {"tools": [{"name": "echo", "inputSchema": {"type": "object"}}]}
        else:
            assert envelope["method"] == "tools/call"
            assert envelope["params"]["name"] == "echo"
            arguments = envelope["params"]["arguments"]
            if self.fail(arguments):
                return MCPHTTPResponse(503, {}, "")
            result = {"content": [{"type": "text", "text": json.dumps(self.mutate(copy.deepcopy(arguments)))}]}
        return MCPHTTPResponse(200, {"content-type": "application/json"},
                               json.dumps({"jsonrpc": "2.0", "id": envelope["id"], "result": result}))


@pytest.fixture
def connected(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config/agent-identity.json").write_text(json.dumps({
        "enabled": True, "mode": "boris-payload", "endpoint": "https://boris.example/agents/test",
        "agents": {name: {"application_name": name}
                   for name in ("buyer-agent", "seller-agent", "cogit-finance")},
    }))
    (tmp_path / ".state/boris").mkdir(parents=True)
    (tmp_path / ".state/boris/caller-key").write_text("test-caller-key")
    transport = EchoTransport()
    evidence = tmp_path / "evidence.jsonl"
    gateway = BorisGateway.from_config(tmp_path, transport=transport, evidence_path=evidence)
    with TestClient(create_bank_app()) as bank_http:
        engine = CatalogDemoEngine(ROOT, bank=SimBankClient(bank_http), step_delay=0, boris=gateway)
        yield engine, gateway, transport, evidence
        engine.close()


def prepare(engine):
    receipt = engine.prepare("seller-co", "offer-1", {"topic": "Boris integration"},
                             "prepare", background=False)
    engine.run_phase({"QUOTED"})
    assert engine.status()["state"] == "QUOTED", engine.status()["error"]
    return receipt["deal_id"]


def advance(engine, deal_id, action, state):
    engine.advance(deal_id, action, action, background=False)
    engine.run_phase({state})
    assert engine.status()["state"] == state, engine.status()["error"]


def test_checkout_uses_all_three_identities_and_records_exact_response_evidence(connected):
    engine, gateway, transport, evidence = connected
    deal_id = prepare(engine)
    advance(engine, deal_id, "fund", "FUNDED")
    advance(engine, deal_id, "deliver", "APPROVED")
    advance(engine, deal_id, "release", "SETTLED")
    report = gateway.report(deal_id)
    assert report["transport_kind"] == "test"
    assert report["summary"]["verified"] >= 15
    assert report["summary"]["failed"] == report["summary"]["pending"] == 0
    calls = [call for call in transport.calls if call["method"] == "tools/call"]
    assert {call["params"]["_meta"]["agentIdentity"]["applicationInfo"]["name"] for call in calls} == {
        "buyer-agent", "seller-agent", "cogit-finance"}
    arguments = [call["params"]["arguments"] for call in calls]
    assert {row["request_id"] for row in report["events"]} == {item["request_id"] for item in arguments}
    assert all(row["request_sha256"] == row["response_sha256"] for row in report["events"])
    messages = [item["message"] for item in arguments if "sender_did" in item["message"]]
    assert all(verify_envelope(message) for message in messages)
    assert {message["sender_did"] for message in messages} == {key.did for key in gateway.agent_keys.values()}
    assert len([item for item in arguments if item["message"].get("action") == "bank_transfer"]) == 3
    assert "test-caller-key" not in evidence.read_text()
    assert "signature" not in evidence.read_text()
    assert engine.source.balances(deal_id)["seller"] == 49500
    client = TestClient(create_checkout_app(engine))
    assert client.get("/api/demo/boris", params={"deal_id": deal_id}).json() == report
    assert client.get("/api/demo/boris", params={"deal_id": "archived-other"}).json()["events"] == []
    assert engine.status()["boris"] == report


def test_failed_prepare_is_visible_but_never_queued(connected):
    engine, gateway, transport, _ = connected
    before = engine.bank.accounts()
    transport.fail = lambda _: True
    with pytest.raises(BorisConnectionError):
        engine.prepare("seller-co", "offer-1", {"topic": "Blocked"}, "blocked", background=False)
    status = engine.status()
    assert status["error"] and status["order"]["service"]["offer_id"] == "offer-1"
    assert status["state"] is None
    assert engine.source.deals() == []
    assert engine.bank.accounts() == before
    assert gateway.report(status["deal_id"])["summary"] == {"pending": 0, "verified": 0, "failed": 1}


@pytest.mark.parametrize("stage,actor", [("fund", "buyer-agent"), ("release", "cogit-finance")])
def test_boris_outage_at_bank_boundary_prevents_the_transfer(connected, stage, actor):
    engine, gateway, transport, _ = connected
    deal_id = prepare(engine)
    if stage == "release":
        advance(engine, deal_id, "fund", "FUNDED")
        advance(engine, deal_id, "deliver", "APPROVED")
    before = engine.bank.accounts()
    transport.fail = lambda args: args["agent_id"] == actor and args["message"].get("action") == "bank_transfer"
    engine.advance(deal_id, stage, "fail-" + stage, background=False)
    engine.run_phase({"FUNDED" if stage == "fund" else "SETTLED"})
    assert engine.status()["error"]
    assert engine.status()["state"] not in {"FUNDED", "SETTLED"}
    assert engine.bank.accounts() == before
    failed = [row for row in gateway.report(deal_id)["events"] if row["status"] == "failed"]
    assert failed and failed[-1]["type_key"] == "checkout.bank_transfer"


def test_mismatched_remote_correlation_is_not_accepted_as_verified(connected):
    engine, gateway, transport, _ = connected
    transport.mutate = lambda args: {**args, "request_id": "another-request"}
    with pytest.raises(BorisConnectionError, match="did not match"):
        engine.prepare("seller-co", "offer-1", {"topic": "Mismatch"}, "mismatch", background=False)
    assert gateway.report()["summary"]["verified"] == 0
    assert engine.source.deals() == []


def test_offline_engine_never_claims_boris_execution():
    with TestClient(create_bank_app()) as bank_http:
        engine = CatalogDemoEngine(ROOT, bank=SimBankClient(bank_http), step_delay=0)
        try:
            assert engine.boris_report()["mode"] == "offline"
            assert engine.status()["boris"]["events"] == []
        finally:
            engine.close()
