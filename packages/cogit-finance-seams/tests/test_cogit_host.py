import hashlib

import pytest

pytest.importorskip("cogit_agent_sdk")

from cogit_agent_sdk import CogitAgent, bind_action, operation  # noqa: E402
from cogit_agent_sdk.types import Context  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from cogit_finance_seams import LocalArtifacts, LocalModuleHost, LocalRuntime  # noqa: E402
from cogit_finance_seams.cogit_host import (  # noqa: E402
    HandleArtifacts,
    HandleModules,
    LocalRunHandle,
    agent_invoker,
    contract_id,
)
from test_local import Notes  # noqa: E402


class AddInput(BaseModel):
    id: str
    text: str


class AddOutput(BaseModel):
    count: int
    artifact_sha256: str


def add_note(request: AddInput, invocation) -> AddOutput:
    modules = HandleModules(invocation.handle)
    artifacts = HandleArtifacts(invocation.handle, filename="note.txt")
    modules.module_command("notes", "note.add", request.model_dump(), idempotency_key=f"note:{request.id}")
    ref = artifacts.put(request.text.encode(), "text/plain")
    assert artifacts.get(ref["artifact_id"]) == request.text.encode()
    count = len(modules.module_query("notes", "note.list")["notes"])
    return AddOutput(count=count, artifact_sha256=ref["sha256"])


class NoteAgent(CogitAgent):
    def configure(self, services) -> None:
        super().configure(services)
        self.register_action(
            bind_action(operation(add_note), name="add_note", description="Add a note.", risk="write", idempotency="keyed")
        )


def test_contract_id():
    assert contract_id("cogit-messaging", "message.send") == "cogit-messaging.message.send.v1"


def test_bound_operation_runs_on_the_local_stand_ins():
    host, artifacts, runtime = LocalModuleHost(), LocalArtifacts(), LocalRuntime()
    host.install(Notes())
    agent = NoteAgent()
    agent.configure(None)
    runtime.register("noter", agent_invoker(agent, "noter", modules=host.port("noter"), artifacts=artifacts))
    run = runtime.admit("noter", "add_note", {"id": "1", "text": "hello"}, idempotency_key="msg:1")
    result = runtime.result(run)
    assert result.status == "succeeded", result.error
    assert result.output == {"count": 1, "artifact_sha256": hashlib.sha256(b"hello").hexdigest()}
    assert host.port("x").module_query("notes", "note.list")["notes"][0]["owner"] == "noter"


def test_local_run_handle_reads_back_artifacts():
    artifacts = LocalArtifacts()
    context = Context(tenant_id="t", correlation_id="c", agent_id="a")
    handle = LocalRunHandle("run", context, modules=LocalModuleHost().port("a"), artifacts=artifacts)
    ref = HandleArtifacts(handle).put(b"zip-bytes", "application/zip")
    assert artifacts.get(ref["artifact_id"]) == b"zip-bytes"
    assert HandleArtifacts(handle).stat(ref["artifact_id"])["byte_length"] == 9
    assert HandleArtifacts(handle).stat("missing") is None
