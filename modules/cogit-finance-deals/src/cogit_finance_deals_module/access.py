"""Reference-host participant reads; native SQL enforces the same predicate."""

from __future__ import annotations

import sqlite3
from cogit_finance_seams import Caller, ModuleError, loads


def _parties(db: sqlite3.Connection, deal: dict) -> set[str]:
    terms = (
        loads(deal.get("terms"))
        if isinstance(deal.get("terms"), str)
        else deal.get("terms")
    )
    if terms:
        return {
            did
            for name in ("buyer_did", "seller_did")
            if isinstance(did := terms.get(name), str)
        }
    request = db.execute(
        "SELECT body FROM deal_events WHERE deal_id = ? AND event_type = 'service_request' ORDER BY seq LIMIT 1",
        (deal["deal_id"],),
    ).fetchone()
    seller = db.execute(
        "SELECT envelope FROM deal_outbox WHERE deal_id = ? AND seq = 1 ORDER BY ordinal LIMIT 1",
        (deal["deal_id"],),
    ).fetchone()
    values = [
        loads(request["body"]).get("envelope", {}).get("sender_did")
        if request
        else None,
        loads(seller["envelope"]).get("recipient_did") if seller else None,
    ]
    return {did for did in values if isinstance(did, str)}


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
        parties = _parties(db, deal)
        return any(
            row["did"] in parties
            for row in db.execute(
                "SELECT did FROM msg_agent_identities WHERE installation_id = ? AND active = 1",
                (caller.installation_id,),
            ).fetchall()
        )
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc):
            return False
        raise ModuleError("authorization_unavailable") from exc
