"""Synthetic deterministic registry functions for the reference agent.

These are trivial, dependency-free helpers registered with the agent's
``FunctionRegistry`` (Proposal 010) and reached from the model through a single
dispatcher/describe action pair rather than one tool per function.
"""

from __future__ import annotations

from typing import Any

from cogit_agent_sdk import FunctionParameter, function


@function(
    name="score_record_risk",
    description="Score the synthetic risk of a record from its id and factors.",
    category="risk",
    parameters=[
        FunctionParameter(
            name="record_id",
            type="str",
            required=True,
            description="Identifier of the record to score.",
        ),
        FunctionParameter(
            name="factors",
            type="list",
            required=True,
            description="Risk factor labels contributing to the score.",
        ),
    ],
)
def score_record_risk(record_id: str, factors: list[str]) -> dict[str, Any]:
    base = sum(ord(character) for character in record_id) % 100
    score = min(100, base + len(factors) * 7)
    if score >= 66:
        level = "high"
    elif score >= 33:
        level = "medium"
    else:
        level = "low"
    return {
        "record_id": record_id,
        "score": score,
        "level": level,
        "factors": list(factors),
    }
