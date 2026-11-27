"""Typed action payloads for the reference agent."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictPayload(BaseModel):
    """Base payload that rejects undeclared fields."""

    model_config = ConfigDict(extra="forbid")


class RefreshRecordIndexInput(StrictPayload):
    """Internal-only payload for refreshing the in-memory record index."""

    force: bool = False


class RefreshRecordIndexOutput(StrictPayload):
    """Internal-only payload reporting the current record index size."""

    record_count: int


class LookupRecordInput(StrictPayload):
    record_id: str = Field(min_length=1)


class LookupRecordOutput(StrictPayload):
    record_id: str
    status: str


class ValidateRequestInput(StrictPayload):
    request_id: str = Field(min_length=1)
    description: str = Field(min_length=1)


class ValidateRequestOutput(StrictPayload):
    valid: bool
    errors: list[str]


class ApplyResolutionInput(StrictPayload):
    case_id: str = Field(min_length=1, max_length=256)
    resolution: str = Field(min_length=1, max_length=4096)


class ApplyResolutionOutput(StrictPayload):
    applied: bool
    already_applied: bool


class LookupResolutionInput(StrictPayload):
    case_id: str = Field(min_length=1, max_length=256)


class LookupResolutionOutput(StrictPayload):
    case_id: str
    resolutions: list[str]


class HandleMessageInput(StrictPayload):
    """One signed message envelope, as claimed by the delivery loop."""

    envelope: dict[str, Any]


class HandleMessageOutput(StrictPayload):
    """What the delivery loop acknowledges for the message."""

    status: Literal["processed", "rejected"]
    reason: str | None = None
