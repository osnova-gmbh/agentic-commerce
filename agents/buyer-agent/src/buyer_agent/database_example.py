"""Optional deterministic agent demonstrating fenced database operations."""

from __future__ import annotations

import json
from hashlib import sha256
from typing import Literal, Self

from cogit_agent_sdk import (
    ActionBinding,
    AgentServices,
    CogitAgent,
    OperationInvocation,
    bind_action,
    operation,
)
from cogit_agent_sdk.types import WorkOutcome
from pydantic import ConfigDict, Field, model_validator

from buyer_agent.agent import Agent
from buyer_agent.schemas import StrictPayload

MODULE_KEY = "cogit.buyer-agent"
PUBLIC_RESULT_VERSION = "reference-request-result.v1"
PUBLIC_RESULT_FILENAME = "reference-request-result.v1.json"


class PersistRequestInput(StrictPayload):
    """Existing typed request or one bounded canonical plain-text instruction."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "oneOf": [
                {
                    "required": ["request_id", "description"],
                    "not": {"required": ["instruction"]},
                },
                {
                    "required": ["instruction"],
                    "not": {
                        "anyOf": [
                            {"required": ["request_id"]},
                            {"required": ["description"]},
                        ]
                    },
                },
            ]
        },
    )

    request_id: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, min_length=1, max_length=2000)
    instruction: str | None = Field(default=None, min_length=1, max_length=2000)

    @model_validator(mode="after")
    def require_one_input_shape(self) -> Self:
        if self.instruction is not None:
            if self.request_id is not None or self.description is not None:
                raise ValueError("Canonical text cannot include typed request fields")
            if not self.instruction.strip() or "\x00" in self.instruction:
                raise ValueError("Canonical text must contain nonempty UTF-8 text")
        elif self.request_id is None or self.description is None:
            raise ValueError("Typed requests require request_id and description")
        return self

    def mapped_request(self, tenant_id: str) -> tuple[str, str]:
        """Derive a stable tenant-scoped business ID from exact canonical text."""
        if self.instruction is not None:
            body = (
                tenant_id.encode("utf-8") + b"\x00" + self.instruction.encode("utf-8")
            )
            return "text-" + sha256(body).hexdigest(), self.instruction
        assert self.request_id is not None and self.description is not None
        return self.request_id, self.description


class PersistRequestOutput(StrictPayload):
    object_id: str
    request_id: str
    description: str
    status: str
    revision: int
    root_artifact_id: str
    root_sha256: str


class ModuleRequestReadback(StrictPayload):
    """Validate module JSON before comparing it or committing public bytes."""

    object_id: str = Field(min_length=1)
    request_id: str = Field(min_length=1, max_length=128)
    description: str = Field(min_length=1, max_length=2000)
    status: Literal["open", "closed"]
    revision: int = Field(ge=1)


class PublicReferenceResult(StrictPayload):
    """Public result bytes omit input text and internal identifiers."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_version: Literal["reference-request-result.v1"] = Field(
        alias="schemaVersion"
    )
    outcome: Literal["completed"]
    request_id: str = Field(alias="requestId", min_length=1, max_length=128)
    status: Literal["open", "closed"]
    revision: int = Field(ge=1)

    def canonical_bytes(self) -> bytes:
        return (
            json.dumps(
                self.model_dump(mode="json", by_alias=True),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
            + b"\n"
        )


def persist_reference_request(
    request: PersistRequestInput,
    invocation: OperationInvocation,
) -> PersistRequestOutput:
    """Write/read the pinned module and commit a public root result."""
    handle = invocation.handle
    request_id, description = request.mapped_request(invocation.context.tenant_id)
    with handle.step("action", "persist-reference-request"):
        stored = handle.module_command(
            MODULE_KEY,
            "requests.put",
            {"requestId": request_id, "description": description},
            contract_id=f"{MODULE_KEY}.requests.put.v1",
            idempotency_key="reference-request:"
            + sha256(request_id.encode("utf-8")).hexdigest(),
        )
        loaded = handle.module_query(
            MODULE_KEY,
            "requests.get",
            {"objectId": stored["objectId"]},
            contract_id=f"{MODULE_KEY}.requests.get.v1",
        )
        readback = ModuleRequestReadback.model_validate(
            {
                "object_id": loaded.get("objectId"),
                "request_id": loaded.get("requestId"),
                "description": loaded.get("description"),
                "status": loaded.get("status"),
                "revision": loaded.get("revision"),
            }
        )
        if (
            readback.object_id != stored["objectId"]
            or readback.request_id != request_id
            or readback.description != description
        ):
            raise ValueError("Module readback did not match the persisted request")
        public_result = PublicReferenceResult(
            schemaVersion=PUBLIC_RESULT_VERSION,
            outcome="completed",
            requestId=readback.request_id,
            status=readback.status,
            revision=readback.revision,
        )
        result_bytes = public_result.canonical_bytes()
        result_sha256 = sha256(result_bytes).hexdigest()
        slot = handle.declare_artifact(
            "result", "application/json", PUBLIC_RESULT_FILENAME
        )
        root = handle.finalize_artifact(slot, result_bytes, result_sha256)
        handle.set_outcome("reference_request_persisted")
        handle.set_work_outcome(
            WorkOutcome(outcome="completed", reason_code="reference_request_persisted")
        )
    return PersistRequestOutput.model_validate(
        {
            "object_id": readback.object_id,
            "request_id": readback.request_id,
            "description": readback.description,
            "status": readback.status,
            "revision": readback.revision,
            "root_artifact_id": root.id,
            "root_sha256": result_sha256,
        }
    )


def persist_request_binding() -> ActionBinding[
    PersistRequestInput, PersistRequestOutput
]:
    return bind_action(
        operation(persist_reference_request),
        name="persist_reference_request",
        description="Persist and read a reference request through AgentDb.",
        risk="write",
        idempotency="inherent",
    )


class DatabaseAgent(Agent):
    """Select with cogit.database.yaml after explicitly installing its package."""

    def configure(self, services: AgentServices) -> None:
        # This deterministic worker exposes only its approved module operation.
        CogitAgent.configure(self, services)
        self.register_action(persist_request_binding())
