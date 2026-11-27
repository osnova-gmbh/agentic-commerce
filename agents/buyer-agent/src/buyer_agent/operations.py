"""Typed domain operations and explicit binding helpers for the reference agent."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256
from typing import TYPE_CHECKING, Any

from cogit_agent_sdk import (
    ActionBinding,
    OperationContract,
    OperationInvocation,
    ToolBinding,
    bind_action,
    bind_tool_from_action,
    operation,
)

from buyer_agent.buyer_operations import handle_message, start_purchase
from buyer_agent.schemas import (
    ApplyResolutionInput,
    ApplyResolutionOutput,
    LookupRecordInput,
    LookupRecordOutput,
    LookupResolutionInput,
    LookupResolutionOutput,
    RefreshRecordIndexInput,
    RefreshRecordIndexOutput,
    ValidateRequestInput,
    ValidateRequestOutput,
)

if TYPE_CHECKING:
    from buyer_agent.agent import Agent


MODULE_KEY = "cogit.buyer-agent"


@dataclass(frozen=True)
class InternalOperations:
    """Configured operations used by domain code but absent from both manifests."""

    refresh_record_index: OperationContract[
        RefreshRecordIndexInput,
        RefreshRecordIndexOutput,
    ]


def build_internal_operations(agent: Agent) -> InternalOperations:
    """Construct instance-dependent internal operations after dependencies exist."""

    return InternalOperations(
        refresh_record_index=operation(_refresh_record_index(agent)),
    )


def build_domain_action_bindings(
    agent: Agent,
) -> list[ActionBinding[Any, Any]]:
    """Return typed action bindings for the reference agent domain surface."""

    return [
        bind_action(
            operation(_lookup_record(agent)),
            name="lookup_record",
            description="Look up a synthetic service record.",
            risk="read",
            idempotency="inherent",
        ),
        bind_action(
            operation(_validate_request(agent)),
            name="validate_request",
            description="Validate a synthetic service request.",
            risk="read",
            idempotency="inherent",
        ),
        bind_action(
            operation(apply_resolution),
            name="apply_resolution",
            description="Apply an approved synthetic case resolution.",
            risk="write",
            idempotency="keyed",
            requires_approval=True,
            required_capabilities=["records.write"],
        ),
        bind_action(
            operation(lookup_resolution),
            name="lookup_resolution",
            description="Read committed synthetic case resolutions.",
            risk="read",
            idempotency="inherent",
            required_capabilities=["records.read"],
        ),
        bind_action(
            operation(handle_message),
            name="handle_message",
            description="Handle one inbound signed finance message.",
            risk="write",
            idempotency="inherent",
        ),
        bind_action(
            operation(start_purchase),
            name="start_purchase",
            description="Discover an offer and request it through the escrow.",
            risk="write",
            idempotency="inherent",
        ),
    ]


def build_domain_tool_bindings(
    action_bindings: list[ActionBinding[Any, Any]],
) -> list[ToolBinding[Any, Any]]:
    """Return tool bindings derived from read-only dual-bound domain actions."""

    by_name = {binding.descriptor.name: binding for binding in action_bindings}
    return [
        bind_tool_from_action(
            by_name["lookup_record"],
            execution_mode="parallel",
        ),
        bind_tool_from_action(
            by_name["validate_request"],
            execution_mode="parallel",
        ),
    ]


def register_domain_action_bindings(
    agent: Agent,
) -> list[ActionBinding[Any, Any]]:
    """Register typed domain action bindings on a configured agent."""

    bindings = build_domain_action_bindings(agent)
    for binding in bindings:
        agent.register_action(binding)
    return bindings


def register_domain_tool_bindings(
    agent: Agent,
    action_bindings: list[ActionBinding[Any, Any]],
) -> None:
    """Register typed domain tool bindings on a configured agent."""

    for binding in build_domain_tool_bindings(action_bindings):
        agent.register_tool(binding)


def _refresh_record_index(
    agent: Agent,
) -> Callable[
    [RefreshRecordIndexInput, OperationInvocation],
    RefreshRecordIndexOutput,
]:
    def refresh_record_index(
        request: RefreshRecordIndexInput,
        invocation: OperationInvocation,
    ) -> RefreshRecordIndexOutput:
        del request, invocation
        return RefreshRecordIndexOutput(
            record_count=len(agent.dependencies.records.records),
        )

    return refresh_record_index


def _lookup_record(
    agent: Agent,
) -> Callable[[LookupRecordInput, OperationInvocation], LookupRecordOutput]:
    def lookup_record(
        request: LookupRecordInput,
        invocation: OperationInvocation,
    ) -> LookupRecordOutput:
        with invocation.handle.step("action", "lookup_record"):
            internal = agent.internal_operations
            assert internal is not None
            internal.refresh_record_index(
                RefreshRecordIndexInput(),
                invocation,
            )
            return agent.dependencies.records.lookup(request)

    return lookup_record


def _validate_request(
    agent: Agent,
) -> Callable[[ValidateRequestInput, OperationInvocation], ValidateRequestOutput]:
    def validate_request(
        request: ValidateRequestInput,
        invocation: OperationInvocation,
    ) -> ValidateRequestOutput:
        with invocation.handle.step("action", "validate_request"):
            return agent.dependencies.records.validate(request)

    return validate_request


def apply_resolution(
    request: ApplyResolutionInput,
    invocation: OperationInvocation,
) -> ApplyResolutionOutput:
    request_key = invocation.idempotency_key
    if request_key is None or not request_key.strip() or len(request_key) > 4096:
        raise ValueError(
            "Resolution storage requires an idempotency key of 1 to 4096 characters"
        )
    with invocation.handle.step("action", "apply_resolution"):
        response = invocation.handle.module_command(
            MODULE_KEY,
            "resolutions.apply",
            {
                "case_id": request.case_id,
                "resolution": request.resolution,
                "request_key": request_key,
            },
            contract_id=f"{MODULE_KEY}.resolutions.apply.v1",
            idempotency_key="reference-resolution:"
            + sha256(request_key.encode("utf-8")).hexdigest(),
        )
    return ApplyResolutionOutput.model_validate(response)


def lookup_resolution(
    request: LookupResolutionInput,
    invocation: OperationInvocation,
) -> LookupResolutionOutput:
    with invocation.handle.step("action", "lookup_resolution"):
        response = invocation.handle.module_query(
            MODULE_KEY,
            "resolutions.list",
            {"case_id": request.case_id},
            contract_id=f"{MODULE_KEY}.resolutions.list.v1",
        )
    result = LookupResolutionOutput.model_validate(response)
    if result.case_id != request.case_id:
        raise ValueError("Resolution readback did not match the requested case")
    return result
