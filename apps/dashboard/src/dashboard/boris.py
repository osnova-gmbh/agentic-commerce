"""Boris is an enforced message boundary; finance execution remains local.

Every connected agent's signed outbound envelope must make an unchanged round
trip through the configured Boris MCP tool before the local queue accepts it.
The evidence below records real replies, not merely successful configuration.
"""

from __future__ import annotations

import copy
import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from cogit_messaging_shim import AgentKey, canonical_hash, verify_envelope
from cogit_messaging_shim.affinidi.boris import BorisAgentIdentity, BorisMCPClient, BorisMCPError

CONNECTED_AGENTS = {"buyer-agent", "seller-agent", "cogit-finance"}


class BorisConnectionError(RuntimeError):
    """A failed boundary check: its message is safe to show in the dashboard."""

    def __init__(self, message: str, deal_id: str | None = None):
        super().__init__(message)
        self.deal_id = deal_id


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def offline_report(deal_id: str | None = None) -> dict:
    return {"mode": "offline", "transport_kind": "offline", "configured": False,
            "endpoint": None, "deal_id": deal_id, "events": [],
            "summary": {"pending": 0, "verified": 0, "failed": 0},
            "execution_location": "local-agent-cores"}


class BorisGateway:
    def __init__(self, endpoint: str, exchange: Callable[[str, dict, str], dict] | None,
                 *, transport_kind: str = "http", evidence_path: Path | None = None):
        if transport_kind not in {"http", "test"}:
            raise ValueError("Unknown Boris transport kind")
        self.endpoint, self.exchange, self.transport_kind = endpoint, exchange, transport_kind
        self.evidence_path = evidence_path
        self.agent_keys: dict[str, AgentKey] = {}
        self._events: list[dict] = []
        self._completed: dict[str, str] = {}
        self._lock = threading.RLock()
        if evidence_path and evidence_path.is_file():
            latest = {}
            for line in evidence_path.read_text(encoding="utf-8").splitlines():
                row = json.loads(line)
                latest[row["event_id"]] = row
            self._events = list(latest.values())

    @classmethod
    def from_config(cls, root: Path, *, transport=None, evidence_path: Path | None = None):
        """Load the enabled project connection; injected transports are always tests.

        The live tool was discovered as ``echo`` and accepts arbitrary object
        arguments. A fresh request ID travels inside those arguments, in addition
        to the MCP client's independently checked JSON-RPC response ID.
        """
        path = root / "config/agent-identity.json"
        if not path.is_file():
            return None
        config = json.loads(path.read_text(encoding="utf-8"))
        if config.get("enabled") is not True:
            return None
        if config.get("mode") != "boris-payload":
            raise ValueError("The demo supports the configured boris-payload identity mode")
        key_path = root / ".state/boris/caller-key"
        api_key = key_path.read_text(encoding="utf-8").strip() if key_path.is_file() else None
        clients = {
            name: BorisMCPClient(config["endpoint"],
                                 BorisAgentIdentity(config["agents"][name]["application_name"]),
                                 headers={"x-boris-api-key": api_key} if api_key else {},
                                 transport=transport)
            for name in sorted(CONNECTED_AGENTS)
        }
        discovered = set()

        def exchange(agent_id: str, payload: dict, request_id: str) -> dict:
            client = clients[agent_id]
            if agent_id not in discovered:
                if "echo" not in {tool["name"] for tool in client.list_tools()}:
                    raise BorisConnectionError("The configured Boris agent does not provide its echo tool")
                discovered.add(agent_id)
            arguments = {"request_id": request_id, "agent_id": agent_id, "message": payload}
            result = client.call_tool("echo", arguments)
            if result.get("isError"):
                raise BorisConnectionError("The Boris echo tool rejected the message")
            if "structuredContent" in result:
                echoed = result["structuredContent"]
            else:
                texts = [item.get("text") for item in result.get("content", [])
                         if isinstance(item, dict) and item.get("type") == "text"]
                if len(texts) != 1:
                    raise BorisConnectionError("Boris returned no unique echo result")
                try:
                    echoed = json.loads(texts[0])
                except (ValueError, TypeError):
                    raise BorisConnectionError("Boris returned an invalid echo result") from None
            if echoed != arguments:
                raise BorisConnectionError("Boris echo did not match the request ID and complete message")
            return echoed["message"]

        gateway = cls(config["endpoint"], exchange if api_key or transport else None,
                      transport_kind="test" if transport else "http", evidence_path=evidence_path)
        gateway.agent_keys = {name: AgentKey.load_or_create(root / ".state/keys" / f"{name}.key")
                              for name in CONNECTED_AGENTS}
        return gateway

    def _save(self, row: dict) -> None:
        if self.evidence_path:
            self.evidence_path.parent.mkdir(parents=True, exist_ok=True)
            with self.evidence_path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(row, sort_keys=True) + "\n")

    def report(self, deal_id: str | None = None) -> dict:
        with self._lock:
            events = [copy.deepcopy(row) for row in self._events
                      if deal_id is None or row["deal_id"] == deal_id]
        return {"mode": "boris", "transport_kind": self.transport_kind,
                "configured": self.exchange is not None, "endpoint": self.endpoint,
                "deal_id": deal_id, "events": events,
                "summary": {state: sum(row["status"] == state for row in events)
                            for state in ("pending", "verified", "failed")},
                "error": None if self.exchange else "Boris is enabled but its caller API key is missing",
                "execution_location": "local-agent-cores"}

    def forward(self, agent_id: str, envelope: dict) -> None:
        if agent_id not in CONNECTED_AGENTS or not verify_envelope(envelope):
            raise BorisConnectionError("Refused an invalid agent envelope before sending to Boris")
        self._roundtrip(agent_id, envelope, envelope["message_id"],
                        envelope["conversation_id"], envelope["type_key"])

    def checkpoint(self, agent_id: str, deal_id: str, action: str, request_key: str, detail: dict) -> None:
        """Require a live response before an explicit money-moving action starts."""
        message_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{agent_id}:{deal_id}:{action}:{request_key}"))
        payload = {"agent_id": agent_id, "deal_id": deal_id, "action": action,
                   "message_id": message_id, "detail": detail}
        self._roundtrip(agent_id, payload, message_id, deal_id, "checkout." + action, reuse_verified=False)

    def _roundtrip(self, agent_id: str, payload: dict, message_id: str, deal_id: str,
                   type_key: str, *, reuse_verified: bool = True) -> None:
        digest = canonical_hash(payload)
        with self._lock:
            if reuse_verified and message_id in self._completed:
                if self._completed[message_id] != digest:
                    raise BorisConnectionError("A previously verified message changed")
                return
            row = {"event_id": str(uuid.uuid4()), "agent_id": agent_id, "endpoint": self.endpoint,
                   "deal_id": deal_id, "message_id": message_id, "type_key": type_key,
                   "request_id": str(uuid.uuid4()), "started_at": now(), "completed_at": None,
                   "status": "pending", "request_sha256": digest, "response_sha256": None,
                   "sender_did": payload.get("sender_did"),
                   "transport_kind": self.transport_kind, "error": None}
            self._events.append(row)
            self._save(row)
        try:
            if self.exchange is None:
                raise BorisConnectionError("Boris is enabled but its relay tool is not configured")
            echoed = self.exchange(agent_id, copy.deepcopy(payload), row["request_id"])
            if not isinstance(echoed, dict) or canonical_hash(echoed) != digest:
                raise BorisConnectionError("Boris returned different message content; local delivery was blocked")
        except Exception as error:
            safe = str(error) if isinstance(error, (BorisConnectionError, BorisMCPError)) else "Boris request failed; local delivery was blocked"
            with self._lock:
                row.update(status="failed", completed_at=now(), error=safe)
                self._save(row)
            raise BorisConnectionError(safe, deal_id) from None
        with self._lock:
            row.update(status="verified", completed_at=now(), response_sha256=digest)
            self._completed[message_id] = digest
            self._save(row)


class BorisModulePort:
    """Intercept the real queue's write boundary, including escrow outbox sends."""

    def __init__(self, delegate, gateway: BorisGateway, agent_id: str, expected_did: str):
        self.delegate, self.gateway = delegate, gateway
        self.agent_id, self.expected_did = agent_id, expected_did

    def module_query(self, module: str, export: str, args: dict | None = None) -> dict:
        return self.delegate.module_query(module, export, args)

    def module_command(self, module: str, export: str, args: dict | None = None, *, idempotency_key: str) -> dict:
        if module == "cogit-messaging" and export == "message.send":
            envelope = (args or {}).get("envelope", {})
            if envelope.get("sender_did") != self.expected_did:
                raise BorisConnectionError("This agent cannot send another agent's identity to Boris")
            self.gateway.forward(self.agent_id, envelope)
        return self.delegate.module_command(module, export, args, idempotency_key=idempotency_key)


class BorisBankPort:
    """A verified transfer-intent roundtrip is required before the bank is called."""

    def __init__(self, delegate, gateway: BorisGateway, agent_id: str):
        self.delegate, self.gateway, self.agent_id = delegate, gateway, agent_id

    def transfer(self, *, from_iban: str, to_iban: str, amount_minor: int,
                 currency: str, reference: str, idempotency_key: str) -> dict:
        # Every finance bank reference ends in its UUID deal ID (including refunds).
        try:
            deal_id = str(uuid.UUID(reference[-36:]))
        except ValueError:
            raise BorisConnectionError("A bank transfer must identify its deal before sending to Boris") from None
        self.gateway.checkpoint(self.agent_id, deal_id, "bank_transfer", idempotency_key,
                                {"from_iban": from_iban, "to_iban": to_iban,
                                 "amount_minor": amount_minor, "currency": currency,
                                 "reference": reference, "idempotency_key": idempotency_key})
        return self.delegate.transfer(from_iban=from_iban, to_iban=to_iban,
                                      amount_minor=amount_minor, currency=currency,
                                      reference=reference, idempotency_key=idempotency_key)

    def lookup(self, idempotency_key: str) -> dict | None:
        return self.delegate.lookup(idempotency_key)

    def credits(self, iban: str, after: str = "0") -> list[dict]:
        return self.delegate.credits(iban, after)

    def accounts(self) -> list[dict]:
        return self.delegate.accounts()
