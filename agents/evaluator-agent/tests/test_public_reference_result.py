"""Canonical text admission and public root result for the existing worker."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from importlib.resources import files
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from cogit_agent_sdk import OperationInvocation
from cogit_agent_sdk.contracts import RunHandle
from cogit_agent_sdk.loop import NoopCancellation
from cogit_agent_sdk.types import ArtifactRef, ArtifactSlot, Context
from jsonschema import Draft202012Validator, ValidationError

from evaluator_agent.database_example import (
    MODULE_KEY,
    PUBLIC_RESULT_FILENAME,
    PersistRequestInput,
    PublicReferenceResult,
    persist_reference_request,
)

FIXTURES = Path(__file__).parent / "fixtures" / "a10"
CANONICAL_TEXT = (FIXTURES / "canonical-input.txt").read_text(encoding="utf-8")
EXPECTED_ROOT = (FIXTURES / "root-result.v1.json").read_bytes()
EXPECTED_ACTION_OUTPUT = json.loads(
    (FIXTURES / "worker-action-output.v1.json").read_bytes()
)
EXPECTED_REQUEST_ID = (
    "text-00e43d91a79b2fdfe6cba58a290073fdbc77737218d52c564ff16e6701b5fcb2"
)


class RecordingHandle(RunHandle):
    def __init__(self, context: Context) -> None:
        super().__init__("00000000-0000-0000-0000-000000000001", context)
        self.commands: list[tuple[str, str, dict[str, Any], str, str]] = []
        self.queries: list[tuple[str, str, dict[str, Any], str]] = []
        self.artifacts: list[tuple[ArtifactSlot, bytes, str]] = []
        self.readback_override: dict[str, Any] = {}

    def module_command(
        self,
        module_key: str,
        command_key: str,
        payload: dict[str, Any],
        *,
        contract_id: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        self.commands.append(
            (module_key, command_key, payload, contract_id, idempotency_key)
        )
        return {"objectId": "00000000-0000-0000-0000-000000000042"}

    def module_query(
        self,
        module_key: str,
        query_key: str,
        payload: dict[str, Any],
        *,
        contract_id: str,
    ) -> dict[str, Any]:
        self.queries.append((module_key, query_key, payload, contract_id))
        command_payload = self.commands[-1][2]
        return {
            "objectId": payload["objectId"],
            "requestId": command_payload["requestId"],
            "description": command_payload["description"],
            "status": "open",
            "revision": 1,
            **self.readback_override,
        }

    def _perform_finalize_artifact(
        self, slot: ArtifactSlot, body: bytes, content_hash: str
    ) -> ArtifactRef:
        self.artifacts.append((slot, body, content_hash))
        return ArtifactRef(
            id="00000000-0000-0000-0000-000000000043",
            name=slot.filename,
            mime_type=slot.media_type,
            size=len(body),
            metadata={"kind": slot.kind, "hash": content_hash},
        )


def _invoke(
    payload: dict[str, str], *, tenant_id: str = "tenant-a"
) -> tuple[RecordingHandle, Any]:
    context = Context(
        tenant_id=tenant_id,
        correlation_id="a10-run",
        agent_id="evaluator-agent",
        trigger="queue",
    )
    handle = RecordingHandle(context)
    invocation = OperationInvocation(
        context=context, handle=handle, cancellation=NoopCancellation()
    )
    return handle, persist_reference_request(
        PersistRequestInput.model_validate(payload), invocation
    )


def test_canonical_text_commits_exact_public_root_result() -> None:
    handle, output = _invoke({"instruction": CANONICAL_TEXT})

    assert output.request_id == EXPECTED_REQUEST_ID
    assert handle.commands == [
        (
            MODULE_KEY,
            "requests.put",
            {"requestId": EXPECTED_REQUEST_ID, "description": CANONICAL_TEXT},
            f"{MODULE_KEY}.requests.put.v1",
            "reference-request:"
            + hashlib.sha256(EXPECTED_REQUEST_ID.encode("utf-8")).hexdigest(),
        )
    ]
    assert handle.queries == [
        (
            MODULE_KEY,
            "requests.get",
            {"objectId": "00000000-0000-0000-0000-000000000042"},
            f"{MODULE_KEY}.requests.get.v1",
        )
    ]
    assert len(handle.artifacts) == 1
    slot, body, digest = handle.artifacts[0]
    assert (slot.kind, slot.media_type, slot.filename) == (
        "result",
        "application/json",
        PUBLIC_RESULT_FILENAME,
    )
    assert body == EXPECTED_ROOT
    assert digest == hashlib.sha256(EXPECTED_ROOT).hexdigest()
    assert output.root_artifact_id == "00000000-0000-0000-0000-000000000043"
    assert output.root_sha256 == digest
    assert output.model_dump(mode="json") == EXPECTED_ACTION_OUTPUT
    assert handle.outcome_label == "reference_request_persisted"
    assert handle.work_outcome is not None
    assert handle.work_outcome.outcome == "completed"
    assert handle.work_outcome.reason_code == "reference_request_persisted"
    assert set(json.loads(body)) == {
        "schemaVersion",
        "outcome",
        "requestId",
        "status",
        "revision",
    }


def test_existing_typed_request_still_uses_its_business_key() -> None:
    handle, output = _invoke(
        {"request_id": "request-db", "description": "Persist a reference record."}
    )
    assert output.request_id == "request-db"
    assert handle.commands[0][2] == {
        "requestId": "request-db",
        "description": "Persist a reference record.",
    }
    assert handle.commands[0][4] == (
        "reference-request:" + hashlib.sha256(b"request-db").hexdigest()
    )
    assert handle.work_outcome is not None
    assert handle.work_outcome.outcome == "completed"


def test_runtime_queue_pipeline_routes_canonical_text_to_existing_worker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import yaml
    from cogit_runtime import CogitRuntimeApp
    from fastapi.testclient import TestClient

    from evaluator_agent.database_example import (
        DatabaseAgent,
    )

    calls: list[str] = []

    def command(
        self: RunHandle,
        module_key: str,
        command_key: str,
        payload: dict[str, Any],
        *,
        contract_id: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        del self, idempotency_key
        assert module_key == MODULE_KEY
        assert contract_id == f"{MODULE_KEY}.requests.put.v1"
        assert payload == {
            "requestId": EXPECTED_REQUEST_ID,
            "description": CANONICAL_TEXT,
        }
        calls.append(command_key)
        return {"objectId": "00000000-0000-0000-0000-000000000042"}

    def query(
        self: RunHandle,
        module_key: str,
        query_key: str,
        payload: dict[str, Any],
        *,
        contract_id: str,
    ) -> dict[str, Any]:
        del self
        assert module_key == MODULE_KEY
        assert contract_id == f"{MODULE_KEY}.requests.get.v1"
        calls.append(query_key)
        return {
            "objectId": payload["objectId"],
            "requestId": EXPECTED_REQUEST_ID,
            "description": CANONICAL_TEXT,
            "status": "open",
            "revision": 1,
        }

    monkeypatch.setattr(RunHandle, "module_command", command)
    monkeypatch.setattr(RunHandle, "module_query", query)
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "enable_database", root / "scripts" / "enable_database.py"
    )
    assert spec is not None and spec.loader is not None
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    manifest = generator.database_manifest(root / "cogit.yaml")
    manifest_path = tmp_path / "cogit.database.yaml"
    manifest_path.write_text(yaml.safe_dump(manifest), encoding="utf-8")
    runtime = CogitRuntimeApp._from_manifest_for_testing(
        manifest_path,
        agent_class=DatabaseAgent,
        env={
            "COGIT_DEV_MODE": "1",
            "COGIT_TENANT_ID": "tenant-a",
        },
    )
    with TestClient(runtime.build()) as client:
        response = client.post(
            "/runs",
            json={
                "instruction": CANONICAL_TEXT,
                "context": {"trigger": "queue"},
                "input": {"instruction": CANONICAL_TEXT},
            },
        )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "completed"
    assert response.json()["workOutcome"]["outcome"] == "completed"
    persist_step = next(
        step for step in response.json()["output"]["steps"] if step["id"] == "persist"
    )
    root_ref = persist_step["output"]
    assert UUID(root_ref["root_artifact_id"])
    assert root_ref["root_sha256"] == hashlib.sha256(EXPECTED_ROOT).hexdigest()
    assert calls == ["requests.put", "requests.get"]


def test_canonical_request_id_is_stable_and_tenant_scoped() -> None:
    request = PersistRequestInput(instruction=CANONICAL_TEXT)
    assert request.mapped_request("tenant-a")[0] == EXPECTED_REQUEST_ID
    assert request.mapped_request("tenant-a")[0] == EXPECTED_REQUEST_ID
    assert request.mapped_request("tenant-b")[0] != EXPECTED_REQUEST_ID


def test_published_root_schema_matches_model_and_excludes_internal_fields() -> None:
    schema = json.loads(
        files("evaluator_agent")
        .joinpath("public/root-result.v1.schema.json")
        .read_text(encoding="utf-8")
    )
    assert schema == {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        **PublicReferenceResult.model_json_schema(by_alias=True),
    }
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    public = json.loads(EXPECTED_ROOT)
    validator.validate(public)
    with pytest.raises(ValidationError):
        validator.validate({**public, "tenantId": "forged"})


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"request_id": "incomplete"},
        {"instruction": "  \n"},
        {"instruction": "contains\x00nul"},
        {"instruction": "x" * 2001},
        {"instruction": "text", "request_id": "forged"},
        {"instruction": "text", "tenant_id": "forged"},
    ],
)
def test_canonical_input_rejects_invalid_or_mixed_shape(
    payload: dict[str, str],
) -> None:
    with pytest.raises(ValueError):
        PersistRequestInput.model_validate(payload)


def test_readback_mismatch_cannot_commit_root_or_business_outcome() -> None:
    context = Context(tenant_id="tenant-a", correlation_id="a10-run")
    handle = RecordingHandle(context)
    handle.readback_override = {"requestId": "another-request"}
    invocation = OperationInvocation(
        context=context, handle=handle, cancellation=NoopCancellation()
    )
    with pytest.raises(ValueError, match="readback"):
        persist_reference_request(
            PersistRequestInput(instruction=CANONICAL_TEXT), invocation
        )
    assert handle.artifacts == []
    assert handle.work_outcome is None
