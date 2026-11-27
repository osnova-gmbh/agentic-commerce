"""Initialize or verify the buyer, seller and escrow Affinidi identities."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time
import uuid

from run_demo import configure_paths

ROOT = configure_paths()

from cogit_messaging_shim import AgentKey
from cogit_messaging_shim.affinidi import (
    DidAuthClient, DidAuthConfig, sign_jws, sign_quote, verify_jws, verify_quote,
)
from cogit_messaging_shim.affinidi.boris import BorisAgentIdentity, BorisMCPClient

AGENTS = {"buyer": "buyer-agent", "seller": "seller-agent", "escrow": "cogit-finance"}
BORIS_ENDPOINT = "https://agent-gateway-01.agw.pool.boris-md.usw1.affinidi.io/agents/teal-orchard-5580"


def enable_boris(path: Path, endpoint: str) -> dict:
    # Validate using the same transport that will consume the configuration.
    BorisMCPClient(endpoint, BorisAgentIdentity("buyer-agent"))
    config = {"enabled": True, "mode": "boris-payload", "endpoint": endpoint,
              "agents": {name: {"application_name": name} for name in AGENTS.values()}}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return {"enabled": True, "mode": "boris-payload", "config_file": str(path.resolve()),
            "endpoint": endpoint, "agents": list(config["agents"]), "remote_verified": False}


def probe_boris(path: Path, key_path: Path | None = None) -> dict:
    config = json.loads(path.read_text(encoding="utf-8"))
    if config.get("enabled") is not True or config.get("mode") != "boris-payload":
        raise ValueError("Enable the project's Boris identity configuration first")
    key_path = key_path or ROOT / ".state/boris/caller-key"
    if not key_path.is_file():
        raise ValueError("Boris caller key is missing from .state/boris/caller-key")
    headers = {"x-boris-api-key": key_path.read_text(encoding="utf-8").strip()}
    result = {}
    for name in AGENTS.values():
        identity = BorisAgentIdentity(config["agents"][name]["application_name"])
        client = BorisMCPClient(config["endpoint"], identity, headers=headers, timeout_seconds=10)
        request_id = str(uuid.uuid4())
        try:
            initialized = client.initialize()
            available = client.list_tools()
            if "echo" not in {tool["name"] for tool in available}:
                raise RuntimeError("Boris does not expose its echo tool")
            expected = {"request_id": request_id, "agent_id": name,
                        "message": {"type": "connection.probe", "purpose": "agentic-commerce connection check"}}
            answer = client.call_tool("echo", expected)
            if answer.get("isError"):
                raise RuntimeError("Boris rejected the connection probe")
            echoed = answer.get("structuredContent")
            if echoed is None:
                texts = [item.get("text") for item in answer.get("content", [])
                         if isinstance(item, dict) and item.get("type") == "text"]
                echoed = json.loads(texts[0]) if len(texts) == 1 else None
            if echoed != expected:
                raise RuntimeError("Boris returned a different connection probe")
            result[name] = {"roundtrip_verified": True, "request_id": request_id,
                            "server": initialized.get("serverInfo", {})}
        except (ValueError, RuntimeError, OSError) as error:
            result[name] = {"roundtrip_verified": False, "request_id": request_id,
                            "error": str(error)}
    verified = all(entry["roundtrip_verified"] for entry in result.values())
    return {"mode": "boris-payload", "mcp_connected": verified,
            "remote_exchange_verified": verified,
            "identity_proof_verified": False, "agents": result}


def load_keys(directory: Path, create: bool = False) -> dict[str, AgentKey]:
    paths = {role: directory / f"{name}.key" for role, name in AGENTS.items()}
    if not create and any(not path.is_file() for path in paths.values()):
        raise ValueError("Initialize the three identities first with the init command")
    keys = {role: AgentKey.load_or_create(path) for role, path in paths.items()}
    if len({key.did for key in keys.values()}) != len(AGENTS):
        raise ValueError("Each agent must have an independent signing key")
    return keys


def setting(role: str, name: str) -> str:
    return os.environ.get(f"{role.upper()}_AFFINIDI_{name}") or os.environ.get(f"AFFINIDI_{name}", "")


def config_for(role: str) -> DidAuthConfig:
    values = {name: setting(role, name) for name in ("SURFACE_URL", "AUDIENCE", "SESSION_HEADER")}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise ValueError(f"{role}: configure " + ", ".join(f"{role.upper()}_AFFINIDI_{name}" for name in missing))
    return DidAuthConfig(
        surface_url=values["SURFACE_URL"], audience=values["AUDIENCE"],
        session_header=values["SESSION_HEADER"],
    )


def verify_local(keys: dict[str, AgentKey]) -> dict:
    now = int(time.time())
    nonce = str(uuid.uuid4())
    expected = {"sku": "identity-demo", "quantity": 1, "nonce": nonce, "amount_minor": 1000, "currency": "EUR"}
    quote = sign_quote(keys["seller"], **expected, now=now)
    buyer_claims = verify_quote(quote, keys["seller"].did, **expected, now=now)
    verify_quote(quote, keys["seller"].did, **expected, now=now)
    receipt_claims = {"buyer_did": keys["buyer"].did, "seller_did": keys["seller"].did,
                      "nonce": nonce, "status": "identity_verified", "iat": now, "exp": now + 60}
    receipt = sign_jws(keys["escrow"], receipt_claims)
    verify_jws(receipt, keys["escrow"].did, expected_claims=receipt_claims, now=now)
    return {"mode": "local-signature-check", "gateway_verified": False,
            "seller_quote_verified": buyer_claims["seller_did"] == keys["seller"].did,
            "escrow_receipt_verified": True}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("enable", "probe", "init", "status", "verify-local", "authenticate"))
    parser.add_argument("--key-dir", type=Path, default=ROOT / ".state/keys")
    parser.add_argument("--config", type=Path, default=ROOT / "config/agent-identity.json")
    parser.add_argument("--endpoint", default=BORIS_ENDPOINT)
    args = parser.parse_args(argv)
    try:
        if args.command in {"enable", "probe"}:
            result = enable_boris(args.config, args.endpoint) if args.command == "enable" else probe_boris(args.config)
            print(json.dumps(result, indent=2))
            return 0 if args.command == "enable" or result["mcp_connected"] else 1
        keys = load_keys(args.key_dir.resolve(), create=args.command == "init")
        identities = {role: {"agent": AGENTS[role], "did": key.did,
                             "key_file": str(args.key_dir.resolve() / f"{AGENTS[role]}.key")}
                      for role, key in keys.items()}
        result = {"identities": identities}
        if args.command == "verify-local":
            result.update(verify_local(keys))
        elif args.command == "authenticate":
            configs = {role: config_for(role) for role in AGENTS}
            sessions = {}
            for role, key in keys.items():
                session = DidAuthClient(key, configs[role]).authenticate()
                sessions[role] = {"authenticated": True, "did": session.did, "expires_at": session.expires_at}
            result.update(mode="affinidi-gateway", sessions=sessions)
        else:
            result.update(mode="local-identities", gateway_verified=False,
                          configured={role: bool(setting(role, "SURFACE_URL")) for role in AGENTS})
            if args.command == "status" and args.config.is_file():
                configured = json.loads(args.config.read_text(encoding="utf-8"))
                if configured.get("enabled") is True and configured.get("mode") == "boris-payload":
                    result.update(mode="boris-payload", payload_identity_enabled=True,
                                  endpoint=configured["endpoint"],
                                  applications={role: configured["agents"][name]["application_name"]
                                                for role, name in AGENTS.items()})
                    result["did_auth_configured"] = result["configured"]
                    result["configured"] = {role: True for role in AGENTS}
                    result["remote_verified"] = result.pop("gateway_verified")
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, RuntimeError, OSError) as error:
        # The client sanitizes transport failures; never print a response body or proof.
        print(json.dumps({"error": str(error), "gateway_verified": False}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
