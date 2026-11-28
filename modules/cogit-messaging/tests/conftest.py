"""Shared fixtures: one host with the module installed, three installations, one type.

The module verifies no signatures, so these tests use readable placeholder DIDs and a
placeholder signature instead of real keys.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from cogit_finance_seams import LocalModuleHost, ModuleError

from cogit_messaging_module import MODULE_NAME, MessagingModule

ESCROW = "cogit-finance"
NOTE_SCHEMA = {
    "type": "object",
    "properties": {"text": {"type": "string", "minLength": 1, "maxLength": 100}},
    "required": ["text"],
    "additionalProperties": False,
}
DIDS = {"alice-agent": "did:key:zAlice", "bob-agent": "did:key:zBob", "carol-agent": "did:key:zCarol"}


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 11, 27, 12, 0, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: int) -> None:
        self.now += timedelta(seconds=seconds)


class Bench:
    """Calls exports as a given installation; every command gets a fresh idempotency key."""

    def __init__(self, settings: dict | None = None) -> None:
        self.clock = Clock()
        self.host = LocalModuleHost(self.clock)
        self.host.install(MessagingModule(), settings)
        self._keys = 0
        self._ids = 0

    def command(
        self, installation_id: str, export: str, args: dict | None = None, principal: str = "installation"
    ) -> dict:
        self._keys += 1
        port = self.host.port(installation_id, principal)
        return port.module_command(MODULE_NAME, export, args or {}, idempotency_key=f"test:{self._keys}")

    def query(self, installation_id: str, export: str, args: dict | None = None) -> dict:
        return self.host.port(installation_id, "operator_ro" if installation_id == "operator" else "installation").module_query(MODULE_NAME, export, args or {})

    def register(self, installation_id: str, did: str, org_id: str = "org", role: str = "buyer") -> dict:
        args = {"did": did, "installation_id": installation_id, "org_id": org_id, "role": role}
        return self.command("operator", "identity.register", args, principal="operator")

    def envelope(self, sender: str = "alice-agent", recipient: str = "bob-agent", **overrides) -> dict:
        self._ids += 1
        envelope = {
            "envelope_version": 1,
            "message_id": f"00000000-0000-4000-8000-{self._ids:012d}",
            "type_key": "test.note",
            "type_version": 1,
            "sender_did": DIDS[sender],
            "recipient_did": DIDS[recipient],
            "conversation_id": "conv-1",
            "causation_id": None,
            "created_at": "2026-11-27T12:00:00Z",
            "body": {"text": "hello"},
            "signature": "not-checked-by-the-module",
        }
        return {**envelope, **overrides}

    def send(self, sender: str = "alice-agent", recipient: str = "bob-agent", **overrides) -> dict:
        envelope = self.envelope(sender, recipient, **overrides)
        assert self.command(sender, "message.send", {"envelope": envelope})["status"] == "queued"
        return envelope

    def claim(self, installation_id: str = "bob-agent", **args) -> list[dict]:
        return self.command(installation_id, "message.claim", args)["messages"]

    def row(self, message_id: str, conversation_id: str = "conv-1") -> dict:
        messages = self.query("operator", "conversation.read", {"conversation_id": conversation_id})["messages"]
        return next(message for message in messages if message["message_id"] == message_id)


def code_of(call, *args, **kwargs) -> str:
    with pytest.raises(ModuleError) as caught:
        call(*args, **kwargs)
    return caught.value.code


@pytest.fixture()
def bench() -> Bench:
    bench = Bench()
    for installation_id, did in DIDS.items():
        bench.register(installation_id, did, org_id=installation_id.replace("-agent", "-co"))
    bench.command(ESCROW, "type.register", {"type_key": "test.note", "type_version": 1, "json_schema": NOTE_SCHEMA})
    return bench
