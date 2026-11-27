"""The public offer overview and company cards share the same source records."""

from pathlib import Path

import yaml
from fastapi.testclient import TestClient
from cogit_finance_catalog_module import CatalogModule
from cogit_finance_seams import LocalModuleHost
from dashboard import ModuleSource, create_app


def test_company_cards_and_overview_publish_the_same_actual_offers():
    root = Path(__file__).resolve().parents[3]
    companies = yaml.safe_load((root / "data/demo/companies.yaml").read_text(encoding="utf-8"))["companies"]
    host = LocalModuleHost()
    host.install(CatalogModule())
    operator = host.port("operator", "operator")
    for company in companies:
        operator.module_command("cogit-finance-catalog", "company.upsert", {"company": company},
                                idempotency_key="seed:" + company["org_id"])
    client = TestClient(create_app(ModuleSource(host.port("dashboard", "operator_ro"))))
    cards = client.get("/api/catalog").json()["companies"]
    offers = client.get("/api/provider-offers").json()["offers"]
    assert offers == [offer for company in cards for offer in company["offers"]]
    providers = [company for company in cards if company["status"] == "prospective_buyer"]
    assert len(providers) == 10
    assert all(company["offers"] for company in providers)
    assert len({(offer["company_id"], offer["offer_id"]) for offer in offers}) == len(offers)
    assert all(offer["source_url"].startswith("https://") for offer in offers)
    assert all(offer["company_id"] != "seller-co" for offer in offers)
    assert all("iban" not in offer and "spending_limit_minor" not in offer for offer in offers)
    quote_offers = [offer for offer in offers if offer["price_minor"] is None]
    assert quote_offers and all(offer["price_label"] for offer in quote_offers)
    course = next(offer for offer in offers if offer["offer_id"] == "context-engineering-claude-code")
    assert course["price_minor"] == 0 and course["price_label"] == "Free course"
    waitlist = next(offer for offer in offers if offer["offer_id"] == "ma-operating-system")
    assert waitlist["availability"] == "waitlist"
    assert client.post("/api/provider-offers", json={}).status_code == 405
