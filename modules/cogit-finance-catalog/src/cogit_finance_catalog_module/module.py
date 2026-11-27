"""Reference implementation of the ``cogit-finance-catalog`` module (SPEC §11.3).

The export contract (fields, kinds, callers, error codes) is contracts/module-exports.md.
Adding a company, an offer or an evaluator is a data change only.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cogit_finance_seams import Caller, ModuleError, SqliteModule

from .rows import COMPANY, EVALUATOR, OFFER, Spec, clean, decode, encode, invalid

_PACKAGE_DIR = Path(__file__).resolve().parent
# Inside a built wheel the migrations sit in the package; in the source tree, beside ``src``.
MIGRATIONS_DIR = next(
    (path for path in (_PACKAGE_DIR / "migrations", _PACKAGE_DIR.parents[1] / "migrations") if path.is_dir()),
    _PACKAGE_DIR / "migrations",
)


def _text_arg(args: dict, name: str, *, optional: bool = False) -> str | None:
    value = args.get(name)
    if value is None and optional:
        return None
    if not isinstance(value, str) or not value:
        raise invalid(f"{name} must be a non-empty string")
    return value


class CatalogModule(SqliteModule):
    name = "cogit-finance-catalog"
    migrations_dir = MIGRATIONS_DIR
    queries = {
        "company.read": "company_read",
        "companies.list": "companies_list",
        "sellers.list": "sellers_list",
        "catalog.read": "catalog_read",
        "evaluators.list": "evaluators_list",
    }
    commands = {
        "company.upsert": "company_upsert",
        "evaluator.upsert": "evaluator_upsert",
        "catalog.publish": "catalog_publish",
    }

    # -- commands ---------------------------------------------------------------------

    def company_upsert(self, args: dict, caller: Caller) -> dict:
        self.require_operator(caller)
        company = clean(args.get("company"), COMPANY, "company")
        self.db.execute("DELETE FROM cat_companies WHERE org_id = ?", (company["org_id"],))
        self._insert("cat_companies", COMPANY, company)
        return {"org_id": company["org_id"]}

    def evaluator_upsert(self, args: dict, caller: Caller) -> dict:
        self.require_operator(caller)
        evaluator = clean(args.get("evaluator"), EVALUATOR, "evaluator")
        if evaluator["version"] < 1:
            raise invalid("evaluator.version must be 1 or greater")
        key = (evaluator["evaluator_id"], evaluator["version"])
        self.db.execute("DELETE FROM cat_evaluators WHERE evaluator_id = ? AND version = ?", key)
        self._insert("cat_evaluators", EVALUATOR, evaluator)
        return {"evaluator_id": key[0], "version": key[1]}

    def catalog_publish(self, args: dict, caller: Caller) -> dict:
        seller_org_id = _text_arg(args, "seller_org_id")
        offers = args.get("offers")
        if not isinstance(offers, list):
            raise invalid("offers must be a list")
        company = self._company(seller_org_id)
        if company is None or "seller" not in company["roles"]:
            raise ModuleError("unknown_seller", f"no company {seller_org_id} with role seller")
        rows, seen = [], set()
        for index, item in enumerate(offers):
            what = f"offers[{index}]"
            if isinstance(item, dict):
                if item.get("seller_org_id") not in (None, seller_org_id):
                    raise invalid(f"{what}.seller_org_id differs from seller_org_id")
                item = {**item, "seller_org_id": seller_org_id}
            offer = clean(item, OFFER, what)
            if offer["offer_id"] in seen:
                raise invalid(f"{what}.offer_id {offer['offer_id']} is listed twice")
            seen.add(offer["offer_id"])
            rows.append(offer)
        self.db.execute("DELETE FROM cat_offers WHERE seller_org_id = ?", (seller_org_id,))
        for offer in rows:
            self._insert("cat_offers", OFFER, offer)
        return {"count": len(rows)}

    # -- queries ----------------------------------------------------------------------

    def company_read(self, args: dict, caller: Caller) -> dict:
        return {"company": self._company(_text_arg(args, "org_id"))}

    def companies_list(self, args: dict, caller: Caller) -> dict:
        role = _text_arg(args, "role", optional=True)
        if role is not None and role not in ("buyer", "seller"):
            raise invalid("role must be buyer or seller")
        companies = self._select("cat_companies", COMPANY, order_by="org_id")
        return {"companies": [row for row in companies if role is None or role in row["roles"]]}

    def sellers_list(self, args: dict, caller: Caller) -> dict:
        category = _text_arg(args, "category", optional=True)
        companies = self._select("cat_companies", COMPANY, order_by="org_id")
        sellers = [
            company
            for company in companies
            if "seller" in company["roles"] and (category is None or category in company["categories"])
        ]
        return {"sellers": sellers}

    def catalog_read(self, args: dict, caller: Caller) -> dict:
        seller_org_id = _text_arg(args, "seller_org_id")
        offers = self._select("cat_offers", OFFER, "seller_org_id = ?", (seller_org_id,), order_by="offer_id")
        return {"offers": offers}

    def evaluators_list(self, args: dict, caller: Caller) -> dict:
        return {"evaluators": self._select("cat_evaluators", EVALUATOR, order_by="evaluator_id, version")}

    # -- storage ----------------------------------------------------------------------

    def _company(self, org_id: str | None) -> dict | None:
        found = self._select("cat_companies", COMPANY, "org_id = ?", (org_id,), order_by="org_id")
        return found[0] if found else None

    def _insert(self, table: str, spec: Spec, row: dict) -> None:
        columns = ", ".join(spec)
        marks = ", ".join("?" for _ in spec)
        self.db.execute(f"INSERT INTO {table} ({columns}) VALUES ({marks})", encode(row, spec))

    def _select(self, table: str, spec: Spec, where: str = "", params: tuple[Any, ...] = (), *, order_by: str) -> list:
        sql = f"SELECT {', '.join(spec)} FROM {table}"
        if where:
            sql += f" WHERE {where}"
        rows = self.db.execute(f"{sql} ORDER BY {order_by}", params).fetchall()
        return [decode(row, spec) for row in rows]
