"""HTTP API of the sim bank (contracts/sim-bank.md)."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .ledger import Ledger, Refusal, load_seed

_HTTP_CODES = {404: "not_found", 405: "method_not_allowed"}


def create_app(seed_file: Path | None = None) -> FastAPI:
    """Build the bank. Without ``seed_file`` the packaged copy of the demo seed is used."""
    ledger = Ledger(lambda: load_seed(seed_file))
    app = FastAPI(title="sim-bank", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.ledger = ledger

    @app.exception_handler(Refusal)
    async def refusal(_: Request, exc: Refusal) -> JSONResponse:
        return JSONResponse({"error": exc.code, "message": exc.message}, status_code=exc.status)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _HTTP_CODES.get(exc.status_code, "http_error")
        return JSONResponse({"error": code, "message": str(exc.detail)}, status_code=exc.status_code)

    @app.post("/transfers")
    async def post_transfer(request: Request) -> dict:
        key = request.headers.get("Idempotency-Key", "").strip()
        if not key:
            raise Refusal(400, "missing_idempotency_key", "send an Idempotency-Key header")
        try:
            body = json.loads(await request.body())
        except ValueError:
            raise Refusal(400, "invalid_transfer", "the body must be a JSON object") from None
        return ledger.transfer(key, body)

    @app.get("/transfers/by-key/{key:path}")
    async def get_transfer(key: str) -> dict:
        return ledger.lookup(key)

    @app.get("/events")
    async def get_events(iban: str = "", after: str = "0") -> dict:
        if not (after.isascii() and after.isdigit() and len(after) <= 18):
            raise Refusal(400, "invalid_request", "after must be an event ID (a non-negative integer)")
        return {"events": ledger.credits(iban, int(after))}

    @app.get("/accounts")
    async def get_accounts() -> dict:
        return {"accounts": ledger.accounts()}

    @app.post("/admin/reset")
    async def post_reset() -> dict:
        ledger.reset()
        return {"ok": True}

    @app.get("/health")
    async def get_health() -> dict:
        return {"status": "ok"}

    return app
