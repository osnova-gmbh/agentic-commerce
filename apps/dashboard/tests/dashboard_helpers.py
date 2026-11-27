"""Shared values and helpers of the dashboard tests."""

from __future__ import annotations

import json
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = APP_ROOT / "fixtures"
CONTRACT_FIXTURES = APP_ROOT.parents[1] / "contracts" / "fixtures"

STATES = {
    "service_request": "REQUESTED",
    "quote": "QUOTED",
    "terms_proposed": "QUOTED",
    "accept_terms": "QUOTED",
    "terms_countersigned": "ACCEPTED",
    "payment_request": "FUNDING_REQUESTED",
    "funding_received": "FUNDED",
    "delivery": "DELIVERED",
    "evaluation_requested": "EVALUATING",
    "verdict": "EVALUATING",
    "approve": "APPROVED",
    "reject": "REJECTED",
    "payout_submitted": "RELEASING",
    "payout_confirmed": "SETTLED",
    "receipt": "SETTLED",
}
AGREE = ["service_request", "quote", "terms_proposed", "accept_terms", "accept_terms", "terms_countersigned",
         "payment_request", "funding_received"]  # fmt: skip
PASSED = ["delivery", "evaluation_requested", "verdict", "verdict", "verdict", "approve"]
REJECTED = ["delivery", "evaluation_requested", "verdict", "verdict", "reject"]
PAY = ["payout_submitted", "payout_confirmed", "receipt"]
HAPPY = AGREE + PASSED + PAY  # SPEC §13.1, 17 events
BROKEN = AGREE + REJECTED + PASSED + PAY


def log(kinds: list[str]) -> list[dict]:
    """Bare deal events; ``approve`` and ``reject`` stand for the two decisions."""
    return [
        {
            "deal_id": "d",
            "seq": seq,
            "event_type": "decision" if kind in ("approve", "reject") else kind,
            "state_after": STATES[kind],
            "body": {},
        }
        for seq, kind in enumerate(kinds, start=1)
    ]


def statuses(steps: list[dict]) -> str:
    """Ten letters: D done, A active, F failed, P pending."""
    return "".join(step["status"][0].upper() for step in steps)


def fixture_deal_id(name: str) -> str:
    return json.loads((FIXTURES / name / "deals.json").read_text())["deals"][0]["deal_id"]


def fixture_read(name: str) -> dict:
    return json.loads((FIXTURES / name / "deals" / f"{fixture_deal_id(name)}.json").read_text())
