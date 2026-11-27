"""The portable messaging contract (SPEC §11.2) and its in-repo implementation."""

from __future__ import annotations

from typing import Protocol

from cogit_finance_seams import ModulePort

from .envelope import build_envelope
from .keys import AgentKey

MESSAGING_MODULE = "cogit-messaging"


class MessagingSeams(Protocol):
    def send(
        self,
        type_key: str,
        type_version: int,
        recipient_did: str,
        conversation_id: str,
        body: dict,
        causation_id: str | None = None,
    ) -> str:
        """Sign and queue one message; return its ``message_id``."""
        ...


def send_envelope(modules: ModulePort, envelope: dict) -> str:
    """Queue an already signed envelope. Idempotent on ``message_id``."""
    result = modules.module_command(
        MESSAGING_MODULE, "message.send", {"envelope": envelope}, idempotency_key=f"send:{envelope['message_id']}"
    )
    return str(result["message_id"])


class ShimMessaging:
    """``MessagingSeams`` over the cogit-messaging module, signing with a local key."""

    def __init__(self, key: AgentKey, modules: ModulePort, sender_did: str | None = None) -> None:
        self._key = key
        self._modules = modules
        self.did = sender_did or key.did

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
            self._key, self.did, type_key, type_version, recipient_did, conversation_id, body, causation_id
        )
        return send_envelope(self._modules, envelope)
