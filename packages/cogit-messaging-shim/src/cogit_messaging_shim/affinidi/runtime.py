"""Durable agent identities and explicit Affinidi authentication commands.

The finance protocol and DID Auth use the same key. Gateway sessions remain in
memory; neither this module nor its CLI output exposes proofs or session IDs.
"""

from __future__ import annotations

import json
import os
import sys
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from ..keys import AgentKey
from .client import DidAuthClient, DidAuthConfig


@dataclass(frozen=True)
class AgentIdentity:
    agent_id: str
    role: str
    default_key_file: str

    def load_key(self, environ: Mapping[str, str] | None = None) -> AgentKey:
        env = os.environ if environ is None else environ
        return AgentKey.load_or_create(env.get("AGENT_KEY_FILE") or self.default_key_file)

    def configuration(self, environ: Mapping[str, str] | None = None) -> DidAuthConfig | None:
        env = os.environ if environ is None else environ
        prefix = self.role.upper() + "_AFFINIDI_"

        def value(name: str, default: str = "") -> str:
            return env.get(prefix + name, env.get("AFFINIDI_" + name, default))

        required = {name: value(name).strip() for name in ("SURFACE_URL", "AUDIENCE", "SESSION_HEADER")}
        if not any(required.values()):
            return None
        missing = [name for name, item in required.items() if not item]
        if missing:
            raise ValueError("Missing Affinidi configuration: " + ", ".join(missing))
        return DidAuthConfig(
            surface_url=required["SURFACE_URL"],
            audience=required["AUDIENCE"],
            session_header=required["SESSION_HEADER"],
            session_prefix=value("SESSION_PREFIX"),
            timeout_seconds=float(value("TIMEOUT_SECONDS", "10")),
            proof_ttl_seconds=int(value("PROOF_TTL_SECONDS", "60")),
        )

    def status(self, environ: Mapping[str, str] | None = None) -> dict[str, Any]:
        config = self.configuration(environ)
        boris = self.boris_configuration(environ)
        return {
            "agent_id": self.agent_id,
            "role": self.role,
            "did": self.load_key(environ).did,
            "configured": config is not None or boris is not None,
            "did_auth_configured": config is not None,
            "authenticated": False,
            "surface_url": config.surface_url if config else None,
            "session_header": config.session_header if config else None,
            "payload_identity_enabled": boris is not None,
            "application_name": boris["application_name"] if boris else None,
            "boris_endpoint": boris["endpoint"] if boris else None,
        }

    def boris_configuration(self, environ: Mapping[str, str] | None = None) -> dict[str, str] | None:
        """Find the public project configuration without reading credentials."""
        env = os.environ if environ is None else environ
        if env.get("BORIS_IDENTITY_ENABLED", "").lower() in {"0", "false", "no"}:
            return None
        explicit = env.get("BORIS_IDENTITY_CONFIG")
        path = Path(explicit) if explicit else None
        if path is None:
            starts = (Path.cwd(), Path(__file__).resolve().parent)
            for start in starts:
                path = next((base / "config/agent-identity.json" for base in (start, *start.parents)
                             if (base / "config/agent-identity.json").is_file()), None)
                if path is not None:
                    break
        if path is None:
            return None
        try:
            config = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise ValueError("Cannot read the Boris identity project configuration") from error
        if not isinstance(config, dict):
            raise ValueError("Boris identity configuration must be an object")
        if config.get("enabled") is not True:
            return None
        if config.get("mode") != "boris-payload":
            raise ValueError("Unsupported Boris identity mode")
        endpoint = config.get("endpoint")
        url = urlsplit(endpoint) if isinstance(endpoint, str) else None
        if not url or url.scheme != "https" or not url.netloc or url.username or url.password or url.query or url.fragment:
            raise ValueError("Boris identity endpoint must be a public HTTPS URL without credentials")
        agents = config.get("agents")
        entry = agents.get(self.agent_id) if isinstance(agents, dict) else None
        name = entry.get("application_name") if isinstance(entry, dict) else None
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Boris identity configuration has no application name for this agent")
        return {"endpoint": endpoint, "application_name": name}

    def boris_client(self, environ: Mapping[str, str] | None = None, **kwargs: Any):
        from .boris import BorisAgentIdentity, BorisMCPClient

        config = self.boris_configuration(environ)
        if config is None:
            raise ValueError("Boris payload identity is not enabled for this project")
        return BorisMCPClient(config["endpoint"], BorisAgentIdentity(config["application_name"]), **kwargs)

    def client(self, environ: Mapping[str, str] | None = None, **kwargs: Any) -> DidAuthClient:
        config = self.configuration(environ)
        if config is None:
            raise ValueError("Affinidi is not configured: set SURFACE_URL, AUDIENCE and SESSION_HEADER")
        return DidAuthClient(self.load_key(environ), config, **kwargs)

    def authenticate(self, environ: Mapping[str, str] | None = None, **kwargs: Any) -> dict[str, Any]:
        session = self.client(environ, **kwargs).authenticate()
        return {
            "agent_id": self.agent_id,
            "role": self.role,
            "did": session.did,
            "authenticated": True,
            "expires_at": session.expires_at,
            "expires_in": session.expires_in,
        }

    def cli_commands(self):
        # Keep importing this helper possible without loading the resident SDK.
        from cogit_agent_sdk import CliCommand, CliCommandGroup

        def status(services, args):
            del services, args
            try:
                output = self.status()
            except (ValueError, OSError):
                print("Identity configuration or key file is invalid.", file=sys.stderr)
                return 1
            print(json.dumps(output, sort_keys=True))
            return 0

        def authenticate(services, args):
            del services, args
            try:
                output = self.authenticate()
            except Exception:
                # Remote error bodies can contain credentials; never echo them.
                print("Affinidi authentication failed. Check gateway configuration and access.", file=sys.stderr)
                return 1
            print(json.dumps(output, sort_keys=True))
            return 0

        return CliCommandGroup(
            name="identity",
            help="Inspect this agent's identity or authenticate to its configured Affinidi surface.",
            commands=[
                CliCommand(name="status", help="Show public identity and gateway configuration.", arguments=[], handler=status),
                CliCommand(name="authenticate", help="Prove this agent's DID to the configured gateway.", arguments=[], handler=authenticate),
            ],
        )


class AgentIdentityRuntime:
    """An agent process's optional, in-memory gateway session."""

    def __init__(self, identity: AgentIdentity, *, environ=None, transport=None, now=time.time):
        self.identity = identity
        self.environ = environ
        self.transport = transport
        self.now = now
        self._session = None
        self._client = None

    def boris_client(self, **kwargs: Any):
        return self.identity.boris_client(self.environ, **kwargs)

    def startup(self) -> None:
        env = os.environ if self.environ is None else self.environ
        self.identity.load_key(env)
        name = self.identity.role.upper() + "_AFFINIDI_AUTHENTICATE_ON_STARTUP"
        enabled = env.get(name, env.get("AFFINIDI_AUTHENTICATE_ON_STARTUP", "0"))
        if enabled.lower() not in {"0", "false", "no", "", "1", "true", "yes"}:
            raise ValueError("AFFINIDI_AUTHENTICATE_ON_STARTUP must be a boolean")
        if enabled.lower() in {"1", "true", "yes"}:
            self._client = self.identity.client(env, transport=self.transport, now=self.now)
            self._session = self._client.authenticate()

    def status(self) -> dict[str, Any]:
        result = self.identity.status(self.environ)
        result["mode"] = ("boris_payload" if result["payload_identity_enabled"] else
                          "affinidi_did_auth" if result["did_auth_configured"] else "local_did_key")
        result["authenticated"] = self._session is not None and self._session.deadline > self.now()
        if result["authenticated"]:
            result["expires_at"] = self._session.expires_at
        return result
