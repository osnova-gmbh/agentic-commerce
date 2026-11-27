"""Exercise generated authorization predicates with SQL NULL semantics.

The predicate uses standard SQL boolean operators. SQLite executes that exact
predicate after its PostgreSQL JSON lookups are bound to the context values;
full PostgreSQL mutation checks also live in test_native_postgres.py.
"""

import re
import sqlite3
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("module", ["cogit-messaging", "cogit-finance-catalog", "cogit-finance-deals"])
@pytest.mark.parametrize("kind,principal,installation,operator,escrow,denied", [
    ("fenced_worker", "worker", "buyer", "operator", None, True),
    ("fenced_worker", "worker", "escrow", "operator", None, True),
    ("fenced_worker", "worker", None, "operator", None, True),
    ("fenced_worker", "worker", "buyer", "operator", "escrow", True),
    ("fenced_worker", "worker", "escrow", "operator", "escrow", False),
    ("tenant_client", "operator", None, "operator", None, False),
    ("tenant_client", "stranger", None, "operator", None, True),
    ("tenant_client", None, None, "operator", None, True),
    ("tenant_client", "", None, "", None, True),
    (None, "operator", "escrow", "operator", "escrow", True),
])
def test_native_operator_guard_fails_closed_with_missing_context(
    module, kind, principal, installation, operator, escrow, denied,
):
    source = (ROOT / "modules" / module / "agentdb/migrations/000001__native.sql").read_text(encoding="utf-8")
    predicate = re.search(r"_operator\(ctx jsonb\).*?BEGIN\s+IF (.*?) THEN", source, re.S).group(1)
    lookups = {
        "ctx->>'callerKind'": ":kind",
        "ctx->>'principalId'": ":principal",
        "ctx->>'installationId'": ":installation",
        "ctx#>>'{settings,operator_principal_id}'": ":operator",
        "ctx#>>'{settings,escrow_installation_id}'": ":escrow",
    }
    for lookup, parameter in lookups.items():
        predicate = predicate.replace(lookup, parameter)
    with sqlite3.connect(":memory:") as database:
        result = database.execute("SELECT " + predicate, {
            "kind": kind, "principal": principal, "installation": installation,
            "operator": operator, "escrow": escrow,
        }).fetchone()[0]
    assert result == int(denied)
