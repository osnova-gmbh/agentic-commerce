"""The seller's bound actions on the local run-handle stand-in."""

from __future__ import annotations

import hashlib
import io
import zipfile
from importlib import resources
from pathlib import Path
from typing import Any

import pytest
from agent_helpers import configured_seller_agent
from cogit_agent_sdk.types import Context
from cogit_finance_seams import LocalArtifacts
from cogit_finance_seams.cogit_host import LocalRunHandle, invoke_action
from cogit_messaging_shim import AgentKey, verify_envelope
from finance_fakes import (
    DEAL_ID,
    REQUIRED_FILES,
    FakeModules,
    decision,
    funding_confirmed,
    relay,
    service_request,
    terms_proposed,
)

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = (
    "ESCROW_DID",
    "SELLER_OFFERS_FILE",
    "SELLER_ORG_ID",
    "SELLER_MODE",
    "SELLER_DELAY_S",
)


@pytest.fixture
def key_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A private key location and no seller settings in the environment."""
    path = tmp_path / "keys" / "seller-agent.key"
    monkeypatch.setenv("AGENT_KEY_FILE", str(path))
    for name in SETTINGS:
        monkeypatch.delenv(name, raising=False)
    return path


def invoke(
    action: str,
    payload: dict[str, Any],
    modules: FakeModules,
    artifacts: LocalArtifacts,
    key: str | None = None,
) -> dict[str, Any]:
    context = Context(tenant_id="local", correlation_id="run-1", agent_id="seller")
    handle = LocalRunHandle("run-1", context, modules=modules, artifacts=artifacts)
    agent = configured_seller_agent()
    return invoke_action(agent, action, payload, handle, idempotency_key=key)


def test_publish_catalog_action_publishes_the_packaged_offers(key_file: Path) -> None:
    modules = FakeModules()  # no escrow identity yet: publishing does not need it

    output = invoke("publish_catalog", {}, modules, LocalArtifacts(), "publish:1")

    assert output == {"count": 1}
    ((args, key),) = modules.published()
    assert args["seller_org_id"] == "seller-co"
    assert [offer["offer_id"] for offer in args["offers"]] == ["offer-1"]
    assert key == "catalog.publish:seller-co:publish:1"
    assert modules.queries == []
    assert not key_file.exists()


def test_publish_catalog_action_reads_the_configured_offers_file(
    key_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    offers_file = tmp_path / "offers.yaml"
    offers_file.write_text(
        "seller_org_id: acme-co\n"
        "offers:\n"
        "  - {offer_id: a, price_minor: 100, currency: EUR}\n"
        "  - {offer_id: b, price_minor: 200, currency: EUR}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("SELLER_OFFERS_FILE", str(offers_file))
    modules = FakeModules()

    assert invoke("publish_catalog", {}, modules, LocalArtifacts()) == {"count": 2}

    ((args, _),) = modules.published()
    assert args["seller_org_id"] == "acme-co"
    assert [offer["offer_id"] for offer in args["offers"]] == ["a", "b"]


def test_handle_message_action_runs_the_seller_side_of_a_broken_deal(
    key_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SELLER_MODE", "broken")
    escrow, buyer = AgentKey.generate(), AgentKey.generate()
    seller_did = AgentKey.load_or_create(key_file).did
    modules, artifacts = FakeModules(escrow_did=escrow.did), LocalArtifacts()
    inbound = [
        relay(escrow, seller_did, service_request(buyer, escrow.did)),
        terms_proposed(escrow, seller_did),
        funding_confirmed(escrow, seller_did),
        decision(escrow, seller_did, "reject", attempts_left=1, attempt=1),
        decision(escrow, seller_did, "approve", attempts_left=0, attempt=2),
    ]

    for envelope in inbound:
        output = invoke(
            "handle_message",
            {"envelope": envelope},
            modules,
            artifacts,
            f"msg:{envelope['message_id']}",
        )
        assert output == {"status": "processed", "reason": None}

    quote, accept, first, second = modules.sent()
    assert [item["type_key"] for item in (quote, accept, first, second)] == [
        "finance.quote",
        "finance.accept_terms",
        "finance.delivery",
        "finance.delivery",
    ]
    for reply, cause in zip(modules.sent(), inbound, strict=False):
        assert verify_envelope(reply)
        assert reply["sender_did"] == seller_did
        assert reply["recipient_did"] == escrow.did
        assert reply["conversation_id"] == DEAL_ID
        assert reply["causation_id"] == cause["message_id"]
    assert quote["body"]["price_minor"] == 50000
    assert (first["body"]["attempt"], second["body"]["attempt"]) == (1, 2)
    names = []
    for delivery in (first, second):
        artifact = delivery["body"]["artifact"]
        data = artifacts.get(artifact["artifact_id"])
        assert artifact["sha256"] == hashlib.sha256(data).hexdigest()
        assert artifact["byte_length"] == len(data)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names.append(archive.namelist())
    assert names == [["report.md", "data.csv"], REQUIRED_FILES]


def test_handle_message_action_rejects_a_message_not_from_escrow(
    key_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    escrow, stranger = AgentKey.generate(), AgentKey.generate()
    monkeypatch.setenv("ESCROW_DID", escrow.did)
    modules = FakeModules()
    envelope = funding_confirmed(stranger, AgentKey.generate().did)

    output = invoke("handle_message", {"envelope": envelope}, modules, LocalArtifacts())

    assert output == {"status": "rejected", "reason": "unexpected_sender"}
    assert modules.queries == []
    assert modules.sent() == []


def test_packaged_offers_match_the_demo_data() -> None:
    source = ROOT.parents[1] / "data" / "demo" / "offers.seller-co.yaml"
    if not source.is_file():
        pytest.skip("the repository's demo data is not next to this project")
    packaged = resources.files("seller_agent").joinpath("data", "offers.seller-co.yaml")
    assert packaged.read_text(encoding="utf-8") == source.read_text(encoding="utf-8")
