"""Reference-host participant reads; native SQL enforces the same predicate."""

from __future__ import annotations

import sqlite3
from cogit_finance_seams import Caller, ModuleError


def can_read(
    db: sqlite3.Connection, caller: Caller, escrow: str, deal: dict | None
) -> bool:
    if caller.principal in ("operator", "operator_ro"):
        return True
    if caller.principal != "installation":
        return False
    if caller.installation_id == escrow:
        return True
    if deal is None:
        return False
    try:
        return (
            db.execute(
                "SELECT 1 FROM msg_agent_identities WHERE installation_id = ? AND active = 1"
                " AND org_id IN (?, ?) LIMIT 1",
                (caller.installation_id, deal["buyer_org_id"], deal["seller_org_id"]),
            ).fetchone()
            is not None
        )
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc):
            return False
        raise ModuleError("authorization_unavailable") from exc
