"""Protected actions resume and read through a test-owned module transport."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
from cogit_runtime import CogitRuntimeApp, QueueWorker
from cogit_runtime.config import WorkerConfig
from cogit_runtime.store import InMemoryRuntimeStore
from fastapi.testclient import TestClient

from buyer_agent import Agent

ROOT = Path(__file__).resolve().parents[1]
WRITE_CONTEXT = (
    '{"permissions":["records.write"],"principal":{"kind":"user","id":"tester"}}'
)
READ_CONTEXT = '{"permissions":["records.read"]}'
PAYLOAD = {"case_id": "durable-case", "resolution": "close after approval"}


def runtime_at(store: InMemoryRuntimeStore) -> CogitRuntimeApp:
    return CogitRuntimeApp._from_manifest_for_testing(
        ROOT / "cogit.yaml",
        agent_class=Agent,
        env={
            "COGIT_DEV_MODE": "1",
            "COGIT_TENANT_ID": "ledger-tenant",
        },
        store=store,
    )


def worker(runtime: CogitRuntimeApp) -> QueueWorker:
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
        action_descriptor=state.loop_host.action_descriptor,
        case_service=state.case_service,
    )


def readback(client: TestClient) -> dict[str, Any]:
    response = client.post(
        "/actions/lookup_resolution",
        json={"case_id": PAYLOAD["case_id"]},
        headers={"X-Cogit-Context": READ_CONTEXT},
    )
    assert response.status_code == 200
    return cast(dict[str, Any], response.json())


@pytest.mark.asyncio
async def test_protected_write_uses_module_after_worker_replacement(
    resolution_backend: dict[tuple[str, str], set[str]],
) -> None:
    store = InMemoryRuntimeStore()
    runtime = runtime_at(store)
    with TestClient(runtime.build()) as client:
        denied = client.post(
            "/actions/apply_resolution",
            json=PAYLOAD,
            headers={"Idempotency-Key": "request-1"},
        )
        assert denied.status_code == 403
        assert runtime.state.approvals.list_pending() == []
        missing_key = client.post(
            "/actions/apply_resolution",
            json=PAYLOAD,
            headers={"X-Cogit-Context": WRITE_CONTEXT},
        )
        assert missing_key.status_code == 400
        assert readback(client)["resolutions"] == []
        parked = client.post(
            "/actions/apply_resolution",
            json=PAYLOAD,
            headers={"X-Cogit-Context": WRITE_CONTEXT, "Idempotency-Key": "request-1"},
        )
        assert parked.status_code == 200 and parked.json()["status"] == "parked"
        attention_id = parked.json()["attention_item_id"]
        assert readback(client)["resolutions"] == []
        decision = client.post(
            f"/attention/{attention_id}/decision",
            json={"action": "approve", "decided_by": "template-test"},
        )
        assert decision.status_code == 200
        assert readback(client)["resolutions"] == []

    restarted = runtime_at(store)
    stats = await worker(restarted).poll_once()
    assert stats.completed == 1 and stats.failed == 0
    assert restarted.state.approvals.record_for(attention_id).consumed
    with TestClient(restarted.build()) as client:
        assert readback(client) == {
            "case_id": "durable-case",
            "resolutions": ["close after approval"],
        }
        denied_read = client.post(
            "/actions/lookup_resolution", json={"case_id": "durable-case"}
        )
        assert denied_read.status_code == 403

    replaced = runtime_at(store)
    assert (await worker(replaced).poll_once()).claimed == 0
    with TestClient(replaced.build()) as client:
        assert readback(client)["resolutions"] == ["close after approval"]
        # A new approval for the original key/payload is a durable replay.
        parked = client.post(
            "/actions/apply_resolution",
            json=PAYLOAD,
            headers={"X-Cogit-Context": WRITE_CONTEXT, "Idempotency-Key": "request-1"},
        )
        replay_id = parked.json()["attention_item_id"]
        client.post(
            f"/attention/{replay_id}/decision",
            json={"action": "approve", "decided_by": "template-test"},
        )
    assert (await worker(replaced).poll_once()).completed == 1
    with TestClient(replaced.build()) as client:
        assert readback(client)["resolutions"] == ["close after approval"]
