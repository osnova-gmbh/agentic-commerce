"""Public, read-only company directory. Payment and onboarding data stay private."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from .sources import DataSource


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
    }


def register_catalog(app: FastAPI, source: DataSource, static: Path) -> None:
    @app.get("/catalog")
    def page() -> FileResponse:
        return FileResponse(static / "catalog.html", media_type="text/html")

    @app.get("/api/catalog")
    def companies() -> dict:
        rows = [public_company(row) for row in source.companies()]
        rows.sort(key=lambda row: (row["outreach_priority"] or 999, row["name"].casefold()))
        return {"companies": rows}
