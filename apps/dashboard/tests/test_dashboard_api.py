import json
import re

import pytest
from cogit_finance_seams import BankError, ModuleError
from dashboard import FixtureSource, create_app, deal_view, dump_source, format_minor
from dashboard_helpers import CONTRACT_FIXTURES, FIXTURES, fixture_deal_id, fixture_read, statuses
from fastapi.testclient import TestClient

RUNS = ["happy", "broken"]
EVALUATORS = ["integrity", "required-files", "deadline"]
ACCOUNTS = {  # SPEC §13.2 after one settled deal of 50000 with a fee of 500
    "DE00EXAMPLE0000000001": (0, "EUR 0.00"),
    "DE00EXAMPLE0000000002": (500, "EUR 5.00"),
    "DE00EXAMPLE0000000010": (950000, "EUR 9,500.00"),
    "DE00EXAMPLE0000000020": (49500, "EUR 495.00"),
}


def client(name: str) -> TestClient:
    return TestClient(create_app(FixtureSource(FIXTURES / name)))


def view(name: str) -> dict:
    response = client(name).get(f"/api/deals/{fixture_deal_id(name)}")
    assert response.status_code == 200
    return response.json()


@pytest.mark.parametrize(
    ("amount", "text"),
    [(0, "EUR 0.00"), (5, "EUR 0.05"), (50000, "EUR 500.00"), (49500, "EUR 495.00"), (1000000, "EUR 10,000.00"),
     (-150, "-EUR 1.50"), (None, "—")],
)  # fmt: skip
def test_amounts_are_shown_as_eur_with_two_decimals(amount, text):
    assert format_minor(amount) == text


@pytest.mark.parametrize("name", RUNS)
def test_deal_list(name):
    deals = client(name).get("/api/deals").json()["deals"]
    assert len(deals) == 1
    deal = deals[0]
    assert (deal["state"], deal["tone"], deal["price"]) == ("SETTLED", "done", "EUR 500.00")
    assert (deal["buyer_org_id"], deal["seller_org_id"], deal["offer_id"]) == ("buyer-co", "seller-co", "offer-1")
    assert re.fullmatch(r"\d\d:\d\d:\d\d", deal["updated_time"])


@pytest.mark.parametrize("name", RUNS)
def test_deal_view_of_a_settled_run(name):
    body = view(name)
    assert set(body) == {"deal", "steps", "money", "attempts", "timeline"}
    assert body["deal"]["state"] == "SETTLED" and body["deal"]["price"] == "EUR 500.00"
    assert statuses(body["steps"]) == "DDDDDDDDDD"
    money = body["money"]
    assert money["phase"] == "released" and money["headline"] == "EUR 500.00 released"
    assert "EUR 495.00 paid to seller-co" in money["detail"] and "EUR 5.00 fee" in money["detail"]
    assert [(tile["key"], tile["amount_minor"], tile["display"]) for tile in money["tiles"]] == [
        ("held", 0, "EUR 0.00"),
        ("seller", 49500, "EUR 495.00"),
        ("fee", 500, "EUR 5.00"),
    ]


@pytest.mark.parametrize("name", RUNS)
def test_timeline_rows(name):
    events = fixture_read(name)["events"]
    rows = view(name)["timeline"]
    assert [row["seq"] for row in rows] == list(range(1, len(events) + 1))
    for row, event in zip(rows, events, strict=True):
        assert row["event_type"] == event["event_type"] and row["state_after"] == event["state_after"]
        assert row["hash8"] == event["hash"][:8] and len(row["hash8"]) == 8
        assert row["time"] == event["recorded_at"][11:19]
        assert row["actor"] in ("buyer", "seller", "escrow", "evaluator") and row["actor_did"] == event["actor_did"]
    assert [row["actor"] for row in rows[:3]] == ["buyer", "seller", "escrow"]
    assert {row["actor"] for row in rows if row["event_type"] == "accept_terms"} == {"buyer", "seller"}
    assert {row["actor"] for row in rows if row["event_type"] == "verdict"} == {"evaluator"}
    tones = {row["event_type"]: row["tone"] for row in rows if row["tone"] in ("held", "released")}
    assert tones == {"funding_received": "held", "payout_confirmed": "released"}


@pytest.mark.parametrize(("name", "contract"), [("happy", "happy-path"), ("broken", "broken-run")])
def test_fixture_events_follow_the_contract_sequence(name, contract):
    if not CONTRACT_FIXTURES.is_dir():
        pytest.skip("not inside the repository")
    expected = json.loads((CONTRACT_FIXTURES / f"{contract}.events.json").read_text())
    kinds = [event["event_type"] for event in fixture_read(name)["events"]]
    position = 0
    for entry in expected["events"]:
        count = 0
        while position < len(kinds) and kinds[position] == entry["event_type"] and count < entry["max"]:
            position, count = position + 1, count + 1
        assert count >= entry["min"], entry
    assert position == len(kinds)
    assert fixture_read(name)["deal"]["state"] == expected["final_state"]


def test_happy_run_has_one_approved_attempt():
    attempts = view("happy")["attempts"]
    assert [(attempt["attempt"], attempt["decision"]) for attempt in attempts] == [(1, "approve")]
    assert [(verdict["evaluator"], verdict["outcome"]) for verdict in attempts[0]["verdicts"]] == [
        (name, "pass") for name in EVALUATORS
    ]


def test_broken_run_shows_the_rejected_attempt_and_the_redelivery():
    first, second = view("broken")["attempts"]
    assert (first["attempt"], first["decision"]) == (1, "reject")
    verdicts = {verdict["evaluator"]: verdict for verdict in first["verdicts"]}
    assert verdicts["required-files"]["outcome"] == "fail"
    assert any("summary.json" in reason for reason in verdicts["required-files"]["reasons"])
    assert all(verdict["outcome"] in ("pass", "fail", "none") for verdict in first["verdicts"])
    assert [verdict["evaluator"] for verdict in first["verdicts"]] == EVALUATORS  # asked ones without a verdict too
    assert (second["attempt"], second["decision"]) == (2, "approve")
    assert [(verdict["evaluator"], verdict["outcome"]) for verdict in second["verdicts"]] == [
        (name, "pass") for name in EVALUATORS
    ]
    failed = [row["event_type"] for row in view("broken")["timeline"] if row["tone"] == "failed"]
    assert failed.count("decision") == 1 and "verdict" in failed


@pytest.mark.parametrize("name", RUNS)
def test_balances_and_accounts(name):
    http = client(name)
    for url in ("/api/balances", f"/api/balances?deal_id={fixture_deal_id(name)}"):
        body = http.get(url).json()
        assert body["balances"] == {"held": 0, "seller": 49500, "fee": 500, "buyer_refund": 0, "returned": 0}
        assert body["display"]["seller"] == "EUR 495.00" and body["display"]["held"] == "EUR 0.00"
    assert http.get("/api/balances?deal_id=unknown").json()["balances"]["seller"] == 0
    accounts = http.get("/api/accounts").json()["accounts"]
    assert {a["iban"]: (a["balance_minor"], a["balance"]) for a in accounts} == ACCOUNTS
    assert all(account["owner"] for account in accounts)


@pytest.mark.parametrize("deal_id", ["unknown", "..%2F..%2Fdeals", "%2e%2e"])
def test_unknown_deal_is_404(deal_id):
    response = client("happy").get(f"/api/deals/{deal_id}")
    assert response.status_code == 404 and response.json()["error"] in ("unknown_deal", "not_found")


def test_the_page_is_served_by_the_app_without_any_external_host():
    http = client("happy")
    page = http.get("/")
    assert page.status_code == 200 and page.headers["content-type"].startswith("text/html")
    assert page.headers["cache-control"] == "no-store"
    assert '<script src="/static/app.js">' in page.text and 'href="/static/app.css"' in page.text
    for path in ("/", "/static/app.js", "/static/app.css"):
        text = http.get(path).text
        hosts = set(re.findall(r"(?:https?:)?//[\w.-]+\.\w+", text)) - {"http://www.w3.org"}  # the SVG namespace
        assert hosts == set(), (path, hosts)
        assert "@import" not in text
        for asset in re.findall(r"url\(\s*['\"]?([^'\")\s]+)['\"]?\s*\)", text):
            assert asset.startswith("/static/"), asset
            assert http.get(asset).status_code == 200, asset
    assert "setTimeout(loop, 1000)" in http.get("/static/app.js").text  # polls every second


def test_the_api_is_read_only():
    app = create_app(FixtureSource(FIXTURES / "happy"))
    for route in app.routes:
        assert set(getattr(route, "methods", None) or {"GET"}) <= {"GET", "HEAD"}, route
    http = TestClient(app)
    for path in ("/api/deals", f"/api/deals/{fixture_deal_id('happy')}", "/api/balances", "/api/accounts", "/"):
        for method in ("post", "put", "patch", "delete"):
            assert getattr(http, method)(path).status_code == 405


def test_empty_fixture_catalog_is_read_only_and_has_no_placeholder_prospects():
    http = client("happy")
    assert http.get("/api/catalog").json() == {"companies": []}
    assert http.get("/catalog").status_code == 200
    assert http.post("/api/catalog", json={}).status_code == 405


def test_deals_are_listed_newest_first(tmp_path):
    rows = []
    for name in RUNS:
        dump_source(FixtureSource(FIXTURES / name), tmp_path)
        rows += json.loads((tmp_path / "deals.json").read_text())["deals"]
    oldest_first = sorted(rows, key=lambda row: row["created_at"])
    (tmp_path / "deals.json").write_text(json.dumps({"deals": oldest_first}))
    listed = TestClient(create_app(FixtureSource(tmp_path))).get("/api/deals").json()["deals"]
    assert [deal["deal_id"] for deal in listed] == [row["deal_id"] for row in reversed(oldest_first)]


def test_json_columns_handed_back_as_text_are_still_read():
    read = fixture_read("broken")
    as_text = {
        **read,
        "deal": {**read["deal"], "terms": json.dumps(read["deal"]["terms"])},
        "events": [{**event, "body": json.dumps(event["body"])} for event in read["events"]],
    }
    balances = {"held": 0, "seller": 49500, "fee": 500, "buyer_refund": 0, "returned": 0}
    assert deal_view(as_text, balances) == deal_view(read, balances)


class FailingSource:
    def deals(self) -> list[dict]:
        raise ModuleError("unknown_module", "cogit-finance-deals")

    def deal(self, deal_id: str) -> dict:
        raise ModuleError("forbidden")

    def balances(self, deal_id: str | None = None) -> dict:
        raise ModuleError("forbidden")

    def accounts(self) -> list[dict]:
        raise BankError(503, "bank_down", "no answer")


def test_a_failing_source_answers_502_with_its_error_code():
    http = TestClient(create_app(FailingSource()))
    assert (http.get("/api/deals").status_code, http.get("/api/deals").json()["error"]) == (502, "unknown_module")
    assert http.get("/api/deals/d1").json()["error"] == "forbidden"
    assert (http.get("/api/accounts").status_code, http.get("/api/accounts").json()["error"]) == (502, "bank_down")
    assert http.get("/").status_code == 200


def test_intermediate_states_from_the_generator(tmp_path):
    pytest.importorskip("cogit_messaging_shim")
    from dashboard.make_fixtures import play

    funded = play("happy", until=8)
    body = TestClient(create_app(funded)).get(f"/api/deals/{funded.deal_id}").json()
    assert body["deal"]["state"] == "FUNDED" and statuses(body["steps"]) == "DDDDDAPPPP"
    assert (body["money"]["phase"], body["money"]["headline"]) == ("held", "EUR 500.00 held in escrow")
    assert body["money"]["tiles"][0]["amount_minor"] == 50000 and body["attempts"] == []

    requested = play("happy", until=7)
    body = TestClient(create_app(requested)).get(f"/api/deals/{requested.deal_id}").json()
    assert body["money"]["phase"] == "requested" and "buyer-co" in body["money"]["headline"]

    rejected = play("broken", until=13)
    http = TestClient(create_app(rejected))
    body = http.get(f"/api/deals/{rejected.deal_id}").json()
    assert body["deal"]["state"] == "REJECTED" and body["deal"]["tone"] == "failed"
    assert statuses(body["steps"]) == "DDDDDDDFPP"
    assert body["money"]["phase"] == "held" and "rejected" in body["money"]["detail"]
    assert [(v["evaluator"], v["outcome"]) for v in body["attempts"][0]["verdicts"]] == [
        ("integrity", "pass"), ("required-files", "fail"), ("deadline", "none"),
    ]  # fmt: skip
    assert body["attempts"][0]["reasons"] == ["required-files@1: missing file: summary.json"]
    held = {a["iban"]: a["balance_minor"] for a in http.get("/api/accounts").json()["accounts"]}
    assert held["DE00EXAMPLE0000000001"] == 50000 and sum(held.values()) == 1000000

    first = play("happy", until=1)  # before the terms: no price, roles from the event types
    body = TestClient(create_app(first)).get(f"/api/deals/{first.deal_id}").json()
    assert body["deal"]["price"] == "—" and body["money"]["phase"] == "none"
    assert body["timeline"][0]["actor"] == "buyer" and statuses(body["steps"]) == "DDDAPPPPPP"


@pytest.mark.parametrize("name", RUNS)
def test_fixture_events_chain_and_envelopes_verify(name):
    shim = pytest.importorskip("cogit_messaging_shim")
    read = fixture_read(name)
    previous = shim.ZERO_HASH
    for event in read["events"]:
        assert event["prev_hash"] == previous and event["hash"] == shim.event_hash(event)
        previous = event["hash"]
        envelope = event["body"].get("envelope")
        if envelope is not None:
            assert shim.verify_envelope(envelope) and envelope["message_id"] == event["source_message_id"]
            assert envelope["sender_did"] == event["actor_did"]
    assert read["deal"]["head_hash"] == previous and read["deal"]["head_seq"] == len(read["events"])
    assert read["deal"]["terms_hash"] == shim.canonical_hash(read["deal"]["terms"])
