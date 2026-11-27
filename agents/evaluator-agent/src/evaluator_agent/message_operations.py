# pyright: basic
"""The ``handle_message`` operation: the evaluator core on a Cogit run handle.

The core is built for each run from the run handle and the environment:

- ``AGENT_KEY_FILE``: the agent's signing key, created on first use; the default
  is ``.state/keys/evaluator-agent.key``;
- ``ESCROW_DID``: E's DID; without it the DID is resolved with ``identity.resolve``.
"""

from __future__ import annotations

import os
from typing import Any

from cogit_agent_sdk import OperationInvocation
from cogit_finance_seams import ModulePort
from cogit_finance_seams.cogit_host import HandleArtifacts, HandleModules
from cogit_messaging_shim import MESSAGING_MODULE, AgentKey, ShimMessaging

from evaluator_agent.evaluator import EvaluatorCore
from evaluator_agent.schemas import HandleMessageInput, HandleMessageOutput

AGENT_ID = "evaluator-agent"


def load_key() -> AgentKey:
    """The agent's signing key; the file is created on first use."""
    path = os.environ.get("AGENT_KEY_FILE") or f".state/keys/{AGENT_ID}.key"
    return AgentKey.load_or_create(path)


def resolve_escrow_did(modules: ModulePort) -> str:
    """E's DID from ``ESCROW_DID``, otherwise from the messaging module."""
    configured = os.environ.get("ESCROW_DID")
    if configured:
        return configured
    answer = modules.module_query(
        MESSAGING_MODULE, "identity.resolve", {"role": "escrow"}
    )
    identity = answer.get("identity")
    if not identity:
        raise RuntimeError("ESCROW_DID is not set and no escrow identity is registered")
    return str(identity["did"])


def build_core(handle: Any) -> EvaluatorCore:
    """Build the evaluator core over the run handle's module and artifact seams."""
    modules = HandleModules(handle)
    return EvaluatorCore(
        messaging=ShimMessaging(load_key(), modules),
        artifacts=HandleArtifacts(handle),
        escrow_did=resolve_escrow_did(modules),
    )


def handle_message(
    request: HandleMessageInput,
    invocation: OperationInvocation,
) -> HandleMessageOutput:
    """Judge the delivery named by a ``finance.evaluation_request`` from E."""
    with invocation.handle.step("action", "handle_message"):
        result = build_core(invocation.handle).handle_message(request.envelope)
    return HandleMessageOutput.model_validate(result)
