"""Fakes shared by the evaluator's product tests."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Any

import jsonschema
from cogit_finance_seams import ModuleError
from cogit_messaging_shim import AgentKey, build_envelope

DEAL_ID = "5f0c7a52-3d0b-4a3e-9d55-0c1f4d0a7e11"
TERMS_HASH = "ab" * 32
REQUIRED_FILES = ["report.md", "data.csv", "summary.json"]
CONTRACTS = Path(__file__).resolve().parents[3] / "contracts" / "messages"


def assert_contract(envelope: dict[str, Any]) -> None:
    """Validate a message body against its frozen schema in ``contracts/messages``."""
    name = f"{envelope['type_key']}.v{envelope['type_version']}.json"
    schema = json.loads((CONTRACTS / name).read_text(encoding="utf-8"))
    jsonschema.validate(envelope["body"], schema)


def make_zip(names: list[str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name in names:
            archive.writestr(name, f"content of {name}\n")
    return buffer.getvalue()


def evaluation_request(
    escrow_key: AgentKey,
    evaluator_did: str,
    artifact: dict[str, Any],
    evaluator_id: str,
    params: dict[str, Any] | None = None,
    *,
    version: int = 1,
    delivered_at: str = "2026-11-27T10:00:30Z",
    sender_key: AgentKey | None = None,
) -> dict[str, Any]:
    """A signed ``finance.evaluation_request`` for attempt 1 of the demo deal."""
    delivery_id = f"{DEAL_ID}:d1"
    body = {
        "evaluation_request_id": f"{delivery_id}:{evaluator_id}@{version}",
        "terms_hash": TERMS_HASH,
        "delivery_id": delivery_id,
        "artifact": artifact,
        "evaluator_id": evaluator_id,
        "evaluator_version": version,
        "params": params or {},
        "delivered_at": delivered_at,
        "respond_by": "2026-11-27T10:01:30Z",
    }
    key = sender_key or escrow_key
    return build_envelope(
        key, key.did, "finance.evaluation_request", 1, evaluator_did, DEAL_ID, body
    )


class FakeModules:
    """Tiny ``ModulePort``: resolves the escrow identity and records what is sent."""

    def __init__(self, escrow_did: str | None = None) -> None:
        self.escrow_did = escrow_did
        self.queries: list[tuple[str, str, dict[str, Any]]] = []
        self.commands: list[tuple[str, str, dict[str, Any], str]] = []

    def module_query(
        self, module: str, export: str, args: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        self.queries.append((module, export, args or {}))
        if (module, export) == ("cogit-messaging", "identity.resolve"):
            if self.escrow_did is None:
                return {"identity": None}
            return {"identity": {"did": self.escrow_did, "role": "escrow"}}
        raise ModuleError("unknown_export", f"{module}.{export}")

    def module_command(
        self,
        module: str,
        export: str,
        args: dict[str, Any] | None = None,
        *,
        idempotency_key: str,
    ) -> dict[str, Any]:
        payload = args or {}
        self.commands.append((module, export, payload, idempotency_key))
        if (module, export) == ("cogit-messaging", "message.send"):
            return {"message_id": payload["envelope"]["message_id"], "status": "queued"}
        raise ModuleError("unknown_export", f"{module}.{export}")

    def sent(self) -> list[dict[str, Any]]:
        return [
            args["envelope"]
            for _, export, args, _ in self.commands
            if export == "message.send"
        ]
