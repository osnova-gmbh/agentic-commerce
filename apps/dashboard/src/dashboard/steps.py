"""The ten demo steps (SPEC §13) derived from a deal's events. Pure functions, no I/O."""

from __future__ import annotations

from typing import NamedTuple

STEPS = (
    ("discover", "Discover"),
    ("catalog", "Catalog"),
    ("request", "Request"),
    ("confirm", "Confirm"),
    ("fund", "Fund"),
    ("work", "Work"),
    ("deliver", "Deliver"),
    ("evaluate", "Evaluate"),
    ("approve", "Approve"),
    ("payout", "Pay out"),
)
DONE, ACTIVE, FAILED, PENDING = "done", "active", "failed", "pending"


class Progress(NamedTuple):
    """What the event log says has happened so far."""

    exists: bool
    confirmed: bool  # terms countersigned
    payment_requested: bool
    funded: bool  # the buyer's money is in escrow
    attempt: int  # deliveries so far; the last one is the current delivery
    verdicts: int  # verdicts recorded for the current delivery
    outcome: str | None  # decision on the current delivery: approve | reject
    payout_submitted: bool
    paid: bool  # the bank confirmed the payout


def find_dict(value: object, key: str, depth: int = 6) -> dict | None:
    """The first dict holding ``key``, searched through nested dicts and lists."""
    if depth < 0:
        return None
    if isinstance(value, dict):
        if key in value:
            return value
        value = list(value.values())
    if isinstance(value, list):
        for item in value:
            found = find_dict(item, key, depth - 1)
            if found is not None:
                return found
    return None


def decision_outcome(event: dict) -> str | None:
    """``approve`` or ``reject`` for a decision event: from the state it led to, else its body."""
    by_state = {"APPROVED": "approve", "REJECTED": "reject"}.get(event.get("state_after") or "")
    if by_state:
        return by_state
    outcome = (find_dict(event.get("body"), "outcome") or {}).get("outcome")
    return outcome if outcome in ("approve", "reject") else None


def progress(events: list[dict]) -> Progress:
    events = sorted(events, key=lambda event: event["seq"])
    types = [event["event_type"] for event in events]
    deliveries = [index for index, kind in enumerate(types) if kind == "delivery"]
    current = events[deliveries[-1] + 1 :] if deliveries else []  # everything after the last delivery
    decisions = [event for event in current if event["event_type"] == "decision"]
    return Progress(
        exists=bool(events),
        confirmed="terms_countersigned" in types,
        payment_requested="payment_request" in types,
        funded="funding_received" in types,
        attempt=len(deliveries),
        verdicts=sum(1 for event in current if event["event_type"] == "verdict"),
        outcome=decision_outcome(decisions[-1]) if decisions else None,
        payout_submitted="payout_submitted" in types,
        paid="payout_confirmed" in types,
    )


def compute_steps(events: list[dict]) -> list[dict]:
    """Map deal events to the ten-step strip: ``[{n, key, label, status, note}]``.

    Steps 1 to 3 are done once the deal exists (it starts with the service request).
    A rejected evaluation fails step 8; a new delivery makes it current again, so a
    successful redelivery ends with steps 7 to 10 done.
    """
    p = progress(events)
    delivered, approved, rejected = p.attempt > 0, p.outcome == "approve", p.outcome == "reject"
    status = {
        "discover": DONE if p.exists else PENDING,
        "catalog": DONE if p.exists else PENDING,
        "request": DONE if p.exists else PENDING,
        "confirm": DONE if p.confirmed else ACTIVE if p.exists else PENDING,
        "fund": DONE if p.funded else ACTIVE if p.confirmed else PENDING,
        "work": DONE if delivered else ACTIVE if p.funded else PENDING,
        "deliver": DONE if delivered else PENDING,
        "evaluate": DONE if approved else FAILED if rejected else ACTIVE if delivered else PENDING,
        "approve": DONE if approved else PENDING,
        "payout": DONE if p.paid else ACTIVE if approved else PENDING,
    }
    note = dict.fromkeys(status, "")
    if p.paid:
        note["fund"] = "released"
    elif p.funded:
        note["fund"] = "held in escrow"
    elif p.payment_requested:
        note["fund"] = "awaiting payment"
    if delivered:
        note["deliver"] = f"attempt {p.attempt}"
    if rejected:
        note["evaluate"] = "rejected"
    elif status["evaluate"] == ACTIVE and p.verdicts:
        note["evaluate"] = f"{p.verdicts} verdict{'' if p.verdicts == 1 else 's'} in"
    if status["payout"] == ACTIVE and p.payout_submitted:
        note["payout"] = "submitted to the bank"
    return [
        {"n": number, "key": key, "label": label, "status": status[key], "note": note[key]}
        for number, (key, label) in enumerate(STEPS, start=1)
    ]
