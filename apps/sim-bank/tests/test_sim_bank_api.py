import json
import re
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from sim_bank import DEFAULT_SEED, create_app
from sim_bank_helpers import BUYER, ESCROW, FEES, SELLER, balances, pay, payment

TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
OPENING = {ESCROW: 0, FEES: 0, BUYER: 1000000, SELLER: 0}


def error(response) -> tuple[int, str]:
    body = response.json()
    assert set(body) == {"error", "message"} and body["message"]
    return response.status_code, body["error"]


def test_health(http):
    assert http.get("/health").json() == {"status": "ok"}


def test_accounts_are_seeded_and_sorted_by_iban(http):
    accounts = http.get("/accounts").json()["accounts"]
    assert [account["iban"] for account in accounts] == sorted(OPENING)
    assert all(set(account) == {"iban", "owner", "balance_minor"} for account in accounts)
    assert balances(http) == OPENING
    assert accounts[2]["owner"] == "buyer-co"


def test_transfer_is_booked_and_moves_the_money(http):
    response = pay(http)
    assert response.status_code == 200
    transfer = response.json()
    assert transfer == {
        "transfer_id": transfer["transfer_id"],
        "event_id": "1",
        "status": "booked",
        "from_iban": BUYER,
        "to_iban": ESCROW,
        "amount_minor": 50000,
        "currency": "EUR",
        "reference": "ESCROW-d1",
        "idempotency_key": "pay:d1",
        "booked_at": transfer["booked_at"],
    }
    assert transfer["transfer_id"] and TIMESTAMP.match(transfer["booked_at"])
    assert balances(http) == {**OPENING, BUYER: 950000, ESCROW: 50000}


def test_same_key_and_body_returns_the_first_transfer_and_books_nothing(http):
    first = pay(http).json()
    again = pay(http)
    assert again.status_code == 200 and again.json() == first
    assert balances(http)[ESCROW] == 50000
    assert len(http.get("/events", params={"iban": ESCROW}).json()["events"]) == 1


def test_replay_still_answers_after_the_payer_is_empty(http):
    pay(http)
    payout = payment(from_iban=ESCROW, to_iban=SELLER, reference="payout")
    first = http.post("/transfers", json=payout, headers={"Idempotency-Key": "d1:payout"}).json()
    again = http.post("/transfers", json=payout, headers={"Idempotency-Key": "d1:payout"})
    assert again.status_code == 200 and again.json() == first
    assert balances(http) == {**OPENING, BUYER: 950000, SELLER: 50000}


@pytest.mark.parametrize(
    "change",
    [{"amount_minor": 50001}, {"reference": "other"}, {"to_iban": SELLER}, {"from_iban": SELLER}],
)
def test_same_key_with_a_different_body_is_a_conflict(http, change):
    pay(http)
    assert error(pay(http, **change)) == (409, "idempotency_conflict")
    assert balances(http) == {**OPENING, BUYER: 950000, ESCROW: 50000}


def test_lookup_by_key(http):
    transfer = pay(http, key="pay:deal/1").json()
    assert http.get("/transfers/by-key/pay%3Adeal%2F1").json() == transfer
    assert http.get("/transfers/by-key/pay:deal/1").json() == transfer
    assert error(http.get("/transfers/by-key/nothing")) == (404, "unknown_transfer")


def test_credit_events_have_stable_increasing_ids_and_an_after_filter(http):
    pay(http, key="k1", reference="first")
    pay(http, key="k2", to_iban=SELLER, reference="not for escrow")
    pay(http, key="k3", reference="third")
    events = http.get("/events", params={"iban": ESCROW}).json()["events"]
    assert [(event["event_id"], event["reference"]) for event in events] == [("1", "first"), ("3", "third")]
    assert set(events[0]) == {
        "event_id", "transfer_id", "from_iban", "to_iban", "amount_minor", "currency", "reference", "booked_at",
    }  # fmt: skip
    assert http.get("/events", params={"iban": ESCROW, "after": "0"}).json()["events"] == events
    assert http.get("/events", params={"iban": ESCROW, "after": "1"}).json()["events"] == events[1:]
    assert http.get("/events", params={"iban": ESCROW, "after": "3"}).json()["events"] == []
    assert http.get("/events", params={"iban": ESCROW}).json()["events"] == events  # stable on re-read
    assert http.get("/events", params={"iban": BUYER}).json()["events"] == []  # debits are not credits
    assert error(http.get("/events", params={"iban": ESCROW, "after": "x"})) == (400, "invalid_request")


def test_unknown_account(http):
    assert error(pay(http, from_iban="DE00NOBODY")) == (404, "unknown_account")
    assert error(pay(http, to_iban="DE00NOBODY")) == (404, "unknown_account")
    assert error(http.get("/events", params={"iban": "DE00NOBODY"})) == (404, "unknown_account")
    assert balances(http) == OPENING


def test_insufficient_funds_books_nothing_and_does_not_burn_the_key(http):
    assert error(pay(http, key="k", from_iban=SELLER, to_iban=BUYER, amount_minor=1)) == (409, "insufficient_funds")
    assert balances(http) == OPENING
    assert error(http.get("/transfers/by-key/k")) == (404, "unknown_transfer")
    assert error(pay(http, amount_minor=1000001)) == (409, "insufficient_funds")
    assert pay(http, amount_minor=1000000).status_code == 200  # the whole balance may leave


def test_missing_idempotency_key(http):
    assert error(http.post("/transfers", json=payment())) == (400, "missing_idempotency_key")
    assert error(http.post("/transfers", json=payment(), headers={"Idempotency-Key": " "})) == (
        400,
        "missing_idempotency_key",
    )
    assert balances(http) == OPENING


@pytest.mark.parametrize(
    "body",
    [
        {key: value for key, value in payment().items() if key != "reference"},
        payment(amount_minor=0),
        payment(amount_minor=-5),
        payment(amount_minor=500.0),
        payment(amount_minor="500"),
        payment(amount_minor=True),
        payment(to_iban=BUYER),
        payment(currency="USD"),
        payment(reference=7),
        ["not", "an", "object"],
    ],
)
def test_invalid_transfer(http, body):
    response = http.post("/transfers", content=json.dumps(body), headers={"Idempotency-Key": "k"})
    assert error(response) == (400, "invalid_transfer")
    assert balances(http) == OPENING


def test_a_body_that_is_not_json_is_an_invalid_transfer(http):
    response = http.post("/transfers", content=b"{nope", headers={"Idempotency-Key": "k"})
    assert error(response) == (400, "invalid_transfer")


def test_reset_reseeds_and_forgets_transfers_but_never_reuses_an_event_id(http):
    pay(http)
    assert http.post("/admin/reset").json() == {"ok": True}
    assert balances(http) == OPENING
    assert error(http.get("/transfers/by-key/pay:d1")) == (404, "unknown_transfer")
    assert http.get("/events", params={"iban": ESCROW}).json()["events"] == []
    assert pay(http).json()["event_id"] == "2"


def test_the_sum_of_all_balances_never_changes(http):
    total = sum(OPENING.values())
    steps = [
        ("a", payment()),
        ("a", payment()),  # replay
        ("a", payment(amount_minor=1)),  # conflict
        ("b", payment(from_iban=ESCROW, to_iban=SELLER, amount_minor=49500)),
        ("c", payment(from_iban=ESCROW, to_iban=FEES, amount_minor=500)),
        ("d", payment(from_iban=ESCROW, to_iban=FEES, amount_minor=1)),  # insufficient funds
        ("e", payment(to_iban="DE00NOBODY")),  # unknown account
        ("f", payment(amount_minor=0)),  # invalid
    ]
    for key, body in steps:
        http.post("/transfers", json=body, headers={"Idempotency-Key": key})
        assert sum(balances(http).values()) == total
    assert balances(http) == {ESCROW: 0, FEES: 500, BUYER: 950000, SELLER: 49500}


def test_unknown_routes_answer_with_the_error_body(http):
    assert error(http.get("/nope")) == (404, "not_found")
    assert error(http.get("/transfers")) == (405, "method_not_allowed")


def test_a_seed_file_sets_the_opening_balances(tmp_path):
    seed = tmp_path / "bank.yaml"
    seed.write_text("accounts:\n  - {iban: A, owner: a, balance_minor: 7}\n  - {iban: B, owner: b}\n")
    http = TestClient(create_app(seed))
    assert balances(http) == {"A": 7, "B": 0}
    seed.write_text("accounts:\n  - {iban: A, owner: a, balance_minor: 9}\n")
    http.post("/admin/reset")
    assert balances(http) == {"A": 9}  # reset reads the seed file again


@pytest.mark.parametrize(
    "text",
    ["accounts: []", "accounts:\n  - {owner: a}", "accounts:\n  - {iban: A, balance_minor: 1.5}", "[]"],
)
def test_a_bad_seed_file_is_refused_at_start(tmp_path, text):
    seed = tmp_path / "bank.yaml"
    seed.write_text(text)
    with pytest.raises(ValueError):
        create_app(seed)


def test_the_packaged_seed_is_the_demo_seed():
    demo = Path(__file__).resolve().parents[3] / "data" / "demo" / "bank.yaml"
    if not demo.exists():
        pytest.skip("not inside the repository")
    assert yaml.safe_load(DEFAULT_SEED.read_text()) == yaml.safe_load(demo.read_text())
