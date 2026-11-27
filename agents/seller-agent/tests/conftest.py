"""Shared runtime fixtures for contract and integration tests."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from cogit_agent_sdk import RunHandle
from cogit_runtime import CogitRuntimeApp
from fastapi.testclient import TestClient
from pydantic import JsonValue

from seller_agent import Agent

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def resolution_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> dict[tuple[str, str], set[str]]:
    """Test-only stand-in for the fenced transport, separate from app state."""
    resolutions: dict[tuple[str, str], set[str]] = {}
    keys: dict[tuple[str, str], tuple[str, str]] = {}

    def command(
        handle: RunHandle,
        module_key: str,
        command_key: str,
        payload: dict[str, JsonValue],
        *,
        contract_id: str,
        idempotency_key: str,
    ) -> dict[str, JsonValue]:
        assert module_key == "cogit.seller-agent"
        assert command_key == "resolutions.apply"
        assert contract_id == f"{module_key}.{command_key}.v1"
        assert idempotency_key.startswith("reference-resolution:")
        case_id = str(payload["case_id"])
        resolution = str(payload["resolution"])
        key = (handle.context.tenant_id, str(payload["request_key"]))
        if keys.setdefault(key, (case_id, resolution)) != (case_id, resolution):
            raise ValueError("Idempotency key is bound to another resolution")
        records = resolutions.setdefault((handle.context.tenant_id, case_id), set())
        replay = resolution in records
        records.add(resolution)
        return {"applied": True, "already_applied": replay}

    def query(
        handle: RunHandle,
        module_key: str,
        query_key: str,
        payload: dict[str, JsonValue],
        *,
        contract_id: str,
    ) -> dict[str, JsonValue]:
        assert module_key == "cogit.seller-agent"
        assert query_key == "resolutions.list"
        assert contract_id == f"{module_key}.{query_key}.v1"
        case_id = str(payload["case_id"])
        records = resolutions.get((handle.context.tenant_id, case_id), set())
        return {"case_id": case_id, "resolutions": list(sorted(records)[:100])}

    monkeypatch.setattr(RunHandle, "module_command", command)
    monkeypatch.setattr(RunHandle, "module_query", query)
    return resolutions


@pytest.fixture
def runtime(resolution_backend: dict[tuple[str, str], set[str]]) -> CogitRuntimeApp:
    return CogitRuntimeApp._from_manifest_for_testing(
        ROOT / "cogit.yaml",
        agent_class=Agent,
        env={"COGIT_DEV_MODE": "1", "COGIT_TENANT_ID": "test-tenant"},
    )


@pytest.fixture
def client(runtime: CogitRuntimeApp) -> Iterator[TestClient]:
    with TestClient(runtime.build()) as test_client:
        yield test_client
