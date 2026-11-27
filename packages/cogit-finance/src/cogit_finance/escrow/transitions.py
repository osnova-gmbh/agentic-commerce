"""SPEC §5.2 as data: every transition of a deal, with the demo's cut line.

``TRANSITIONS`` is the whole table. A row of the SPEC that names several source
states, or that E carries out as several events, appears as several entries with
the same ``row`` number. Entries with ``in_demo`` false are known but not built:
their messages are refused with ``not_in_demo`` and E never records their events.
"""

from __future__ import annotations

from dataclasses import dataclass

NONE = "none"  # no deal yet
REQUESTED = "REQUESTED"
QUOTED = "QUOTED"
ACCEPTED = "ACCEPTED"
FUNDING_REQUESTED = "FUNDING_REQUESTED"
FUNDED = "FUNDED"
DELIVERED = "DELIVERED"
EVALUATING = "EVALUATING"
APPROVED = "APPROVED"
REJECTED = "REJECTED"
RELEASING = "RELEASING"
REFUNDING = "REFUNDING"
DISPUTED = "DISPUTED"
SETTLED = "SETTLED"
REFUNDED = "REFUNDED"
DECLINED = "DECLINED"
EXPIRED = "EXPIRED"
CANCELLED = "CANCELLED"

TERMINAL = (SETTLED, REFUNDED, DECLINED, EXPIRED, CANCELLED)
STATES = (
    REQUESTED,
    QUOTED,
    ACCEPTED,
    FUNDING_REQUESTED,
    FUNDED,
    DELIVERED,
    EVALUATING,
    APPROVED,
    REJECTED,
    RELEASING,
    REFUNDING,
    DISPUTED,
    *TERMINAL,
)
DEMO_STATES = (
    REQUESTED,
    QUOTED,
    ACCEPTED,
    FUNDING_REQUESTED,
    FUNDED,
    DELIVERED,
    EVALUATING,
    APPROVED,
    REJECTED,
    RELEASING,
    SETTLED,
)
# A deal never rests in these: E moves on at once. Finding one means a run died.
TRANSIENT = (ACCEPTED, DELIVERED, APPROVED, RELEASING)

ILLEGAL_IN_STATE = "illegal_in_state"
NOT_IN_DEMO = "not_in_demo"


@dataclass(frozen=True)
class Transition:
    row: int  # row of the SPEC §5.2 table, counted from 1
    source: str
    trigger: str  # message name, E's event type, or timer name
    kind: str  # message | escrow | bank | timer
    actors: tuple[str, ...]
    guard: str
    target: str
    in_demo: bool


# Guard column of the SPEC table, by row.
GUARDS: dict[int, str] = {
    1: "Buyer org registered with role buyer; offer active; max_price >= offer "
    "price; within the buyer's spending limit",
    2: "Seller owns the offer; every named evaluator registered and independent "
    "of both parties. E then sends terms_proposed",
    3: "none",
    4: "quote_ttl passes",
    5: "valid_until passes",
    6: "terms_hash equals the proposed terms; once per party",
    7: "Both parties accepted; payment_request follows at once",
    8: "No credit received for the deal",
    9: "Bank credit with the deal reference and the exact price",
    10: "funding_due_by passes",
    11: "attempt = 1; before delivery_deadline",
    12: "delivery_deadline passes",
    13: "E sends an evaluation_request to each named evaluator",
    14: "Correlates with the current delivery (§9); E decides once the policy does",
    15: "An evaluator errors or misses respond_by twice (one re-request)",
    16: "E prepares payout and fee intents",
    17: "attempts_left > 0 and before rework_deadline",
    18: "Within dispute_window",
    19: "No redelivery possible and dispute_window passed without dispute",
    20: "Ruling: release or refund",
    21: "Bank confirms the payout intent",
    22: "Bank confirms the refund intent",
    23: "E sends the receipt",
}

MSG, ESC, BANK, TIMER = "message", "escrow", "bank", "timer"
E = "escrow"
_OPEN = (REQUESTED, QUOTED, ACCEPTED, FUNDING_REQUESTED)


def _rows(
    row: int,
    sources: tuple[str, ...],
    trigger: str,
    kind: str,
    actors: str,
    target: str | None = None,
    demo: bool = True,
) -> list[Transition]:
    """One entry per source state; ``target`` None means the state is unchanged."""
    who = tuple(actors.split("|"))
    return [
        Transition(row, src, trigger, kind, who, GUARDS[row], target or src, demo)
        for src in sources
    ]


TRANSITIONS: tuple[Transition, ...] = (
    *_rows(1, (NONE,), "service_request", MSG, "buyer", REQUESTED),
    *_rows(2, (REQUESTED,), "quote", MSG, "seller", QUOTED),
    *_rows(2, (QUOTED,), "terms_proposed", ESC, E),
    *_rows(3, (REQUESTED, QUOTED), "decline", MSG, "buyer|seller", DECLINED, False),
    *_rows(4, (REQUESTED,), "quote_ttl", TIMER, E, EXPIRED, False),
    *_rows(5, (QUOTED,), "valid_until", TIMER, E, EXPIRED, False),
    *_rows(6, (QUOTED,), "accept_terms", MSG, "buyer|seller"),
    *_rows(7, (QUOTED,), "terms_countersigned", ESC, E, ACCEPTED),
    *_rows(7, (ACCEPTED,), "payment_request", ESC, E, FUNDING_REQUESTED),
    *_rows(8, _OPEN, "cancel", MSG, "buyer", CANCELLED, False),
    *_rows(9, (FUNDING_REQUESTED,), "funding_received", BANK, E, FUNDED),
    *_rows(10, (FUNDING_REQUESTED,), "funding_due_by", TIMER, E, CANCELLED, False),
    *_rows(11, (FUNDED,), "delivery", MSG, "seller", DELIVERED),
    *_rows(12, (FUNDED,), "delivery_deadline", TIMER, E, REFUNDING, False),
    *_rows(13, (DELIVERED,), "evaluation_requested", ESC, E, EVALUATING),
    *_rows(14, (EVALUATING,), "verdict", MSG, "evaluator"),
    *_rows(14, (EVALUATING,), "decision", ESC, E, APPROVED),
    *_rows(14, (EVALUATING,), "decision", ESC, E, REJECTED),
    *_rows(15, (EVALUATING,), "evaluator_unavailable", TIMER, E, DISPUTED, False),
    *_rows(16, (APPROVED,), "payout_submitted", ESC, E, RELEASING),
    *_rows(17, (REJECTED,), "delivery", MSG, "seller", DELIVERED),
    *_rows(18, (REJECTED,), "dispute", MSG, "buyer|seller", DISPUTED, False),
    *_rows(19, (REJECTED,), "rework_exhausted", TIMER, E, REFUNDING, False),
    *_rows(20, (DISPUTED,), "ruling", MSG, "operator", RELEASING, False),
    *_rows(20, (DISPUTED,), "ruling", MSG, "operator", REFUNDING, False),
    *_rows(21, (RELEASING,), "payout_confirmed", BANK, E, SETTLED),
    *_rows(22, (REFUNDING,), "refund_confirmed", BANK, E, REFUNDED, False),
    *_rows(23, (SETTLED,), "receipt", ESC, E),
    *_rows(23, (REFUNDED,), "receipt", ESC, E, None, False),
)

MESSAGE_TRIGGERS = frozenset(t.trigger for t in TRANSITIONS if t.kind == "message")
DEMO_MESSAGE_TRIGGERS = frozenset(
    t.trigger for t in TRANSITIONS if t.kind == "message" and t.in_demo
)


def find(state: str, trigger: str) -> tuple[Transition, ...]:
    """Every table entry for this trigger in this state."""
    return tuple(t for t in TRANSITIONS if t.source == state and t.trigger == trigger)


def refuse_message(state: str, trigger: str) -> str | None:
    """Why a message is not allowed in this state, or None when a row allows it."""
    entries = [t for t in find(state, trigger) if t.kind == "message"]
    if not entries:
        return NOT_IN_DEMO if trigger not in DEMO_MESSAGE_TRIGGERS else ILLEGAL_IN_STATE
    if not any(t.in_demo for t in entries):
        return NOT_IN_DEMO
    return None


def is_legal(state: str, trigger: str, target: str) -> bool:
    """True when the demo's part of the table has exactly this transition."""
    return any(t.in_demo and t.target == target for t in find(state, trigger))
