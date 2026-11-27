"""Public, read-only company directory. Payment and onboarding data stay private."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from .sources import DataSource
from .api_models import CatalogResponse, ProviderOffersResponse


def public_offer(company: dict, offer: dict) -> dict:
    profile = company.get("profile") or {}
    return {
        "company_id": company["org_id"],
        "company_name": profile.get("display_name") or company["legal_name"],
        "offer_id": offer["offer_id"],
        "title": offer["title"],
        "description": offer.get("description", ""),
        "category": offer.get("category", ""),
        "source_url": offer["source_url"],
        "price_minor": offer.get("price_minor"),
        "currency": offer.get("currency"),
        "price_label": offer.get("price_label") or "Request quote",
        "pricing_basis": offer.get("pricing_basis"),
        "contact_url": offer.get("contact_url"),
        "availability": offer.get("availability", "contact_provider"),
        "verified_on": offer.get("verified_on"),
    }


def public_company(company: dict) -> dict:
    profile = company.get("profile") or {}
    return {
        "org_id": company["org_id"],
        "name": profile.get("display_name") or company["legal_name"],
        "roles": company.get("roles", []),
        "categories": company.get("categories", []),
        "website": profile.get("website"),
        "products_and_services": profile.get("products_and_services", ""),
        "target_customers": profile.get("target_customers", ""),
        "campus": profile.get("campus"),
        "programme": profile.get("programme"),
        "status": profile.get("status"),
        "outreach_priority": profile.get("outreach_priority"),
        "recommended": profile.get("recommended", False),
        "offers": [public_offer(company, offer) for offer in profile.get("offers", [])],
    }


def register_catalog(app: FastAPI, source: DataSource, static: Path) -> None:
    def directory() -> list[dict]:
        rows = [public_company(row) for row in source.companies()]
        rows.sort(key=lambda row: (row["outreach_priority"] or 999, row["name"].casefold()))
        return rows

    @app.get("/catalog", include_in_schema=False)
    def page() -> FileResponse:
        return FileResponse(static / "catalog.html", media_type="text/html")

    @app.get("/api/catalog", response_model=CatalogResponse, response_model_exclude_unset=True,
             operation_id="list_companies", tags=["Catalog"], summary="Discover public Delta Campus companies and their offerings")
    def companies() -> dict:
        return {"companies": directory()}

    @app.get("/api/provider-offers", response_model=ProviderOffersResponse, response_model_exclude_unset=True,
             operation_id="list_provider_offers", tags=["Catalog"], summary="List published provider offerings and their pricing basis")
    def offers() -> dict:
        return {"offers": [offer for company in directory() for offer in company["offers"]]}
