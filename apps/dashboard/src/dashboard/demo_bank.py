"""Replenish fictional buyer funds in the explicitly launched checkout demo.

The normal bank adapter and agent cores still reject insufficient funds. This
wrapper is installed only by run_demo.py, outside the signed-message logic and
inside the Boris transfer boundary.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from urllib.parse import urlsplit

import httpx

from cogit_finance_seams import BankError, SimBankClient


class DemoFundingBank:
    def __init__(self, bank, fund: Callable[..., dict], *,
                 buyer_iban: str = "DE00EXAMPLE0000000010",
                 reserve_minor: int = 1_000_000):
        self.bank = bank
        self.fund = fund
        self.buyer_iban = buyer_iban
        self.reserve_minor = reserve_minor
        self._lock = threading.RLock()

    @classmethod
    def from_url(cls, base_url: str) -> "DemoFundingBank":
        target = urlsplit(base_url)
        if target.scheme not in {"http", "https"} or target.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("Automatic demo funding is only available for a loopback simulated bank")
        http = httpx.Client(base_url=base_url, timeout=5)

        def fund(*, iban: str, minimum_balance_minor: int, idempotency_key: str) -> dict:
            response = http.post(
                "/admin/fund",
                json={"iban": iban, "minimum_balance_minor": minimum_balance_minor},
                headers={"Idempotency-Key": idempotency_key},
            )
            try:
                body = response.json()
            except ValueError:
                body = {}
            if response.status_code >= 400:
                raise BankError(response.status_code, str(body.get("error", "demo_funding_failed")),
                                str(body.get("message", "The simulated bank could not replenish demo funds")))
            return body

        return cls(SimBankClient(http), fund)

    def transfer(self, *, from_iban: str, to_iban: str, amount_minor: int,
                 currency: str, reference: str, idempotency_key: str) -> dict:
        with self._lock:
            # Replayed payments must not issue more demo funds. The real
            # transfer still performs its normal idempotency/body validation.
            if (from_iban == self.buyer_iban and currency == "EUR"
                    and type(amount_minor) is int and amount_minor > 0
                    and self.bank.lookup(idempotency_key) is None):
                account = next((row for row in self.bank.accounts()
                                if row["iban"] == self.buyer_iban), None)
                if account is not None and account["balance_minor"] < amount_minor:
                    minimum = max(amount_minor, self.reserve_minor)
                    try:
                        self.fund(iban=self.buyer_iban, minimum_balance_minor=minimum,
                                  idempotency_key="demo-fund:" + idempotency_key)
                    except BankError as error:
                        if error.status != 404:
                            raise
                        # Older running demo banks have no funding endpoint.
                        # Recycle already settled demo proceeds, never held
                        # escrow. These remain ordinary, recorded transfers.
                        self._recycle_settled_funds(minimum, idempotency_key)
            return self.bank.transfer(from_iban=from_iban, to_iban=to_iban,
                                      amount_minor=amount_minor, currency=currency,
                                      reference=reference, idempotency_key=idempotency_key)

    def _recycle_settled_funds(self, minimum: int, payment_key: str) -> None:
        for donor in ("DE00EXAMPLE0000000020", "DE00EXAMPLE0000000002"):
            refill_key = "demo-refill:" + payment_key + ":" + donor
            if self.bank.lookup(refill_key) is not None:
                continue
            accounts = {row["iban"]: row["balance_minor"] for row in self.bank.accounts()}
            shortfall = minimum - accounts.get(self.buyer_iban, 0)
            amount = min(shortfall, accounts.get(donor, 0))
            if amount <= 0:
                continue
            self.bank.transfer(from_iban=donor, to_iban=self.buyer_iban,
                               amount_minor=amount, currency="EUR",
                               reference="DEMO-REFILL/" + payment_key,
                               idempotency_key=refill_key)

    def lookup(self, idempotency_key: str) -> dict | None:
        return self.bank.lookup(idempotency_key)

    def credits(self, iban: str, after: str = "0") -> list[dict]:
        return self.bank.credits(iban, after)

    def accounts(self) -> list[dict]:
        return self.bank.accounts()
