"""Demo data for E's tests: the values of PARALLEL-PLAN §5.1, a clock, a zip."""

from __future__ import annotations

import io
import zipfile
from datetime import UTC, datetime, timedelta
from typing import Any

from cogit_messaging_shim import to_ts

Row = dict[str, Any]
ESCROW_IBAN = "DE00EXAMPLE0000000001"
FEE_IBAN = "DE00EXAMPLE0000000002"
BUYER_IBAN = "DE00EXAMPLE0000000010"
SELLER_IBAN = "DE00EXAMPLE0000000020"
HAPPY_DEAL = "11111111-1111-4111-8111-111111111111"
BROKEN_DEAL = "22222222-2222-4222-8222-222222222222"
FILES = ("report.md", "data.csv", "summary.json")
PRICE = 50000
EVALUATORS = ("integrity", "required-files", "deadline")


class FakeClock:
    def __init__(self, start: str = "2026-11-27T10:00:00Z") -> None:
        self.moment = datetime.strptime(start, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)

    def now(self) -> datetime:
        return self.moment

    def tick(self, seconds: int = 1) -> None:
        self.moment += timedelta(seconds=seconds)

    def ts(self, plus: int = 0) -> str:
        return to_ts(self.moment + timedelta(seconds=plus))


def company(org_id: str, roles: list[str], iban: str, limit: int) -> Row:
    return {
        "org_id": org_id,
        "legal_name": f"Example {org_id}",
        "register_id": "HRB 000000",
        "address": "Example Street 1, 10115 Berlin",
        "roles": roles,
        "categories": ["reports"] if "seller" in roles else [],
        "iban": iban,
        "kyb_verified": True,
        "kyb_verified_by": "operator-co",
        "spending_limit_minor": limit,
    }


def acceptance(deadline: str | None = None) -> Row:
    params: dict[str, Row] = {
        "integrity": {},
        "required-files": {"required_files": list(FILES)},
        "deadline": {"delivery_deadline": deadline} if deadline else {},
    }
    return {
        "policy": "all",
        "max_attempts": 2,
        "evaluators": [
            {"evaluator_id": name, "version": 1, "params": params[name]}
            for name in EVALUATORS
        ],
    }


def offer() -> Row:
    return {
        "seller_org_id": "seller-co",
        "offer_id": "offer-1",
        "title": "Market report",
        "description": "A short market report.",
        "category": "reports",
        "price_minor": PRICE,
        "currency": "EUR",
        "delivery_time_s": 60,
        "input_schema": {"type": "object"},
        "deliverable": {"media_type": "application/zip", "required_files": list(FILES)},
        "default_acceptance": acceptance(),
        "active": True,
    }


def zip_bytes(names: tuple[str, ...]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name in names:
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            archive.writestr(info, f"demo content of {name}\n")
    return buffer.getvalue()
