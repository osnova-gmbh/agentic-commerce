from __future__ import annotations

from deals_kit import NEW_DEAL, TERMS, TERMS_HASH, credit, delivery, evaluation, intent, posting

DEAL_KEYS = {
    "deal_id",
    "buyer_org_id",
    "seller_org_id",
    "offer_id",
    "state",
    "head_seq",
    "head_hash",
    "terms",
    "terms_hash",
    "created_at",
    "updated_at",
}
EVENT_KEYS = {
    "deal_id",
    "seq",
    "prev_hash",
    "hash",
    "event_type",
    "source_message_id",
    "actor_did",
    "body",
    "state_after",
    "recorded_at",
}
LIST_KEYS = [
    "deal_id",
    "state",
    "buyer_org_id",
    "seller_org_id",
    "offer_id",
    "head_seq",
    "price_minor",
    "currency",
    "created_at",
    "updated_at",
]
EVALUATORS = ("integrity", "required-files", "deadline")


def test_an_empty_module_returns_empty_lists_and_zero_balances(deals):
    assert deals.query("deal.list") == {"deals": []}
    assert deals.query("outbox.pending") == {"entries": []}
    assert deals.read("nobody") == dict(deal=None, events=[], deliveries=[], evaluations=[], intents=[], credits=[])
    assert deals.query("ledger.balances") == {"held": 0, "seller": 0, "fee": 0, "buyer_refund": 0, "returned": 0}


def test_deal_read_returns_the_deal_with_all_its_rows(deals, clock):
    deals.commit("service_request", "REQUESTED", source_message_id="m1")
    deals.commit("terms_proposed", "TERMS_PROPOSED", deal={"terms": TERMS, "terms_hash": TERMS_HASH})
    deals.commit("funding_received", "FUNDED", credits=[credit("7")], postings=[posting("7", "held", 50000)])
    deals.commit("delivery", "DELIVERED", source_message_id="m2", deliveries=[delivery(1)])
    requested = [evaluation(evaluator_id) for evaluator_id in EVALUATORS]
    deals.commit("evaluation_requested", "EVALUATING", evaluations=requested)
    clock.advance(30)
    deals.commit("payout_submitted", "PAYING_OUT", intents=[intent("payout", 49500), intent("fee", 500)])
    # Rows of another deal stay out of the answer.
    deals.commit("service_request", "REQUESTED", deal_id="deal-2", deliveries=[delivery(1, "deal-2")])

    read = deals.read()
    assert set(read) == {"deal", "events", "deliveries", "evaluations", "intents", "credits"}
    assert set(read["deal"]) == DEAL_KEYS
    assert read["deal"]["terms"] == TERMS and read["deal"]["terms"]["price_minor"] == 50000
    assert len(read["events"]) == 6 and all(set(event) == EVENT_KEYS for event in read["events"])
    assert read["deliveries"] == [{"deal_id": "deal-1", **delivery(1)}]
    assert list(read["deliveries"][0])[:2] == ["delivery_id", "deal_id"]
    by_id = {row["evaluation_request_id"]: row for row in read["evaluations"]}
    assert by_id == {row["evaluation_request_id"]: row for row in requested}
    assert read["credits"] == [{"deal_id": "deal-1", **credit("7")}]
    assert [row["intent_id"] for row in read["intents"]] == ["deal-1:fee", "deal-1:payout"]
    assert set(read["intents"][0]) == {
        "intent_id",
        "deal_id",
        "kind",
        "amount_minor",
        "currency",
        "to_iban",
        "status",
        "bank_ref",
        "created_at",
        "updated_at",
    }
    assert read["intents"][0]["created_at"] == clock.ts
    assert len(deals.read("deal-2")["deliveries"]) == 1


def test_deliveries_and_evaluations_are_upserted_by_their_id(deals):
    deals.commit("service_request", "REQUESTED", source_message_id="m1")
    deals.commit("delivery", "DELIVERED", deliveries=[delivery(1)])
    deals.commit("evaluation_requested", "EVALUATING", evaluations=[evaluation(name) for name in EVALUATORS])

    # A verdict names only what changed; a whole row replaces what it names.
    verdict = {"evaluation_request_id": "deal-1:d1:required-files@1", "verdict_message_id": "v1", "outcome": "fail"}
    deals.commit("verdict", "EVALUATING", source_message_id="v1", evaluations=[verdict])
    whole = evaluation("integrity", verdict_message_id="v2", outcome="pass")
    deals.commit("verdict", "EVALUATING", source_message_id="v2", evaluations=[whole])
    rejected = {"delivery_id": "deal-1:d1", "status": "rejected"}
    redelivered = delivery(2, artifact_id="art_fixed", delivered_at="2026-11-27T12:03:00Z")
    deals.commit("decision", "REJECTED", deliveries=[rejected])
    deals.commit("delivery", "DELIVERED", deliveries=[redelivered], evaluations=[evaluation("integrity", attempt=2)])

    read = deals.read()
    assert read["deliveries"] == [
        {"deal_id": "deal-1", **delivery(1, status="rejected")},
        {"deal_id": "deal-1", **redelivered},
    ]
    outcomes = [(row["delivery_id"], row["evaluator_id"], row["outcome"]) for row in read["evaluations"]]
    assert outcomes == [
        ("deal-1:d1", "deadline", None),
        ("deal-1:d1", "integrity", "pass"),
        ("deal-1:d1", "required-files", "fail"),
        ("deal-1:d2", "integrity", None),
    ]
    failed = read["evaluations"][2]
    assert failed == evaluation("required-files", verdict_message_id="v1", outcome="fail")
    assert deals.counts()["deliveries"] == 2 and deals.counts()["evaluations"] == 4

    # A row of one deal cannot be rewritten through another deal's commit.
    foreign = deals.commit_args("delivery", "DELIVERED", deal_id="deal-2", deliveries=[rejected])
    assert deals.fails("deal.commit", foreign) == "invalid_argument"


def test_deal_list_is_newest_first_with_the_price_from_the_terms(deals, clock):
    deals.commit("service_request", "REQUESTED", deal_id="deal-old", source_message_id="m1")
    deals.commit("quote", "QUOTED", deal_id="deal-old", source_message_id="m2")
    terms = {**TERMS, "deal_id": "deal-old", "price_minor": 70000}
    clock.advance(60)
    updated_at = clock.ts
    proposed = {"terms": terms, "terms_hash": TERMS_HASH}
    deals.commit("terms_proposed", "TERMS_PROPOSED", deal_id="deal-old", deal=proposed)
    clock.advance(60)
    other_parties = {**NEW_DEAL, "buyer_org_id": "buyer-2", "offer_id": "offer-7"}
    deals.commit("service_request", "REQUESTED", deal_id="deal-new", source_message_id="m3", deal=other_parties)

    listed = deals.query("deal.list")["deals"]
    assert [list(row) for row in listed] == [LIST_KEYS, LIST_KEYS]
    assert listed == [
        {
            "deal_id": "deal-new",
            "state": "REQUESTED",
            "buyer_org_id": "buyer-2",
            "seller_org_id": "seller-co",
            "offer_id": "offer-7",
            "head_seq": 1,
            "price_minor": None,
            "currency": None,
            "created_at": clock.ts,
            "updated_at": clock.ts,
        },
        {
            "deal_id": "deal-old",
            "state": "TERMS_PROPOSED",
            **NEW_DEAL,
            "head_seq": 3,
            "price_minor": 70000,
            "currency": "EUR",
            "created_at": "2026-11-27T12:00:00Z",
            "updated_at": updated_at,
        },
    ]
