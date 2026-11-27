"""The reusable demo budget must not reset payments, receipts or escrow funds."""

from datetime import timedelta
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from cogit_finance_seams import BankError, SimBankClient
from dashboard.boris import BorisConnectionError, BorisGateway
from dashboard.checkout import CatalogDemoEngine
from dashboard.demo_bank import DemoFundingBank
from sim_bank import create_app
from sim_bank.ledger import DEFAULT_SEED

ROOT = Path(__file__).resolve().parents[2]
BUYER = "DE00EXAMPLE0000000010"
SELLER = "DE00EXAMPLE0000000020"
ESCROW = "DE00EXAMPLE0000000001"
FEES = "DE00EXAMPLE0000000002"


def funder(http, calls):
    def fund(**request):
        calls.append(request)
        key = request.pop("idempotency_key")
        response = http.post("/admin/fund", json=request, headers={"Idempotency-Key": key})
        assert response.status_code == 200, response.text
        return response.json()
    return fund


def quote(engine, key, offer="ai-training"):
    inputs = {"topic": "Reusable demo funds", "audience": "Operators"} if offer == "ai-training" else {"topic": "Funding recovery"}
    result = engine.prepare("seller-co", offer, inputs, key, background=False)
    engine.run_phase({"QUOTED"})
    assert engine.status()["state"] == "QUOTED", engine.status()["error"]
    return result["deal_id"]


def advance(engine, deal, action, expected):
    engine.advance(deal, action, f"{action}:{deal}", background=False)
    engine.run_phase({expected})
    assert engine.status()["state"] == expected, engine.status()["error"]
    assert engine.status()["error"] is None


def low_budget_seed(tmp_path, *, buyer=100, seller=0, held=0, fees=0):
    seed = yaml.safe_load(DEFAULT_SEED.read_text())
    amounts = {BUYER: buyer, SELLER: seller, ESCROW: held, FEES: fees}
    for row in seed["accounts"]:
        row["balance_minor"] = amounts[row["iban"]]
    path = tmp_path / "bank.yaml"
    path.write_text(yaml.safe_dump(seed))
    return path


def test_repeated_boris_checkouts_refill_budget_without_losing_history():
    calls, exchanges = [], []
    def echo(agent, payload, request_id):
        exchanges.append((agent, payload))
        return payload
    gateway = BorisGateway("https://example.test/echo", echo, transport_kind="test")
    with TestClient(create_app()) as http:
        bank = DemoFundingBank(SimBankClient(http), funder(http, calls))
        engine = CatalogDemoEngine(ROOT, bank=bank, step_delay=0, boris=gateway)
        try:
            deals = []
            for index in range(9):
                deal = quote(engine, f"training:{index}")
                deals.append(deal)
                advance(engine, deal, "fund", "FUNDED")
                advance(engine, deal, "deliver", "APPROVED")
                advance(engine, deal, "release", "SETTLED")
            assert len(calls) == 1
            assert calls[0]["iban"] == BUYER
            assert calls[0]["minimum_balance_minor"] == 1_000_000
            assert len(engine.source.deals()) == 9
            assert all(engine.source.deal(deal)["deal"]["state"] == "SETTLED" for deal in deals)
            assert all(bank.lookup("pay:" + deal)["amount_minor"] == 120000 for deal in deals)
            assert len(bank.credits(ESCROW)) == 9
            assert {agent for agent, _ in exchanges} == {"buyer-agent", "seller-agent", "cogit-finance"}
            assert {row["iban"]: row["balance_minor"] for row in bank.accounts()}[ESCROW] == 0
            before = bank.accounts()
            payment = bank.lookup("pay:" + deals[0])
            bank.transfer(**{name: payment[name] for name in ("from_iban", "to_iban", "amount_minor", "currency", "reference", "idempotency_key")})
            assert bank.accounts() == before and len(calls) == 1
        finally:
            engine.close()


def test_failed_funding_can_be_retried_after_refill_without_duplicate_payment(tmp_path):
    calls = []
    enabled = False
    with TestClient(create_app(low_budget_seed(tmp_path))) as http:
        real_fund = funder(http, calls)
        def funding(**request):
            return real_fund(**request) if enabled else {}
        bank = DemoFundingBank(SimBankClient(http), funding)
        engine = CatalogDemoEngine(ROOT, bank=bank, step_delay=0)
        try:
            deal = quote(engine, "failed-first", "offer-1")
            engine.advance(deal, "fund", "first-fund", background=False)
            engine.run_phase({"FUNDED"})
            assert engine.status()["state"] == "FUNDING_REQUESTED"
            assert "insufficient_funds" in engine.status()["error"]
            assert bank.lookup("pay:" + deal) is None
            enabled = True
            later = engine.bus.host.clock() + timedelta(seconds=2)
            engine.bus.host.clock = lambda: later
            advance(engine, deal, "fund", "FUNDED")
            advance(engine, deal, "deliver", "APPROVED")
            advance(engine, deal, "release", "SETTLED")
            assert len(bank.credits(ESCROW)) == 1
            assert len(calls) == 1
            before = bank.accounts()
            engine.advance(deal, "fund", "fund:" + deal, background=False)
            assert bank.accounts() == before
        finally:
            engine.close()


def test_legacy_refill_recycles_only_settled_accounts_and_is_idempotent(tmp_path):
    def unavailable(**_):
        raise BankError(404, "not_found")
    with TestClient(create_app(low_budget_seed(tmp_path, seller=700000, held=230000, fees=7000))) as http:
        bank = DemoFundingBank(SimBankClient(http), unavailable)
        result = bank.transfer(from_iban=BUYER, to_iban=ESCROW, amount_minor=180000,
                               currency="EUR", reference="DEMO-PAYMENT", idempotency_key="pay:legacy")
        balances = {row["iban"]: row["balance_minor"] for row in bank.accounts()}
        assert balances[ESCROW] == 410000
        assert balances[BUYER] == 527100
        assert bank.lookup("demo-refill:pay:legacy:" + SELLER)["reference"] == "DEMO-REFILL/pay:legacy"
        assert bank.transfer(from_iban=BUYER, to_iban=ESCROW, amount_minor=180000,
                             currency="EUR", reference="DEMO-PAYMENT", idempotency_key="pay:legacy") == result
        assert {row["iban"]: row["balance_minor"] for row in bank.accounts()} == balances


def test_boris_rejection_cannot_trigger_demo_refill(tmp_path):
    calls = []
    def echo(agent, payload, request_id):
        if payload.get("action") == "bank_transfer":
            raise BorisConnectionError("Boris unavailable")
        return payload
    gateway = BorisGateway("https://example.test/echo", echo, transport_kind="test")
    with TestClient(create_app(low_budget_seed(tmp_path))) as http:
        bank = DemoFundingBank(SimBankClient(http), funder(http, calls))
        engine = CatalogDemoEngine(ROOT, bank=bank, step_delay=0, boris=gateway)
        try:
            deal = quote(engine, "gate", "offer-1")
            before = bank.accounts()
            engine.advance(deal, "fund", "blocked", background=False)
            engine.run_phase({"FUNDED"})
            assert engine.status()["error"]
            assert bank.accounts() == before
            assert calls == []
        finally:
            engine.close()


def test_legacy_refill_does_not_borrow_another_deals_escrow(tmp_path):
    def unavailable(**_):
        raise BankError(404, "not_found")
    with TestClient(create_app(low_budget_seed(tmp_path, held=230000))) as http:
        bank = DemoFundingBank(SimBankClient(http), unavailable)
        before = bank.accounts()
        with pytest.raises(BankError, match="insufficient_funds"):
            bank.transfer(from_iban=BUYER, to_iban=ESCROW, amount_minor=180000,
                          currency="EUR", reference="DEMO-PAYMENT", idempotency_key="pay:no-reserve")
        assert bank.accounts() == before


def test_refill_is_never_enabled_for_nonlocal_bank():
    with pytest.raises(ValueError, match="loopback"):
        DemoFundingBank.from_url("https://bank.example/api")
