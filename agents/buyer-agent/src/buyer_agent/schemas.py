"""Typed action payloads for the reference agent and the buyer actions."""

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
    """One inbound signed envelope, exactly as the delivery loop claimed it."""

    envelope: dict[str, Any]


class HandleMessageOutput(StrictPayload):
    """Disposition of the message; the delivery loop maps it to the acknowledgement."""

    status: Literal["processed", "rejected"]
    reason: str | None = None


class StartPurchaseInput(StrictPayload):
    """Optional overrides of the configured category and maximum price."""

    category: str | None = Field(default=None, min_length=1, max_length=256)
    max_price_minor: int | None = Field(default=None, ge=0)


class StartPurchaseOutput(StrictPayload):
    """What discovery found and which deal, if any, was requested."""

    status: Literal["requested", "no_offer"]
    deal_id: str | None = None
    seller_org_id: str | None = None
    offer_id: str | None = None
    sellers_seen: int
    offers_seen: int
