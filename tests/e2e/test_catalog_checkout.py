import io
import json
import zipfile
from pathlib import Path

import pytest
from cogit_finance_seams import SimBankClient
from dashboard.checkout import CatalogDemoEngine, create_checkout_app
from fastapi.testclient import TestClient
from sim_bank import create_app

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def checkout():
    with TestClient(create_app()) as bank:
        engine = CatalogDemoEngine(ROOT, bank=SimBankClient(bank), step_delay=0)
        yield engine
        engine.close()


def advance(engine, deal_id, action, target, *, scenario="happy", key=None):
    engine.advance(deal_id, action, key or action, scenario=scenario, background=False)
    engine.run_phase(set(target))
    assert engine.status()["error"] is None


@pytest.mark.parametrize(("offer_id", "inputs", "price", "files"), [
    ("offer-1", {"topic": "The European cake market"}, 50000, {"report.md", "data.csv", "summary.json"}),
    ("ai-training", {"topic": "AI for sales", "audience": "Account managers"}, 120000, {"course.md", "exercises.md", "summary.json"}),
])
def test_selected_service_is_quoted_funded_delivered_and_released_separately(checkout, offer_id, inputs, price, files):
    before = checkout.bank.accounts()
    selected = checkout.prepare("seller-co", offer_id, inputs, "select", background=False)
    checkout.run_phase({"QUOTED"})
    deal_id = selected["deal_id"]
    assert checkout.status()["state"] == "QUOTED"
    assert checkout.status()["terms"]["offer_id"] == offer_id
    assert checkout.status()["terms"]["inputs"] == inputs
    assert checkout.status()["terms"]["price_minor"] == price
    assert checkout.bank.accounts() == before
    with pytest.raises(RuntimeError):
        checkout.advance(deal_id, "deliver", "too-early")
    with pytest.raises(RuntimeError):
        checkout.advance(deal_id, "release", "too-early")

    advance(checkout, deal_id, "fund", {"FUNDED"})
    held = checkout.source.balances(deal_id)
    assert held["held"] == price and held["seller"] == held["fee"] == 0
    assert checkout.source.deal(deal_id)["deliveries"] == []
    funded_accounts = checkout.bank.accounts()
    checkout.advance(deal_id, "fund", "fund")  # same request never pays twice
    assert checkout.bank.accounts() == funded_accounts

    advance(checkout, deal_id, "deliver", {"APPROVED", "REJECTED"})
    assert checkout.status()["state"] == "APPROVED"
    assert checkout.bank.accounts() == funded_accounts
    assert checkout.source.balances(deal_id)["held"] == price
    client = TestClient(create_checkout_app(checkout))
    delivery = client.get(f"/api/demo/deals/{deal_id}/delivery")
    with zipfile.ZipFile(io.BytesIO(delivery.content)) as archive:
        assert set(archive.namelist()) == files
        primary = "course.md" if offer_id == "ai-training" else "report.md"
        assert inputs["topic"] in archive.read(primary).decode()

    advance(checkout, deal_id, "release", {"SETTLED"})
    balances = checkout.source.balances(deal_id)
    assert balances["held"] == 0 and balances["seller"] + balances["fee"] == price
    assert balances["fee"] == price // 100
    settled = checkout.bank.accounts()
    checkout.advance(deal_id, "release", "release")
    assert checkout.bank.accounts() == settled
    assert len(checkout.source.deal(deal_id)["events"]) == 17
    assert client.get(f"/api/deals/{deal_id}").json()["deal"]["offer_title"] == checkout.status()["order"]["service"]["title"]


def test_rejected_delivery_needs_a_separate_retry_and_cannot_release_funds(checkout):
    result = checkout.prepare("seller-co", "ai-training", {"topic": "AI", "audience": "Operations"}, "select", background=False)
    checkout.run_phase({"QUOTED"})
    deal_id = result["deal_id"]
    advance(checkout, deal_id, "fund", {"FUNDED"})
    advance(checkout, deal_id, "deliver", {"APPROVED", "REJECTED"}, scenario="rework", key="first-delivery")
    assert checkout.status()["state"] == "REJECTED"
    assert checkout.source.balances(deal_id)["held"] == 120000
    assert checkout.status()["allowed_actions"] == ["deliver"]
    with pytest.raises(RuntimeError):
        checkout.advance(deal_id, "release", "bad-release")
    advance(checkout, deal_id, "deliver", {"APPROVED", "REJECTED"}, scenario="rework", key="corrected-delivery")
    assert checkout.status()["state"] == "APPROVED"
    advance(checkout, deal_id, "release", {"SETTLED"})
    assert len(checkout.source.deal(deal_id)["events"]) == 22
    assert checkout.source.balances(deal_id)["seller"] == 118800


def test_catalog_request_validation_and_idempotency(checkout):
    client = TestClient(create_checkout_app(checkout))
    services = client.get("/api/demo/services").json()["services"]
    assert {row["offer_id"]: row["price_minor"] for row in services} == {"offer-1": 50000, "ai-training": 120000}
    assert all(row["demo"] for row in services)
    headers = {"Idempotency-Key": "validation"}
    assert client.post("/api/demo/orders", json={}, headers=headers).status_code == 422
    body = {"seller_org_id": "seller-co", "offer_id": "ai-training", "inputs": {"topic": "AI"}}
    assert client.post("/api/demo/orders", json=body, headers=headers).status_code == 422
    assert client.post("/api/demo/orders", json={**body, "price_minor": 1}, headers=headers).status_code == 422
    assert checkout.source.deals() == []
    first = checkout.prepare("seller-co", "offer-1", {"topic": "Research"}, "same", background=False)
    repeat = checkout.prepare("seller-co", "offer-1", {"topic": "Research"}, "same", background=False)
    assert repeat == first
    with pytest.raises(ValueError):
        checkout.prepare("seller-co", "offer-1", {"topic": "Changed"}, "same", background=False)
    checkout.run_phase({"QUOTED"})
    with pytest.raises(RuntimeError):
        checkout.prepare("seller-co", "ai-training", {"topic": "AI", "audience": "Team"}, "other")


def test_saved_history_stays_visible_after_restart(tmp_path):
    saved = json.loads((ROOT / "apps/dashboard/fixtures/happy/deals.json").read_text())
    deal_id = saved["deals"][0]["deal_id"]
    from dashboard import FixtureSource
    from dashboard.view import deal_view
    source = FixtureSource(ROOT / "apps/dashboard/fixtures/happy")
    view = deal_view(source.deal(deal_id), source.balances(deal_id))
    history = tmp_path / "history.json"
    history.write_text(json.dumps({"views": {deal_id: view}}))
    with TestClient(create_app()) as bank:
        engine = CatalogDemoEngine(ROOT, bank=SimBankClient(bank), history_file=history)
        client = TestClient(create_checkout_app(engine))
        assert client.get("/api/deals").json()["deals"][0]["deal_id"] == deal_id
        assert client.get(f"/api/deals/{deal_id}").json()["timeline"] == view["timeline"]
        engine.close()
