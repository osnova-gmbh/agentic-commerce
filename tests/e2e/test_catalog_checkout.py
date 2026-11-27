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
    assert {row["offer_id"]: row["price_minor"] for row in services if not row.get("provider_demo")} == {"offer-1": 50000, "ai-training": 120000}
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
    other = checkout.prepare("seller-co", "ai-training", {"topic": "AI", "audience": "Team"}, "other", background=False)
    checkout.run_phase({"QUOTED"})
    assert other["deal_id"] != first["deal_id"]
    assert checkout.status(first["deal_id"])["state"] == "QUOTED"


@pytest.mark.parametrize(("company", "offer", "amount"), [
    ("elephant-technologies", "ai-coursebuilder", 180000),
    ("base-baselinker", "base-enterprise", 50000),
    ("bonanza-studios", "context-engineering-claude-code", 10000),
])
def test_provider_selection_runs_its_own_escrow_and_delivery(checkout, company, offer, amount):
    client = TestClient(create_checkout_app(checkout))
    services = client.get("/api/demo/services").json()["services"]
    providers = [service for service in services if service.get("provider_demo")]
    assert len(providers) == 26
    assert len({service["provider_company_id"] for service in providers}) == 10
    service = next(row for row in providers if row["provider_company_id"] == company and row["provider_offer_id"] == offer)
    company_before = next(row for row in checkout.source.companies() if row["org_id"] == company)
    accounts_before = checkout.bank.accounts()
    selected = checkout.prepare(service["seller_org_id"], service["offer_id"],
                                {"brief": "Evaluate this exact product for the sales team"},
                                "provider-select", demo_price_minor=amount, background=False)
    checkout.run_phase({"QUOTED"})
    deal_id = selected["deal_id"]
    assert checkout.status()["error"] is None
    assert checkout.status()["state"] == "QUOTED"
    assert checkout.status()["terms"]["offer_id"] == service["offer_id"]
    assert checkout.status()["terms"]["price_minor"] == amount
    assert checkout.status()["order"]["service"]["provider_company_id"] == company
    assert checkout.status()["order"]["service"]["provider_offer_id"] == offer
    assert checkout.bank.accounts() == accounts_before
    assert client.get(f"/api/deals/{deal_id}").json()["deal"]["offer_title"] == service["title"]
    advance(checkout, deal_id, "fund", {"FUNDED"})
    assert checkout.source.balances(deal_id)["held"] == amount
    advance(checkout, deal_id, "deliver", {"APPROVED", "REJECTED"})
    assert checkout.status()["state"] == "APPROVED"
    assert checkout.source.balances(deal_id)["held"] == amount
    with zipfile.ZipFile(io.BytesIO(client.get(f"/api/demo/deals/{deal_id}/delivery").content)) as archive:
        assert set(archive.namelist()) == {"delivery.md", "license.json", "summary.json"}
        manifest = json.loads(archive.read("summary.json"))
        assert manifest["provider_company_id"] == company
        assert manifest["offer_id"] == offer
        assert manifest["product"] == service["title"]
        assert manifest["simulated"] is True
        assert "Evaluate this exact product" in archive.read("delivery.md").decode()
    advance(checkout, deal_id, "release", {"SETTLED"})
    assert checkout.source.balances(deal_id)["held"] == 0
    assert next(row for row in checkout.source.companies() if row["org_id"] == company) == company_before
    assert company_before["kyb_verified"] is False
    assert "seller" not in company_before["roles"]


def test_provider_demo_amounts_are_validated_without_overwriting_public_prices(checkout):
    client = TestClient(create_checkout_app(checkout))
    providers = [row for row in checkout.services() if row.get("provider_demo")]
    quote = next(row for row in providers if row["provider_company_id"] == "base-baselinker")
    assert quote["published_price_minor"] is None and quote["price_minor"] is None
    assert quote["requires_demo_amount"] is True
    free = next(row for row in providers if row["provider_company_id"] == "bonanza-studios" and row["provider_offer_id"] == "context-engineering-claude-code")
    assert free["published_price_minor"] == 0 and free["requires_demo_amount"] is True
    expensive = next(row for row in providers if row["provider_offer_id"] == "content-hub")
    assert expensive["published_price_minor"] == 500000
    assert expensive["suggested_demo_price_minor"] == 50000
    body = {"seller_org_id": quote["seller_org_id"], "offer_id": quote["offer_id"], "inputs": {"brief": "Trial"}}
    for invalid in [None, 0, -1, True, 12.5, 200001]:
        submitted = body if invalid is None else {**body, "demo_price_minor": invalid}
        response = client.post("/api/demo/orders", json=submitted, headers={"Idempotency-Key": f"invalid-{invalid}"})
        assert response.status_code == 422, response.text
    assert checkout.source.deals() == []


def test_two_provider_checkouts_keep_their_own_price_messages_and_actions(checkout):
    """Switching offers must neither block nor silently advance another order."""
    client = TestClient(create_checkout_app(checkout))
    offer_id = "provider:elephant-technologies:sop-builder"
    before = checkout.bank.accounts()
    first = checkout.prepare("seller-co", offer_id, {"brief": "First SOP"}, "first",
                             demo_price_minor=10000, background=False)["deal_id"]
    # A worker still serializes mutations until this phase reaches its pause.
    with pytest.raises(RuntimeError, match="still processing"):
        checkout.prepare("seller-co", offer_id, {"brief": "Second SOP"}, "second",
                         demo_price_minor=20000, background=False)
    checkout.run_phase({"QUOTED"})
    second = checkout.prepare("seller-co", offer_id, {"brief": "Second SOP"}, "second",
                              demo_price_minor=20000, background=False)["deal_id"]
    assert checkout.status(first)["running"] is False
    assert checkout.status(first)["server_busy"] is True
    assert checkout.status(first)["active_deal_id"] == second
    checkout.run_phase({"QUOTED"})
    assert checkout.bank.accounts() == before
    assert checkout.status(first)["state"] == checkout.status(second)["state"] == "QUOTED"
    assert client.get("/api/demo/status").json()["deal_id"] == second
    first_status = client.get(f"/api/demo/orders/{first}").json()
    assert first_status["order"]["inputs"] == {"brief": "First SOP"}
    assert first_status["allowed_actions"] == ["fund"]
    assert client.get("/api/demo/orders/missing").status_code == 404

    advance(checkout, first, "fund", {"FUNDED"}, key="fund-first")
    assert checkout.status(second)["state"] == "QUOTED"
    advance(checkout, second, "fund", {"FUNDED"}, key="fund-second")
    assert checkout.status(first)["state"] == "FUNDED"
    assert checkout.source.deal(first)["deliveries"] == []
    assert checkout.source.deal(second)["deliveries"] == []
    assert checkout.status(first)["terms"]["price_minor"] == 10000
    assert checkout.status(second)["terms"]["price_minor"] == 20000

    advance(checkout, first, "deliver", {"REJECTED"}, scenario="rework", key="bad-first")
    assert checkout.status(first)["allowed_actions"] == ["deliver"]
    assert checkout.status(second)["state"] == "FUNDED"
    advance(checkout, second, "deliver", {"APPROVED"}, key="deliver-second")
    assert checkout.status(first)["state"] == "REJECTED"
    with pytest.raises(RuntimeError, match="Cannot release"):
        checkout.advance(first, "release", "reject-release")
    advance(checkout, first, "deliver", {"APPROVED"}, scenario="rework", key="fix-first")
    assert checkout.source.balances(first)["held"] == 10000
    assert checkout.source.balances(second)["held"] == 20000

    advance(checkout, second, "release", {"SETTLED"}, key="release-second")
    assert checkout.status(first)["state"] == "APPROVED"
    assert checkout.source.balances(first)["held"] == 10000
    advance(checkout, first, "release", {"SETTLED"}, key="release-first")
    assert checkout.source.balances(first)["seller"] == 9900
    assert checkout.source.balances(second)["seller"] == 19800
    for deal_id, brief in [(first, "First SOP"), (second, "Second SOP")]:
        delivery = client.get(f"/api/demo/deals/{deal_id}/delivery")
        with zipfile.ZipFile(io.BytesIO(delivery.content)) as archive:
            assert json.loads(archive.read("summary.json"))["brief"] == brief


def test_evaluator_failure_stays_on_its_order_while_another_order_can_finish(checkout, monkeypatch):
    first = checkout.prepare("seller-co", "offer-1", {"topic": "First report"}, "first", background=False)["deal_id"]
    checkout.run_phase({"QUOTED"})
    advance(checkout, first, "fund", {"FUNDED"}, key="first-fund")
    second = checkout.prepare("seller-co", "ai-training", {"topic": "AI", "audience": "Team"},
                              "second", background=False)["deal_id"]
    checkout.run_phase({"QUOTED"})
    evaluator = checkout.bus.runtime.agents["evaluator-agent"]
    original = evaluator.handle_message

    def unavailable(envelope):
        if envelope["conversation_id"] == first:
            raise RuntimeError("Evaluator unavailable for first order")
        return original(envelope)

    monkeypatch.setattr(evaluator, "handle_message", unavailable)
    checkout.advance(first, "deliver", "first-deliver", background=False)
    checkout.run_phase({"APPROVED", "REJECTED"})
    assert "Evaluator unavailable" in checkout.status(first)["error"]
    assert checkout.status(first)["running"] is False
    assert checkout.status(second)["error"] is None
    assert checkout.status(second)["allowed_actions"] == ["fund"]
    advance(checkout, second, "fund", {"FUNDED"}, key="second-fund")
    advance(checkout, second, "deliver", {"APPROVED"}, key="second-deliver")
    advance(checkout, second, "release", {"SETTLED"}, key="second-release")
    assert checkout.source.balances(first)["held"] == 50000
    assert "Evaluator unavailable" in checkout.status(first)["error"]


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
