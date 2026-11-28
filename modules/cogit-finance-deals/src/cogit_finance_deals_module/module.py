"""Reference implementation of the ``cogit-finance-deals`` module (SPEC §11.4).

The export contract (fields, kinds, callers, error codes) is contracts/module-exports.md.
Every command belongs to the escrow installation; reads require a participant or
operator identity. The module enforces the expected head, the chain links and the uniqueness constraints; E
decides which transitions are legal and computes the event hashes.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from cogit_finance_seams import Caller, ModuleError, SqliteModule, loads

from .access import can_read
from .commit import commit, insert_posting
from .rows import (
    ACCOUNTS,
    CREDITS,
    DELIVERIES,
    EVALUATIONS,
    INTENT_STATUSES,
    INTENTS,
    POSTINGS,
    clean,
    invalid,
    is_natural,
    is_text,
    insert,
    select,
)

_PACKAGE_DIR = Path(__file__).resolve().parent
# Inside a built wheel the migrations sit in the package; in the source tree, beside ``src``.
MIGRATIONS_DIR = next(
    (
        path
        for path in (
            _PACKAGE_DIR / "migrations",
            _PACKAGE_DIR.parents[1] / "migrations",
        )
        if path.is_dir()
    ),
    _PACKAGE_DIR / "migrations",
)
DEFAULT_ESCROW_INSTALLATION_ID = "cogit-finance"
DEAL_COLUMNS = (
    "deal_id, buyer_org_id, seller_org_id, offer_id, state, head_seq, head_hash, terms, terms_hash,"
    " created_at, updated_at"
)
EVENT_COLUMNS = "deal_id, seq, prev_hash, hash, event_type, source_message_id, actor_did, body, state_after, recorded_at"


def _text_arg(args: dict, name: str, *, optional: bool = False) -> Any:
    value = args.get(name)
    if value is None and optional:
        return None
    if not is_text(value):
        raise invalid(f"{name} must be a non-empty string")
    return value


class DealsModule(SqliteModule):
    name = "cogit-finance-deals"
    migrations_dir = MIGRATIONS_DIR
    queries = {
        "outbox.pending": "outbox_pending",
        "credit.read": "credit_read",
        "intents.unresolved": "intents_unresolved",
        "deal.read": "deal_read",
        "deal.list": "deal_list",
        "ledger.balances": "ledger_balances",
    }
    commands = {
        "deal.commit": "deal_commit",
        "outbox.mark_sent": "outbox_mark_sent",
        "intent.update": "intent_update",
        "credit.return": "credit_return",
    }

    def require_escrow(self, caller: Caller) -> None:
        escrow = (
            self.settings.get("escrow_installation_id")
            or DEFAULT_ESCROW_INSTALLATION_ID
        )
        if caller.principal != "installation" or caller.installation_id != escrow:
            raise ModuleError(
                "forbidden", "commands of this module belong to the escrow installation"
            )

    def can_read(self, caller: Caller, deal: dict | None) -> bool:
        escrow = (
            self.settings.get("escrow_installation_id")
            or DEFAULT_ESCROW_INSTALLATION_ID
        )
        return can_read(self.db, caller, escrow, deal)

    # -- commands ---------------------------------------------------------------------

    def deal_commit(self, args: dict, caller: Caller) -> dict:
        self.require_escrow(caller)
        try:
            return commit(self.db, self.now_ts(), args)
        except sqlite3.IntegrityError as error:
            raise invalid(f"a constraint rejected the commit: {error}") from error

    def outbox_mark_sent(self, args: dict, caller: Caller) -> dict:
        self.require_escrow(caller)
        outbox_id = _text_arg(args, "outbox_id")
        self.db.execute(
            "UPDATE deal_outbox SET status = 'sent', sent_at = ? WHERE outbox_id = ? AND status = 'pending'",
            (self.now_ts(), outbox_id),
        )
        return {}

    def intent_update(self, args: dict, caller: Caller) -> dict:
        self.require_escrow(caller)
        intent_id, status = _text_arg(args, "intent_id"), args.get("status")
        bank_ref = _text_arg(args, "bank_ref", optional=True)
        postings = args.get("postings") or []
        if status not in INTENT_STATUSES:
            raise invalid(f"status must be one of {', '.join(INTENT_STATUSES)}")
        if not isinstance(postings, list):
            raise invalid("postings must be a list")
        intent = self.db.execute(
            "SELECT deal_id FROM deal_payment_intents WHERE intent_id = ?", (intent_id,)
        ).fetchone()
        if intent is None:
            raise ModuleError("unknown_intent", intent_id)
        now = self.now_ts()
        try:
            self.db.execute(
                "UPDATE deal_payment_intents SET status = ?, bank_ref = COALESCE(?, bank_ref), updated_at = ?"
                " WHERE intent_id = ?",
                (status, bank_ref, now, intent_id),
            )
        except sqlite3.IntegrityError as error:
            raise ModuleError(
                "intent_conflict",
                f"the deal has another active payout or refund: {error}",
            ) from error
        for index, item in enumerate(postings):
            where = f"postings[{index}]"
            if isinstance(item, dict):
                item = {"source_id": intent_id, **item}
            key, given = clean(POSTINGS, item, intent["deal_id"], where)
            written = self.db.execute(
                "SELECT 1 FROM deal_ledger_postings WHERE source_id = ? AND account = ?",
                (given.get("source_id"), given.get("account")),
            ).fetchone()
            if written is None:
                insert_posting(self.db, now, intent["deal_id"], key, given, where)
        return {}

    def credit_return(self, args: dict, caller: Caller) -> dict:
        """Unknown credit, return intent and held posting are one transaction."""
        self.require_escrow(caller)
        credit, intent, posting = args["credit"], args["intent"], args["posting"]
        if (
            credit.get("disposition") != "returned"
            or intent.get("kind") != "return_unmatched"
        ):
            raise invalid("only unmatched credits may have no deal")
        known = self.credit_read({"bank_event_id": credit["bank_event_id"]}, caller)
        if known["credit"] is not None:
            return {}
        now = self.now_ts()
        for table, item in ((CREDITS, credit), (INTENTS, intent), (POSTINGS, posting)):
            key, fields = clean(table, item, None, table.key)
            stamps = {"created_at": now} if table in (INTENTS, POSTINGS) else {}
            if table == INTENTS:
                stamps["updated_at"] = now
            insert(self.db, table, None, key, fields, table.key, stamps)
        return {}

    def credit_read(self, args: dict, caller: Caller) -> dict:
        self.require_escrow(caller)
        rows = select(
            self.db,
            CREDITS,
            "t.bank_event_id = ?",
            (_text_arg(args, "bank_event_id"),),
            "t.bank_event_id",
        )
        return {"credit": rows[0] if rows else None}

    def intents_unresolved(self, args: dict, caller: Caller) -> dict:
        self.require_escrow(caller)
        return {
            "intents": select(
                self.db,
                INTENTS,
                "t.status IN ('prepared','submitted','unknown')",
                (),
                "t.intent_id",
            )
        }

    # -- queries ----------------------------------------------------------------------

    def outbox_pending(self, args: dict, caller: Caller) -> dict:
        self.require_escrow(caller)
        limit = args.get("limit")
        limit = 50 if limit is None else limit
        if not is_natural(limit):
            raise invalid("limit must be a non-negative integer")
        rows = self.db.execute(
            "SELECT outbox_id, deal_id, seq, envelope FROM deal_outbox WHERE status = 'pending'"
            " ORDER BY created_at, deal_id, seq, ordinal, outbox_id LIMIT ?",
            (limit,),
        ).fetchall()
        return {
            "entries": [
                {**dict(row), "envelope": loads(row["envelope"])} for row in rows
            ]
        }

    def deal_read(self, args: dict, caller: Caller) -> dict:
        deal_id = _text_arg(args, "deal_id")
        deal = self.db.execute(
            f"SELECT {DEAL_COLUMNS} FROM deal_deals WHERE deal_id = ?", (deal_id,)
        ).fetchone()
        if not self.can_read(caller, dict(deal) if deal else None):
            raise ModuleError("forbidden", "not a deal participant")
        events = self.db.execute(
            f"SELECT {EVENT_COLUMNS} FROM deal_events WHERE deal_id = ? ORDER BY seq",
            (deal_id,),
        ).fetchall()
        attempt = "(SELECT d.attempt FROM deal_deliveries d WHERE d.delivery_id = t.delivery_id)"
        own = ("t.deal_id = ?", (deal_id,))
        return {
            "deal": None
            if deal is None
            else {**dict(deal), "terms": loads(deal["terms"])},
            "events": [
                {**dict(event), "body": loads(event["body"])} for event in events
            ],
            "deliveries": select(self.db, DELIVERIES, *own, "t.attempt, t.delivery_id"),
            "evaluations": select(
                self.db,
                EVALUATIONS,
                *own,
                f"{attempt}, t.delivery_id, t.evaluation_request_id",
            ),
            "intents": select(self.db, INTENTS, *own, "t.created_at, t.intent_id"),
            "credits": select(self.db, CREDITS, *own, "t.received_at, t.bank_event_id"),
        }

    def deal_list(self, args: dict, caller: Caller) -> dict:
        rows = self.db.execute(
            "SELECT deal_id, state, buyer_org_id, seller_org_id, offer_id, head_seq, terms, created_at, updated_at"
            " FROM deal_deals ORDER BY created_at DESC, updated_at DESC, deal_id"
        ).fetchall()
        deals = []
        for row in rows:
            if not self.can_read(caller, dict(row)):
                continue
            terms = loads(row["terms"]) or {}
            deal = {
                name: row[name]
                for name in (
                    "deal_id",
                    "state",
                    "buyer_org_id",
                    "seller_org_id",
                    "offer_id",
                )
            }
            deal.update(
                head_seq=row["head_seq"],
                price_minor=terms.get("price_minor"),
                currency=terms.get("currency"),
            )
            deal.update(created_at=row["created_at"], updated_at=row["updated_at"])
            deals.append(deal)
        return {"deals": deals}

    def ledger_balances(self, args: dict, caller: Caller) -> dict:
        deal_id = _text_arg(args, "deal_id", optional=True)
        if deal_id is not None:
            self.deal_read({"deal_id": deal_id}, caller)
        balances = dict.fromkeys(ACCOUNTS, 0)
        for row in self.db.execute("SELECT * FROM deal_ledger_postings").fetchall():
            if deal_id is not None and row["deal_id"] != deal_id:
                continue
            deal = self.db.execute(
                "SELECT * FROM deal_deals WHERE deal_id = ?", (row["deal_id"],)
            ).fetchone()
            if self.can_read(caller, dict(deal) if deal else None):
                balances[row["account"]] += row["amount_minor"]
        return balances
