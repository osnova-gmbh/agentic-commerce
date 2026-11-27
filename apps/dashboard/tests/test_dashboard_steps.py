import pytest
from dashboard.steps import STEPS, compute_steps, decision_outcome, progress
from dashboard_helpers import AGREE, BROKEN, HAPPY, PASSED, REJECTED, fixture_read, log, statuses

# The strip after each event of the happy path, by the event that came last.
AFTER = {
    "service_request": "DDDAPPPPPP",
    "quote": "DDDAPPPPPP",
    "terms_proposed": "DDDAPPPPPP",
    "accept_terms": "DDDAPPPPPP",
    "terms_countersigned": "DDDDAPPPPP",
    "payment_request": "DDDDAPPPPP",
    "funding_received": "DDDDDAPPPP",
    "delivery": "DDDDDDDAPP",
    "evaluation_requested": "DDDDDDDAPP",
    "verdict": "DDDDDDDAPP",
    "approve": "DDDDDDDDDA",
    "payout_submitted": "DDDDDDDDDA",
    "payout_confirmed": "DDDDDDDDDD",
    "receipt": "DDDDDDDDDD",
}


def note(steps: list[dict], key: str) -> str:
    return next(step["note"] for step in steps if step["key"] == key)


def test_the_strip_has_the_ten_steps_in_order():
    steps = compute_steps([])
    assert [step["n"] for step in steps] == list(range(1, 11))
    assert [step["label"] for step in steps] == [
        "Discover", "Catalog", "Request", "Confirm", "Fund", "Work", "Deliver", "Evaluate", "Approve", "Pay out",
    ]  # fmt: skip
    assert [step["key"] for step in steps] == [key for key, _ in STEPS]
    assert statuses(steps) == "PPPPPPPPPP"


def test_happy_path_ends_with_every_step_done():
    steps = compute_steps(log(HAPPY))
    assert statuses(steps) == "DDDDDDDDDD"
    assert note(steps, "fund") == "released" and note(steps, "deliver") == "attempt 1"


@pytest.mark.parametrize("length", range(1, len(HAPPY) + 1))
def test_every_prefix_of_the_happy_path(length):
    steps = compute_steps(log(HAPPY[:length]))
    assert statuses(steps) == AFTER[HAPPY[length - 1]]
    assert statuses(steps).count("A") <= 1 and "F" not in statuses(steps)


def test_discover_and_catalog_are_done_once_the_deal_exists():
    assert statuses(compute_steps(log(HAPPY[:1])))[:3] == "DDD"


def test_fund_is_the_moment_the_money_is_held():
    assert note(compute_steps(log(HAPPY[:6])), "fund") == ""
    assert note(compute_steps(log(HAPPY[:7])), "fund") == "awaiting payment"
    for length in range(8, 16):  # funding_received up to payout_submitted
        assert note(compute_steps(log(HAPPY[:length])), "fund") == "held in escrow"
    assert note(compute_steps(log(HAPPY[:16])), "fund") == "released"
    assert note(compute_steps(log(HAPPY[:15])), "payout") == "submitted to the bank"


def test_a_rejected_evaluation_fails_step_eight():
    steps = compute_steps(log(AGREE + REJECTED))
    assert statuses(steps) == "DDDDDDDFPP"
    assert note(steps, "evaluate") == "rejected" and note(steps, "deliver") == "attempt 1"
    assert note(steps, "fund") == "held in escrow"  # a rejection moves no money


def test_a_redelivery_makes_evaluation_current_again():
    redelivered = AGREE + REJECTED + ["delivery"]
    assert statuses(compute_steps(log(redelivered))) == "DDDDDDDAPP"
    steps = compute_steps(log(redelivered + ["evaluation_requested", "verdict", "verdict"]))
    assert statuses(steps) == "DDDDDDDAPP"
    assert note(steps, "deliver") == "attempt 2" and note(steps, "evaluate") == "2 verdicts in"


def test_a_successful_redelivery_turns_steps_seven_to_ten_green():
    assert statuses(compute_steps(log(AGREE + REJECTED + PASSED))) == "DDDDDDDDDA"
    steps = compute_steps(log(BROKEN))
    assert statuses(steps) == "DDDDDDDDDD"
    assert note(steps, "deliver") == "attempt 2" and note(steps, "evaluate") == ""


def test_a_second_rejection_fails_step_eight_again():
    assert statuses(compute_steps(log(AGREE + REJECTED + REJECTED))) == "DDDDDDDFPP"


def test_events_are_read_in_seq_order_and_unknown_types_are_ignored():
    events = log(HAPPY[:9]) + [{"deal_id": "d", "seq": 10, "event_type": "something_new", "state_after": "DELIVERED"}]
    assert statuses(compute_steps(list(reversed(events)))) == "DDDDDDDAPP"


def test_the_decision_is_read_from_the_state_it_led_to_or_from_its_body():
    assert decision_outcome({"state_after": "REJECTED", "body": {"outcome": "approve"}}) == "reject"
    assert decision_outcome({"state_after": "APPROVED", "body": {}}) == "approve"
    assert decision_outcome({"state_after": "EVALUATING", "body": {"decision": {"outcome": "reject"}}}) == "reject"
    assert decision_outcome({"state_after": "EVALUATING", "body": {"sent": [{"body": {"outcome": "approve"}}]}}) == "approve"
    assert decision_outcome({"state_after": "EVALUATING", "body": {}}) is None


def test_progress_counts_only_the_current_delivery():
    seen = progress(log(AGREE + REJECTED + ["delivery", "evaluation_requested", "verdict"]))
    assert (seen.attempt, seen.verdicts, seen.outcome) == (2, 1, None)
    assert seen.funded and not seen.paid


@pytest.mark.parametrize("name", ["happy", "broken"])
def test_fixture_runs_end_with_every_step_done(name):
    events = fixture_read(name)["events"]
    assert statuses(compute_steps(events)) == "DDDDDDDDDD"
    for length in range(1, len(events) + 1):
        strip = statuses(compute_steps(events[:length]))
        assert strip.rstrip("P") == strip.rstrip("P").replace("P", "")  # no gap: pending steps come last
        assert strip.count("A") + strip.count("F") <= 1


def test_the_broken_fixture_shows_the_rejection_until_the_redelivery():
    events = fixture_read("broken")["events"]
    kinds = [event["event_type"] for event in events]
    rejected_at = kinds.index("decision") + 1
    assert statuses(compute_steps(events[:rejected_at])) == "DDDDDDDFPP"
    assert kinds[rejected_at] == "delivery"
    assert statuses(compute_steps(events[: rejected_at + 1])) == "DDDDDDDAPP"
