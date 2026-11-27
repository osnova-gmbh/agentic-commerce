"""Optional module resources and deterministic pipeline regression checks."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from cogit_agent_sdk import AgentServices
from cogit_agent_sdk.contracts import RunHandle
from cogit_runtime import CogitRuntimeApp
from fastapi.testclient import TestClient

from seller_agent.database_bundle import (
    load_database_bundle,
)
from seller_agent.database_example import (
    DatabaseAgent,
    PersistRequestInput,
)

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "seller_agent"
AGENT_ID = "seller-agent"
DATABASE_ROOT = ROOT / "src" / PACKAGE_NAME / "database"


@pytest.mark.parametrize(
    "payload",
    [
        {"request_id": "x", "description": "ok", "tenantId": "forged"},
        {"request_id": "x", "description": "x" * 2001},
        {"request_id": "x" * 129, "description": "ok"},
    ],
)
def test_durable_input_rejects_extra_fields_and_oversize(
    payload: dict[str, Any],
) -> None:
    with pytest.raises(ValueError):
        PersistRequestInput.model_validate(payload)


def _example_manifest() -> dict[str, Any]:
    spec = importlib.util.spec_from_file_location(
        "enable_database", ROOT / "scripts" / "enable_database.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.database_manifest(ROOT / "cogit.yaml")


def test_bundle_digest_and_explicit_requirements() -> None:
    manifest, digest = load_database_bundle()
    expected = json.dumps(
        manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    assert digest == hashlib.sha256(expected).hexdigest()
    assert digest == "8e26fe7bb65d908122f44b35059f75bbfdff21aeb363ac2231f13a7e1ea1e835"
    descriptor = _example_manifest()
    assert descriptor["database_packages"][0]["artifact_sha256"] == digest
    assert descriptor["pipelines"][0]["applies_to"] == ["queue"]
    assert descriptor["runtime"]["worker"]["concurrency"] == 1
    assert descriptor["runtime"]["model"] == {"profile": "disabled"}
    assert "model" not in descriptor
    assert descriptor["tools"] == []
    assert [action["name"] for action in descriptor["actions"]] == [
        "persist_reference_request"
    ]
    worker = DatabaseAgent()
    worker.configure(AgentServices())
    assert [binding.descriptor.name for binding in worker.action_bindings()] == [
        "persist_reference_request"
    ]
    assert not worker.tool_bindings()
    assert [step["kind"] for step in descriptor["pipelines"][0]["steps"]] == [
        "deterministic",
        "terminal",
    ]
    worker_put = next(
        export for export in manifest["exports"] if export["key"] == "requests.put"
    )
    assert worker_put["callerKinds"] == ["fenced_worker"]
    assert "requests.put" not in manifest["resources"][0]["actions"].values()
    assert manifest["version"] == "1.1.7"
    assert manifest["platform"]["minSchema"] == 179
    assert manifest["platform"]["maxSchema"] == 216
    assert manifest["upgradeFrom"] == [
        "1.1.1",
        "1.1.2",
        "1.1.3",
        "1.1.4",
        "1.1.5",
        "1.1.6",
    ]
    assert [item["id"] for item in manifest["migrations"]] == [
        "000001__reference_domain",
        "000002__reference_commands",
        "000003__reference_list_v2",
        "000004__reference_resolutions",
    ]
    listing = next(
        item for item in manifest["exports"] if item["key"] == "requests.list"
    )
    assert listing["contractId"] == f"cogit.{AGENT_ID}.requests.list.v2"
    assert listing["version"] == "1.1.0"
    assert listing["functionName"] == f"{PACKAGE_NAME}_list_v2"
    assert "select" not in listing["inputSchema"]["properties"]
    assert "minLength" not in listing["inputSchema"]["properties"]["after"]
    assert descriptor["database_packages"][0]["version"] == "1.1.7"


def test_retained_1_1_6_preserves_the_exact_previous_bundle() -> None:
    retained, digest = load_database_bundle(historical_version="1.1.6")
    assert retained["version"] == "1.1.6"
    assert retained["platform"] == {"minSchema": 179, "maxSchema": 215}
    assert digest == "2008aec06a5eef639297ecf99445069f118d65b4dcb4af1117f63b56dea942a5"
    active, _ = load_database_bundle()
    for key in ("migrations", "files", "exports", "resources", "settings"):
        assert active[key] == retained[key]


def test_retained_1_1_5_preserves_the_exact_previous_bundle() -> None:
    retained, digest = load_database_bundle(historical_version="1.1.5")
    assert retained["version"] == "1.1.5"
    assert digest == "0d670517080cd259ebf43451b0a572308a46d29c51ee0d2c8ca3c2649eba2d56"
    active, _ = load_database_bundle()
    for key in ("migrations", "files", "exports"):
        assert active[key][: len(retained[key])] == retained[key]
    assert active["resources"] == retained["resources"]
    assert active["settings"] == retained["settings"]


def test_retained_1_1_4_preserves_the_exact_released_bundle() -> None:
    retained, digest = load_database_bundle(historical_version="1.1.4")
    assert retained["version"] == "1.1.4"
    assert digest == "2d5a38716e07146b82f6653f7552f633a24be422fe6c799223ac6403f254a5f4"
    assert retained["platform"] == {"minSchema": 179, "maxSchema": 211}
    assert retained["upgradeFrom"] == ["1.1.1", "1.1.2", "1.1.3"]
    active, _ = load_database_bundle()
    for key in ("migrations", "files", "exports"):
        assert active[key][: len(retained[key])] == retained[key]
    assert active["resources"] == retained["resources"]
    assert active["settings"] == retained["settings"]
    active_root = DATABASE_ROOT
    retained_root = active_root / "historical" / "module-1.1.4"
    for path in retained_root.rglob("*"):
        if path.is_file() and path.name != "manifest.json":
            assert (
                path.read_bytes()
                == (active_root / path.relative_to(retained_root)).read_bytes()
            )


def test_retained_1_1_3_preserves_the_released_upstream_commitment_and_resources() -> (
    None
):
    retained, digest = load_database_bundle(historical_version="1.1.3")
    assert retained["version"] == "1.1.3"
    assert digest == "d5e829bbb3e6f885b84447a44cb843710efc62dc3cb2de3dd0db8eb2299e665a"
    assert retained["platform"] == {"minSchema": 179, "maxSchema": 205}
    assert retained["upgradeFrom"] == ["1.1.2"]
    active, _ = load_database_bundle()
    assert active["migrations"][: len(retained["migrations"])] == retained["migrations"]
    assert active["files"][: len(retained["files"])] == retained["files"]
    assert active["exports"][: len(retained["exports"])] == retained["exports"]
    active_root = DATABASE_ROOT
    retained_root = active_root / "historical" / "module-1.1.3"
    for path in retained_root.rglob("*"):
        if path.is_file() and path.name != "manifest.json":
            assert (
                path.read_bytes()
                == (active_root / path.relative_to(retained_root)).read_bytes()
            )


def test_retained_1_1_2_preserves_its_original_commitment_and_resources() -> None:
    retained, digest = load_database_bundle(historical_version="1.1.2")
    assert retained["version"] == "1.1.2"
    assert digest == "4f3ebe91c8a160f07df95258fb79d6297a58740c218b19f95fc9bb80a4c1cc3d"
    assert retained["platform"] == {"minSchema": 179, "maxSchema": 204}
    assert retained["upgradeFrom"] == ["1.1.1"]
    active, _ = load_database_bundle()
    assert active["migrations"][: len(retained["migrations"])] == retained["migrations"]
    assert active["files"][: len(retained["files"])] == retained["files"]
    assert active["exports"][: len(retained["exports"])] == retained["exports"]
    active_root = DATABASE_ROOT
    retained_root = active_root / "historical" / "module-1.1.2"
    for path in retained_root.rglob("*"):
        if path.is_file() and path.name != "manifest.json":
            assert (
                path.read_bytes()
                == (active_root / path.relative_to(retained_root)).read_bytes()
            )


def test_retained_1_1_1_preserves_its_original_commitment_and_resources() -> None:
    retained, digest = load_database_bundle(historical_version="1.1.1")
    assert retained["version"] == "1.1.1"
    assert digest == "54ec404351ec5f636f56770539f1eb179881c2ebabe1b4f6bf76ce3818b2cecc"
    assert retained["platform"] == {"minSchema": 179, "maxSchema": 203}
    assert retained["upgradeFrom"] == ["1.1.0"]
    active, _ = load_database_bundle()
    assert active["migrations"][: len(retained["migrations"])] == retained["migrations"]
    assert active["files"][: len(retained["files"])] == retained["files"]
    assert active["exports"][: len(retained["exports"])] == retained["exports"]


def test_retained_1_1_0_preserves_its_original_commitment_and_resources() -> None:
    retained, digest = load_database_bundle(historical_version="1.1.0")
    assert retained["version"] == "1.1.0"
    assert digest == "60f030fbffecfb72d4f9d3daf43bd5faf5c4fdc1b447830ad77d85f14c23bc14"
    assert retained["platform"] == {"minSchema": 179, "maxSchema": 199}
    active, _ = load_database_bundle()
    assert active["migrations"][: len(retained["migrations"])] == retained["migrations"]
    assert active["files"][: len(retained["files"])] == retained["files"]
    assert active["exports"][: len(retained["exports"])] == retained["exports"]


@pytest.mark.parametrize("selector", ["../escape", "1.1.7", ""])
def test_unknown_retained_bundle_selector_is_rejected(selector: Any) -> None:
    with pytest.raises(ValueError, match="Unknown retained"):
        load_database_bundle(historical_version=selector)


def test_retained_v1_bundle_has_original_identity_and_bytes() -> None:
    historical, digest = load_database_bundle(historical=True)
    assert historical["version"] == "1.0.0"
    assert digest == "552526cd0334c64abd236f6f759d14b9a5b01b07c27e27ff788e715a1f75b540"
    old_root = DATABASE_ROOT / "historical" / "module-1.0.0"
    active_root = DATABASE_ROOT
    for name in (
        "migrations/000001__reference_domain.sql",
        "migrations/000002__reference_commands.sql",
        "contracts/requests.v1.json",
        "contracts/settings.v1.json",
        "catalog/resources.v1.json",
    ):
        assert (old_root / name).read_bytes() == (active_root / name).read_bytes()


@pytest.mark.parametrize(
    "unsafe", ["../escape.sql", "C:/escape.sql", "migrations\\escape.sql"]
)
def test_bundle_rejects_unsafe_resource_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, unsafe: str
) -> None:
    package = tmp_path / "package"
    shutil.copytree(DATABASE_ROOT, package / "database")
    path = package / "database" / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["migrations"][0]["path"] = unsafe
    path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(f"{PACKAGE_NAME}.database_bundle.files", lambda _: package)
    with pytest.raises(ValueError, match="resource path"):
        load_database_bundle()


def test_bundle_rejects_stale_sql_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = tmp_path / "package"
    shutil.copytree(DATABASE_ROOT, package / "database")
    sql = package / "database" / "migrations" / "000001__reference_domain.sql"
    sql.write_bytes(sql.read_bytes() + b"\n-- tampered\n")
    monkeypatch.setattr(f"{PACKAGE_NAME}.database_bundle.files", lambda _: package)
    with pytest.raises(ValueError, match="hash mismatch"):
        load_database_bundle()


@pytest.mark.parametrize("request_id", ["request-db", "ü" * 128])
def test_queue_pipeline_uses_registered_transport_without_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, request_id: str
) -> None:
    import yaml

    calls: list[str] = []
    rows: dict[str, dict[str, Any]] = {}

    def command(
        self: RunHandle,
        module_key: str,
        command_key: str,
        payload: dict[str, Any],
        *,
        contract_id: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        del self
        assert module_key == "cogit.seller-agent"
        assert command_key == "requests.put"
        assert contract_id == f"{module_key}.requests.put.v1"
        assert (
            idempotency_key
            == "reference-request:"
            + hashlib.sha256(request_id.encode("utf-8")).hexdigest()
        )
        calls.append(command_key)
        row = {
            "objectId": "00000000-0000-0000-0000-000000000042",
            "requestId": payload["requestId"],
            "description": payload["description"],
            "status": "open",
            "revision": 1,
        }
        rows[row["objectId"]] = row
        return row

    def query(
        self: RunHandle,
        module_key: str,
        query_key: str,
        payload: dict[str, Any],
        *,
        contract_id: str,
    ) -> dict[str, Any]:
        del self
        assert contract_id == f"{module_key}.requests.get.v1"
        calls.append(query_key)
        return rows[payload["objectId"]]

    monkeypatch.setattr(RunHandle, "module_command", command)
    monkeypatch.setattr(RunHandle, "module_query", query)
    manifest_path = tmp_path / "cogit.database.yaml"
    manifest_path.write_text(yaml.safe_dump(_example_manifest()), encoding="utf-8")
    runtime = CogitRuntimeApp._from_manifest_for_testing(
        manifest_path,
        agent_class=DatabaseAgent,
        env={
            "COGIT_DEV_MODE": "1",
            "COGIT_TENANT_ID": "test-tenant",
        },
    )
    with TestClient(runtime.build()) as client:
        response = client.post(
            "/runs",
            json={
                "instruction": "Persist the typed request.",
                "context": {"trigger": "queue"},
                "input": {
                    "request_id": request_id,
                    "description": "Durable example.",
                },
            },
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "completed", body
    assert calls == ["requests.put", "requests.get"]
    steps = runtime.state.store.list_execution_steps(body["executionRecord"]["id"])
    assert [step.name for step in steps] == ["persist", "finish"]
    assert len(rows) == 1
    assert next(iter(rows.values()))["requestId"] == request_id
