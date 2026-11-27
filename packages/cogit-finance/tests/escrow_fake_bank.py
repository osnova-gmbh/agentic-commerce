"""In-memory bank for E's tests, after contracts/sim-bank.md."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from cogit_finance_seams import BankError
from cogit_messaging_shim import to_ts

Row = dict[str, Any]


class FakeBank:
    """``BankPort`` with idempotency keys, lookup by key and stable credit events."""

    def __init__(
        self, clock: Callable[[], datetime], balances: dict[str, int] | None = None
    ) -> None:
        self.clock = clock
        self.balances = dict(balances or {})
        self.owners: dict[str, str] = {}
        self.transfers: dict[str, Row] = {}  # by idempotency key
        self.requests = 0

    def transfer(
        self,
        *,
        from_iban: str,
        to_iban: str,
        amount_minor: int,
        currency: str,
        reference: str,
        idempotency_key: str,
    ) -> Row:
        self.requests += 1
        body = {
            "from_iban": from_iban,
            "to_iban": to_iban,
            "amount_minor": amount_minor,
            "currency": currency,
            "reference": reference,
        }
        known = self.transfers.get(idempotency_key)
        if known is not None:
            if {name: known[name] for name in body} != body:
                raise BankError(409, "idempotency_conflict")
            return dict(known)
        if from_iban not in self.balances or to_iban not in self.balances:
            raise BankError(404, "unknown_account")
        if type(amount_minor) is not int or amount_minor <= 0 or currency != "EUR":
            raise BankError(400, "invalid_transfer")
        if self.balances[from_iban] < amount_minor:
            raise BankError(409, "insufficient_funds")
        self.balances[from_iban] -= amount_minor
        self.balances[to_iban] += amount_minor
        number = len(self.transfers) + 1
        transfer = {
            "transfer_id": f"tr_{number:05d}",
            "event_id": str(number),
            "status": "booked",
            **body,
            "idempotency_key": idempotency_key,
            "booked_at": to_ts(self.clock()),
        }
        self.transfers[idempotency_key] = transfer
        return dict(transfer)

    def lookup(self, idempotency_key: str) -> Row | None:
        found = self.transfers.get(idempotency_key)
        return None if found is None else dict(found)

    def credits(self, iban: str, after: str = "0") -> list[Row]:
        names = ("event_id", "transfer_id", "from_iban", "to_iban", "amount_minor")
        names += ("currency", "reference", "booked_at")
        return [
            {name: transfer[name] for name in names}
            for transfer in self.transfers.values()
            if transfer["to_iban"] == iban and int(transfer["event_id"]) > int(after)
        ]

    def accounts(self) -> list[Row]:
        return [
            {
                "iban": iban,
                "owner": self.owners.get(iban, iban),
                "balance_minor": balance,
            }
            for iban, balance in sorted(self.balances.items())
        ]
