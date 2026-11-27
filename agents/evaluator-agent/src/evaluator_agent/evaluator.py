# pyright: basic
"""Evaluator core: run one deterministic check on a delivery and answer with a verdict.

Plain Python. The ports come in through the constructor and nothing here imports
the Cogit SDK, so the behaviour is unit-tested with fakes. The core keeps no state:
everything a verdict needs is in the evaluation request and the stored artifact.
"""

from __future__ import annotations

import hashlib
import io
import zipfile
from collections.abc import Callable
from typing import Any

from cogit_finance_seams import ArtifactPort
from cogit_messaging_shim import MessagingSeams, parse_ts, verify_envelope

EVALUATION_REQUEST = "finance.evaluation_request"
VERDICT = "finance.verdict"
MAX_REASONS = 20
MAX_REASON_LENGTH = 500

Fetch = Callable[[], bytes]
CheckResult = tuple[str, list[str]]


class CheckError(Exception):
    """The check could not run; the verdict is ``error`` with this text as reason."""


def check_integrity(body: dict[str, Any], fetch: Fetch) -> CheckResult:
    """The stored bytes hash to ``artifact.sha256`` and have ``byte_length``."""
    artifact = body["artifact"]
    data = fetch()
    digest = hashlib.sha256(data).hexdigest()
    reasons: list[str] = []
    if digest != artifact["sha256"]:
        reasons.append(f"sha256_mismatch: the stored bytes hash to {digest}")
    if len(data) != artifact["byte_length"]:
        reasons.append(
            f"byte_length_mismatch: {len(data)} bytes stored, "
            f"{artifact['byte_length']} declared"
        )
    if reasons:
        return "fail", reasons
    return "pass", [f"sha256 and byte_length ({len(data)}) match the delivery"]


def check_required_files(body: dict[str, Any], fetch: Fetch) -> CheckResult:
    """Every name in ``params.required_files`` is in the zip."""
    required = body["params"].get("required_files")
    if (
        not isinstance(required, list)
        or not required
        or not all(isinstance(name, str) and name for name in required)
    ):
        raise CheckError("bad_params: required_files must be a list of file names")
    data = fetch()
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            present = set(archive.namelist())
    except zipfile.BadZipFile:
        return "fail", ["not_a_zip: the artifact is not a readable zip archive"]
    missing = [name for name in required if name not in present]
    if missing:
        return "fail", [f"missing_file: {name}" for name in missing]
    return "pass", [f"all {len(required)} required files are present"]


def check_deadline(body: dict[str, Any], fetch: Fetch) -> CheckResult:
    """``delivered_at`` is not after ``params.delivery_deadline``."""
    del fetch  # the artifact plays no part in this check
    delivered_at = body["delivered_at"]
    deadline = body["params"].get("delivery_deadline")
    try:
        on_time = parse_ts(delivered_at) <= parse_ts(deadline)
    except (TypeError, ValueError) as exc:
        raise CheckError(
            "bad_params: delivered_at and delivery_deadline must be UTC timestamps"
        ) from exc
    if on_time:
        return "pass", [f"delivered at {delivered_at}, deadline {deadline}"]
    return "fail", [f"late: delivered at {delivered_at}, deadline {deadline}"]


CHECKS: dict[tuple[str, int], Callable[[dict[str, Any], Fetch], CheckResult]] = {
    ("integrity", 1): check_integrity,
    ("required-files", 1): check_required_files,
    ("deadline", 1): check_deadline,
}


def _rejected(reason: str) -> dict[str, Any]:
    return {"status": "rejected", "reason": reason}


class EvaluatorCore:
    """Answers each evaluation request from E with one ``finance.verdict``."""

    def __init__(
        self, *, messaging: MessagingSeams, artifacts: ArtifactPort, escrow_did: str
    ) -> None:
        self._messaging = messaging
        self._artifacts = artifacts
        self._escrow_did = escrow_did

    def handle_message(self, envelope: dict[str, Any]) -> dict[str, Any]:
        """Process one inbound envelope; return ``{"status", "reason"}``."""
        if not verify_envelope(envelope):
            return _rejected("bad_signature")
        if envelope["sender_did"] != self._escrow_did:
            return _rejected("unexpected_sender")
        if envelope["type_key"] != EVALUATION_REQUEST or envelope["type_version"] != 1:
            return _rejected("unsupported_type")
        try:
            verdict = self.evaluate(envelope["body"])
        except (KeyError, TypeError, AttributeError):
            return _rejected("invalid_body")
        # The inbound message_id as causation_id gives the verdict a stable ID, so
        # judging the same request twice queues the same verdict once.
        self._messaging.send(
            VERDICT,
            1,
            self._escrow_did,
            envelope["conversation_id"],
            verdict,
            envelope["message_id"],
        )
        return {"status": "processed", "reason": None}

    def evaluate(self, body: dict[str, Any]) -> dict[str, Any]:
        """Run the check named by the request and return the verdict body."""
        verdict: dict[str, Any] = {
            "evaluation_request_id": body["evaluation_request_id"],
            "terms_hash": body["terms_hash"],
            "delivery_id": body["delivery_id"],
            "artifact_sha256": body["artifact"]["sha256"],
            "evaluator_id": body["evaluator_id"],
            "evaluator_version": body["evaluator_version"],
        }
        artifact_id = body["artifact"]["artifact_id"]
        check = CHECKS.get((body["evaluator_id"], body["evaluator_version"]))
        if check is None:
            name = f"{body['evaluator_id']}@{body['evaluator_version']}"
            outcome, reasons = "error", [f"unknown_evaluator: {name}"]
        else:
            try:
                outcome, reasons = check(body, lambda: self._fetch(artifact_id))
            except CheckError as exc:
                outcome, reasons = "error", [str(exc)]
        verdict["outcome"] = outcome
        verdict["reasons"] = [
            reason[:MAX_REASON_LENGTH] for reason in reasons[:MAX_REASONS]
        ]
        return verdict

    def _fetch(self, artifact_id: str) -> bytes:
        try:
            return self._artifacts.get(artifact_id)
        except Exception as exc:  # whatever the store raises, the check cannot run
            raise CheckError(
                f"artifact_unreadable: {artifact_id} ({type(exc).__name__})"
            ) from exc
