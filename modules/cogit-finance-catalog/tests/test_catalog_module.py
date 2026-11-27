from __future__ import annotations

from pathlib import Path

import pytest
from cogit_finance_catalog_module import CatalogModule
from cogit_finance_seams import LocalModuleHost, ModuleError

MODULE = "cogit-finance-catalog"
DEMO_DATA = Path(__file__).resolve().parents[3] / "data" / "demo"


class Catalog:
    """The module as its callers see it: one port per caller, keys made up per call."""

    def __init__(self) -> None:
        self.host = LocalModuleHost()
        self.host.install(CatalogModule())
        self.operator = self.host.port("operator", "operator")
        self.seller = self.host.port("seller-agent")
        self.buyer = self.host.port("buyer-agent")
        self._keys = 0

    def command(self, port, export: str, args: dict) -> dict:
        self._keys += 1
        return port.module_command(MODULE, export, args, idempotency_key=f"k{self._keys}")

    def query(self, export: str, args: dict | None = None) -> dict:
        return self.buyer.module_query(MODULE, export, args)

    def add_company(self, org_id: str, roles=("seller",), categories=("reports",), **extra) -> dict:
        company = {"org_id": org_id, "legal_name": f"{org_id} GmbH", "roles": list(roles)}
        company.update(categories=list(categories), **extra)
        return self.command(self.operator, "company.upsert", {"company": company})

    def publish(self, seller_org_id: str, offers: list) -> dict:
        return self.command(self.seller, "catalog.publish", {"seller_org_id": seller_org_id, "offers": offers})


@pytest.fixture()
def catalog() -> Catalog:
    return Catalog()


def offer(offer_id: str, **extra) -> dict:
    base = {
        "offer_id": offer_id,
        "title": "Market report",
        "description": "A short market report.",
        "category": "reports",
        "price_minor": 50000,
        "currency": "EUR",
        "delivery_time_s": 60,
        "input_schema": {"type": "object", "properties": {"topic": {"type": "string"}}, "required": ["topic"]},
        "deliverable": {"media_type": "application/zip", "required_files": ["report.md", "data.csv"]},
        "default_acceptance": {
            "policy": "all",
            "max_attempts": 2,
            "evaluators": [{"evaluator_id": "integrity", "version": 1, "params": {}}],
        },
        "active": True,
    }
    return {**base, **extra}


def code_of(error) -> str:
    return error.value.code


def test_empty_catalog_returns_empty_lists(catalog):
    assert catalog.query("sellers.list") == {"sellers": []}
    assert catalog.query("sellers.list", {"category": "reports"}) == {"sellers": []}
    assert catalog.query("catalog.read", {"seller_org_id": "seller-co"}) == {"offers": []}
    assert catalog.query("evaluators.list") == {"evaluators": []}
    assert catalog.query("company.read", {"org_id": "seller-co"}) == {"company": None}


def test_company_round_trip_keeps_lists_and_booleans(catalog):
    company = {
        "org_id": "seller-co",
        "legal_name": "Example Seller GmbH",
        "register_id": "HRB 000002",
        "address": "Example Street 20, 10115 Berlin",
        "roles": ["seller"],
        "categories": ["reports", "data"],
        "iban": "DE00EXAMPLE0000000020",
        "kyb_verified": True,
        "kyb_verified_by": "operator-co",
        "spending_limit_minor": 200000,
        "profile": {},
    }
    assert catalog.command(catalog.operator, "company.upsert", {"company": company}) == {"org_id": "seller-co"}
    stored = catalog.query("company.read", {"org_id": "seller-co"})["company"]
    assert stored == company
    assert stored["kyb_verified"] is True and isinstance(stored["roles"], list)
    assert catalog.query("sellers.list") == {"sellers": [company]}


def test_company_upsert_replaces_the_row_and_fills_defaults(catalog):
    catalog.add_company("seller-co", kyb_verified=True, iban="DE00EXAMPLE0000000020")
    catalog.command(catalog.operator, "company.upsert", {"company": {"org_id": "seller-co", "legal_name": "Renamed"}})
    assert catalog.query("company.read", {"org_id": "seller-co"})["company"] == {
        "org_id": "seller-co",
        "legal_name": "Renamed",
        "register_id": None,
        "address": None,
        "roles": [],
        "categories": [],
        "iban": None,
        "kyb_verified": False,
        "kyb_verified_by": None,
        "spending_limit_minor": 0,
        "profile": {},
    }


def test_company_profile_round_trip_and_role_filter(catalog):
    profile = {
        "display_name": "Example Prospect",
        "website": "https://example.invalid/",
        "products_and_services": "Business software",
        "target_customers": "Manufacturers",
        "status": "prospective_buyer",
        "outreach_priority": 1,
        "recommended": True,
    }
    catalog.add_company("prospect", roles=("buyer",), profile=profile)
    catalog.add_company("seller")
    buyers = catalog.query("companies.list", {"role": "buyer"})["companies"]
    assert [row["org_id"] for row in buyers] == ["prospect"]
    assert buyers[0]["profile"] == profile
    assert [row["org_id"] for row in catalog.query("companies.list")["companies"]] == ["prospect", "seller"]
    with pytest.raises(ModuleError) as error:
        catalog.query("companies.list", {"role": "unknown"})
    assert code_of(error) == "invalid_argument"


def test_evaluator_round_trip_and_sort_order(catalog):
    def evaluator(evaluator_id: str, version: int, **extra) -> dict:
        base = {"evaluator_id": evaluator_id, "version": version, "org_id": "operator-co", "did": "did:key:z6Mk"}
        return {**base, **extra}

    full = evaluator(
        "required-files",
        1,
        description="Every required file is present.",
        deterministic=True,
        accepts=["application/zip"],
        params_schema={"type": "object", "required": ["required_files"]},
    )
    for item in (full, evaluator("required-files", 2), evaluator("integrity", 1, did=None)):
        result = catalog.command(catalog.operator, "evaluator.upsert", {"evaluator": item})
        assert result == {"evaluator_id": item["evaluator_id"], "version": item["version"]}
    listed = catalog.query("evaluators.list")["evaluators"]
    assert [(row["evaluator_id"], row["version"]) for row in listed] == [
        ("integrity", 1),
        ("required-files", 1),
        ("required-files", 2),
    ]
    assert listed[1] == full
    assert listed[1]["deterministic"] is True
    assert listed[0] == {
        "evaluator_id": "integrity",
        "version": 1,
        "org_id": "operator-co",
        "did": None,
        "description": None,
        "deterministic": False,
        "accepts": [],
        "params_schema": {},
    }
    # An upsert of the same key replaces the row.
    catalog.command(catalog.operator, "evaluator.upsert", {"evaluator": evaluator("integrity", 1, did="did:key:z6New")})
    assert catalog.query("evaluators.list")["evaluators"][0]["did"] == "did:key:z6New"
    assert len(catalog.query("evaluators.list")["evaluators"]) == 3


def test_publish_then_read_returns_offers_sorted_by_offer_id(catalog):
    catalog.add_company("seller-co")
    listed = [offer("offer-2", active=False, description=""), offer("offer-1")]
    assert catalog.publish("seller-co", listed) == {"count": 2}
    offers = catalog.query("catalog.read", {"seller_org_id": "seller-co"})["offers"]
    assert [row["offer_id"] for row in offers] == ["offer-1", "offer-2"]
    assert offers[0] == {"seller_org_id": "seller-co", **offer("offer-1")}
    assert offers[0]["active"] is True and offers[1]["active"] is False
    assert offers[0]["deliverable"]["required_files"] == ["report.md", "data.csv"]
    assert offers[0]["default_acceptance"]["evaluators"][0]["version"] == 1


def test_publish_replaces_only_that_sellers_offers(catalog):
    catalog.add_company("seller-co")
    catalog.add_company("other-co")
    catalog.publish("seller-co", [offer("offer-1"), offer("offer-2")])
    catalog.publish("other-co", [offer("offer-9")])
    assert catalog.publish("seller-co", [offer("offer-3", price_minor=70000)]) == {"count": 1}
    offers = catalog.query("catalog.read", {"seller_org_id": "seller-co"})["offers"]
    assert [(row["offer_id"], row["price_minor"]) for row in offers] == [("offer-3", 70000)]
    assert len(catalog.query("catalog.read", {"seller_org_id": "other-co"})["offers"]) == 1
    assert catalog.publish("seller-co", []) == {"count": 0}
    assert catalog.query("catalog.read", {"seller_org_id": "seller-co"}) == {"offers": []}


def test_publish_for_an_unknown_seller_fails(catalog):
    catalog.add_company("buyer-co", roles=("buyer",), categories=())
    for org_id in ("nobody", "buyer-co"):
        with pytest.raises(ModuleError) as error:
            catalog.publish(org_id, [offer("offer-1")])
        assert code_of(error) == "unknown_seller"
    assert catalog.query("catalog.read", {"seller_org_id": "buyer-co"}) == {"offers": []}


def test_a_bad_offer_leaves_the_published_catalog_unchanged(catalog):
    catalog.add_company("seller-co")
    catalog.publish("seller-co", [offer("offer-1")])
    bad_lists = (
        [offer("offer-2"), offer("offer-3", price_minor=499.5)],
        [offer("offer-2", price_minor=True)],
        [offer("offer-2", title="")],
        [{"offer_id": "offer-2"}],
        [offer("offer-2"), offer("offer-2")],
        [offer("offer-2", colour="red")],
        [offer("offer-2", seller_org_id="other-co")],
    )
    for offers in bad_lists:
        with pytest.raises(ModuleError) as error:
            catalog.publish("seller-co", offers)
        assert code_of(error) == "invalid_argument"
    offers = catalog.query("catalog.read", {"seller_org_id": "seller-co"})["offers"]
    assert [row["offer_id"] for row in offers] == ["offer-1"]


def test_sellers_list_filters_by_category_and_sorts_by_org_id(catalog):
    catalog.add_company("zeta-co", categories=("reports",))
    catalog.add_company("alpha-co", categories=("reports", "translations"))
    catalog.add_company("mid-co", categories=("translations",))
    catalog.add_company("buyer-co", roles=("buyer",), categories=("reports",))
    catalog.add_company("both-co", roles=("buyer", "seller"), categories=())

    def org_ids(args: dict | None = None) -> list:
        return [row["org_id"] for row in catalog.query("sellers.list", args)["sellers"]]

    assert org_ids() == ["alpha-co", "both-co", "mid-co", "zeta-co"]
    assert org_ids({"category": None}) == ["alpha-co", "both-co", "mid-co", "zeta-co"]
    assert org_ids({"category": "reports"}) == ["alpha-co", "zeta-co"]
    assert org_ids({"category": "translations"}) == ["alpha-co", "mid-co"]
    assert org_ids({"category": "nothing"}) == []


def test_upserts_are_for_the_operator_only(catalog):
    company = {"company": {"org_id": "seller-co", "legal_name": "Example Seller GmbH", "roles": ["seller"]}}
    evaluator = {"evaluator": {"evaluator_id": "integrity", "version": 1, "org_id": "operator-co"}}
    for export, args in (("company.upsert", company), ("evaluator.upsert", evaluator)):
        with pytest.raises(ModuleError) as error:
            catalog.command(catalog.seller, export, args)
        assert code_of(error) == "forbidden"
    assert catalog.query("company.read", {"org_id": "seller-co"}) == {"company": None}
    assert catalog.query("evaluators.list") == {"evaluators": []}
    with pytest.raises(ModuleError) as error:
        catalog.command(catalog.host.port("dashboard", "operator_ro"), "company.upsert", company)
    assert code_of(error) == "read_only"


def test_the_demo_data_files_load_through_the_exports(catalog):
    yaml = pytest.importorskip("yaml")
    companies = yaml.safe_load((DEMO_DATA / "companies.yaml").read_text(encoding="utf-8"))["companies"]
    evaluators = yaml.safe_load((DEMO_DATA / "evaluators.yaml").read_text(encoding="utf-8"))["evaluators"]
    published = yaml.safe_load((DEMO_DATA / "offers.seller-co.yaml").read_text(encoding="utf-8"))
    for company in companies:
        catalog.command(catalog.operator, "company.upsert", {"company": company})
    for evaluator in evaluators:
        catalog.command(catalog.operator, "evaluator.upsert", {"evaluator": evaluator})
    assert catalog.publish(published["seller_org_id"], published["offers"]) == {"count": len(published["offers"])}

    sellers = catalog.query("sellers.list", {"category": "reports"})["sellers"]
    assert [row["org_id"] for row in sellers] == ["seller-co"]
    assert sellers[0] == next(company for company in companies if company["org_id"] == "seller-co")
    offers = catalog.query("catalog.read", {"seller_org_id": "seller-co"})["offers"]
    assert offers == [
        {"seller_org_id": "seller-co", **row}
        for row in sorted(published["offers"], key=lambda row: row["offer_id"])
    ]
    listed = catalog.query("evaluators.list")["evaluators"]
    assert [row["evaluator_id"] for row in listed] == ["deadline", "integrity", "required-files"]
    assert all(row["did"] is None and row["deterministic"] is True for row in listed)
