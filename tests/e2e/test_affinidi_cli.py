import json
import os
from pathlib import Path
import subprocess
import sys
import runpy


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/affinidi_agents.py"


def run_cli(tmp_path, command, *extra):
    env = {name: value for name, value in os.environ.items() if "AFFINIDI_" not in name}
    return subprocess.run(
        [sys.executable, str(SCRIPT), command, "--key-dir", str(tmp_path), *extra],
        cwd=ROOT, env=env, text=True, capture_output=True, check=False,
    )


def test_init_creates_three_distinct_reusable_identities_without_exposing_keys(tmp_path):
    first = run_cli(tmp_path, "init")
    assert first.returncode == 0, first.stderr
    result = json.loads(first.stdout)
    identities = result["identities"]
    assert set(identities) == {"buyer", "seller", "escrow"}
    assert len({entry["did"] for entry in identities.values()}) == 3
    for entry in identities.values():
        assert Path(entry["key_file"]).read_text().strip() not in first.stdout
    second = run_cli(tmp_path, "init")
    assert json.loads(second.stdout)["identities"] == identities


def test_status_does_not_create_missing_keys(tmp_path):
    result = run_cli(tmp_path, "status")
    assert result.returncode == 1
    assert not list(tmp_path.iterdir())


def test_local_signatures_are_not_reported_as_live_gateway_verification(tmp_path):
    assert run_cli(tmp_path, "init").returncode == 0
    result = run_cli(tmp_path, "verify-local")
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["seller_quote_verified"] is True
    assert report["escrow_receipt_verified"] is True
    assert report["gateway_verified"] is False


def test_authenticate_requires_real_surface_configuration(tmp_path):
    assert run_cli(tmp_path, "init").returncode == 0
    result = run_cli(tmp_path, "authenticate")
    assert result.returncode == 1
    report = json.loads(result.stderr)
    assert "BUYER_AFFINIDI_SURFACE_URL" in report["error"]
    assert report["gateway_verified"] is False


def test_enable_configures_three_distinct_boris_payload_identities(tmp_path):
    config = tmp_path / "config/agent-identity.json"
    result = run_cli(tmp_path, "enable", "--config", str(config))
    assert result.returncode == 0, result.stderr
    saved = json.loads(config.read_text())
    assert saved["enabled"] is True
    assert saved["mode"] == "boris-payload"
    assert saved["endpoint"].endswith("/agents/teal-orchard-5580")
    assert {x["application_name"] for x in saved["agents"].values()} == {
        "buyer-agent", "seller-agent", "cogit-finance",
    }
    assert not list(tmp_path.glob("*.key"))
    assert json.loads(result.stdout)["remote_verified"] is False
    again = run_cli(tmp_path, "enable", "--config", str(config))
    assert again.returncode == 0
    assert json.loads(config.read_text()) == saved
    assert run_cli(tmp_path, "init").returncode == 0
    status = run_cli(tmp_path, "status", "--config", str(config))
    report = json.loads(status.stdout)
    assert all(report["configured"].values())
    assert report["remote_verified"] is False


def test_probe_checks_an_authenticated_roundtrip_for_each_agent(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    namespace = runpy.run_path(str(SCRIPT))
    probe = namespace["probe_boris"]
    key_path = tmp_path / "caller-key"
    key_path.write_text("test-key")
    config_path = tmp_path / "agent-identity.json"
    namespace["enable_boris"](config_path, "https://example.test/mcp")
    seen = []

    class Client:
        def __init__(self, endpoint, identity, *, headers, timeout_seconds):
            assert headers == {"x-boris-api-key": "test-key"}
            self.name = identity.application_name

        def initialize(self):
            return {"serverInfo": {"name": "test"}}

        def list_tools(self):
            return [{"name": "echo"}]

        def call_tool(self, name, arguments):
            seen.append((self.name, arguments))
            return {"content": [{"type": "text", "text": json.dumps(arguments)}]}

    monkeypatch.setitem(probe.__globals__, "BorisMCPClient", Client)
    result = probe(config_path, key_path)
    assert result["remote_exchange_verified"] is True
    assert result["identity_proof_verified"] is False
    assert {name for name, _ in seen} == {"buyer-agent", "seller-agent", "cogit-finance"}
    assert len({args["request_id"] for _, args in seen}) == 3
    assert "test-key" not in json.dumps(result)

    Client.call_tool = lambda *_: {"content": [{"type": "text", "text": "{}"}]}
    result = probe(config_path, key_path)
    assert result["remote_exchange_verified"] is False
    assert all(not item["roundtrip_verified"] for item in result["agents"].values())
