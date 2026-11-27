"""Reference implementation of the cogit-messaging module (SPEC §11.1) over SQLite.

Contract: contracts/module-exports.md, section "cogit-messaging". The module knows
nothing about escrow and verifies no signatures (SPEC §6.2): it binds DIDs to
installations, keeps the immutable type registry and runs the message queue.
"""

from __future__ import annotations

import sqlite3
from datetime import timedelta
from pathlib import Path

from cogit_finance_seams import Caller, ModuleError, SqliteModule, dumps, loads, to_ts
from jsonschema import Draft202012Validator
from jsonschema.exceptions import best_match

from .checks import check_envelope, has_float, int_arg, text_arg
from .dialect import check_dialect

MODULE_NAME = "cogit-messaging"
ROLES = ("buyer", "seller", "evaluator", "escrow")
OUTCOMES = ("processed", "rejected")
FINAL = ("processed", "rejected", "dead")
DEFAULT_SETTINGS = {"escrow_installation_id": "cogit-finance", "redeliver_after_s": 30, "max_delivery_attempts": 5}
MAX_CLAIM = 100

_PACKAGED = Path(__file__).resolve().parent / "migrations"  # inside a built wheel
MIGRATIONS_DIR = _PACKAGED if _PACKAGED.is_dir() else Path(__file__).resolve().parents[2] / "migrations"

# Messages the caller may claim now: its own, queued and due, or claimed too long ago.
_CLAIMABLE = (
    "recipient_did IN (SELECT did FROM msg_agent_identities WHERE installation_id = ? AND active = 1)"
    " AND ((status = 'queued' AND available_at <= ?) OR (status = 'claimed' AND claimed_at <= ?))"
)
_CONVERSATION_COLUMNS = (
    "message_id, type_key, type_version, sender_did, recipient_did, causation_id, status, reason,"
    " attempts, run_id, created_at, acked_at, envelope"
)


class MessagingModule(SqliteModule):
    name = MODULE_NAME
    migrations_dir = MIGRATIONS_DIR
    queries = {"identity.resolve": "identity_resolve", "conversation.read": "conversation_read"}
    commands = {
        "identity.register": "identity_register",
        "type.register": "type_register",
        "message.send": "message_send",
        "message.claim": "message_claim",
        "message.ack": "message_ack",
        "message.release": "message_release",
    }

    def attach(self, host, settings: dict | None = None) -> None:
        super().attach(host, {**DEFAULT_SETTINGS, **(settings or {})})
        for name in ("redeliver_after_s", "max_delivery_attempts"):
            int_arg(self.settings, name, minimum=0 if name == "redeliver_after_s" else 1)

    # identities

    def identity_register(self, args: dict, caller: Caller) -> dict:
        self.require_operator(caller)
        did, installation_id, org_id = (text_arg(args, name) for name in ("did", "installation_id", "org_id"))
        if args.get("role") not in ROLES:
            raise ModuleError("invalid_argument", f"role must be one of {', '.join(ROLES)}")
        self.db.execute(
            "INSERT INTO msg_agent_identities (did, installation_id, org_id, role, active, registered_at)"
            " VALUES (?, ?, ?, ?, 1, ?)"
            " ON CONFLICT (did) DO UPDATE SET installation_id = excluded.installation_id,"
            " org_id = excluded.org_id, role = excluded.role, active = 1",
            (did, installation_id, org_id, args["role"], self.now_ts()),
        )
        return {"did": did}

    def identity_resolve(self, args: dict, caller: Caller) -> dict:
        if args.get("did") is not None:
            row = self._identity(args["did"])
        elif args.get("role") is not None:
            sql, params = "SELECT * FROM msg_agent_identities WHERE active = 1 AND role = ?", [args["role"]]
            if args.get("org_id") is not None:
                sql, params = sql + " AND org_id = ?", [*params, args["org_id"]]
            row = self.db.execute(sql + " ORDER BY registered_at, did LIMIT 1", params).fetchone()
        else:
            raise ModuleError("invalid_argument", "did or role is required")
        return {"identity": None if row is None else {**dict(row), "active": bool(row["active"])}}

    def _identity(self, did: object) -> sqlite3.Row | None:
        return self.db.execute("SELECT * FROM msg_agent_identities WHERE did = ? AND active = 1", (did,)).fetchone()

    def _bound(self, did: str, caller: Caller) -> bool:
        row = self._identity(did)
        return row is not None and row["installation_id"] == caller.installation_id

    # type registry

    def type_register(self, args: dict, caller: Caller) -> dict:
        if caller.principal != "installation" or caller.installation_id != self.settings["escrow_installation_id"]:
            raise ModuleError("forbidden", "only the escrow installation registers message types")
        type_key, type_version = text_arg(args, "type_key"), int_arg(args, "type_version", minimum=1)
        schema = args.get("json_schema")
        check_dialect(schema)
        if has_float(schema):
            raise ModuleError("unsupported_schema", "schemas carry no floating-point values")
        text = dumps(schema)
        row = self.db.execute(
            "SELECT json_schema FROM msg_message_types WHERE type_key = ? AND type_version = ?",
            (type_key, type_version),
        ).fetchone()
        if row is None:
            self.db.execute(
                "INSERT INTO msg_message_types (type_key, type_version, json_schema, registered_by, registered_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (type_key, type_version, text, caller.installation_id, self.now_ts()),
            )
            return {"status": "created"}
        if row["json_schema"] == text:
            return {"status": "unchanged"}
        raise ModuleError("type_conflict", f"{type_key} v{type_version} is registered with a different schema")

    # queue

    def message_send(self, args: dict, caller: Caller) -> dict:
        envelope = check_envelope(args.get("envelope"))
        if caller.principal != "installation" or not self._bound(envelope["sender_did"], caller):
            raise ModuleError("not_your_did", "sender_did is not bound to the calling installation")
        message_id = envelope["message_id"]
        if self.db.execute("SELECT 1 FROM msg_messages WHERE message_id = ?", (message_id,)).fetchone():
            return {"message_id": message_id, "status": "duplicate"}
        if self._identity(envelope["recipient_did"]) is None:
            raise ModuleError("unknown_recipient", envelope["recipient_did"])
        type_key, type_version = envelope["type_key"], envelope["type_version"]
        registered = self.db.execute(
            "SELECT json_schema FROM msg_message_types WHERE type_key = ? AND type_version = ?",
            (type_key, type_version),
        ).fetchone()
        if registered is None:
            raise ModuleError("unknown_type", f"{type_key} v{type_version}")
        error = best_match(Draft202012Validator(loads(registered["json_schema"])).iter_errors(envelope["body"]))
        if error is not None:
            where = "/".join(str(part) for part in error.absolute_path) or "body"
            raise ModuleError("invalid_body", f"{where}: {error.message}"[:300])
        now = self.now_ts()
        seq = self.db.execute("SELECT COALESCE(MAX(seq), 0) + 1 FROM msg_messages").fetchone()[0]
        self.db.execute(
            "INSERT INTO msg_messages (message_id, seq, conversation_id, causation_id, type_key, type_version,"
            " sender_did, recipient_did, envelope, status, attempts, available_at, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued', 0, ?, ?)",
            (
                message_id,
                seq,
                envelope["conversation_id"],
                envelope["causation_id"],
                type_key,
                type_version,
                envelope["sender_did"],
                envelope["recipient_did"],
                dumps(envelope),
                now,
                now,
            ),
        )
        return {"message_id": message_id, "status": "queued"}

    def message_claim(self, args: dict, caller: Caller) -> dict:
        limit = min(int_arg(args, "limit", default=10, minimum=1), MAX_CLAIM)
        now = self.now()
        now_ts = to_ts(now)
        stale = to_ts(now - timedelta(seconds=self.settings["redeliver_after_s"]))
        mine = (caller.installation_id, now_ts, stale)
        claimable = _CLAIMABLE
        if args.get("conversation_id") is not None:
            claimable += " AND conversation_id = ?"
            mine += (text_arg(args, "conversation_id"),)
        # A message that used up its attempts is dead: visible to the operator, never delivered again.
        self.db.execute(
            "UPDATE msg_messages SET status = 'dead', reason = 'max_delivery_attempts', acked_at = ?"
            f" WHERE attempts >= ? AND {claimable}",
            (now_ts, self.settings["max_delivery_attempts"], *mine),
        )
        rows = self.db.execute(
            f"SELECT message_id, envelope, attempts FROM msg_messages WHERE {claimable} ORDER BY seq LIMIT ?",
            (*mine, limit),
        ).fetchall()
        messages = []
        for row in rows:
            self.db.execute(
                "UPDATE msg_messages SET status = 'claimed', claimed_at = ?, attempts = attempts + 1,"
                " admission_key = ? WHERE message_id = ?",
                (now_ts, f"msg:{row['message_id']}", row["message_id"]),
            )
            messages.append(
                {"message_id": row["message_id"], "envelope": loads(row["envelope"]), "attempts": row["attempts"] + 1}
            )
        return {"messages": messages}

    def _own_message(self, args: dict, caller: Caller) -> sqlite3.Row:
        message_id = text_arg(args, "message_id")
        row = self.db.execute(
            "SELECT message_id, recipient_did, status, attempts FROM msg_messages WHERE message_id = ?", (message_id,)
        ).fetchone()
        if row is None:
            raise ModuleError("unknown_message", message_id)
        if not self._bound(row["recipient_did"], caller):
            raise ModuleError("not_your_message", message_id)
        return row

    def message_ack(self, args: dict, caller: Caller) -> dict:
        row = self._own_message(args, caller)
        if args.get("outcome") not in OUTCOMES:
            raise ModuleError("invalid_argument", f"outcome must be one of {', '.join(OUTCOMES)}")
        if row["status"] in FINAL:  # repeating an acknowledgement is harmless
            return {}
        self.db.execute(
            "UPDATE msg_messages SET status = ?, reason = ?, run_id = COALESCE(?, run_id), acked_at = ?"
            " WHERE message_id = ?",
            (args["outcome"], args.get("reason"), args.get("run_id"), self.now_ts(), row["message_id"]),
        )
        return {}

    def message_release(self, args: dict, caller: Caller) -> dict:
        row = self._own_message(args, caller)
        delay_s = int_arg(args, "delay_s", default=0, minimum=0)
        if row["status"] != "claimed":
            return {}
        now = self.now()
        if row["attempts"] >= self.settings["max_delivery_attempts"]:
            self.db.execute(
                "UPDATE msg_messages SET status = 'dead', reason = 'max_delivery_attempts', acked_at = ?"
                " WHERE message_id = ?",
                (to_ts(now), row["message_id"]),
            )
        else:
            self.db.execute(
                "UPDATE msg_messages SET status = 'queued', available_at = ? WHERE message_id = ?",
                (to_ts(now + timedelta(seconds=delay_s)), row["message_id"]),
            )
        return {}

    def conversation_read(self, args: dict, caller: Caller) -> dict:
        rows = self.db.execute(
            f"SELECT {_CONVERSATION_COLUMNS} FROM msg_messages WHERE conversation_id = ? ORDER BY seq",
            (text_arg(args, "conversation_id"),),
        ).fetchall()
        return {"messages": [{**dict(row), "envelope": loads(row["envelope"])} for row in rows]}
