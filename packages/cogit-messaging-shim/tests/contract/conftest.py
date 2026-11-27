"""The one fixture the contract tests run on.

The tests in this folder are black-box: they use only ``env`` and the objects it hands
out, ``agent.messaging`` (``MessagingSeams``) and ``agent.loop`` (``DeliveryLoop``).
A port of messaging into the SDK and runtime re-implements ``Env`` on its own stack and
must pass the test files unchanged.

What an environment must provide:

- ``env.agent(installation_id, role="buyer")``: an installation with its own DID, a
  ``messaging`` seam, a delivery ``loop`` and a scripted ``handler`` for ``handle_message``.
- ``env.register_type``: ``type.register`` as the escrow installation; returns the status.
- ``env.sign`` / ``env.send_raw``: build a signed envelope without sending it, and queue
  any envelope as a given installation (returns ``queued`` or ``duplicate``).
- ``env.claim`` / ``env.admit``: the first two steps of the loop, done by hand.
- ``env.advance(seconds)``: move the queue's clock.
- ``env.message(message_id)``: the queue's row for a message, from ``conversation.read``.
- ``env.refused(code)``: context manager asserting a refusal with that error code.
- ``env.redeliver_after_s`` and the registered type ``test.note`` v1 (``NOTE_SCHEMA``).
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterator

import pytest

pytest.importorskip("cogit_messaging_module")

from cogit_finance_seams import ModuleError  # noqa: E402

from cogit_messaging_shim import MESSAGING_MODULE, DeliveryLoop, MessagingSeams, build_envelope  # noqa: E402
from cogit_messaging_shim.testing import LocalBus  # noqa: E402

REDELIVER_AFTER_S = 30
ESCROW = "cogit-finance"
NOTE_SCHEMA = {
    "type": "object",
    "properties": {"text": {"type": "string", "minLength": 1, "maxLength": 100}},
    "required": ["text"],
    "additionalProperties": False,
}


class Handler:
    """Stands in for an agent: one action, ``handle_message``.

    ``script`` holds what the next calls do: ``"processed"``, ``"rejected"`` or
    ``"raise"``; when it is empty the handler processes. ``on_message`` runs first.
    """

    def __init__(self) -> None:
        self.seen: list[dict] = []
        self.script: list[str] = []
        self.on_message: Callable[[dict], None] | None = None

    def handle_message(self, envelope: dict) -> dict:
        self.seen.append(envelope)
        step = self.script.pop(0) if self.script else "processed"
        if step == "raise":
            raise RuntimeError("the handler failed")
        if self.on_message is not None:
            self.on_message(envelope)
        if step == "rejected":
            return {"status": "rejected", "reason": "not_wanted"}
        return {"status": "processed", "reason": None}


@dataclass
class Agent:
    installation_id: str
    did: str
    messaging: MessagingSeams
    loop: DeliveryLoop
    handler: Handler = field(default_factory=Handler)


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 11, 27, 12, 0, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now


class Env:
    redeliver_after_s = REDELIVER_AFTER_S

    def __init__(self) -> None:
        self._clock = Clock()
        self._bus = LocalBus(self._clock, {"escrow_installation_id": ESCROW, "redeliver_after_s": REDELIVER_AFTER_S})
        self.register_type("test.note", 1, NOTE_SCHEMA)

    def agent(self, installation_id: str, role: str = "buyer") -> Agent:
        key = self._bus.add_agent(installation_id, f"{installation_id}-org", role)
        agent = Agent(installation_id, key.did, self._bus.messaging(installation_id), self._bus.loop(installation_id))
        self._bus.runtime.register(installation_id, agent.handler)
        return agent

    def register_type(self, type_key: str, type_version: int, json_schema: dict) -> str:
        args = {"type_key": type_key, "type_version": type_version, "json_schema": json_schema}
        return self._command(ESCROW, "type.register", args)["status"]

    def sign(
        self,
        sender: Agent,
        type_key: str,
        type_version: int,
        recipient_did: str,
        conversation_id: str,
        body: dict,
        causation_id: str | None = None,
    ) -> dict:
        key = self._bus.keys[sender.installation_id]
        return build_envelope(key, key.did, type_key, type_version, recipient_did, conversation_id, body, causation_id)

    def send_raw(self, caller: Agent, envelope: dict) -> str:
        return self._command(caller.installation_id, "message.send", {"envelope": envelope})["status"]

    def claim(self, agent: Agent, limit: int = 10) -> list[dict]:
        return self._command(agent.installation_id, "message.claim", {"limit": limit})["messages"]

    def admit(self, agent: Agent, envelope: dict) -> str:
        return self._bus.runtime.admit(
            agent.installation_id,
            "handle_message",
            {"envelope": envelope},
            idempotency_key=f"msg:{envelope['message_id']}",
        )

    def advance(self, seconds: int) -> None:
        self._clock.now += timedelta(seconds=seconds)

    def conversation(self, conversation_id: str) -> list[dict]:
        port = self._bus.host.port("operator", "operator_ro")
        return port.module_query(MESSAGING_MODULE, "conversation.read", {"conversation_id": conversation_id})[
            "messages"
        ]

    def message(self, message_id: str, conversation_id: str = "conv-1") -> dict:
        return next(row for row in self.conversation(conversation_id) if row["message_id"] == message_id)

    @contextmanager
    def refused(self, code: str) -> Iterator[None]:
        with pytest.raises(ModuleError) as caught:
            yield
        assert caught.value.code == code

    def _command(self, installation_id: str, export: str, args: dict) -> dict:
        port = self._bus.host.port(installation_id)
        return port.module_command(MESSAGING_MODULE, export, args, idempotency_key=f"env:{uuid.uuid4()}")


@pytest.fixture()
def env() -> Env:
    return Env()
