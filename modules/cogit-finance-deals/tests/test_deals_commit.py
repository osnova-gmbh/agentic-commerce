from __future__ import annotations

import pytest
from cogit_finance_deals_module import ZERO_HASH, DealsModule
from cogit_finance_seams import ModuleError
from deals_kit import (
    BUYER_DID,
    ESCROW_DID,
    MODULE,
    NEW_DEAL,
    TERMS,
    TERMS_HASH,
    Deals,
    credit,
    delivery,
    envelope,
    evaluation,
    event_hash,
    intent,
    outbox,
    posting,
)

EMPTY = dict.fromkeys(
    ("deals", "events", "outbox", "deliveries", "evaluations", "payment_intents", "bank_credits", "ledger_postings"), 0
)


def test_first_commit_creates_the_deal_and_its_first_event(deals, clock):
    body = {"envelope": envelope("m1", "finance.service_request")}
    args = deals.commit_args("service_request", "REQUESTED", source_message_id="m1", actor_did=BUYER_DID, body=body)
    assert (args["expected_seq"], args["expected_hash"], args["event"]["seq"]) == (0, ZERO_HASH, 1)

    result = deals.command("deal.commit", args)
    assert result == {"seq": 1, "hash": args["event"]["hash"], "duplicate": False}

    read = deals.read()
    assert read["deal"] == {
        "deal_id": "deal-1",
        **NEW_DEAL,
        "state": "REQUESTED",
        "head_seq": 1,
        "head_hash": result["hash"],
        "terms": None,
        "terms_hash": None,
        "created_at": clock.ts,
        "updated_at": clock.ts,
    }
    assert read["events"] == [
        {
            "deal_id": "deal-1",
            "seq": 1,
            "prev_hash": ZERO_HASH,
            "hash": result["hash"],
            "event_type": "service_request",
            "source_message_id": "m1",
            "actor_did": BUYER_DID,
            "body": body,
            "state_after": "REQUESTED",
            "recorded_at": clock.ts,
        }
    ]


def test_a_chain_of_commits_links_every_event_to_the_one_before(deals, clock):
    created_at = clock.ts
    first = deals.commit("service_request", "REQUESTED", source_message_id="m1", deal={**NEW_DEAL, "terms": None})
    clock.advance(5)
    quote = {
        "envelope": {"message_id": "m2", "body": {"price_minor": 50000, "note": "Größe", "list": [1, {"a": None}]}}
    }
    second = deals.commit("quote", "QUOTED", source_message_id="m2", body=quote)
    third = deals.commit("terms_proposed", "TERMS_PROPOSED", deal={"terms": TERMS, "terms_hash": TERMS_HASH})
    clock.advance(5)
    # E may send the whole deal object again; null terms do not erase the stored ones.
    fourth = deals.commit("accept_terms", "TERMS_PROPOSED", source_message_id="m3", deal={**NEW_DEAL, "terms": None})

    assert [result["seq"] for result in (first, second, third, fourth)] == [1, 2, 3, 4]
    read = deals.read()
    assert [event["seq"] for event in read["events"]] == [1, 2, 3, 4]
    assert [event["prev_hash"] for event in read["events"]] == [ZERO_HASH, first["hash"], second["hash"], third["hash"]]
    assert [event["hash"] for event in read["events"]] == [result["hash"] for result in (first, second, third, fourth)]
    assert [event["actor_did"] for event in read["events"]] == [ESCROW_DID] * 4
    # An event read back is the event E hashed: the body comes back value for value.
    assert read["events"][1]["body"] == quote
    assert all(event_hash(event) == event["hash"] for event in read["events"])
    assert read["deal"]["state"] == "TERMS_PROPOSED"
    assert (read["deal"]["head_seq"], read["deal"]["head_hash"]) == (4, fourth["hash"])
    assert (read["deal"]["terms"], read["deal"]["terms_hash"]) == (TERMS, TERMS_HASH)
    assert (read["deal"]["created_at"], read["deal"]["updated_at"]) == (created_at, clock.ts)


def test_a_stale_head_is_a_head_mismatch(deals):
    first = deals.commit("service_request", "REQUESTED", source_message_id="m1")
    second = deals.commit("quote", "QUOTED", source_message_id="m2")
    before = deals.counts()

    stale = deals.commit_args("terms_proposed", "TERMS_PROPOSED", head=(1, first["hash"]), outbox=outbox("o1"))
    assert deals.fails("deal.commit", stale) == "head_mismatch"
    right_seq_wrong_hash = deals.commit_args("terms_proposed", "TERMS_PROPOSED", head=(2, first["hash"]))
    assert deals.fails("deal.commit", right_seq_wrong_hash) == "head_mismatch"
    restart = deals.commit_args("service_request", "REQUESTED", head=(0, ZERO_HASH), deal=NEW_DEAL)
    assert deals.fails("deal.commit", restart) == "head_mismatch"

    assert deals.counts() == before
    assert deals.head() == (2, second["hash"])


def test_an_unknown_deal_has_head_zero_and_needs_its_parties(deals):
    ahead = deals.commit_args("quote", "QUOTED", head=(1, "ab" * 32), deal=NEW_DEAL)
    assert deals.fails("deal.commit", ahead) == "head_mismatch"
    for incomplete in ({}, {"buyer_org_id": "buyer-co", "seller_org_id": "seller-co"}):
        args = deals.commit_args("service_request", "REQUESTED", deal=incomplete)
        assert deals.fails("deal.commit", args) == "head_mismatch"
    args = deals.commit_args("service_request", "REQUESTED")
    del args["deal"]
    assert deals.fails("deal.commit", args) == "head_mismatch"
    assert deals.counts() == EMPTY


@pytest.mark.parametrize(
    "change",
    [
        {"seq": 2},
        {"seq": 4},
        {"prev_hash": ZERO_HASH},
        {"prev_hash": "cd" * 32},
        {"hash": "not-a-hash"},
        {"state_after": ""},
        {"body": None},
        {"recorded_at": "2026-11-27T12:00:00Z"},
    ],
)
def test_an_event_that_is_not_the_next_link_is_a_bad_event(deals, change):
    deals.commit("service_request", "REQUESTED", source_message_id="m1")
    second = deals.commit("quote", "QUOTED", source_message_id="m2")
    before = deals.counts()

    args = deals.commit_args("terms_proposed", "TERMS_PROPOSED", outbox=outbox("o1"))
    args["event"].update(change)
    assert deals.fails("deal.commit", args) == "bad_event"
    assert deals.counts() == before
    assert deals.head() == (2, second["hash"])


def test_the_event_may_name_its_deal(deals):
    args = deals.commit_args("service_request", "REQUESTED", source_message_id="m1")
    args["event"]["deal_id"] = "deal-2"
    assert deals.fails("deal.commit", args) == "bad_event"
    args["event"]["deal_id"] = "deal-1"  # as in the dict E passes to event_hash
    assert deals.command("deal.commit", args)["seq"] == 1


def test_an_event_hash_is_stored_as_given_and_only_once(deals):
    args = deals.commit_args("service_request", "REQUESTED", source_message_id="m1")
    args["event"]["hash"] = "ef" * 32  # not what E would compute: the module does not recompute it
    assert deals.command("deal.commit", args)["hash"] == "ef" * 32

    other = deals.commit_args("service_request", "REQUESTED", deal_id="deal-2", source_message_id="m2")
    other["event"]["hash"] = "ef" * 32
    assert deals.fails("deal.commit", other) == "bad_event"
    assert deals.read("deal-2")["deal"] is None
    assert deals.counts()["events"] == 1


def test_a_repeated_source_message_returns_the_original_result_and_writes_nothing(deals):
    first = deals.commit("service_request", "REQUESTED", source_message_id="m1", outbox=outbox("o1"))
    before = deals.counts()

    # The same message processed again by a caller that still sees the empty head.
    again = deals.commit_args(
        "service_request",
        "REQUESTED",
        head=(0, ZERO_HASH),
        source_message_id="m1",
        deal=NEW_DEAL,
        outbox=outbox("o2", "o3"),
        deliveries=[delivery()],
        evaluations=[evaluation("integrity")],
        intents=[intent("payout", 49500)],
        credits=[credit()],
        postings=[posting("7", "held", 50000)],
    )
    assert deals.command("deal.commit", again) == {"seq": 1, "hash": first["hash"], "duplicate": True}
    assert deals.counts() == before
    assert [entry["outbox_id"] for entry in deals.query("outbox.pending")["entries"]] == ["o1"]

    # Still the original answer after the head has moved on, whatever head the caller names.
    second = deals.commit("quote", "QUOTED", source_message_id="m2")
    on_new_head = deals.commit_args("service_request", "QUOTED", source_message_id="m1", outbox=outbox("o4"))
    assert deals.command("deal.commit", on_new_head) == {"seq": 1, "hash": first["hash"], "duplicate": True}
    assert deals.head() == (2, second["hash"])
    assert deals.counts()["events"] == 2 and deals.counts()["outbox"] == 1

    # A message recorded for one deal cannot be claimed by another.
    elsewhere = deals.commit_args("service_request", "REQUESTED", deal_id="deal-2", source_message_id="m1")
    assert deals.fails("deal.commit", elsewhere) == "bad_event"


def test_the_same_idempotency_key_replays_the_first_result(deals):
    args = deals.commit_args("service_request", "REQUESTED", source_message_id="m1", outbox=outbox("o1"))
    first = deals.command("deal.commit", args, key="evt:m1")
    assert deals.command("deal.commit", args, key="evt:m1") == first == {**first, "duplicate": False}
    assert deals.counts()["events"] == 1 and deals.counts()["outbox"] == 1


def test_events_without_a_source_message_do_not_collide(deals):
    deals.commit("service_request", "REQUESTED", source_message_id="m1")
    deals.commit("terms_proposed", "TERMS_PROPOSED")
    deals.commit("payment_request", "FUNDING_REQUESTED")
    assert [event["source_message_id"] for event in deals.read()["events"]] == ["m1", None, None]


def full_commit(deals: Deals, **extra) -> dict:
    rows = {
        "outbox": outbox("o1", "o2"),
        "deliveries": [delivery()],
        "evaluations": [evaluation("integrity")],
        "intents": [intent("payout", 49500), intent("fee", 500)],
        "credits": [credit()],
        "postings": [posting("7", "held", 50000)],
    }
    return deals.commit_args("decision", "APPROVED", **{**rows, **extra})


@pytest.mark.parametrize(
    ("extra", "code"),
    [
        ({"intents": [intent("payout", 49500), intent("refund", 50000)]}, "intent_conflict"),
        ({"credits": [credit("7"), credit("7")]}, "duplicate_credit"),
        ({"postings": [posting("7", "held", 50000), posting("7", "held", 1, "p2")]}, "duplicate_posting"),
        ({"postings": [posting("7", "held", 500.0)]}, "invalid_argument"),
        ({"outbox": outbox("o1", "o1")}, "invalid_argument"),
        ({"outbox": [{**outbox("o1")[0], "deal_id": "deal-9"}]}, "invalid_argument"),
        ({"evaluations": [evaluation("integrity", reasons=["x"])]}, "invalid_argument"),
        ({"deliveries": [{"delivery_id": "deal-1:d1"}]}, "invalid_argument"),
        ({"surprise": 1}, "invalid_argument"),
    ],
)
def test_a_failing_commit_leaves_no_partial_rows(deals, extra, code):
    # On a new deal: not even the deal row survives.
    assert deals.fails("deal.commit", full_commit(deals, **extra)) == code
    assert deals.counts() == EMPTY
    assert deals.read() == dict(deal=None, events=[], deliveries=[], evaluations=[], intents=[], credits=[])

    # On an existing deal: the head, the state and every table stay as they were.
    first = deals.commit("service_request", "REQUESTED", source_message_id="m1")
    before = deals.counts()
    assert deals.fails("deal.commit", full_commit(deals, **extra)) == code
    assert deals.counts() == before
    assert deals.head() == (1, first["hash"]) and deals.read()["deal"]["state"] == "REQUESTED"
    assert deals.query("outbox.pending") == {"entries": []}

    # The same commit without the fault goes through.
    assert deals.command("deal.commit", full_commit(deals))["seq"] == 2


def test_the_parties_of_a_deal_cannot_change(deals):
    deals.commit("service_request", "REQUESTED", source_message_id="m1")
    args = deals.commit_args("quote", "QUOTED", deal={**NEW_DEAL, "buyer_org_id": "someone-else"})
    assert deals.fails("deal.commit", args) == "invalid_argument"
    assert deals.read()["deal"]["buyer_org_id"] == "buyer-co"


def test_commands_are_forbidden_for_everyone_but_the_escrow_installation(host, clock, deals):
    deals.commit("service_request", "REQUESTED", intents=[intent("payout", 49500)], outbox=outbox("o1"))
    commands = {
        "deal.commit": deals.commit_args("quote", "QUOTED"),
        "outbox.mark_sent": {"outbox_id": "o1"},
        "intent.update": {"intent_id": "deal-1:payout", "status": "submitted"},
    }
    before = deals.counts()
    for caller in (host.port("buyer-agent"), host.port("seller-agent"), host.port("cogit-finance", "operator")):
        for export, args in commands.items():
            with pytest.raises(ModuleError) as error:
                caller.module_command(MODULE, export, args, idempotency_key=f"{export}-x")
            assert error.value.code == "forbidden"
        # Queries are open in the demo.
        assert caller.module_query(MODULE, "deal.read", {"deal_id": "deal-1"})["deal"]["head_seq"] == 1
        assert len(caller.module_query(MODULE, "deal.list")["deals"]) == 1
    assert deals.counts() == before
    assert deals.read()["intents"][0]["status"] == "prepared"
    assert len(deals.query("outbox.pending")["entries"]) == 1


def test_the_escrow_installation_is_a_module_setting(clock):
    from cogit_finance_seams import LocalModuleHost

    host = LocalModuleHost(clock=clock)
    host.install(DealsModule(), {"escrow_installation_id": "escrow-2"})
    assert Deals(host, clock, "escrow-2").commit("service_request", "REQUESTED")["seq"] == 1
    default = Deals(host, clock, "cogit-finance")
    assert default.fails("deal.commit", default.commit_args("quote", "QUOTED")) == "forbidden"
