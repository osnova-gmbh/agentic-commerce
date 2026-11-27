"""The installed database adapter validates generic JSON before typed output."""

from __future__ import annotations

import pytest
from cogit_agent_sdk import OperationInvocation
from cogit_agent_sdk.contracts import RunHandle
from cogit_agent_sdk.loop import NoopCancellation
from cogit_agent_sdk.types import Context
from pydantic import ValidationError

from seller_agent.database_example import (
    PersistRequestInput,
    persist_reference_request,
)


@pytest.mark.parametrize(
    "field,value", [("description", None), ("revision", "invalid")]
)
def test_module_output_rejects_invalid_typed_values(
    monkeypatch: pytest.MonkeyPatch, field: str, value: object
) -> None:
    def command(*args: object, **kwargs: object) -> dict[str, object]:
        return {"objectId": "object-42"}

    def query(*args: object, **kwargs: object) -> dict[str, object]:
        return {
            "objectId": "object-42",
            "requestId": "request-42",
            "description": "A persistent reference request.",
            "status": "open",
            "revision": 1,
            field: value,
        }

    monkeypatch.setattr(RunHandle, "module_command", command)
    monkeypatch.setattr(RunHandle, "module_query", query)
    context = Context(tenant_id="tenant", correlation_id="run", agent_id="reference")
    invocation = OperationInvocation(
        context=context,
        handle=RunHandle("run", context),
        cancellation=NoopCancellation(),
    )
    with pytest.raises(ValidationError):
        persist_reference_request(
            PersistRequestInput(
                request_id="request-42", description="A persistent reference request."
            ),
            invocation,
        )
