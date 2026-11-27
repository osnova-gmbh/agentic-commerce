"""The bank through ``SimBankClient``, the client the agents use."""

import os
import socket
import subprocess
import sys
import threading
import time

import httpx
import pytest
from cogit_finance_seams import BankError, SimBankClient
from fastapi.testclient import TestClient
from sim_bank import Ledger, create_app
from sim_bank_helpers import BUYER, ESCROW, FEES, SELLER

DEAL = "0b0e7f0c-3d0a-4f0e-9d53-5f0f6c1d2a01"


@pytest.fixture()
def bank() -> SimBankClient:
    return SimBankClient(TestClient(create_app()))


def pay(bank: SimBankClient, **changes) -> dict:
    args = {
        "from_iban": BUYER,
        "to_iban": ESCROW,
        "amount_minor": 50000,
        "currency": "EUR",
        "reference": f"ESCROW-{DEAL}",
        "idempotency_key": f"pay:{DEAL}",
    }
    args.update(changes)
    return bank.transfer(**args)


def balances(bank: SimBankClient) -> dict:
    return {account["iban"]: account["balance_minor"] for account in bank.accounts()}


def test_one_deal_from_funding_to_payout(bank):
    funding = pay(bank)
    assert funding["status"] == "booked" and funding["idempotency_key"] == f"pay:{DEAL}"
    credits = bank.credits(ESCROW)
    assert [(c["event_id"], c["amount_minor"], c["reference"]) for c in credits] == [("1", 50000, f"ESCROW-{DEAL}")]
    assert balances(bank) == {ESCROW: 50000, FEES: 0, BUYER: 950000, SELLER: 0}

    payout = {"from_iban": ESCROW, "to_iban": SELLER, "amount_minor": 49500, "idempotency_key": f"{DEAL}:payout"}
    fee = {"from_iban": ESCROW, "to_iban": FEES, "amount_minor": 500, "idempotency_key": f"{DEAL}:fee"}
    first = pay(bank, **payout)
    pay(bank, **fee)
    assert pay(bank, **payout) == first  # a re-submission after a lost answer pays nothing twice
    assert balances(bank) == {ESCROW: 0, FEES: 500, BUYER: 950000, SELLER: 49500}
    assert bank.credits(ESCROW, after=credits[-1]["event_id"]) == []


def test_replay_and_conflict(bank):
    first = pay(bank)
    assert pay(bank) == first
    with pytest.raises(BankError) as refused:
        pay(bank, amount_minor=49999)
    assert (refused.value.status, refused.value.code) == (409, "idempotency_conflict")
    assert balances(bank)[ESCROW] == 50000


def test_lookup_by_key(bank):
    assert bank.lookup(f"pay:{DEAL}") is None
    transfer = pay(bank)
    assert bank.lookup(f"pay:{DEAL}") == transfer


def test_credits_after(bank):
    pay(bank, idempotency_key="k1")
    pay(bank, idempotency_key="k2")
    assert [credit["event_id"] for credit in bank.credits(ESCROW)] == ["1", "2"]
    assert [credit["event_id"] for credit in bank.credits(ESCROW, after="1")] == ["2"]


def test_refusals_carry_the_contract_codes(bank):
    for changes, expected in [
        ({"to_iban": "DE00NOBODY"}, (404, "unknown_account")),
        ({"amount_minor": 1000001}, (409, "insufficient_funds")),
        ({"currency": "USD"}, (400, "invalid_transfer")),
        ({"idempotency_key": ""}, (400, "missing_idempotency_key")),
    ]:
        with pytest.raises(BankError) as refused:
            pay(bank, **changes)
        assert (refused.value.status, refused.value.code) == expected
        assert refused.value.message
    assert balances(bank)[BUYER] == 1000000


def test_concurrent_transfers_keep_the_ledger_consistent():
    ledger = Ledger()
    body = {"from_iban": BUYER, "to_iban": ESCROW, "amount_minor": 100, "currency": "EUR", "reference": "r"}

    def worker(number: int) -> None:
        for index in range(50):
            ledger.transfer(f"shared-{index}", body)  # every thread replays the same 50 keys
            ledger.transfer(f"own-{number}-{index}", body)

    threads = [threading.Thread(target=worker, args=(number,)) for number in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    balances = {account["iban"]: account["balance_minor"] for account in ledger.accounts()}
    booked = 50 + 8 * 50
    assert balances[ESCROW] == booked * 100 and sum(balances.values()) == 1000000
    event_ids = [int(credit["event_id"]) for credit in ledger.credits(ESCROW)]
    assert event_ids == list(range(1, booked + 1))


def test_python_m_sim_bank_serves_on_the_configured_port(tmp_path):
    seed = tmp_path / "bank.yaml"
    seed.write_text("accounts:\n  - {iban: A, owner: a, balance_minor: 7}\n")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    env = {**os.environ, "SIM_BANK_PORT": str(port), "SIM_BANK_SEED": str(seed), "SIM_BANK_LOG_LEVEL": "warning"}
    process = subprocess.Popen([sys.executable, "-m", "sim_bank"], env=env)
    try:
        bank = SimBankClient.from_url(f"http://127.0.0.1:{port}")
        deadline = time.monotonic() + 20
        while True:
            try:
                assert bank.accounts() == [{"iban": "A", "owner": "a", "balance_minor": 7}]
                break
            except httpx.TransportError:
                assert process.poll() is None and time.monotonic() < deadline, "the bank did not start"
                time.sleep(0.1)
    finally:
        process.terminate()
        process.wait(timeout=10)
