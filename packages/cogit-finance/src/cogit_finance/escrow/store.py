# pyright: basic
"""The modules as E uses them: read a deal, commit one event, send its outbox."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from datetime import datetime
from typing import Any

from cogit_finance_seams import ModuleError, ModulePort
from cogit_messaging_shim import AgentKey, build_envelope, event_hash, to_ts

from cogit_finance.escrow import ids, transitions
from cogit_finance.escrow.messages import Outgoing
from cogit_finance.escrow.view import DealView

log = logging.getLogger(__name__)

MESSAGING = "cogit-messaging"
CATALOG = "cogit-finance-catalog"
DEALS = "cogit-finance-deals"
ROW_KINDS = ("deliveries", "evaluations", "intents", "credits", "postings")
Row = dict[str, Any]


class EscrowError(RuntimeError):
    """E cannot go on right now. The run fails and is retried."""


class DealStore:
    """One ``deal.commit`` per deal event; the outbox of a commit is sent after it."""

    def __init__(
        self, modules: ModulePort, key: AgentKey, clock: Callable[[], datetime]
    ) -> None:
        self.modules = modules
        self.key = key
        self.clock = clock
        self.sent = 0  # outbox entries sent through this store

    def read(self, deal_id: str) -> DealView:
        snapshot = self.modules.module_query(DEALS, "deal.read", {"deal_id": deal_id})
        return DealView(deal_id, snapshot)

    def list_deals(self) -> list[Row]:
        return list(self.modules.module_query(DEALS, "deal.list", {})["deals"])

    def record_message(
        self, view: DealView, envelope: Row, state_after: str, **parts: Any
    ) -> DealView:
        """Record an accepted inbound message, verbatim, as the next deal event."""
        return self._commit(
            view,
            str(envelope["type_key"]).removeprefix("finance."),
            state_after,
            {"envelope": envelope},
            actor_did=envelope["sender_did"],
            source_message_id=envelope["message_id"],
            key=ids.message_event_key(envelope["message_id"]),
            **parts,
        )

    def record_own(
        self, view: DealView, event_type: str, state_after: str, body: Row, **parts: Any
    ) -> DealView:
        """Record an event E originates: what it decided or sent."""
        return self._commit(
            view,
            event_type,
            state_after,
            body,
            actor_did=self.key.did,
            source_message_id=None,
            key=ids.own_event_key(view.deal_id, view.head_seq + 1, event_type),
            **parts,
        )

    def _commit(
        self,
        view: DealView,
        event_type: str,
        state_after: str,
        body: Row,
        *,
        actor_did: str,
        source_message_id: str | None,
        key: str,
        deal: Row | None = None,
        outbox: Iterable[Outgoing] = (),
        **rows: list[Row],
    ) -> DealView:
        if not transitions.is_legal(view.state, event_type, state_after):
            raise EscrowError(
                f"illegal transition: {view.state} -{event_type}-> {state_after}"
            )
        seq = view.head_seq + 1
        event: Row = {
            "deal_id": view.deal_id,
            "seq": seq,
            "prev_hash": view.head_hash,
            "event_type": event_type,
            "source_message_id": source_message_id,
            "actor_did": actor_did,
            "body": body,
            "state_after": state_after,
        }
        digest = event_hash(event)
        del event["deal_id"]
        event["hash"] = digest
        entries = [self._entry(view.deal_id, seq, n, o) for n, o in enumerate(outbox)]
        args: Row = {
            "deal_id": view.deal_id,
            "expected_seq": view.head_seq,
            "expected_hash": view.head_hash,
            "event": event,
        }
        if deal is not None:
            args["deal"] = deal
        if entries:
            args["outbox"] = entries
        for kind in ROW_KINDS:
            if rows.get(kind):
                args[kind] = rows[kind]
        result = self.modules.module_command(
            DEALS, "deal.commit", args, idempotency_key=key
        )
        if not result.get("duplicate"):
            self.flush(entries)
        return self.read(view.deal_id)

    def _entry(self, deal_id: str, seq: int, n: int, item: Outgoing) -> Row:
        message_id = ids.own_message_id(
            deal_id, seq, item.type_key, item.recipient_did, n
        )
        envelope = build_envelope(
            self.key,
            self.key.did,
            item.type_key,
            item.type_version,
            item.recipient_did,
            deal_id,
            item.body,
            item.causation_id,
            message_id=message_id,
            created_at=to_ts(self.clock()),
        )
        return {"outbox_id": message_id, "envelope": envelope}

    # outbox -----------------------------------------------------------------

    def flush(self, entries: Iterable[Row]) -> int:
        """Send each entry and mark it sent. One that is refused stays pending."""
        sent = 0
        for entry in entries:
            outbox_id = str(entry["outbox_id"])
            try:
                self.modules.module_command(
                    MESSAGING,
                    "message.send",
                    {"envelope": entry["envelope"]},
                    idempotency_key=ids.outbox_send_key(outbox_id),
                )
            except ModuleError as error:
                log.warning("outbox entry %s not sent: %s", outbox_id, error.code)
                continue
            self.modules.module_command(
                DEALS,
                "outbox.mark_sent",
                {"outbox_id": outbox_id},
                idempotency_key=ids.outbox_sent_key(outbox_id),
            )
            sent += 1
        self.sent += sent
        return sent

    def flush_pending(self, limit: int = 50) -> int:
        """Re-send what an earlier run committed but did not get to send."""
        pending = self.modules.module_query(DEALS, "outbox.pending", {"limit": limit})
        return self.flush(pending["entries"])

    def update_intent(self, intent_id: str, status: str, **fields: Any) -> None:
        self.modules.module_command(
            DEALS,
            "intent.update",
            {"intent_id": intent_id, "status": status, **fields},
            idempotency_key=ids.intent_update_key(intent_id, status),
        )


class Directory:
    """Identities, companies, offers and evaluators, read from the modules."""

    def __init__(self, modules: ModulePort) -> None:
        self.modules = modules

    def identity(self, did: str) -> Row | None:
        found = self.modules.module_query(MESSAGING, "identity.resolve", {"did": did})
        return found.get("identity")

    def identity_for(self, role: str, org_id: str) -> Row | None:
        query = {"role": role, "org_id": org_id}
        return self.modules.module_query(MESSAGING, "identity.resolve", query).get(
            "identity"
        )

    def company(self, org_id: str) -> Row | None:
        found = self.modules.module_query(CATALOG, "company.read", {"org_id": org_id})
        return found.get("company")

    def offer(self, seller_org_id: str, offer_id: str) -> Row | None:
        query = {"seller_org_id": seller_org_id}
        offers = self.modules.module_query(CATALOG, "catalog.read", query)["offers"]
        return next((o for o in offers if o["offer_id"] == offer_id), None)

    def evaluators(self) -> dict[tuple[str, int], Row]:
        rows = self.modules.module_query(CATALOG, "evaluators.list", {})["evaluators"]
        return {(row["evaluator_id"], int(row["version"])): row for row in rows}


class EscrowContext:
    """What the steps of the core share: ports, config, clock."""

    def __init__(
        self,
        *,
        store: DealStore,
        directory: Directory,
        bank: Any,
        artifacts: Any,
        config: Row,
        clock: Callable[[], datetime],
        release_authorized: Callable[[str], bool] | None = None,
    ) -> None:
        self.store = store
        self.directory = directory
        self.bank = bank
        self.artifacts = artifacts
        self.config = config
        self.clock = clock
        self.release_authorized = release_authorized or (lambda deal_id: True)

    @property
    def escrow_did(self) -> str:
        return self.store.key.did
