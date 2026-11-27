import io
import zipfile
from pathlib import Path

import pytest
from cogit_finance_seams import SimBankClient
from cogit_messaging_shim import ZERO_HASH, event_hash, verify_envelope
from dashboard.demo import DemoEngine, create_demo_app
from fastapi.testclient import TestClient
from sim_bank import create_app as create_bank_app

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def engine():
    with TestClient(create_bank_app()) as bank_http:
        demo = DemoEngine(ROOT, bank=SimBankClient(bank_http), step_delay=0)
        yield demo
        demo.close()


def run_purchase(engine, scenario, key):
    result = engine.start(scenario, key, background=False)
    engine.run()
    assert engine.status()["error"] is None
    assert engine.status()["state"] == "SETTLED"
    return result["deal_id"]


@pytest.mark.parametrize(("scenario", "event_count", "attempts"), [("happy", 17, 1), ("rework", 22, 2)])
def test_signed_agent_transaction_settles_with_correct_bank_balances(engine, scenario, event_count, attempts):
    deal_id = run_purchase(engine, scenario, f"purchase:{scenario}")
    read = engine.source.deal(deal_id)
    assert len(read["events"]) == event_count
    assert len(read["deliveries"]) == attempts
    assert engine.source.balances(deal_id) == {
        "held": 0, "seller": 49500, "fee": 500, "buyer_refund": 0, "returned": 0,
    }
    balances = {a["owner"]: a["balance_minor"] for a in engine.bank.accounts()}
    assert balances == {"escrow held": 0, "escrow fees": 500, "buyer-co": 950000, "seller-co": 49500}
    assert sum(balances.values()) == 1000000
    previous = ZERO_HASH
    for event in read["events"]:
        assert event["prev_hash"] == previous
        assert event["hash"] == event_hash(event)
        previous = event["hash"]
        envelope = event["body"].get("envelope")
        if envelope:
            assert verify_envelope(envelope)
    assert read["deal"]["head_hash"] == previous
    if scenario == "rework":
        assert any(event["state_after"] == "REJECTED" for event in read["events"])
        assert any(row["evaluator_id"] == "required-files" and row["outcome"] == "fail" for row in read["evaluations"])


def test_repeated_request_does_not_create_or_pay_twice(engine):
    deal_id = run_purchase(engine, "happy", "repeat-this-request")
    balances = engine.bank.accounts()
    assert engine.start("happy", "repeat-this-request")["deal_id"] == deal_id
    assert len(engine.source.deals()) == 1
    assert engine.bank.accounts() == balances
    with pytest.raises(ValueError):
        engine.start("rework", "repeat-this-request")


def test_cannot_start_a_second_purchase_until_the_first_finishes(engine):
    engine.start("happy", "first", background=False)
    with pytest.raises(RuntimeError, match="already running"):
        engine.start("happy", "second", background=False)
    engine.run()
    second = run_purchase(engine, "rework", "second")
    assert engine.source.deal(second)["deal"]["state"] == "SETTLED"
    assert len(engine.source.deals()) == 2
    assert {a["owner"]: a["balance_minor"] for a in engine.bank.accounts()} == {
        "escrow held": 0, "escrow fees": 1000, "buyer-co": 900000, "seller-co": 99000,
    }


def test_demo_api_and_real_deliverable_download(engine):
    client = TestClient(create_demo_app(engine))
    assert client.get("/demo").status_code == 200
    assert client.post("/api/demo/purchases", json={"scenario": "happy"}).status_code == 422
    assert client.post("/api/demo/purchases", headers={"Idempotency-Key": "invalid"}, json={"scenario": "other"}).status_code == 422
    deal_id = run_purchase(engine, "happy", "download")
    retry = client.post("/api/demo/purchases", headers={"Idempotency-Key": "download"}, json={"scenario": "happy"})
    assert retry.status_code == 202 and retry.json()["deal_id"] == deal_id
    response = client.get(f"/api/demo/deals/{deal_id}/delivery")
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as report:
        assert set(report.namelist()) == {"report.md", "data.csv", "summary.json"}
    assert client.get("/api/demo/deals/missing/delivery").status_code == 404
    assert client.get(f"/api/deals/{deal_id}").json()["deal"]["state"] == "SETTLED"


def test_delta_campus_prospects_are_in_the_catalog_and_browsable(engine):
    client = TestClient(create_demo_app(engine))
    response = client.get("/api/catalog")
    assert response.status_code == 200
    prospects = [row for row in response.json()["companies"] if row["status"] == "prospective_buyer"]
    assert [row["name"] for row in prospects] == [
        "Elephant Technologies", "Base / BaseLinker", "MeinGPT / SelectCode",
        "Kenjo", "FORMATION", "Nala Earth", "Tilla", "dealspec", "Overfly", "Bonanza Studios",
    ]
    assert [row["outreach_priority"] for row in prospects] == list(range(1, 11))
    assert [row["recommended"] for row in prospects] == [True] * 3 + [False] * 7
    for row in prospects:
        assert row["roles"] == ["buyer"]
        assert row["website"].startswith("https://")
        assert row["products_and_services"] and row["target_customers"]
        assert "iban" not in row and "register_id" not in row and "spending_limit_minor" not in row
        stored = engine.bus.host.port("dashboard", "operator_ro").module_query(
            "cogit-finance-catalog", "company.read", {"org_id": row["org_id"]}
        )["company"]
        assert not stored["kyb_verified"] and stored["iban"] is None
        assert stored["spending_limit_minor"] == 0
    assert client.get("/catalog").status_code == 200
    assert client.get("/static/catalog.js").status_code == 200
    assert client.get("/static/catalog.css").status_code == 200
    assert engine.source.deals() == []
