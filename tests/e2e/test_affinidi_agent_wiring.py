"""Three-agent integration tests; injected transport is not a live gateway."""

import asyncio
import json
from datetime import UTC, datetime

import pytest

from buyer_agent.identity import identity as buyer_identity
from seller_agent.identity import identity as seller_identity
from cogit_finance.identity import identity as escrow_identity
from cogit_messaging_shim import build_envelope, verify_envelope
from cogit_messaging_shim.affinidi import verify_jws
from cogit_messaging_shim.affinidi.runtime import AgentIdentityRuntime

IDENTITIES = [buyer_identity, seller_identity, escrow_identity]


@pytest.fixture(autouse=True)
def isolate_public_project_configuration(monkeypatch):
    monkeypatch.setenv("BORIS_IDENTITY_ENABLED", "0")


def configured(identity, key_path, *, startup="1"):
    prefix = identity.role.upper() + "_AFFINIDI_"
    return {
        "AGENT_KEY_FILE": str(key_path),
        "BORIS_IDENTITY_ENABLED": "0",
        prefix + "SURFACE_URL": "https://gateway.example/" + identity.role,
        prefix + "AUDIENCE": "urn:commerce:" + identity.role,
        prefix + "SESSION_HEADER": "X-DID-Session",
        prefix + "AUTHENTICATE_ON_STARTUP": startup,
    }


def test_three_default_identities_are_separate_and_persistent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    keys = [identity.load_key({}) for identity in IDENTITIES]
    assert len({key.did for key in keys}) == 3
    assert [identity.load_key({}).did for identity in IDENTITIES] == [key.did for key in keys]
    for key in keys:
        envelope = build_envelope(key, key.did, "finance.receipt", 1, keys[0].did, "deal", {})
        assert verify_envelope(envelope)


@pytest.mark.parametrize("identity", IDENTITIES, ids=lambda item: item.role)
def test_startup_authenticates_with_the_existing_finance_key(identity, tmp_path):
    env = configured(identity, tmp_path / (identity.role + ".key"))
    key = identity.load_key(env)
    now = [1_800_000_000.0]
    calls = []

    def transport(method, url, payload, headers):
        calls.append((method, url, payload, headers))
        assert method == "POST"
        assert headers == {}
        assert payload["did"] == key.did
        if url.endswith("/authenticate/challenge"):
            return {"challenge": "challenge-" + identity.role, "expires_in": 60}
        assert url.endswith("/authenticate")
        verify_jws(
            payload["challenge_response"], key.did,
            expected_claims={"challenge": "challenge-" + identity.role,
                             "aud": "urn:commerce:" + identity.role}, now=now[0],
        )
        return {"session_id": "DO_NOT_PRINT_THIS_SESSION", "expires_in": 300,
                "expires_at": datetime.fromtimestamp(now[0] + 300, UTC).isoformat()}

    runtime = AgentIdentityRuntime(identity, environ=env, transport=transport, now=lambda: now[0])
    runtime.startup()
    assert len(calls) == 2
    status = runtime.status()
    assert status["did"] == key.did
    assert status["mode"] == "affinidi_did_auth"
    assert status["authenticated"] is True
    assert "DO_NOT_PRINT_THIS_SESSION" not in json.dumps(status)
    now[0] += 301
    assert runtime.status()["authenticated"] is False


def test_gateway_configuration_does_not_start_network_without_opt_in(tmp_path):
    env = configured(buyer_identity, tmp_path / "buyer.key", startup="0")
    runtime = AgentIdentityRuntime(
        buyer_identity, environ=env,
        transport=lambda *args: pytest.fail("Network used without startup opt-in"),
    )
    runtime.startup()
    assert runtime.status()["configured"] is True
    assert runtime.status()["authenticated"] is False


def test_startup_authentication_fails_closed_without_gateway(tmp_path):
    runtime = AgentIdentityRuntime(buyer_identity, environ={
        "AGENT_KEY_FILE": str(tmp_path / "buyer.key"),
        "AFFINIDI_AUTHENTICATE_ON_STARTUP": "1",
    })
    with pytest.raises(ValueError, match="not configured"):
        runtime.startup()


def test_role_configuration_overrides_shared_gateway(tmp_path):
    env = configured(seller_identity, tmp_path / "seller.key")
    env.update({"AFFINIDI_SURFACE_URL": "https://other.example/surface",
                "AFFINIDI_AUDIENCE": "other", "AFFINIDI_SESSION_HEADER": "Other"})
    config = seller_identity.configuration(env)
    assert config.surface_url == "https://gateway.example/seller"
    assert config.audience == "urn:commerce:seller"
    assert config.session_header == "X-DID-Session"


@pytest.mark.parametrize("package", ["buyer_agent", "seller_agent", "cogit_finance"])
def test_real_agents_expose_commands_and_identity_health(package, tmp_path, monkeypatch):
    from importlib import import_module

    monkeypatch.chdir(tmp_path)
    for name in list(__import__("os").environ):
        if name.startswith("AFFINIDI_") or "_AFFINIDI_" in name or name == "AGENT_KEY_FILE":
            monkeypatch.delenv(name, raising=False)
    agent = import_module(package).Agent()
    groups = {group.name: group for group in agent.commands()}
    assert {command.name for command in groups["identity"].commands} == {"status", "authenticate"}
    asyncio.run(agent.startup())
    status = agent.health()["identity"]
    assert status["did"].startswith("did:key:z6Mk")
    assert status["mode"] == "local_did_key"
    assert status["authenticated"] is False


def test_authenticate_command_never_prints_gateway_errors(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("AGENT_KEY_FILE", str(tmp_path / "buyer.key"))
    monkeypatch.setattr(type(buyer_identity), "authenticate",
                        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("SECRET_SESSION")))
    command = next(item for item in buyer_identity.cli_commands().commands if item.name == "authenticate")
    assert command.handler(None, None) == 1
    output = capsys.readouterr()
    assert "SECRET_SESSION" not in output.out + output.err
    assert "failed" in output.err


@pytest.mark.parametrize("identity", IDENTITIES, ids=lambda item: item.role)
def test_project_payload_identity_reaches_every_boris_request(identity, tmp_path):
    from cogit_messaging_shim.affinidi.boris import MCPHTTPResponse

    config = tmp_path / "agent-identity.json"
    config.write_text(json.dumps({
        "enabled": True, "mode": "boris-payload",
        "endpoint": "https://gateway.example/agents/test-project",
        "agents": {item.agent_id: {"application_name": item.agent_id} for item in IDENTITIES},
    }), encoding="utf-8")
    env = {"BORIS_IDENTITY_CONFIG": str(config), "AGENT_KEY_FILE": str(tmp_path / "agent.key")}
    methods = []

    def transport(method, url, payload, headers):
        assert method == "POST"
        assert url == "https://gateway.example/agents/test-project"
        assert payload["params"]["_meta"]["agentIdentity"]["applicationInfo"]["name"] == identity.agent_id
        methods.append(payload["method"])
        if "id" not in payload:
            return MCPHTTPResponse(202, {}, "")
        result = {"protocolVersion": "2025-03-26"} if payload["method"] == "initialize" else {"tools": []}
        return MCPHTTPResponse(200, {"Content-Type": "application/json"},
                               json.dumps({"jsonrpc": "2.0", "id": payload["id"], "result": result}))

    assert identity.boris_client(env, transport=transport).list_tools() == []
    assert methods == ["initialize", "notifications/initialized", "tools/list"]
    status = AgentIdentityRuntime(identity, environ=env).status()
    assert status["mode"] == "boris_payload"
    assert status["payload_identity_enabled"] is True
    assert status["application_name"] == identity.agent_id
    assert status["authenticated"] is False  # Payload metadata is not DID proof.


def test_enabled_project_configuration_requires_this_agent_mapping(tmp_path):
    config = tmp_path / "agent-identity.json"
    config.write_text(json.dumps({"enabled": True, "mode": "boris-payload",
                                 "endpoint": "https://gateway.example/mcp", "agents": {}}))
    with pytest.raises(ValueError, match="application name"):
        buyer_identity.boris_configuration({"BORIS_IDENTITY_CONFIG": str(config)})
