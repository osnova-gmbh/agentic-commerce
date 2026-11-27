"""The delivery loop (SPEC §7, steps 1, 2 and 5): claim, verify, admit, acknowledge.

Delivery is at-least-once. The loop makes it exactly-once in effect with the stable
admission key ``msg:<message_id>``: a message claimed again after a crash is admitted
under the same key, so the host returns the run that already exists.
"""

from __future__ import annotations

import uuid

from cogit_finance_seams import ModulePort, WorkPort

from .envelope import verify_envelope
from .seams import MESSAGING_MODULE


class DeliveryLoop:
    """Delivers the messages addressed to one installation's DIDs as work for that installation."""

    def __init__(
        self,
        installation_id: str,
        modules: ModulePort,
        work: WorkPort,
        *,
        action: str = "handle_message",
        limit: int = 10,
        release_delay_s: int = 1,
    ) -> None:
        self.installation_id = installation_id
        self.action = action
        self.limit = limit
        self.release_delay_s = release_delay_s
        self._modules = modules
        self._work = work

    def run_once(self) -> int:
        """One pass: claim up to ``limit`` messages and settle each. Returns how many it handled."""
        # Every pass is its own command: a reused key would replay the previous pass's claim.
        claimed = self._command("message.claim", {"limit": self.limit}, f"claim:{uuid.uuid4()}")
        messages = claimed.get("messages") or []
        for message in messages:
            self._deliver(message)
        return len(messages)

    def _deliver(self, message: dict) -> None:
        message_id, envelope = message["message_id"], message["envelope"]
        if not verify_envelope(envelope):
            self._ack(message_id, "rejected", reason="bad_signature")
            return
        try:
            run_id = self._work.admit(
                self.installation_id, self.action, {"envelope": envelope}, idempotency_key=f"msg:{message_id}"
            )
            result = self._work.result(run_id)
        except Exception:  # the host could not take or report the work: retry later
            self._release(message)
            return
        if result.status != "succeeded":
            self._release(message)
            return
        output = result.output or {}
        if output.get("status") == "rejected":
            self._ack(message_id, "rejected", reason=output.get("reason"), run_id=run_id)
        else:
            self._ack(message_id, "processed", run_id=run_id)

    def _ack(self, message_id: str, outcome: str, *, reason: object = None, run_id: str | None = None) -> None:
        args: dict = {"message_id": message_id, "outcome": outcome}
        if reason is not None:
            args["reason"] = str(reason)
        if run_id is not None:
            args["run_id"] = run_id
        self._command("message.ack", args, f"ack:{message_id}")

    def _release(self, message: dict) -> None:
        # The attempt number keeps the key unique per delivery, so a later release is not a replay.
        args = {"message_id": message["message_id"], "delay_s": self.release_delay_s}
        self._command("message.release", args, f"release:{message['message_id']}:{message['attempts']}")

    def _command(self, export: str, args: dict, idempotency_key: str) -> dict:
        return self._modules.module_command(MESSAGING_MODULE, export, args, idempotency_key=idempotency_key)
