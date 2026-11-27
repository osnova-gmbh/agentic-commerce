"""Read-only view of one deal, as ``deal.read`` returns it. No I/O."""

from __future__ import annotations

from typing import Any

from cogit_finance.escrow.transitions import NONE

ZERO_HASH = "0" * 64
Row = dict[str, Any]


class DealView:
    def __init__(self, deal_id: str, snapshot: Row) -> None:
        self.deal_id = deal_id
        self.deal: Row | None = snapshot.get("deal")
        self.events: list[Row] = list(snapshot.get("events") or [])
        self.deliveries: list[Row] = list(snapshot.get("deliveries") or [])
        self.evaluations: list[Row] = list(snapshot.get("evaluations") or [])
        self.intents: list[Row] = list(snapshot.get("intents") or [])
        self.credits: list[Row] = list(snapshot.get("credits") or [])

    @property
    def exists(self) -> bool:
        return self.deal is not None

    @property
    def state(self) -> str:
        return NONE if self.deal is None else str(self.deal["state"])

    @property
    def head_seq(self) -> int:
        return 0 if self.deal is None else int(self.deal["head_seq"])

    @property
    def head_hash(self) -> str:
        return ZERO_HASH if self.deal is None else str(self.deal["head_hash"])

    def _field(self, name: str) -> Any:
        return None if self.deal is None else self.deal.get(name)

    @property
    def buyer_org_id(self) -> str:
        return str(self._field("buyer_org_id"))

    @property
    def seller_org_id(self) -> str:
        return str(self._field("seller_org_id"))

    @property
    def offer_id(self) -> str:
        return str(self._field("offer_id"))

    @property
    def terms(self) -> Row:
        """The proposed terms. Only read this once ``terms_hash`` is set."""
        terms = self._field("terms")
        if not isinstance(terms, dict):
            raise LookupError(f"deal {self.deal_id} has no terms yet")
        return terms  # pyright: ignore[reportUnknownVariableType]

    @property
    def terms_hash(self) -> str | None:
        return self._field("terms_hash")

    # events ---------------------------------------------------------------

    def events_of(self, event_type: str) -> list[Row]:
        return [event for event in self.events if event["event_type"] == event_type]

    def last_event(self, event_type: str) -> Row | None:
        found = self.events_of(event_type)
        return found[-1] if found else None

    def event_for_message(self, message_id: str) -> Row | None:
        for event in self.events:
            if event.get("source_message_id") == message_id:
                return event
        return None

    def message_of(self, event_type: str) -> Row:
        """The envelope recorded by the latest event of this type."""
        event = self.last_event(event_type)
        if event is None:
            raise LookupError(f"deal {self.deal_id} has no {event_type} event")
        return event["body"]["envelope"]

    @property
    def request(self) -> Row:
        """The buyer's ``service_request`` envelope."""
        return self.message_of("service_request")

    @property
    def buyer_did(self) -> str:
        return str(self.request["sender_did"])

    @property
    def acceptances(self) -> dict[str, str]:
        """``sender_did -> message_id`` of the recorded ``accept_terms``, in order."""
        found: dict[str, str] = {}
        for event in self.events_of("accept_terms"):
            envelope = event["body"]["envelope"]
            found.setdefault(str(envelope["sender_did"]), str(envelope["message_id"]))
        return found

    # deliveries and evaluations -------------------------------------------

    @property
    def current_delivery(self) -> Row | None:
        """The latest delivery; it supersedes every earlier one (SPEC §9.1)."""
        if not self.deliveries:
            return None
        return max(self.deliveries, key=lambda row: int(row["attempt"]))

    @property
    def next_attempt(self) -> int:
        current = self.current_delivery
        return 1 if current is None else int(current["attempt"]) + 1

    def evaluation(self, evaluation_request_id: str) -> Row | None:
        for row in self.evaluations:
            if row["evaluation_request_id"] == evaluation_request_id:
                return row
        return None

    def evaluations_for(self, delivery_id: str) -> list[Row]:
        return [row for row in self.evaluations if row["delivery_id"] == delivery_id]

    def intent(self, intent_id: str) -> Row | None:
        for row in self.intents:
            if row["intent_id"] == intent_id:
                return row
        return None
