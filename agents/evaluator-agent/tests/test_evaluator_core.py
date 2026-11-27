"""Unit tests of the evaluator core on fake ports."""

from __future__ import annotations

from typing import Any

import pytest
from cogit_finance_seams import LocalArtifacts
from cogit_messaging_shim import AgentKey, build_envelope, verify_envelope
from cogit_messaging_shim.testing import RecordingMessaging
from finance_fakes import (
    CONTRACTS,
    DEAL_ID,
    REQUIRED_FILES,
    TERMS_HASH,
    assert_contract,
    evaluation_request,
    make_zip,
)

from evaluator_agent.evaluator import EvaluatorCore

DEADLINE = "2026-11-27T10:01:00Z"


class Rig:
    def __init__(self) -> None:
        self.escrow = AgentKey.generate()
        self.artifacts = LocalArtifacts()
        self.messaging = RecordingMessaging()
        self.core = EvaluatorCore(
            messaging=self.messaging,
            artifacts=self.artifacts,
            escrow_did=self.escrow.did,
        )

    def deliver(self, names: list[str]) -> dict[str, Any]:
        return self.artifacts.put(make_zip(names), "application/zip")

    def judge(
        self, artifact: dict[str, Any], evaluator_id: str, **options: Any
    ) -> dict[str, Any]:
        """Send one request from E and return the verdict body."""
        request = evaluation_request(
            self.escrow, self.messaging.did, artifact, evaluator_id, **options
        )
        before = len(self.messaging.sent)
        assert self.core.handle_message(request) == {
            "status": "processed",
            "reason": None,
        }
        assert len(self.messaging.sent) == before + 1
        return self.messaging.sent[-1]["body"]


@pytest.fixture
def rig() -> Rig:
    return Rig()


def test_verdict_echoes_the_request_and_goes_to_escrow(rig: Rig) -> None:
    artifact = rig.deliver(REQUIRED_FILES)
    request = evaluation_request(rig.escrow, rig.messaging.did, artifact, "integrity")

    assert rig.core.handle_message(request)["status"] == "processed"

    (verdict,) = rig.messaging.sent
    assert verify_envelope(verdict)
    assert verdict["type_key"] == "finance.verdict"
    assert verdict["type_version"] == 1
    assert verdict["sender_did"] == rig.messaging.did
    assert verdict["recipient_did"] == rig.escrow.did
    assert verdict["conversation_id"] == DEAL_ID
    assert verdict["causation_id"] == request["message_id"]
    assert verdict["body"] == {
        "evaluation_request_id": f"{DEAL_ID}:d1:integrity@1",
        "terms_hash": TERMS_HASH,
        "delivery_id": f"{DEAL_ID}:d1",
        "artifact_sha256": artifact["sha256"],
        "evaluator_id": "integrity",
        "evaluator_version": 1,
        "outcome": "pass",
        "reasons": verdict["body"]["reasons"],
    }


def test_integrity_passes_when_digest_and_size_match(rig: Rig) -> None:
    verdict = rig.judge(rig.deliver(REQUIRED_FILES), "integrity")
    assert verdict["outcome"] == "pass"


@pytest.mark.parametrize(
    "change,reason",
    [
        ({"sha256": "0" * 64}, "sha256_mismatch"),
        ({"byte_length": 1}, "byte_length_mismatch"),
    ],
)
def test_integrity_fails_on_a_wrong_reference(
    rig: Rig, change: dict[str, Any], reason: str
) -> None:
    artifact = {**rig.deliver(REQUIRED_FILES), **change}
    verdict = rig.judge(artifact, "integrity")
    assert verdict["outcome"] == "fail"
    assert [text.split(":")[0] for text in verdict["reasons"]] == [reason]
    assert verdict["artifact_sha256"] == artifact["sha256"]


def test_required_files_passes_on_a_complete_zip(rig: Rig) -> None:
    verdict = rig.judge(
        rig.deliver(REQUIRED_FILES),
        "required-files",
        params={"required_files": REQUIRED_FILES},
    )
    assert verdict["outcome"] == "pass"


def test_required_files_fails_when_a_file_is_missing(rig: Rig) -> None:
    verdict = rig.judge(
        rig.deliver(["report.md", "data.csv"]),
        "required-files",
        params={"required_files": REQUIRED_FILES},
    )
    assert verdict["outcome"] == "fail"
    assert verdict["reasons"] == ["missing_file: summary.json"]


def test_required_files_fails_on_bytes_that_are_no_zip(rig: Rig) -> None:
    artifact = rig.artifacts.put(b"not a zip", "application/zip")
    verdict = rig.judge(
        artifact, "required-files", params={"required_files": REQUIRED_FILES}
    )
    assert verdict["outcome"] == "fail"
    assert verdict["reasons"][0].startswith("not_a_zip")


@pytest.mark.parametrize(
    "delivered_at,outcome",
    [
        ("2026-11-27T10:00:30Z", "pass"),
        (DEADLINE, "pass"),
        ("2026-11-27T10:01:01Z", "fail"),
    ],
)
def test_deadline_compares_delivery_time_and_deadline(
    rig: Rig, delivered_at: str, outcome: str
) -> None:
    verdict = rig.judge(
        rig.deliver(REQUIRED_FILES),
        "deadline",
        params={"delivery_deadline": DEADLINE},
        delivered_at=delivered_at,
    )
    assert verdict["outcome"] == outcome
    assert len(verdict["reasons"]) == 1


def test_error_when_the_check_cannot_run(rig: Rig) -> None:
    stored = rig.deliver(REQUIRED_FILES)
    missing = {**stored, "artifact_id": "art_missing"}

    unknown = rig.judge(stored, "plagiarism")
    assert unknown["outcome"] == "error"
    assert unknown["reasons"] == ["unknown_evaluator: plagiarism@1"]
    assert rig.judge(stored, "integrity", version=2)["outcome"] == "error"

    unreadable = rig.judge(missing, "integrity")
    assert unreadable["outcome"] == "error"
    assert unreadable["reasons"][0].startswith("artifact_unreadable")

    assert rig.judge(stored, "required-files")["outcome"] == "error"
    assert rig.judge(stored, "deadline")["outcome"] == "error"


def test_message_not_from_escrow_is_rejected(rig: Rig) -> None:
    stranger = AgentKey.generate()
    request = evaluation_request(
        rig.escrow,
        rig.messaging.did,
        rig.deliver(REQUIRED_FILES),
        "integrity",
        sender_key=stranger,
    )
    assert rig.core.handle_message(request) == {
        "status": "rejected",
        "reason": "unexpected_sender",
    }
    assert rig.messaging.sent == []


def test_other_types_and_bad_signatures_are_rejected(rig: Rig) -> None:
    receipt = build_envelope(
        rig.escrow,
        rig.escrow.did,
        "finance.receipt",
        1,
        rig.messaging.did,
        DEAL_ID,
        {"outcome": "settled"},
    )
    assert rig.core.handle_message(receipt) == {
        "status": "rejected",
        "reason": "unsupported_type",
    }

    request = evaluation_request(
        rig.escrow, rig.messaging.did, rig.deliver(REQUIRED_FILES), "integrity"
    )
    request["body"]["delivery_id"] = f"{DEAL_ID}:d2"
    assert rig.core.handle_message(request) == {
        "status": "rejected",
        "reason": "bad_signature",
    }
    assert rig.messaging.sent == []


def test_the_same_request_twice_gives_the_same_verdict_id(rig: Rig) -> None:
    request = evaluation_request(
        rig.escrow, rig.messaging.did, rig.deliver(REQUIRED_FILES), "integrity"
    )
    rig.core.handle_message(request)
    rig.core.handle_message(request)
    first, second = rig.messaging.sent
    assert first["message_id"] == second["message_id"]
    assert first["body"] == second["body"]


def test_messages_match_the_frozen_contracts(rig: Rig) -> None:
    if not CONTRACTS.is_dir():
        pytest.skip("the repository's contracts are not next to this project")
    artifact = rig.deliver(["report.md"])
    checks: list[tuple[str, dict[str, Any]]] = [
        ("integrity", {}),
        ("required-files", {"required_files": REQUIRED_FILES}),
        ("deadline", {"delivery_deadline": DEADLINE}),
        ("plagiarism", {}),
    ]
    requests = [
        evaluation_request(rig.escrow, rig.messaging.did, artifact, name, params)
        for name, params in checks
    ]

    for request in requests:
        assert rig.core.handle_message(request)["status"] == "processed"

    verdicts = rig.messaging.sent
    assert [verdict["body"]["outcome"] for verdict in verdicts] == [
        "pass",
        "fail",
        "pass",
        "error",
    ]
    for envelope in (*requests, *verdicts):
        assert_contract(envelope)
