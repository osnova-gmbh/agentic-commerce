"""In-memory fake of the three modules, as far as E calls them.

``FakeModules`` follows contracts/module-exports.md; the real modules belong to
other lanes. It enforces what the contract says the modules enforce: command
replay by idempotency key, the expected head, unique source messages, one
active payout intent, unique credits and postings.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime
from typing import Any

from cogit_finance_seams import ModuleError
from cogit_messaging_shim import ENVELOPE_FIELDS, canonical_bytes, to_ts

from cogit_finance.escrow.schema_check import validate

Row = dict[str, Any]
ZERO_HASH = "0" * 64
ACCOUNTS = ("held", "seller", "fee", "buyer_refund", "returned")
ACTIVE_INTENT = ("prepared", "submitted", "unknown")


def _copy(value: Any) -> Any:
    canonical_bytes(value)  # no floats, string keys only
    return json.loads(json.dumps(value, allow_nan=False))


class FakeModules:
    """``ModulePort`` over dictionaries, called as installation ``cogit-finance``."""

    def __init__(
        self, clock: Callable[[], datetime], installation_id: str = "cogit-finance"
    ) -> None:
        self.clock = clock
        self.installation_id = installation_id
        self.identities: dict[str, Row] = {}
        self.types: dict[tuple[str, int], Row] = {}
        self.messages: dict[str, Row] = {}
        self.companies: dict[str, Row] = {}
        self.offers: dict[str, list[Row]] = {}
        self.evaluators: list[Row] = []
        self.deals: dict[str, Row] = {}
        self.events: dict[str, list[Row]] = {}
        self.outbox: dict[str, Row] = {}
        self.deliveries: dict[str, Row] = {}
        self.evaluations: dict[str, Row] = {}
        self.intents: dict[str, Row] = {}
        self.credits: dict[str, Row] = {}
        self.postings: dict[tuple[str, str], Row] = {}
        self.replays: dict[tuple[str, str, str], Row] = {}
        self.commands: list[tuple[str, str, str]] = []  # module, export, key
        self._failures: dict[str, list[Any]] = {}  # export -> [calls to skip, error]

    def now(self) -> str:
        return to_ts(self.clock())

    # the port -----------------------------------------------------------------

    def module_query(self, module: str, export: str, args: Row | None = None) -> Row:
        return _copy(self._handler(module, export)(_copy(args or {})))

    def module_command(
        self, module: str, export: str, args: Row | None = None, *, idempotency_key: str
    ) -> Row:
        assert idempotency_key, "a command needs an idempotency key"
        self.commands.append((module, export, idempotency_key))
        self._maybe_fail(export)
        replay = (module, export, idempotency_key)
        if replay not in self.replays:
            self.replays[replay] = _copy(
                self._handler(module, export)(_copy(args or {})) or {}
            )
        return _copy(self.replays[replay])

    def fail_once(self, export: str, error: Exception, skip: int = 0) -> None:
        """Make one later call of this command raise, after ``skip`` good calls."""
        self._failures[export] = [skip, error]

    def _maybe_fail(self, export: str) -> None:
        planned = self._failures.get(export)
        if planned is None:
            return
        if planned[0] > 0:
            planned[0] -= 1
            return
        del self._failures[export]
        raise planned[1]

    def _handler(self, module: str, export: str) -> Callable[[Row], Row]:
        name = f"_{module}__{export}".replace("-", "_").replace(".", "_")
        handler = getattr(self, name, None)
        if handler is None:
            raise ModuleError("unknown_export", f"{module}.{export}")
        return handler

    # cogit-messaging -----------------------------------------------------------

    def register_identity(
        self, did: str, installation_id: str, org_id: str, role: str
    ) -> None:
        self.identities[did] = {
            "did": did,
            "installation_id": installation_id,
            "org_id": org_id,
            "role": role,
            "active": True,
            "registered_at": self.now(),
        }

    def _cogit_messaging__identity_resolve(self, args: Row) -> Row:
        if "did" in args:
            return {"identity": self.identities.get(args["did"])}
        for row in self.identities.values():
            org_ok = args.get("org_id") in (None, row["org_id"])
            if row["role"] == args.get("role") and org_ok:
                return {"identity": row}
        return {"identity": None}

    def _cogit_messaging__type_register(self, args: Row) -> Row:
        key = (args["type_key"], args["type_version"])
        if key not in self.types:
            self.types[key] = args["json_schema"]
            return {"status": "created"}
        if self.types[key] != args["json_schema"]:
            raise ModuleError("type_conflict", args["type_key"])
        return {"status": "unchanged"}

    def _cogit_messaging__message_send(self, args: Row) -> Row:
        envelope = args["envelope"]
        if set(envelope) != set(ENVELOPE_FIELDS):
            raise ModuleError("invalid_envelope")
        sender = self.identities.get(envelope["sender_did"])
        if sender is None or sender["installation_id"] != self.installation_id:
            raise ModuleError("not_your_did", envelope["sender_did"])
        if envelope["recipient_did"] not in self.identities:
            raise ModuleError("unknown_recipient", envelope["recipient_did"])
        schema = self.types.get((envelope["type_key"], envelope["type_version"]))
        if schema is None:
            raise ModuleError("unknown_type", envelope["type_key"])
        error = validate(schema, envelope["body"])
        if error:
            raise ModuleError("invalid_body", error)
        message_id = envelope["message_id"]
        if message_id in self.messages:
            return {"message_id": message_id, "status": "duplicate"}
        self.messages[message_id] = envelope
        return {"message_id": message_id, "status": "queued"}

    # cogit-finance-catalog -----------------------------------------------------

    def _cogit_finance_catalog__company_read(self, args: Row) -> Row:
        return {"company": self.companies.get(args["org_id"])}

    def _cogit_finance_catalog__catalog_read(self, args: Row) -> Row:
        offers = self.offers.get(args["seller_org_id"], [])
        return {"offers": sorted(offers, key=lambda offer: offer["offer_id"])}

    def _cogit_finance_catalog__evaluators_list(self, args: Row) -> Row:
        del args
        rows = sorted(self.evaluators, key=lambda e: (e["evaluator_id"], e["version"]))
        return {"evaluators": rows}

    # cogit-finance-deals: commands ---------------------------------------------

    def _cogit_finance_deals__deal_commit(self, args: Row) -> Row:
        deal_id, event = args["deal_id"], args["event"]
        source = event.get("source_message_id")
        if source is not None:
            for rows in self.events.values():
                for row in rows:
                    if row["source_message_id"] == source:
                        return {
                            "seq": row["seq"],
                            "hash": row["hash"],
                            "duplicate": True,
                        }
        deal = self.deals.get(deal_id)
        head = (deal["head_seq"], deal["head_hash"]) if deal else (0, ZERO_HASH)
        if head != (args["expected_seq"], args["expected_hash"]):
            raise ModuleError("head_mismatch", deal_id)
        if event["seq"] != head[0] + 1 or event["prev_hash"] != head[1]:
            raise ModuleError("bad_event", "seq or prev_hash")
        known = (row["hash"] for rows in self.events.values() for row in rows)
        if event["hash"] in known:
            raise ModuleError("bad_event", "hash is not unique")
        now = self.now()
        fields = args.get("deal") or {}
        if deal is None:
            if not all(fields.get(k) for k in ("buyer_org_id", "seller_org_id")):
                raise ModuleError("bad_event", "a new deal needs its parties")
            deal = {
                "deal_id": deal_id,
                "buyer_org_id": fields["buyer_org_id"],
                "seller_org_id": fields["seller_org_id"],
                "offer_id": fields["offer_id"],
                "terms": None,
                "terms_hash": None,
                "created_at": now,
            }
        self._check_rows(deal_id, args)
        self.deals[deal_id] = deal
        for name in ("terms", "terms_hash"):
            if name in fields:
                deal[name] = fields[name]
        deal.update(
            state=event["state_after"],
            head_seq=event["seq"],
            head_hash=event["hash"],
            updated_at=now,
        )
        self.events.setdefault(deal_id, []).append(
            {"deal_id": deal_id, **event, "recorded_at": now}
        )
        self._write_rows(deal_id, event["seq"], args, now)
        return {"seq": event["seq"], "hash": event["hash"], "duplicate": False}

    def _check_rows(self, deal_id: str, args: Row) -> None:
        for intent in args.get("intents", []):
            clash = any(
                row["deal_id"] == deal_id
                and row["kind"] in ("payout", "refund")
                and row["status"] in ACTIVE_INTENT
                for row in self.intents.values()
            )
            if intent["kind"] in ("payout", "refund") and clash:
                raise ModuleError("intent_conflict", intent["intent_id"])
        for credit in args.get("credits", []):
            if credit["bank_event_id"] in self.credits:
                raise ModuleError("duplicate_credit", credit["bank_event_id"])

    def _write_rows(self, deal_id: str, seq: int, args: Row, now: str) -> None:
        for entry in args.get("outbox", []):
            self.outbox[entry["outbox_id"]] = {
                **entry,
                "deal_id": deal_id,
                "seq": seq,
                "status": "pending",
                "sent_at": None,
            }
        for row in args.get("deliveries", []):
            self.deliveries[row["delivery_id"]] = {**row, "deal_id": deal_id}
        for row in args.get("evaluations", []):
            self.evaluations[row["evaluation_request_id"]] = dict(row)
        for row in args.get("intents", []):
            self.intents[row["intent_id"]] = {
                **row,
                "deal_id": deal_id,
                "bank_ref": None,
                "created_at": now,
                "updated_at": now,
            }
        for row in args.get("credits", []):
            self.credits[row["bank_event_id"]] = {**row, "deal_id": deal_id}
        self._post(deal_id, args.get("postings", []), now)

    def _post(self, deal_id: str, postings: list[Row], now: str) -> None:
        for row in postings:
            assert row["account"] in ACCOUNTS
            key = (row["source_id"], row["account"])
            self.postings.setdefault(
                key, {**row, "deal_id": deal_id, "created_at": now}
            )

    def _cogit_finance_deals__outbox_mark_sent(self, args: Row) -> Row:
        self.outbox[args["outbox_id"]].update(status="sent", sent_at=self.now())
        return {}

    def _cogit_finance_deals__intent_update(self, args: Row) -> Row:
        intent = self.intents.get(args["intent_id"])
        if intent is None:
            raise ModuleError("unknown_intent", args["intent_id"])
        intent.update(status=args["status"], updated_at=self.now())
        if args.get("bank_ref") is not None:
            intent["bank_ref"] = args["bank_ref"]
        self._post(intent["deal_id"], args.get("postings") or [], self.now())
        return {}

    # cogit-finance-deals: queries ----------------------------------------------

    def _cogit_finance_deals__outbox_pending(self, args: Row) -> Row:
        pending = [row for row in self.outbox.values() if row["status"] == "pending"]
        names = ("outbox_id", "deal_id", "seq", "envelope")
        entries = [{name: row[name] for name in names} for row in pending]
        return {"entries": entries[: args.get("limit", 50)]}

    def _cogit_finance_deals__deal_read(self, args: Row) -> Row:
        deal_id = args["deal_id"]
        deliveries = [d for d in self.deliveries.values() if d["deal_id"] == deal_id]
        ids = {row["delivery_id"] for row in deliveries}
        mine = [e for e in self.evaluations.values() if e["delivery_id"] in ids]
        return {
            "deal": self.deals.get(deal_id),
            "events": self.events.get(deal_id, []),
            "deliveries": sorted(deliveries, key=lambda row: row["attempt"]),
            "evaluations": mine,
            "intents": [i for i in self.intents.values() if i["deal_id"] == deal_id],
            "credits": [c for c in self.credits.values() if c["deal_id"] == deal_id],
        }

    def _cogit_finance_deals__deal_list(self, args: Row) -> Row:
        del args
        names = ("deal_id", "state", "buyer_org_id", "seller_org_id", "offer_id")
        deals = []
        for deal in reversed(list(self.deals.values())):
            terms = deal["terms"] or {}
            row = {name: deal[name] for name in (*names, "head_seq")}
            row["price_minor"] = terms.get("price_minor")
            row["currency"] = terms.get("currency")
            row["created_at"] = deal["created_at"]
            row["updated_at"] = deal["updated_at"]
            deals.append(row)
        return {"deals": deals}

    def _cogit_finance_deals__ledger_balances(self, args: Row) -> Row:
        balances = dict.fromkeys(ACCOUNTS, 0)
        for row in self.postings.values():
            if args.get("deal_id") in (None, row["deal_id"]):
                balances[row["account"]] += row["amount_minor"]
        return balances
