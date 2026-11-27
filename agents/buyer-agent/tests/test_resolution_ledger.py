"""Resolution actions require an authorized module transport."""

from __future__ import annotations

import pytest
from cogit_agent_sdk import NoopCancellation, OperationInvocation, RunHandle
from cogit_agent_sdk.types import Context

from buyer_agent import operations, schemas


def invocation(tenant_id: str, key: str | None = None) -> OperationInvocation:
    context = Context(tenant_id=tenant_id, correlation_id="resolution-test")
    return OperationInvocation(
        context=context,
        handle=RunHandle("resolution-test", context),
        cancellation=NoopCancellation(),
        idempotency_key=key,
    )


def test_no_resolution_backend_is_invented() -> None:
    with pytest.raises(NotImplementedError, match="no database module transport"):
        operations.lookup_resolution(
            schemas.LookupResolutionInput(case_id="missing"), invocation("tenant")
        )


def test_resolution_write_requires_key_before_transport() -> None:
    with pytest.raises(ValueError, match="idempotency key"):
        operations.apply_resolution(
            schemas.ApplyResolutionInput(case_id="case", resolution="close"),
            invocation("tenant"),
        )


def test_resolution_operations_delegate_scope_and_replay(
    resolution_backend: dict[tuple[str, str], set[str]],
) -> None:
    request = schemas.ApplyResolutionInput(case_id="case", resolution="café")
    first = operations.apply_resolution(request, invocation("tenant-a", "key"))
    assert first.applied and not first.already_applied
    assert operations.apply_resolution(
        request, invocation("tenant-a", "key")
    ).already_applied
    other = request.model_copy(update={"resolution": "different"})
    with pytest.raises(ValueError, match="another resolution"):
        operations.apply_resolution(other, invocation("tenant-a", "key"))
    assert (
        operations.lookup_resolution(
            schemas.LookupResolutionInput(case_id="case"), invocation("tenant-b")
        ).resolutions
        == []
    )
    assert operations.lookup_resolution(
        schemas.LookupResolutionInput(case_id="case"), invocation("tenant-a")
    ).resolutions == ["café"]
    assert resolution_backend == {("tenant-a", "case"): {"café"}}
