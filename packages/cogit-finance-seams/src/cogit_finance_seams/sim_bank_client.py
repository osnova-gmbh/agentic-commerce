"""BankPort over the sim bank's HTTP API (contracts/sim-bank.md)."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from .protocols import BankError


class SimBankClient:
    def __init__(self, http: Any) -> None:
        """``http`` is an ``httpx.Client`` with a base URL, or a Starlette ``TestClient``."""
        self._http = http

    @classmethod
    def from_url(cls, base_url: str, timeout: float = 5.0) -> "SimBankClient":
        return cls(httpx.Client(base_url=base_url, timeout=timeout))

    def transfer(
        self,
        *,
        from_iban: str,
        to_iban: str,
        amount_minor: int,
        currency: str,
        reference: str,
        idempotency_key: str,
    ) -> dict:
        response = self._http.post(
            "/transfers",
            json={
                "from_iban": from_iban,
                "to_iban": to_iban,
                "amount_minor": amount_minor,
                "currency": currency,
                "reference": reference,
            },
            headers={"Idempotency-Key": idempotency_key},
        )
        return self._json(response)

    def lookup(self, idempotency_key: str) -> dict | None:
        response = self._http.get(f"/transfers/by-key/{quote(idempotency_key, safe='')}")
        if response.status_code == 404:
            return None
        return self._json(response)

    def credits(self, iban: str, after: str = "0") -> list[dict]:
        return self._json(self._http.get("/events", params={"iban": iban, "after": after}))["events"]

    def accounts(self) -> list[dict]:
        return self._json(self._http.get("/accounts"))["accounts"]

    @staticmethod
    def _json(response: Any) -> dict:
        if response.status_code >= 400:
            try:
                body = response.json()
            except ValueError:
                body = {}
            raise BankError(response.status_code, str(body.get("error", "bank_error")), str(body.get("message", "")))
        return response.json()
