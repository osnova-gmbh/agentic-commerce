"""Assertions on a ``deal.read`` result, shared by E's tests."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from cogit_messaging_shim import ZERO_HASH, event_hash, verify_envelope

Row = dict[str, Any]
REPO = Path(__file__).resolve().parents[3]
CONTRACT_FIXTURES = REPO / "contracts" / "fixtures"


def load_sequence(name: str) -> Row:
    """One of the frozen event-sequence fixtures of the contracts folder."""
    return json.loads((CONTRACT_FIXTURES / name).read_text(encoding="utf-8"))


def roles_of(deal: Row) -> dict[str, set[str]]:
    """Role name -> DIDs, read from the deal itself (terms and evaluations)."""
    terms = deal["deal"]["terms"]
    return {
        "buyer": {terms["buyer_did"]},
        "seller": {terms["seller_did"]},
        "escrow": {terms["escrow_did"]},
        "evaluator": {row["evaluator_did"] for row in deal["evaluations"]},
    }


def assert_sequence(deal: Row, spec: Row) -> None:
    """The deal's events are exactly the fixture's sequence, actors included."""
    events = deal["events"]
    roles = roles_of(deal)
    position = 0
    for entry in spec["events"]:
        allowed = set().union(*(roles[name] for name in entry["actor"].split("|")))
        count = 0
        while (
            position < len(events)
            and count < entry["max"]
            and events[position]["event_type"] == entry["event_type"]
        ):
            assert events[position]["actor_did"] in allowed, events[position]
            position += 1
            count += 1
        assert count >= entry["min"], (entry, position)
    assert position == len(events), [e["event_type"] for e in events[position:]]
    assert deal["deal"]["state"] == spec["final_state"]


def assert_chain(deal: Row) -> None:
    """Sequence numbers run from 1, hashes link, and the head is the last event."""
    previous = ZERO_HASH
    for number, event in enumerate(deal["events"], start=1):
        assert event["seq"] == number
        assert event["prev_hash"] == previous
        assert event["hash"] == event_hash(event)
        previous = event["hash"]
    head = deal["deal"]
    assert (head["head_seq"], head["head_hash"]) == (len(deal["events"]), previous)


def assert_envelopes(deal: Row) -> None:
    """A message-sourced event holds the verbatim signed envelope of its actor."""
    escrow_did = deal["deal"]["terms"]["escrow_did"]
    for event in deal["events"]:
        if event["source_message_id"] is None:
            assert event["actor_did"] == escrow_did
            continue
        assert set(event["body"]) == {"envelope"}
        envelope = event["body"]["envelope"]
        assert verify_envelope(envelope)
        assert envelope["message_id"] == event["source_message_id"]
        assert envelope["sender_did"] == event["actor_did"]
        assert envelope["type_key"] == f"finance.{event['event_type']}"
        assert envelope["conversation_id"] == event["deal_id"]


def frozen(world: Any) -> Row:
    """Everything a refused message must leave untouched."""
    m = world.modules
    return copy.deepcopy(
        {
            "deals": m.deals,
            "events": m.events,
            "outbox": m.outbox,
            "messages": m.messages,
            "rows": [m.deliveries, m.evaluations, m.intents, m.credits],
            "postings": list(m.postings.values()),
            "bank": world.bank.transfers,
        }
    )


def refused(world: Any, result: Row, reason: str, before: Row) -> None:
    assert result == {"status": "rejected", "reason": reason}
    assert frozen(world) == before
