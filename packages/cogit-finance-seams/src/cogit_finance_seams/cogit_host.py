"""Bridge between the ports and a Cogit run handle. Needs ``cogit-agent-sdk``.

Inside an operation, wrap ``invocation.handle``::

    modules = HandleModules(invocation.handle)
    artifacts = HandleArtifacts(invocation.handle)

Outside AgentDb (tests, the offline demo), ``LocalRunHandle`` is a run handle
whose database and artifact seams end in the in-process stand-ins, so the real
bound operations of an agent run unchanged.
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
from typing import Any, Callable

from cogit_agent_sdk import OperationInvocation
from cogit_agent_sdk.contracts import RunHandle
from cogit_agent_sdk.loop import NoopCancellation
from cogit_agent_sdk.types import ArtifactRef, ArtifactSlot, Context

from .protocols import ArtifactPort, ModuleError, ModulePort

MAX_ARTIFACT_BYTES = 50 * 1024 * 1024


def contract_id(module: str, export: str, major: int = 1) -> str:
    """Contract ID of a module export, e.g. ``cogit-messaging.message.send.v1``."""
    return f"{module}.{export}.v{major}"


class HandleModules:
    """ModulePort over the SDK's DatabaseSeams."""

    def __init__(self, handle: Any) -> None:
        self._handle = handle

    def module_query(self, module: str, export: str, args: dict | None = None) -> dict:
        return self._handle.module_query(module, export, args or {}, contract_id=contract_id(module, export))

    def module_command(self, module: str, export: str, args: dict | None = None, *, idempotency_key: str) -> dict:
        return self._handle.module_command(
            module, export, args or {}, contract_id=contract_id(module, export), idempotency_key=idempotency_key
        )


class HandleArtifacts:
    """ArtifactPort over the SDK's artifact seams."""

    def __init__(self, handle: Any, kind: str = "deliverable", filename: str = "deliverable.zip") -> None:
        self._handle = handle
        self._kind = kind
        self._filename = filename

    def put(self, data: bytes, media_type: str) -> dict:
        digest = hashlib.sha256(data).hexdigest()
        slot = self._handle.declare_artifact(self._kind, media_type, self._filename)
        ref = self._handle.finalize_artifact(slot, data, digest)
        return {"artifact_id": ref.id, "sha256": digest, "byte_length": len(data), "media_type": media_type}

    def get(self, artifact_id: str) -> bytes:
        return self._handle.read_artifact(ArtifactRef(id=artifact_id), max_bytes=MAX_ARTIFACT_BYTES)

    def stat(self, artifact_id: str) -> dict | None:
        try:
            data = self.get(artifact_id)
        except (ModuleError, KeyError, LookupError):
            return None
        return {
            "artifact_id": artifact_id,
            "sha256": hashlib.sha256(data).hexdigest(),
            "byte_length": len(data),
            "media_type": None,
        }


class LocalRunHandle(RunHandle):
    """Run handle for work executed outside AgentDb, on the in-process stand-ins."""

    def __init__(self, execution_id: str, context: Context, *, modules: ModulePort, artifacts: ArtifactPort) -> None:
        super().__init__(execution_id, context)
        self.local_context = context
        self._modules = modules
        self._artifacts = artifacts

    def module_query(self, module_key: str, query_key: str, payload: dict, *, contract_id: str) -> dict:
        del contract_id
        return self._modules.module_query(module_key, query_key, payload)

    def module_command(
        self, module_key: str, command_key: str, payload: dict, *, contract_id: str, idempotency_key: str
    ) -> dict:
        del contract_id
        return self._modules.module_command(module_key, command_key, payload, idempotency_key=idempotency_key)

    def _perform_finalize_artifact(self, slot: ArtifactSlot, body: bytes, hash: str) -> ArtifactRef:
        stored = self._artifacts.put(body, slot.media_type)
        if stored["sha256"] != hash:
            raise ValueError("Artifact hash does not match its body")
        return ArtifactRef(
            id=stored["artifact_id"],
            name=slot.filename,
            mime_type=slot.media_type,
            size=len(body),
            metadata={"kind": slot.kind, "hash": hash},
        )

    def _perform_read_artifact(self, ref: ArtifactRef, *, max_bytes: int) -> bytes:
        del max_bytes
        return self._artifacts.get(ref.id)


def invoke_action(agent: Any, action: str, payload: dict, handle: RunHandle, *, idempotency_key: str | None = None) -> dict:
    """Run one bound action of a configured agent the way a run host would."""
    binding = next((item for item in agent.action_bindings() if item.descriptor.name == action), None)
    if binding is None:
        raise ModuleError("unknown_action", action)
    request = binding.operation.input_model.model_validate(payload)
    context = getattr(handle, "local_context", None) or Context(
        tenant_id="local", correlation_id="local", agent_id=agent.descriptor.name
    )
    invocation = OperationInvocation(
        context=context, handle=handle, cancellation=NoopCancellation(), idempotency_key=idempotency_key
    )
    result = binding.invoke(request, invocation)
    if inspect.isawaitable(result):
        result = asyncio.run(result)  # type: ignore[arg-type]
    return result.model_dump(mode="json") if hasattr(result, "model_dump") else dict(result or {})


def agent_invoker(
    agent: Any, installation_id: str, *, modules: ModulePort, artifacts: ArtifactPort, tenant_id: str = "local"
) -> Callable[[str, dict, str], dict]:
    """Invoker for ``LocalRuntime.register``: each run gets its own LocalRunHandle."""
    counter = {"n": 0}

    def invoke(action: str, payload: dict, idempotency_key: str) -> dict:
        counter["n"] += 1
        execution_id = f"{installation_id}-{counter['n']:05d}"
        context = Context(tenant_id=tenant_id, correlation_id=execution_id, agent_id=installation_id)
        handle = LocalRunHandle(execution_id, context, modules=modules, artifacts=artifacts)
        return invoke_action(agent, action, payload, handle, idempotency_key=idempotency_key)

    return invoke
