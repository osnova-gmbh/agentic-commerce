"""Verdict policy and verdict correlation (SPEC §9.2, §9.3). No I/O."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

APPROVE = "approve"
REJECT = "reject"
PASS = "pass"  # noqa: S105 - a verdict outcome
FAIL = "fail"
ERROR = "error"

NEW = "new"
DUPLICATE = "duplicate"
CONFLICT = "conflict"


def decide(policy: str, outcomes: Sequence[str | None]) -> str | None:
    """``approve``, ``reject`` or None while the outcome is still open.

    ``outcomes`` holds one entry per named evaluator: its verdict, or None while
    it has not answered. Only ``pass`` and ``fail`` count. E decides as soon as
    the outcome is certain, so with ``all`` the first ``fail`` rejects.
    """
    passed = sum(1 for outcome in outcomes if outcome == PASS)
    failed = sum(1 for outcome in outcomes if outcome == FAIL)
    total = len(outcomes)
    if total == 0:
        return None
    if policy == "all":
        if failed:
            return REJECT
        return APPROVE if passed == total else None
    if policy == "any":
        if passed:
            return APPROVE
        return REJECT if failed == total else None
    if policy.startswith("quorum "):
        try:
            needed = int(policy.removeprefix("quorum "))
        except ValueError as exc:
            raise ValueError(f"invalid quorum: {policy}") from exc
        if not 1 <= needed <= total:
            raise ValueError(f"invalid quorum: {policy} for {total} evaluators")
        if passed >= needed:
            return APPROVE
        return REJECT if total - failed < needed else None
    raise ValueError(f"unsupported policy: {policy}")


def classify_verdict(
    evaluation: dict[str, Any], recorded: dict[str, Any] | None, body: dict[str, Any]
) -> str:
    """How a verdict relates to what is recorded for its request.

    ``new``: nothing recorded yet. ``duplicate``: the same judgement again, a
    no-op. ``conflict``: a different judgement for an answered request.
    """
    if evaluation.get("outcome") is None:
        return NEW
    same_outcome = evaluation["outcome"] == body["outcome"]
    same_reasons = recorded is None or recorded.get("reasons") == body.get("reasons")
    return DUPLICATE if same_outcome and same_reasons else CONFLICT


def attempts_left(max_attempts: int, attempt: int) -> int:
    return max(0, max_attempts - attempt)
