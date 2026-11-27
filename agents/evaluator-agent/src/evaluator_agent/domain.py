"""Synthetic read-only domain logic for the reference agent."""

from __future__ import annotations

from dataclasses import dataclass, field

from evaluator_agent.schemas import (
    LookupRecordInput,
    LookupRecordOutput,
    ValidateRequestInput,
    ValidateRequestOutput,
)


@dataclass
class RecordService:
    """Small deterministic service for synthetic records and validation."""

    records: dict[str, str] = field(
        default_factory=lambda: {
            "record-open": "open",
            "record-closed": "closed",
        }
    )

    def lookup(self, request: LookupRecordInput) -> LookupRecordOutput:
        return LookupRecordOutput(
            record_id=request.record_id,
            status=self.records.get(request.record_id, "missing"),
        )

    def validate(self, request: ValidateRequestInput) -> ValidateRequestOutput:
        errors: list[str] = []
        if len(request.description.strip()) < 8:
            errors.append("description must contain at least 8 characters")
        return ValidateRequestOutput(valid=not errors, errors=errors)
