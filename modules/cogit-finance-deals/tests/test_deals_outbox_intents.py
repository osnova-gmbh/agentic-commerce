from __future__ import annotations

import sqlite3

import pytest
from deals_kit import Deals, credit, delivery, envelope, evaluation, intent, outbox, posting

ZERO_BALANCES = {"held": 0, "seller": 0, "fee": 0, "buyer_refund": 0, "returned": 0}


def pending_ids(deals: Deals, limit: int | None = None) -> list:
    args = {} if limit is None else {"limit": limit}
    return [entry["outbox_id"] for entry in deals.query("outbox.pending", args)["entries"]]


def intents_by_id(deals: Deals, deal_id: str = "deal-1") -> dict:
    return {row["intent_id"]: row for row in deals.read(deal_id)["intents"]}


def test_outbox_entries_are_pending_until_marked_sent(deals, host, clock):
    assert deals.query("outbox.pending") == {"entries": []}
    deals.commit("service_request", "REQUESTED", source_message_id="m1", outbox=outbox("o-b", "o-a"))
    clock.advance(1)
    deals.commit("service_request", "REQUESTED", deal_id="deal-0", source_message_id="m9", outbox=outbox("o-z"))
    deals.commit("quote", "QUOTED", source_message_id="m2")
    deals.commit("terms_proposed", "TERMS_PROPOSED", outbox=outbox("o-c"))

    entries = deals.query("outbox.pending")["entries"]
    assert entries[0] == {"outbox_id": "o-b", "deal_id": "deal-1", "seq": 1, "envelope": envelope("o-b")}
    # Oldest first, in the order the commit listed them.
    assert [(entry["outbox_id"], entry["deal_id"], entry["seq"]) for entry in entries] == [
        ("o-b", "deal-1", 1),
        ("o-a", "deal-1", 1),
        ("o-z", "deal-0", 1),
        ("o-c", "deal-1", 3),
    ]
    assert pending_ids(deals, limit=2) == ["o-b", "o-a"]

    sent_at = clock.ts
    assert deals.command("outbox.mark_sent", {"outbox_id": "o-b"}) == {}
    assert pending_ids(deals) == ["o-a", "o-z", "o-c"]
    clock.advance(60)
    assert deals.command("outbox.mark_sent", {"outbox_id": "o-b"}) == {}  # repeating it is harmless
    assert deals.command("outbox.mark_sent", {"outbox_id": "never-written"}) == {}
    row = host.db.execute("SELECT status, sent_at FROM deal_outbox WHERE outbox_id = 'o-b'").fetchone()
    assert (row["status"], row["sent_at"]) == ("sent", sent_at)

    for outbox_id in ("o-a", "o-z", "o-c"):
        deals.command("outbox.mark_sent", {"outbox_id": outbox_id})
    assert deals.query("outbox.pending") == {"entries": []}
    assert deals.counts()["outbox"] == 4


def test_a_deal_has_one_active_payout_or_refund_intent(deals):
    deals.commit("service_request", "REQUESTED", source_message_id="m1")
    deals.commit("decision", "APPROVED", intents=[intent("payout", 49500), intent("fee", 500)])
    assert {row["kind"]: row["status"] for row in deals.read()["intents"]} == {"payout": "prepared", "fee": "prepared"}

    for second in (intent("refund", 50000), intent("payout", 49500, intent_id="deal-1:payout:2")):
        refund = deals.commit_args("ruling", "REFUNDING", intents=[second])
        assert deals.fails("deal.commit", refund) == "intent_conflict"
    # Still active while submitted or unknown.
    for status in ("submitted", "unknown"):
        deals.command("intent.update", {"intent_id": "deal-1:payout", "status": status})
        refund = deals.commit_args("ruling", "REFUNDING", intents=[intent("refund", 50000)])
        assert deals.fails("deal.commit", refund) == "intent_conflict"
    # The same intent ID twice is a conflict too, whatever its kind.
    again = deals.commit_args("decision", "APPROVED", intents=[intent("fee", 500)])
    assert deals.fails("deal.commit", again) == "intent_conflict"
    assert deals.head()[0] == 2 and len(deals.read()["intents"]) == 2

    # Other kinds and other deals are not affected; a failed payout frees the slot.
    deals.commit("note", "APPROVED", intents=[intent("return_unmatched", 10)])
    deals.commit("service_request", "REQUESTED", deal_id="deal-2", intents=[intent("payout", 1, deal_id="deal-2")])
    deals.command("intent.update", {"intent_id": "deal-1:payout", "status": "failed"})
    deals.commit("ruling", "REFUNDING", intents=[intent("refund", 50000)])
    assert intents_by_id(deals)["deal-1:refund"]["status"] == "prepared"
    # Reviving the failed payout would make two active ones again.
    revive = {"intent_id": "deal-1:payout", "status": "submitted"}
    assert deals.fails("intent.update", revive) == "intent_conflict"
    assert intents_by_id(deals)["deal-1:payout"]["status"] == "failed"


def test_a_bank_credit_is_recorded_once(deals):
    deals.commit("service_request", "REQUESTED", source_message_id="m1")
    funded = deals.commit("funding_received", "FUNDED", credits=[credit("7")], postings=[posting("7", "held", 50000)])
    assert deals.read()["credits"] == [{"deal_id": "deal-1", **credit("7")}]

    same_deal = deals.commit_args("funding_received", "FUNDED", credits=[credit("7")], outbox=outbox("o1"))
    assert deals.fails("deal.commit", same_deal) == "duplicate_credit"
    other_deal = deals.commit_args(
        "funding_received", "FUNDED", deal_id="deal-2", credits=[credit("7", deal_id="deal-2")]
    )
    assert deals.fails("deal.commit", other_deal) == "duplicate_credit"

    assert deals.head() == (2, funded["hash"])
    assert deals.read("deal-2")["deal"] is None
    assert deals.counts()["bank_credits"] == 1 and deals.counts()["outbox"] == 0
    assert deals.query("ledger.balances")["held"] == 50000


def test_intent_update_confirms_with_postings_written_once(deals, clock):
    deals.commit("service_request", "REQUESTED", source_message_id="m1")
    deals.commit("decision", "APPROVED", intents=[intent("payout", 49500)])
    prepared_at = clock.ts
    assert intents_by_id(deals)["deal-1:payout"] == {
        "deal_id": "deal-1",
        **intent("payout", 49500),
        "bank_ref": None,
        "created_at": prepared_at,
        "updated_at": prepared_at,
    }

    clock.advance(10)
    assert deals.command("intent.update", {"intent_id": "deal-1:payout", "status": "submitted"}) == {}
    assert intents_by_id(deals)["deal-1:payout"]["status"] == "submitted"
    assert deals.query("ledger.balances") == ZERO_BALANCES

    clock.advance(10)
    confirm = {
        "intent_id": "deal-1:payout",
        "status": "confirmed",
        "bank_ref": "tr_42",
        "postings": [posting("deal-1:payout", "held", -49500), posting("deal-1:payout", "seller", 49500)],
    }
    assert deals.command("intent.update", confirm) == {}
    confirmed = intents_by_id(deals)["deal-1:payout"]
    assert (confirmed["status"], confirmed["bank_ref"]) == ("confirmed", "tr_42")
    assert (confirmed["created_at"], confirmed["updated_at"]) == (prepared_at, clock.ts)
    after_first = {**ZERO_BALANCES, "held": -49500, "seller": 49500}
    assert deals.query("ledger.balances") == after_first

    # Repeated under new keys, with new posting IDs or without a bank reference: nothing is added.
    deals.command("intent.update", confirm)
    renamed = [{**item, "posting_id": f"again-{index}"} for index, item in enumerate(confirm["postings"])]
    deals.command("intent.update", {"intent_id": "deal-1:payout", "status": "confirmed", "postings": renamed})
    assert deals.query("ledger.balances") == after_first
    assert deals.counts()["ledger_postings"] == 2
    assert intents_by_id(deals)["deal-1:payout"]["bank_ref"] == "tr_42"


def test_intent_update_of_an_unknown_intent_fails(deals):
    deals.commit("service_request", "REQUESTED", source_message_id="m1")
    update = {"intent_id": "deal-1:payout", "status": "confirmed", "postings": [posting("x", "held", -1)]}
    assert deals.fails("intent.update", update) == "unknown_intent"
    assert deals.fails("intent.update", {"intent_id": "deal-1:payout", "status": "paid"}) == "invalid_argument"
    assert deals.counts()["ledger_postings"] == 0


def test_a_posting_without_a_source_belongs_to_the_intent(deals):
    deals.commit("service_request", "REQUESTED", intents=[intent("fee", 500)])
    postings = [{"posting_id": "p1", "account": "held", "amount_minor": -500}]
    postings.append({"posting_id": "p2", "account": "fee", "amount_minor": 500})
    deals.command("intent.update", {"intent_id": "deal-1:fee", "status": "confirmed", "postings": postings})
    rows = deals.host.db.execute("SELECT source_id, deal_id FROM deal_ledger_postings").fetchall()
    assert {(row["source_id"], row["deal_id"]) for row in rows} == {("deal-1:fee", "deal-1")}


def settle(deals: Deals, deal_id: str, bank_event_id: str, price: int = 50000, fee: int = 500) -> None:
    """The money side of one happy-path deal: funded, then payout and fee confirmed."""
    payout = price - fee
    deals.commit("service_request", "REQUESTED", deal_id=deal_id, source_message_id=f"{deal_id}:m1")
    deals.commit(
        "funding_received",
        "FUNDED",
        deal_id=deal_id,
        credits=[credit(bank_event_id, price, deal_id)],
        postings=[posting(bank_event_id, "held", price)],
    )
    assert deals.query("ledger.balances", {"deal_id": deal_id}) == {**ZERO_BALANCES, "held": price}
    intents = [intent("payout", payout, deal_id), intent("fee", fee, deal_id, to_iban="DE00EXAMPLE0000000002")]
    deals.commit("payout_submitted", "PAYING_OUT", deal_id=deal_id, intents=intents)
    for kind, account, amount in (("payout", "seller", payout), ("fee", "fee", fee)):
        intent_id = f"{deal_id}:{kind}"
        deals.command("intent.update", {"intent_id": intent_id, "status": "submitted"})
        postings = [posting(intent_id, "held", -amount), posting(intent_id, account, amount)]
        update = {"intent_id": intent_id, "status": "confirmed", "bank_ref": f"tr_{kind}", "postings": postings}
        deals.command("intent.update", update)
        deals.command("intent.update", update)  # a retried confirmation
    deals.commit("payout_confirmed", "SETTLED", deal_id=deal_id)


def test_ledger_balances_of_the_happy_path(deals):
    assert deals.query("ledger.balances") == ZERO_BALANCES
    settle(deals, "deal-1", "7")
    settled = {"held": 0, "seller": 49500, "fee": 500, "buyer_refund": 0, "returned": 0}
    assert deals.query("ledger.balances", {"deal_id": "deal-1"}) == settled
    assert deals.query("ledger.balances") == settled
    assert all(type(amount) is int for amount in settled.values())

    # A second deal that is only funded: balances per deal and over all deals.
    deals.commit("service_request", "REQUESTED", deal_id="deal-2", source_message_id="deal-2:m1")
    deals.commit(
        "funding_received",
        "FUNDED",
        deal_id="deal-2",
        credits=[credit("8", 70000, "deal-2")],
        postings=[posting("8", "held", 70000)],
    )
    assert deals.query("ledger.balances", {"deal_id": "deal-1"}) == settled
    assert deals.query("ledger.balances", {"deal_id": "deal-2"}) == {**ZERO_BALANCES, "held": 70000}
    assert deals.query("ledger.balances", {"deal_id": None}) == {**settled, "held": 70000}
    assert deals.query("ledger.balances", {"deal_id": "unknown"}) == ZERO_BALANCES
    assert [row["status"] for row in deals.read()["intents"]] == ["confirmed", "confirmed"]


def test_the_schema_itself_holds_the_uniqueness_rules(deals, host):
    """Rows written past the module still meet the constraints of the DDL."""
    deals.commit("service_request", "REQUESTED", source_message_id="m1", intents=[intent("payout", 49500)])
    deals.commit("funding_received", "FUNDED", credits=[credit("7")], postings=[posting("7", "held", 50000)])
    event = "INSERT INTO deal_events VALUES ('deal-1', ?, 'p', ?, 't', ?, 'a', '{}', 'S', '2026-11-27T12:00:00Z')"
    hash_1 = deals.read()["events"][0]["hash"]
    intent_row = "INSERT INTO deal_payment_intents VALUES (?, 'deal-1', ?, 1, 'EUR', 'iban', ?, NULL, 'now', 'now')"
    violations = [
        (event, (1, "new-hash", None)),  # primary key (deal_id, seq)
        (event, (9, hash_1, None)),  # unique hash
        (event, (9, "new-hash", "m1")),  # unique source_message_id
        (intent_row, ("i2", "refund", "prepared")),  # one active payout or refund per deal
        (intent_row, ("i2", "payout", "unknown")),
        ("INSERT INTO deal_bank_credits VALUES ('7', 'deal-1', 'r', 1, 'iban', 'now', 'funded')", ()),
        ("INSERT INTO deal_ledger_postings VALUES ('p9', 'deal-1', '7', 'held', 1, 'now')", ()),
    ]
    for sql, params in violations:
        with pytest.raises(sqlite3.IntegrityError):
            host.db.execute(sql, params)
    # What the constraints leave open: null message IDs, settled or other intents, other accounts.
    host.db.execute(event, (9, "new-hash", None))
    host.db.execute(event, (10, "newer-hash", None))
    host.db.execute(intent_row, ("i3", "refund", "confirmed"))
    host.db.execute(intent_row, ("i4", "fee", "prepared"))
    host.db.execute("INSERT INTO deal_ledger_postings VALUES ('p9', 'deal-1', '7', 'seller', 1, 'now')")


def test_the_write_order_satisfies_the_foreign_keys(deals, host):
    """PostgreSQL enforces the REFERENCES clauses; SQLite does once it is told to."""
    host.db.execute("PRAGMA foreign_keys = ON")
    deals.commit(
        "service_request",
        "REQUESTED",
        source_message_id="m1",
        outbox=outbox("o1"),
        deliveries=[delivery()],
        evaluations=[evaluation("integrity")],
        intents=[intent("payout", 49500)],
        credits=[credit("7")],
        postings=[posting("7", "held", 50000)],
    )
    update = {"intent_id": "deal-1:payout", "status": "confirmed", "postings": [posting("deal-1:payout", "held", -1)]}
    deals.command("intent.update", update)
    assert deals.counts() == {
        "deals": 1,
        "events": 1,
        "outbox": 1,
        "deliveries": 1,
        "evaluations": 1,
        "payment_intents": 1,
        "bank_credits": 1,
        "ledger_postings": 2,
    }
    with pytest.raises(sqlite3.IntegrityError):
        host.db.execute("INSERT INTO deal_bank_credits VALUES ('8', 'no-such-deal', 'r', 1, 'iban', 'now', 'funded')")
