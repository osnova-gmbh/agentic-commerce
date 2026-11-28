# pyright: basic
"""E's core: ``handle_message`` and ``tick`` over ports. No SDK import.

Every inbound message is verified again here (signature, type, body), checked
against the SPEC §5.2 table and its guard, and recorded as exactly one deal
event. A refused message leaves no trace in the deal and gets a reason.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from datetime import datetime
from typing import Any

import httpx
from cogit_finance_seams import (
    ArtifactPort,
    BankError,
    BankPort,
    ModuleError,
    ModulePort,
    utcnow,
)
from cogit_messaging_shim import ENVELOPE_FIELDS, AgentKey, verify_envelope
from cogit_messaging_shim.envelope import freshness_error

from cogit_finance.escrow import followups, funding, ids, inbound, recovery, settings
from cogit_finance.escrow import reasons as r
from cogit_finance.escrow import transitions as t
from cogit_finance.escrow.messages import OWN_TYPES
from cogit_finance.escrow.schema_check import validate
from cogit_finance.escrow.store import (
    MESSAGING,
    DealStore,
    Directory,
    EscrowContext,
    EscrowError,
)

log = logging.getLogger(__name__)
Row = dict[str, Any]
PROCESSED = "processed"
REJECTED = "rejected"
TEXT_FIELDS = ("message_id", "type_key", "sender_did", "recipient_did", "created_at")


class EscrowCore:
    def __init__(
        self,
        modules: ModulePort,
        bank: BankPort,
        artifacts: ArtifactPort,
        key: AgentKey,
        config: Row,
        contracts_dir: str | os.PathLike[str],
        clock: Callable[[], datetime] = utcnow,
        *,
        release_authorized: Callable[[str], bool] | None = None,
    ) -> None:
        self.config = settings.check_operator_config(config)
        self.schemas = settings.load_message_schemas(contracts_dir)
        self.key = key
        self.modules = modules
        self.store = DealStore(modules, key, clock)
        self.ctx = EscrowContext(
            store=self.store,
            directory=Directory(modules),
            bank=bank,
            artifacts=artifacts,
            config=self.config,
            clock=clock,
            release_authorized=release_authorized,
        )

    # messages ---------------------------------------------------------------

    def handle_message(self, envelope: Any) -> Row:
        """Process one inbound ``finance.*`` message.

        Returns ``processed``, or ``rejected`` with a reason. Raises only for a
        failure worth retrying; handling the same message again then continues.
        """
        try:
            self._handle(envelope)
        except r.Rejected as refusal:
            return {"status": REJECTED, "reason": refusal.reason}
        return {"status": PROCESSED, "reason": None}

    def _handle(self, envelope: Any) -> None:
        trigger = self._admit(envelope)
        if trigger == "cancel":
            funding.collect(self.ctx)  # do not cancel over a credit already at the bank
        view = self.store.read(envelope["conversation_id"])
        # Finish what an earlier run left open, so the guard sees a deal at rest.
        view = followups.advance(self.ctx, view)
        recorded = view.event_for_message(envelope["message_id"])
        if recorded is None:
            view = inbound.record(self.ctx, view, trigger, envelope)
        elif recorded["body"]["envelope"] != envelope:
            raise r.Rejected(r.MESSAGE_ID_REUSED)
        followups.advance(self.ctx, view)

    def _admit(self, envelope: Any) -> str:
        """Envelope checks that need no deal. Returns the table's trigger name."""
        if not isinstance(envelope, dict) or set(envelope) != set(ENVELOPE_FIELDS):
            raise r.Rejected(r.INVALID_ENVELOPE)
        if not all(isinstance(envelope[name], str) for name in TEXT_FIELDS):
            raise r.Rejected(r.INVALID_ENVELOPE)
        if type(envelope["type_version"]) is not int:
            raise r.Rejected(r.INVALID_ENVELOPE)
        if not verify_envelope(envelope):
            raise r.Rejected(r.BAD_SIGNATURE)
        stale = freshness_error(envelope, self.ctx.clock())
        if stale:
            raise r.Rejected(stale)
        if envelope["recipient_did"] != self.key.did:
            raise r.Rejected(r.WRONG_RECIPIENT)
        type_key = envelope["type_key"]
        trigger = type_key.removeprefix(settings.TYPE_PREFIX)
        if type_key in OWN_TYPES:
            raise r.Rejected(r.UNEXPECTED_TYPE)
        if trigger == type_key or trigger not in t.MESSAGE_TRIGGERS:
            raise r.Rejected(r.UNKNOWN_TYPE)
        schema = self.schemas.get((type_key, envelope["type_version"]))
        if schema is None:
            raise r.Rejected(r.UNKNOWN_TYPE)
        if validate(schema, envelope["body"]) is not None:
            raise r.Rejected(r.INVALID_BODY)
        if not ids.is_uuid(envelope["conversation_id"]):
            raise r.Rejected(r.INVALID_DEAL_ID)
        return trigger

    # tick -------------------------------------------------------------------

    def tick(self) -> Row:
        """Register the message types, re-send the outbox, fund deals from credits.

        Also continues a deal that an interrupted run left in a state E never
        rests in. ``outbox_sent`` counts every entry sent during this tick.
        """
        sent_before = self.store.sent
        types_registered = self.register_types()
        self.store.flush_pending()
        deals = self.store.list_deals()
        credits_seen, deals_funded = 0, 0
        try:
            credits_seen, deals_funded = funding.collect(self.ctx)
            funding.reconcile_returns(self.ctx)
        except (BankError, httpx.HTTPError, OSError) as error:
            log.warning("bank unavailable; durable timers still run: %s", error)
        for row in deals:
            try:
                view = followups.advance(self.ctx, self.store.read(row["deal_id"]))
                view = recovery.timer(self.ctx, view)
                followups.advance(self.ctx, view)
            except (ModuleError, EscrowError, OSError) as error:
                log.warning("deal %s will retry: %s", row["deal_id"], error)
        return {
            "types_registered": types_registered,
            "credits_seen": credits_seen,
            "deals_funded": deals_funded,
            "outbox_sent": self.store.sent - sent_before,
        }

    def register_types(self) -> int:
        """Register every ``finance.*`` type. Returns how many are in place."""
        registered = 0
        for (type_key, version), schema in sorted(self.schemas.items()):
            args = {
                "type_key": type_key,
                "type_version": version,
                "json_schema": schema,
            }
            try:
                self.modules.module_command(
                    MESSAGING,
                    "type.register",
                    args,
                    idempotency_key=ids.type_register_key(type_key, version),
                )
            except ModuleError as error:
                log.warning("type %s v%s not registered: %s", type_key, version, error)
                continue
            registered += 1
        return registered
