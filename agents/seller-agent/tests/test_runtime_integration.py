"""End-to-end runtime checks for the reference agent."""

from __future__ import annotations

from typing import Any, cast

import pytest
from cogit_runtime import CogitRuntimeApp, QueueWorker
from cogit_runtime.config import WorkerConfig
from cogit_runtime.store import InMemoryRuntimeStore
from fastapi.testclient import TestClient

from seller_agent import Agent


def _worker(runtime: CogitRuntimeApp) -> QueueWorker:
    state = runtime.state
    return QueueWorker(
        coordinator=state.coordinator,
        config=WorkerConfig(**state.config.worker.model_dump()),
        queues=["default"],
        item_types=[],
        executor=state.loop_host.run,
        reporter=state.reporter,
        default_agent_id=state.descriptor.id or state.descriptor.name,
        approvals=state.approvals,
        action_executor=state.loop_host.execute_action_for_worker,
        case_service=state.case_service,
    )


def test_runtime_boots_and_handles_read_action(
    client: TestClient,
) -> None:
    health = client.get("/health")
    assert health.status_code == 200

    lookup = client.post(
        "/actions/lookup_record",
        json={"record_id": "record-open"},
    )
    assert lookup.status_code == 200
    assert lookup.json() == {"record_id": "record-open", "status": "open"}


def test_manifest_pipeline_runs_and_records_steps(
    client: TestClient,
    runtime: CogitRuntimeApp,
) -> None:
    response = client.post(
        "/runs",
        json={
            "instruction": "Resolve this synthetic case.",
            "pipeline": "resolve-case",
            "input": {
                "request_id": "request-http",
                "description": "A complete synthetic request.",
            },
        },
    )
    assert response.status_code == 200
    body = cast(dict[str, Any], response.json())
    assert body["status"] == "completed"

    execution = cast(dict[str, Any], body["executionRecord"])
    steps = runtime.state.store.list_execution_steps(cast(str, execution["id"]))
    assert [step.name for step in steps] == ["validate", "finish"]
    assert all(step.status == "completed" for step in steps)


@pytest.mark.asyncio
async def test_gated_write_parks_and_continues_exactly_once(
    client: TestClient,
    runtime: CogitRuntimeApp,
    resolution_backend: dict[tuple[str, str], set[str]],
) -> None:
    parked = client.post(
        "/actions/apply_resolution",
        json={"case_id": "case-approval", "resolution": "close safely"},
        headers={
            "X-Cogit-Context": '{"permissions":["records.write"]}',
            "Idempotency-Key": "case-approval-key",
        },
    )
    assert parked.status_code == 200
    parked_body = cast(dict[str, Any], parked.json())
    assert parked_body["status"] == "parked"

    assert resolution_backend == {}

    decision = client.post(
        f"/attention/{parked_body['attention_item_id']}/decision",
        json={"action": "approve", "decided_by": "template-test"},
    )
    assert decision.status_code == 200

    first = await _worker(runtime).poll_once()
    second = await _worker(runtime).poll_once()
    assert first.completed == 1
    assert second.claimed == 0

    assert resolution_backend == {("test-tenant", "case-approval"): {"close safely"}}


@pytest.mark.asyncio
async def test_queue_pipeline_records_case_timeline(
    client: TestClient,
    runtime: CogitRuntimeApp,
) -> None:
    enqueued = client.post(
        "/dev/enqueue",
        json={
            "queue_name": "default",
            "item_type": "case_request",
            "source_id": "REQUEST-42",
            "payload": {
                "instruction": "Resolve request 42.",
                "pipeline": "resolve-case",
                "input": {
                    "request_id": "REQUEST-42",
                    "description": "A synthetic queue request for the template.",
                },
            },
        },
    )
    assert enqueued.status_code == 200
    enqueued_body = cast(dict[str, Any], enqueued.json())

    stats = await _worker(runtime).poll_once()
    assert stats.completed == 1

    case_id = cast(str, enqueued_body["caseId"])
    case = runtime.state.store.get_case(case_id)
    assert case is not None
    assert case.status == "succeeded"

    queue_runs = [
        run
        for run in runtime.state.store.list_runs()
        if run.metadata and run.metadata.get("queue_item_id")
    ]
    assert len(queue_runs) == 1
    assert queue_runs[0].case_id == case_id
    assert {
        step.case_id
        for step in runtime.state.store.list_execution_steps(queue_runs[0].id)
    } == {case_id}

    assert isinstance(runtime.state.store, InMemoryRuntimeStore)
    restarted = CogitRuntimeApp._from_manifest_for_testing(
        runtime.state.manifest_path,
        agent_class=Agent,
        env={
            "COGIT_DEV_MODE": "1",
            "COGIT_TENANT_ID": "test-tenant",
        },
        store=runtime.state.store,
    )
    recovered_case = restarted.state.store.get_case(case_id)
    assert recovered_case is not None
    assert recovered_case.status == "succeeded"


@pytest.mark.asyncio
async def test_gated_write_denial_does_not_apply(
    client: TestClient,
    runtime: CogitRuntimeApp,
    resolution_backend: dict[tuple[str, str], set[str]],
) -> None:
    parked = client.post(
        "/actions/apply_resolution",
        json={"case_id": "case-denial", "resolution": "denied resolution"},
        headers={
            "X-Cogit-Context": '{"permissions":["records.write"]}',
            "Idempotency-Key": "case-denial-key",
        },
    )
    assert parked.status_code == 200
    parked_body = cast(dict[str, Any], parked.json())
    assert parked_body["status"] == "parked"

    assert resolution_backend == {}

    decision = client.post(
        f"/attention/{parked_body['attention_item_id']}/decision",
        json={"action": "deny", "decided_by": "template-test"},
    )
    assert decision.status_code == 200

    first = await _worker(runtime).poll_once()
    assert first.claimed == 0
    assert first.completed == 0

    assert resolution_backend == {}
