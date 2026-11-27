"""In-memory double-entry ledger of the sim bank (contracts/sim-bank.md).

Every transfer debits one account and credits another under one lock, so the sum of all
balances never changes. Money is integer minor units; there are no floats.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

import yaml

DEFAULT_SEED = Path(__file__).with_name("bank.yaml")
TRANSFER_FIELDS = ("from_iban", "to_iban", "amount_minor", "currency", "reference")
EVENT_FIELDS = ("event_id", "transfer_id", *TRANSFER_FIELDS, "booked_at")


class Refusal(Exception):
    """The bank refuses a call. Rendered as ``{"error": code, "message": message}``."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(f"{status} {code}: {message}")
        self.status = status
        self.code = code
        self.message = message


def now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _is_int(value: object) -> bool:
    return type(value) is int  # bool is a subclass of int and is not an amount


def load_seed(seed_file: Path | str | None = None) -> list[dict]:
    """Read opening balances from a YAML file shaped like ``data/demo/bank.yaml``."""
    path = Path(seed_file) if seed_file is not None else DEFAULT_SEED
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    rows = data.get("accounts") if isinstance(data, dict) else None
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"{path}: expected a non-empty 'accounts' list")
    accounts: list[dict] = []
    for row in rows:
        iban = row.get("iban") if isinstance(row, dict) else None
        if not isinstance(iban, str) or not iban:
            raise ValueError(f"{path}: every account needs an 'iban'")
        if any(account["iban"] == iban for account in accounts):
            raise ValueError(f"{path}: duplicate account {iban}")
        balance = row.get("balance_minor", 0)
        if not _is_int(balance) or balance < 0:
            raise ValueError(f"{path}: balance_minor of {iban} must be a non-negative integer")
        accounts.append({"iban": iban, "owner": str(row.get("owner", "")), "balance_minor": balance})
    return accounts


def validate_transfer(body: object) -> dict:
    """Return the five transfer fields of a request body, or refuse with ``invalid_transfer``."""

    def invalid(message: str) -> Refusal:
        return Refusal(400, "invalid_transfer", message)

    if not isinstance(body, dict):
        raise invalid("the body must be a JSON object")
    missing = [name for name in TRANSFER_FIELDS if name not in body]
    if missing:
        raise invalid(f"missing field: {', '.join(missing)}")
    for name in ("from_iban", "to_iban", "currency", "reference"):
        if not isinstance(body[name], str):
            raise invalid(f"{name} must be a string")
    if not _is_int(body["amount_minor"]) or body["amount_minor"] <= 0:
        raise invalid("amount_minor must be a positive integer (minor units)")
    if body["currency"] != "EUR":
        raise invalid("currency must be EUR")
    if body["from_iban"] == body["to_iban"]:
        raise invalid("from_iban and to_iban are the same account")
    return {name: body[name] for name in TRANSFER_FIELDS}


class Ledger:
    """Accounts, booked transfers and their credit events. One lock guards everything."""

    def __init__(self, seed: Callable[[], list[dict]] = load_seed, clock: Callable[[], str] = now_ts) -> None:
        self._seed = seed
        self._clock = clock
        self._lock = threading.Lock()
        self._last_id = 0  # survives reset(): an event ID is never used twice by one process
        self._owners: dict[str, str] = {}
        self._balances: dict[str, int] = {}
        self._transfers: list[dict] = []
        self._by_key: dict[str, dict] = {}
        self.reset()

    def reset(self) -> None:
        """Reseed the accounts and forget all transfers."""
        accounts = self._seed()
        with self._lock:
            self._owners = {account["iban"]: account["owner"] for account in accounts}
            self._balances = {account["iban"]: account["balance_minor"] for account in accounts}
            self._transfers = []
            self._by_key = {}

    def transfer(self, idempotency_key: str, body: object) -> dict:
        request = validate_transfer(body)
        with self._lock:
            known = self._by_key.get(idempotency_key)
            if known is not None:
                if any(known[name] != request[name] for name in TRANSFER_FIELDS):
                    raise Refusal(409, "idempotency_conflict", "this key was used with a different body")
                return dict(known)
            for name in ("from_iban", "to_iban"):
                if request[name] not in self._balances:
                    raise Refusal(404, "unknown_account", f"{name} {request[name]} is not an account")
            if self._balances[request["from_iban"]] < request["amount_minor"]:
                raise Refusal(409, "insufficient_funds", f"the balance of {request['from_iban']} is too low")
            self._last_id += 1
            transfer = {
                "transfer_id": f"tr-{self._last_id:06d}",
                "event_id": str(self._last_id),
                "status": "booked",
                **request,
                "idempotency_key": idempotency_key,
                "booked_at": self._clock(),
            }
            self._balances[request["from_iban"]] -= request["amount_minor"]
            self._balances[request["to_iban"]] += request["amount_minor"]
            self._transfers.append(transfer)
            self._by_key[idempotency_key] = transfer
            return dict(transfer)

    def lookup(self, idempotency_key: str) -> dict:
        with self._lock:
            transfer = self._by_key.get(idempotency_key)
            if transfer is None:
                raise Refusal(404, "unknown_transfer", "no transfer under that key")
            return dict(transfer)

    def credits(self, iban: str, after: int = 0) -> list[dict]:
        """Credits to ``iban`` with an event ID greater than ``after``, oldest first."""
        with self._lock:
            if iban not in self._balances:
                raise Refusal(404, "unknown_account", f"{iban} is not an account")
            return [
                {name: transfer[name] for name in EVENT_FIELDS}
                for transfer in self._transfers
                if transfer["to_iban"] == iban and int(transfer["event_id"]) > after
            ]

    def accounts(self) -> list[dict]:
        with self._lock:
            return [
                {"iban": iban, "owner": self._owners[iban], "balance_minor": balance}
                for iban, balance in sorted(self._balances.items())
            ]
