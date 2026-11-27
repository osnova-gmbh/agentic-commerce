"""The loop delivering to a real bound Cogit operation, the wiring the agents use."""

import pytest

pytest.importorskip("cogit_agent_sdk")
pytest.importorskip("cogit_messaging_module")

from cogit_agent_sdk import CogitAgent, bind_action, operation  # noqa: E402
from cogit_finance_seams.cogit_host import HandleModules, agent_invoker  # noqa: E402
from pydantic import BaseModel, ConfigDict  # noqa: E402

from cogit_messaging_shim import AgentKey, ShimMessaging, verify_envelope  # noqa: E402
from cogit_messaging_shim.testing import LocalBus  # noqa: E402

NOTE = {
    "type": "object",
    "properties": {"text": {"type": "string"}},
    "required": ["text"],
    "additionalProperties": False,
}


class HandleMessageInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    envelope: dict


class HandleMessageOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str
    reason: str | None = None


class EchoAgent(CogitAgent):
    """Replies ``ack`` to every ``test.note`` except its own acks; rejects the text ``spam``."""

    def __init__(self, key: AgentKey) -> None:
        super().__init__()
        self.key = key

    def configure(self, services) -> None:
        super().configure(services)

        def handle_message(request: HandleMessageInput, invocation) -> HandleMessageOutput:
            envelope = request.envelope
            if not verify_envelope(envelope):
                return HandleMessageOutput(status="rejected", reason="bad_signature")
            if envelope["body"]["text"] == "spam":
                return HandleMessageOutput(status="rejected", reason="spam")
            if envelope["body"]["text"] != "ack":
                messaging = ShimMessaging(self.key, HandleModules(invocation.handle))
                messaging.send(
                    "test.note", 1, envelope["sender_did"], "conv-1", {"text": "ack"}, envelope["message_id"]
                )
            return HandleMessageOutput(status="processed")

        self.register_action(
            bind_action(
                operation(handle_message),
                name="handle_message",
                description="Handle one inbound message.",
                risk="write",
                idempotency="inherent",
            )
        )


def test_loop_admits_messages_to_bound_operations():
    bus = LocalBus()
    bus.register_type("test.note", 1, NOTE)
    for installation_id, role in (("alice-agent", "buyer"), ("bob-agent", "seller")):
        agent = EchoAgent(bus.add_agent(installation_id, f"{installation_id}-co", role))
        agent.configure(None)
        invoker = agent_invoker(agent, installation_id, modules=bus.host.port(installation_id), artifacts=bus.artifacts)
        bus.runtime.register(installation_id, invoker)
    bob_did = bus.keys["bob-agent"].did
    hello = bus.messaging("alice-agent").send("test.note", 1, bob_did, "conv-1", {"text": "hello"})
    spam = bus.messaging("alice-agent").send("test.note", 1, bob_did, "conv-1", {"text": "spam"})
    assert bus.pump() == 3
    assert all(run.status == "succeeded" for run in bus.runtime.runs.values())
    reader = bus.host.port("operator", "operator_ro")
    rows = reader.module_query("cogit-messaging", "conversation.read", {"conversation_id": "conv-1"})["messages"]
    assert [(row["message_id"], row["status"], row["reason"]) for row in rows[:2]] == [
        (hello, "processed", None),
        (spam, "rejected", "spam"),
    ]
    assert (rows[2]["causation_id"], rows[2]["status"], rows[2]["envelope"]["body"]) == (
        hello,
        "processed",
        {"text": "ack"},
    )
    assert all(row["run_id"] for row in rows)
