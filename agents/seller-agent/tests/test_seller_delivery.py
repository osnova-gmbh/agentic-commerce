"""Unit tests of the seller core on fake ports: delivery and redelivery."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from typing import Any

import pytest
from cogit_messaging_shim import verify_envelope
from finance_fakes import (
    CONTRACTS,
    DEAL_ID,
    REQUIRED_FILES,
    Rig,
    assert_contract,
    decision,
    from_escrow,
    funding_confirmed,
    relay,
    service_request,
    terms_proposed,
)

from seller_agent.deliverable import build_deliverable

PROCESSED = {"status": "processed", "reason": None}


def stored_files(rig: Rig, delivery: dict[str, Any]) -> dict[str, bytes]:
    """Check the artifact reference against the stored bytes; return the zip's files."""
    artifact = delivery["body"]["artifact"]
    assert set(artifact) == {"artifact_id", "sha256", "byte_length", "media_type"}
    data = rig.artifacts.get(artifact["artifact_id"])
    assert artifact["sha256"] == hashlib.sha256(data).hexdigest()
    assert artifact["byte_length"] == len(data)
    assert artifact["media_type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def test_funding_is_followed_by_a_complete_delivery() -> None:
    rig = Rig(delay_s=3)
    inbound = funding_confirmed(rig.escrow, rig.did)

    assert rig.core.handle_message(inbound) == PROCESSED

    assert rig.slept == [3]
    (delivery,) = rig.messaging.sent
    assert verify_envelope(delivery)
    assert delivery["type_key"] == "finance.delivery"
    assert delivery["recipient_did"] == rig.escrow.did
    assert delivery["conversation_id"] == DEAL_ID
    assert delivery["causation_id"] == inbound["message_id"]
    assert delivery["body"]["attempt"] == 1
    files = stored_files(rig, delivery)
    assert list(files) == REQUIRED_FILES
    assert DEAL_ID in files["report.md"].decode()
    assert files["data.csv"].decode().splitlines()[0] == "region,units,revenue_minor"
    summary = json.loads(files["summary.json"])
    assert summary["deal_id"] == DEAL_ID
    assert summary["revenue_minor"] == 5288000


def test_broken_mode_omits_the_summary_on_the_first_attempt() -> None:
    rig = Rig(mode="broken")

    assert rig.core.handle_message(funding_confirmed(rig.escrow, rig.did)) == PROCESSED

    assert rig.slept == []
    (delivery,) = rig.messaging.sent
    assert delivery["body"]["attempt"] == 1
    assert list(stored_files(rig, delivery)) == ["report.md", "data.csv"]


def test_a_reject_with_attempts_left_is_followed_by_a_complete_redelivery() -> None:
    rig = Rig(mode="broken", delay_s=3)
    inbound = decision(rig.escrow, rig.did, "reject", attempts_left=1, attempt=1)

    assert rig.core.handle_message(inbound) == PROCESSED

    assert rig.slept == []
    (delivery,) = rig.messaging.sent
    assert delivery["type_key"] == "finance.delivery"
    assert delivery["causation_id"] == inbound["message_id"]
    assert delivery["body"]["attempt"] == 2
    assert list(stored_files(rig, delivery)) == REQUIRED_FILES


def test_other_decisions_need_no_action() -> None:
    rig = Rig(mode="broken")
    for inbound in (
        decision(rig.escrow, rig.did, "approve", attempts_left=1, attempt=1),
        decision(rig.escrow, rig.did, "reject", attempts_left=0, attempt=2),
    ):
        assert rig.core.handle_message(inbound) == PROCESSED
    assert rig.messaging.sent == []


def test_a_decision_without_a_delivery_attempt_is_rejected() -> None:
    rig = Rig()
    inbound = decision(rig.escrow, rig.did, "reject", attempts_left=1, attempt=1)
    body = {**inbound["body"], "delivery_id": "7"}
    broken = from_escrow(rig.escrow, rig.did, "finance.decision", body)
    assert rig.core.handle_message(broken) == {
        "status": "rejected",
        "reason": "invalid_body",
    }
    assert rig.messaging.sent == []


def test_the_same_message_twice_gives_the_same_reply_id() -> None:
    rig = Rig(mode="broken")
    inbound = [
        relay(rig.escrow, rig.did, service_request(rig.buyer, rig.escrow.did)),
        funding_confirmed(rig.escrow, rig.did),
        decision(rig.escrow, rig.did, "reject", attempts_left=1, attempt=1),
    ]

    for envelope in (*inbound, *inbound):
        assert rig.core.handle_message(envelope) == PROCESSED

    first, second = rig.messaging.sent[:3], rig.messaging.sent[3:]
    assert [item["type_key"] for item in first] == [
        "finance.quote",
        "finance.delivery",
        "finance.delivery",
    ]
    assert [item["message_id"] for item in first] == [
        item["message_id"] for item in second
    ]
    assert len({item["message_id"] for item in first}) == 3
    assert [item["body"] for item in first] == [item["body"] for item in second]


def test_the_deliverable_is_deterministic() -> None:
    assert build_deliverable(DEAL_ID) == build_deliverable(DEAL_ID)
    assert build_deliverable(DEAL_ID) != build_deliverable(DEAL_ID.replace("5", "6"))
    broken = build_deliverable(DEAL_ID, include_summary=False)
    assert len(broken) < len(build_deliverable(DEAL_ID))


def test_messages_match_the_frozen_contracts() -> None:
    if not CONTRACTS.is_dir():
        pytest.skip("the repository's contracts are not next to this project")
    rig = Rig(mode="broken")
    request = service_request(rig.buyer, rig.escrow.did)
    inbound = [
        relay(rig.escrow, rig.did, request),
        terms_proposed(rig.escrow, rig.did),
        funding_confirmed(rig.escrow, rig.did),
        decision(rig.escrow, rig.did, "reject", attempts_left=1, attempt=1),
    ]

    for envelope in inbound:
        assert rig.core.handle_message(envelope) == PROCESSED

    assert [item["type_key"] for item in rig.messaging.sent] == [
        "finance.quote",
        "finance.accept_terms",
        "finance.delivery",
        "finance.delivery",
    ]
    for envelope in (request, *inbound, *rig.messaging.sent):
        assert_contract(envelope)
