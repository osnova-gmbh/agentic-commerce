"""Where the dashboard reads from: JSON fixture files, or the deals module and the bank.

Both sources return module results unchanged (contracts/module-exports.md, section
"cogit-finance-deals"). They only read: queries on the module, ``accounts()`` on the bank.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Protocol

from cogit_finance_seams import BankPort, ModulePort

DEALS_MODULE = "cogit-finance-deals"
LEDGER_ACCOUNTS = ("held", "seller", "fee", "buyer_refund", "returned")
_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


def empty_read() -> dict:
    """``deal.read`` for an unknown deal."""
    return {"deal": None, "events": [], "deliveries": [], "evaluations": [], "intents": [], "credits": []}


class DataSource(Protocol):
    def companies(self) -> list[dict]:
        """Company records, including their public catalog profiles."""
        ...

    def deals(self) -> list[dict]:
        """Rows of ``deal.list``."""
        ...

    def deal(self, deal_id: str) -> dict:
        """Result of ``deal.read``; ``deal`` is None for an unknown deal."""
        ...

    def balances(self, deal_id: str | None = None) -> dict:
        """Result of ``ledger.balances``, for one deal or for all."""
        ...

    def accounts(self) -> list[dict]:
        """The bank's accounts: ``iban``, ``owner``, ``balance_minor``."""
        ...


class ModuleSource:
    """Live data: the ``cogit-finance-deals`` queries and, when given, the bank's accounts."""

    def __init__(self, modules: ModulePort, bank: BankPort | None = None) -> None:
        self._modules = modules
        self._bank = bank

    def companies(self) -> list[dict]:
        return self._modules.module_query("cogit-finance-catalog", "companies.list", {})["companies"]

    def deals(self) -> list[dict]:
        return self._modules.module_query(DEALS_MODULE, "deal.list", {})["deals"]

    def deal(self, deal_id: str) -> dict:
        return self._modules.module_query(DEALS_MODULE, "deal.read", {"deal_id": deal_id})

    def balances(self, deal_id: str | None = None) -> dict:
        return self._modules.module_query(DEALS_MODULE, "ledger.balances", {} if deal_id is None else {"deal_id": deal_id})

    def accounts(self) -> list[dict]:
        return [] if self._bank is None else self._bank.accounts()


class FixtureSource:
    """A directory of module results as JSON files, read again on every call.

    ``deals.json`` (``deal.list``), ``deals/<deal_id>.json`` (``deal.read``),
    ``balances.json`` and ``balances/<deal_id>.json`` (``ledger.balances``),
    ``accounts.json`` (the bank's ``GET /accounts``).
    """

    def __init__(self, directory: Path | str) -> None:
        self.directory = Path(directory)
        if not (self.directory / "deals.json").is_file():
            raise FileNotFoundError(f"{self.directory} is not a fixture set: deals.json is missing")

    def _read(self, relative: str, default: dict) -> dict:
        path = self.directory / relative
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default

    def deals(self) -> list[dict]:
        return self._read("deals.json", {"deals": []})["deals"]

    def companies(self) -> list[dict]:
        return self._read("companies.json", {"companies": []})["companies"]

    def deal(self, deal_id: str) -> dict:
        if not _SAFE_ID.fullmatch(deal_id):  # the ID becomes a file name
            return empty_read()
        return self._read(f"deals/{deal_id}.json", empty_read())

    def balances(self, deal_id: str | None = None) -> dict:
        zero = dict.fromkeys(LEDGER_ACCOUNTS, 0)
        if deal_id is None:
            return self._read("balances.json", zero)
        return self._read(f"balances/{deal_id}.json", zero) if _SAFE_ID.fullmatch(deal_id) else zero

    def accounts(self) -> list[dict]:
        return self._read("accounts.json", {"accounts": []})["accounts"]


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)  # a running dashboard never reads a half-written file


def dump_source(source: DataSource, directory: Path | str) -> Path:
    """Write everything a source returns as a fixture set, e.g. a dump of a real run."""
    target = Path(directory)
    deals = source.deals()
    for row in deals:
        if not _SAFE_ID.fullmatch(row["deal_id"]):
            raise ValueError(f"deal ID {row['deal_id']!r} cannot be a file name")
        _write(target / "deals" / f"{row['deal_id']}.json", source.deal(row["deal_id"]))
        _write(target / "balances" / f"{row['deal_id']}.json", source.balances(row["deal_id"]))
    _write(target / "balances.json", source.balances())
    _write(target / "accounts.json", {"accounts": source.accounts()})
    _write(target / "deals.json", {"deals": deals})
    return target
