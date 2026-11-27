"""Test doubles for code that sends messages, and an in-process message bus."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Callable

from cogit_finance_seams import LocalArtifacts, LocalModuleHost, LocalRuntime, utcnow

from .canonical import canonical_hash
from .envelope import build_envelope
from .keys import AgentKey
from .loop import DeliveryLoop
from .seams import MESSAGING_MODULE, ShimMessaging

_FINANCE_TYPE_FILE = re.compile(r"(finance\.[a-z_]+)\.v(\d+)\.json")


class RecordingMessaging:
    """``MessagingSeams`` that signs and keeps what was sent instead of queueing it."""

    def __init__(self, key: AgentKey | None = None) -> None:
        self.key = key or AgentKey.generate()
        self.did = self.key.did
        self.sent: list[dict] = []

    def send(
        self,
        type_key: str,
        type_version: int,
        recipient_did: str,
        conversation_id: str,
        body: dict,
        causation_id: str | None = None,
    ) -> str:
        envelope = build_envelope(
            self.key, self.did, type_key, type_version, recipient_did, conversation_id, body, causation_id
        )
        self.sent.append(envelope)
        return envelope["message_id"]

    def of_type(self, type_key: str) -> list[dict]:
        return [envelope for envelope in self.sent if envelope["type_key"] == type_key]


class LocalBus:
    """The cogit-messaging module, agent keys and delivery loops in one process.

    ``host`` runs the module (install further modules on it), ``runtime`` admits work
    (register each agent with ``bus.runtime.register(installation_id, agent)``) and
    ``artifacts`` is the shared artifact store. Needs the ``cogit-messaging-module``
    package, imported only here so that the shim itself does not depend on it.
    """

    def __init__(self, clock: Callable[[], datetime] | None = None, settings: dict | None = None) -> None:
        from cogit_messaging_module import DEFAULT_SETTINGS, MessagingModule

        self.host = LocalModuleHost(clock or utcnow)
        self.runtime = LocalRuntime()
        self.artifacts = LocalArtifacts()
        self.keys: dict[str, AgentKey] = {}
        self.escrow_installation_id: str = {**DEFAULT_SETTINGS, **(settings or {})}["escrow_installation_id"]
        self.host.install(MessagingModule(), settings)

    def add_agent(self, installation_id: str, org_id: str, role: str, key: AgentKey | None = None) -> AgentKey:
        """Bind a DID to the installation (``identity.register`` as the operator) and keep its key."""
        key = key or AgentKey.generate()
        self.host.port("operator", "operator").module_command(
            MESSAGING_MODULE,
            "identity.register",
            {"did": key.did, "installation_id": installation_id, "org_id": org_id, "role": role},
            idempotency_key=f"identity:{key.did}:{installation_id}:{org_id}:{role}",
        )
        self.keys[installation_id] = key
        return key

    def register_type(self, type_key: str, type_version: int, json_schema: dict) -> None:
        """Register a message type as the escrow installation. Raises ``type_conflict`` or ``unsupported_schema``."""
        self.host.port(self.escrow_installation_id).module_command(
            MESSAGING_MODULE,
            "type.register",
            {"type_key": type_key, "type_version": type_version, "json_schema": json_schema},
            idempotency_key=f"type:{type_key}:{type_version}:{canonical_hash(json_schema)}",
        )

    def register_finance_types(self, contracts_dir: str | Path) -> int:
        """Register every ``finance.*.v<n>.json`` under ``contracts_dir`` (or its ``messages`` folder)."""
        folder = Path(contracts_dir)
        if (folder / "messages").is_dir():
            folder = folder / "messages"
        count = 0
        for path in sorted(folder.glob("finance.*.json")):
            match = _FINANCE_TYPE_FILE.fullmatch(path.name)
            if match is None:
                continue
            self.register_type(match.group(1), int(match.group(2)), json.loads(path.read_text(encoding="utf-8")))
            count += 1
        return count

    def messaging(self, installation_id: str) -> ShimMessaging:
        return ShimMessaging(self.keys[installation_id], self.host.port(installation_id))

    def loop(self, installation_id: str) -> DeliveryLoop:
        return DeliveryLoop(installation_id, self.host.port(installation_id), self.runtime)

    def pump(self, max_rounds: int = 50) -> int:
        """Run every agent's loop until a full round handles nothing. Returns the messages handled.

        Installations without an agent in ``runtime`` are skipped: their messages stay queued.
        """
        total = 0
        for _ in range(max_rounds):
            handled = sum(self.loop(name).run_once() for name in list(self.keys) if name in self.runtime.agents)
            if handled == 0:
                break
            total += handled
        return total
