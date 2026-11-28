"""Run the inbox as admitted AgentDb work, using the worker's fenced context.

The external scheduler admits one bounded drain action per installation. Each
message's own business operations retain their stable idempotency keys. A crash
before acknowledgement leaves the message claim available for redelivery.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from cogit_agent_sdk import OperationInvocation, bind_action, operation
from pydantic import BaseModel, Field

from .cogit_host import HandleModules
from .local import utcnow

log = logging.getLogger(__name__)


class DrainInput(BaseModel):
    limit: int = Field(default=10, ge=1, le=100)


class DrainOutput(BaseModel):
    handled: int
    rejected: int
    released: int


def inbox_binding(handler: Callable[..., Any], input_type: type[BaseModel]):
    """Bind an agent's existing handle_message operation to durable inbox work."""

    def drain_inbox(
        request: DrainInput, invocation: OperationInvocation
    ) -> DrainOutput:
        from cogit_messaging_shim import verify_envelope
        from cogit_messaging_shim.envelope import freshness_error

        modules = HandleModules(invocation.handle)
        request_key = invocation.idempotency_key
        if not request_key:
            raise ValueError(
                "Inbox work requires its durable admission idempotency key"
            )
        claimed = modules.module_command(
            "cogit-messaging",
            "message.claim",
            {"limit": request.limit},
            idempotency_key=f"claim:{request_key}",
        )
        counts = {"handled": 0, "rejected": 0, "released": 0}
        for message in claimed["messages"]:
            mid = message["message_id"]
            envelope = message["envelope"]
            # A resumed drain may replay its earlier claim response. Do not
            # invoke a handler whose successful acknowledgement already exists.
            current = modules.module_query(
                "cogit-messaging",
                "conversation.read",
                {"conversation_id": envelope["conversation_id"]},
            )
            if any(
                row["message_id"] == mid
                and row["status"] in {"processed", "rejected", "dead"}
                for row in current["messages"]
            ):
                continue
            outcome, reason = "rejected", "bad_signature"
            valid = verify_envelope(envelope)
            if valid:
                reason = freshness_error(envelope, utcnow())
            if valid and reason is None:
                try:
                    # Nested step names distinguish messages inside this bounded run.
                    with invocation.handle.step("action", f"message:{mid}"):
                        value = handler(
                            input_type.model_validate({"envelope": envelope}),
                            invocation,
                        )
                    output = (
                        value.model_dump(mode="json")
                        if hasattr(value, "model_dump")
                        else dict(value)
                    )
                    outcome = (
                        "rejected"
                        if output.get("status") == "rejected"
                        else "processed"
                    )
                    reason = output.get("reason")
                except Exception:
                    log.exception("Inbox handler failed for message %s", mid)
                    modules.module_command(
                        "cogit-messaging",
                        "message.release",
                        {"message_id": mid, "delay_s": 2},
                        idempotency_key=f"release:{mid}:{message['attempts']}",
                    )
                    counts["released"] += 1
                    continue
            payload = {"message_id": mid, "outcome": outcome}
            if reason:
                payload["reason"] = reason
            modules.module_command(
                "cogit-messaging", "message.ack", payload, idempotency_key=f"ack:{mid}"
            )
            counts["handled"] += 1
            counts["rejected"] += outcome == "rejected"
        return DrainOutput(**counts)

    return bind_action(
        operation(drain_inbox),
        name="drain_inbox",
        description="Process a bounded batch of signed messages under the worker's AgentDb context.",
        risk="write",
        idempotency="inherent",
    )
