import json
import os
import socket
import subprocess
import sys
import time

import httpx
import pytest
from dashboard import FixtureSource, ModuleSource, create_app, dump_source
from dashboard_helpers import FIXTURES, fixture_deal_id, fixture_read, statuses
from fastapi.testclient import TestClient

MODULE = "cogit-finance-deals"


class FakeModules:
    """A tiny ModulePort: answers the three deals queries and refuses every command."""

    def __init__(self, read: dict) -> None:
        self.read = read
        self.queries: list[tuple[str, str, dict]] = []

    def module_query(self, module: str, export: str, args: dict | None = None) -> dict:
        self.queries.append((module, export, dict(args or {})))
        assert module == MODULE
        deal = self.read["deal"]
        if export == "deal.list":
            row = {name: deal[name] for name in ("deal_id", "state", "buyer_org_id", "seller_org_id", "offer_id",
                                                 "head_seq", "created_at", "updated_at")}  # fmt: skip
            return {"deals": [{**row, "price_minor": deal["terms"]["price_minor"], "currency": "EUR"}]}
        if export == "deal.read":
            if args == {"deal_id": deal["deal_id"]}:
                return self.read
            return {"deal": None, "events": [], "deliveries": [], "evaluations": [], "intents": [], "credits": []}
        if export == "ledger.balances":
            return {"held": 0, "seller": 49500, "fee": 500, "buyer_refund": 0, "returned": 0}
        raise AssertionError(f"unexpected query {export}")

    def module_command(self, module: str, export: str, args: dict | None = None, *, idempotency_key: str) -> dict:
        raise AssertionError("the dashboard must never send a command")


class FakeBank:
    def accounts(self) -> list[dict]:
        return [{"iban": "DE00EXAMPLE0000000001", "owner": "escrow held", "balance_minor": 0}]

    def __getattr__(self, name: str):
        raise AssertionError(f"the dashboard must not call bank.{name}")


@pytest.fixture()
def modules() -> FakeModules:
    return FakeModules(fixture_read("happy"))


def test_module_source_calls_the_three_queries(modules):
    source = ModuleSource(modules, FakeBank())
    deal_id = modules.read["deal"]["deal_id"]
    assert [row["deal_id"] for row in source.deals()] == [deal_id]
    assert source.deal(deal_id) == modules.read
    assert source.deal("other")["deal"] is None
    assert source.balances()["seller"] == 49500 and source.balances(deal_id)["fee"] == 500
    assert source.accounts() == FakeBank().accounts()
    assert modules.queries == [
        (MODULE, "deal.list", {}),
        (MODULE, "deal.read", {"deal_id": deal_id}),
        (MODULE, "deal.read", {"deal_id": "other"}),
        (MODULE, "ledger.balances", {}),
        (MODULE, "ledger.balances", {"deal_id": deal_id}),
    ]


def test_module_source_without_a_bank_has_no_accounts(modules):
    assert ModuleSource(modules).accounts() == []
    assert ModuleSource(modules, None).accounts() == []


def test_the_app_on_a_module_source_only_queries(modules):
    http = TestClient(create_app(ModuleSource(modules, FakeBank())))
    deal_id = modules.read["deal"]["deal_id"]
    assert http.get("/api/deals").json()["deals"][0]["price"] == "EUR 500.00"
    body = http.get(f"/api/deals/{deal_id}").json()
    assert statuses(body["steps"]) == "DDDDDDDDDD" and body["money"]["phase"] == "released"
    assert http.get("/api/deals/other").status_code == 404
    assert http.get(f"/api/balances?deal_id={deal_id}").json()["balances"]["seller"] == 49500
    assert http.get("/api/accounts").json()["accounts"][0]["balance"] == "EUR 0.00"
    assert {export for _, export, _ in modules.queries} == {"deal.list", "deal.read", "ledger.balances"}


def test_fixture_source_returns_the_files_and_reads_them_again(tmp_path):
    dump_source(FixtureSource(FIXTURES / "happy"), tmp_path)
    source = FixtureSource(tmp_path)
    deal_id = fixture_deal_id("happy")
    assert source.deals() == json.loads((FIXTURES / "happy" / "deals.json").read_text())["deals"]
    assert source.deal(deal_id) == fixture_read("happy")
    assert source.balances() == source.balances(deal_id) == json.loads((FIXTURES / "happy" / "balances.json").read_text())
    assert len(source.accounts()) == 4
    (tmp_path / "balances.json").write_text(json.dumps({"held": 7, "seller": 0, "fee": 0, "buyer_refund": 0, "returned": 0}))
    assert source.balances()["held"] == 7  # a new dump shows up without a restart


def test_fixture_source_handles_what_is_not_there(tmp_path):
    with pytest.raises(FileNotFoundError):
        FixtureSource(tmp_path)
    (tmp_path / "deals.json").write_text('{"deals": []}')
    source = FixtureSource(tmp_path)
    assert source.deals() == [] and source.accounts() == []
    for deal_id in ("unknown", "../deals", "..", ""):
        assert source.deal(deal_id) == {
            "deal": None, "events": [], "deliveries": [], "evaluations": [], "intents": [], "credits": [],
        }  # fmt: skip
        assert set(source.balances(deal_id).values()) == {0}
    assert source.balances() == {"held": 0, "seller": 0, "fee": 0, "buyer_refund": 0, "returned": 0}


def test_python_m_dashboard_serves_a_fixture_set():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    env = {**os.environ, "DASHBOARD_PORT": str(port), "DASHBOARD_LOG_LEVEL": "warning"}
    command = [sys.executable, "-m", "dashboard", "--fixtures", str(FIXTURES / "broken")]
    process = subprocess.Popen(command, env=env)
    try:
        deadline = time.monotonic() + 20
        while True:
            try:
                deals = httpx.get(f"http://127.0.0.1:{port}/api/deals", timeout=2).json()["deals"]
                break
            except httpx.TransportError:
                assert process.poll() is None and time.monotonic() < deadline, "the dashboard did not start"
                time.sleep(0.1)
        assert [deal["deal_id"] for deal in deals] == [fixture_deal_id("broken")]
        assert "Escrow deals" in httpx.get(f"http://127.0.0.1:{port}/", timeout=2).text
    finally:
        process.terminate()
        process.wait(timeout=10)
