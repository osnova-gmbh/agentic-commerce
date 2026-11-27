"""The dashboard: a small read-only JSON API and one static page."""

from __future__ import annotations

from pathlib import Path

import httpx
from cogit_finance_seams import BankError, ModuleError
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from .sources import DataSource
from .catalog import register_catalog
from .view import accounts_view, balances_view, deal_summary, deal_view

STATIC = Path(__file__).with_name("static")


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"error": code, "message": message}, status_code=status)


def create_app(source: DataSource) -> FastAPI:
    """Serve ``source`` (a ``FixtureSource`` or a ``ModuleSource``). GET routes only."""
    app = FastAPI(title="Escrow dashboard", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.source = source
    app.state.archived_views = {}
    app.state.service_titles = {}

    def with_service_title(view: dict) -> dict:
        deal = view["deal"]
        title = app.state.service_titles.get((deal["seller_org_id"], deal["offer_id"]))
        return {**view, "deal": {**deal, "offer_title": title}} if title else view

    @app.middleware("http")
    async def no_store(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(ModuleError)
    async def module_error(_: Request, exc: ModuleError) -> JSONResponse:
        return _error(502, exc.code, exc.message or "the deals module refused the query")

    @app.exception_handler(BankError)
    async def bank_error(_: Request, exc: BankError) -> JSONResponse:
        return _error(502, exc.code, exc.message or "the bank refused the call")

    @app.exception_handler(httpx.HTTPError)
    async def unreachable(_: Request, exc: httpx.HTTPError) -> JSONResponse:
        return _error(502, "source_unreachable", type(exc).__name__)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return _error(exc.status_code, code, str(exc.detail))

    @app.get("/")
    def page() -> FileResponse:
        return FileResponse(STATIC / "index.html", media_type="text/html")

    @app.get("/api/deals")
    def list_deals() -> dict:
        rows = [deal_summary(row) for row in source.deals()]
        live_ids = {row["deal_id"] for row in rows}
        rows += [view["deal"] for deal_id, view in app.state.archived_views.items() if deal_id not in live_ids]
        for row in rows:
            title = app.state.service_titles.get((row["seller_org_id"], row["offer_id"]))
            if title:
                row["offer_title"] = title
        rows.sort(key=lambda row: (row["created_at"], row["updated_at"]), reverse=True)  # newest first
        return {"deals": rows}

    @app.get("/api/deals/{deal_id}")
    def read_deal(deal_id: str):
        read = source.deal(deal_id)
        if not read.get("deal"):
            if deal_id in app.state.archived_views:
                return with_service_title(app.state.archived_views[deal_id])
            return _error(404, "unknown_deal", f"no deal {deal_id}")
        return with_service_title(deal_view(read, source.balances(deal_id)))

    @app.get("/api/balances")
    def read_balances(deal_id: str | None = None) -> dict:
        return balances_view(source.balances(deal_id), deal_id)

    @app.get("/api/accounts")
    def read_accounts() -> dict:
        return accounts_view(source.accounts())

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    register_catalog(app, source, STATIC)
    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app
