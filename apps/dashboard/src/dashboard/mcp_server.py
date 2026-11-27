"""MCP tools over the existing commerce HTTP API, using the official MCP SDK."""
from __future__ import annotations

import hashlib
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from fastapi import FastAPI
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field, StrictBool
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse

from .api_models import (
    BorisReportResponse, CatalogResponse, CheckoutMutationResponse,
    CheckoutStatusResponse, DealsResponse, DealViewResponse,
    ProviderOffersResponse, ServiceListResponse,
)
from .discovery import (build_commerce_openapi, build_order_actions, checkout_links,
                        describe_openapi, prepare_action)

DEFAULT_API_URL = "http://127.0.0.1:8091"
MAX_DELIVERY_BYTES = 16 * 1024 * 1024
ROOT = Path(__file__).resolve().parents[4]
SKILL_FILE = ROOT / ".agents/skills/use-agentic-commerce/SKILL.md"
Key = Annotated[str, Field(min_length=1, max_length=200, description="A unique key for one logical operation. Reuse exactly this key and body on a retry.")]
Amount = Annotated[int, Field(strict=True, gt=0, description="Current quoted total in EUR cents, read from the checkout terms before confirming.")]
READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
PAYMENT = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False)


class DiscoveryResponse(BaseModel):
    name: str
    api_base_url: str
    api_manifest_url: str
    openapi_url: str
    mcp_endpoint: str | None
    protocol_version: str
    simulation: bool
    workflow: list[str]
    resources: dict[str, str]
    api_contract: dict[str, Any]


class DeliveryResponse(BaseModel):
    deal_id: str
    available: bool
    download_url: str
    media_type: str | None = None
    size_bytes: int | None = None
    sha256: str | None = None
    filename: str | None = None


def validate_api_url(value: str) -> str:
    parsed = urlsplit(value)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname
            or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}):
        raise ValueError("Commerce API URL must be an HTTP(S) origin without credentials, path, query or fragment")
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("The local demo MCP adapter only connects to loopback API addresses")
    return value.rstrip("/")


def rewrite_schema_links(value: Any, api_base: str, schema_url: str) -> Any:
    """Keep operations on the backend; resolve schemas on the sidecar that serves them."""
    if isinstance(value, list):
        return [rewrite_schema_links(item, api_base, schema_url) for item in value]
    if isinstance(value, dict):
        result = {key: rewrite_schema_links(item, api_base, schema_url) for key, item in value.items()}
        ref = result.get("$ref")
        if isinstance(ref, str):
            for prefix in (api_base + "/openapi.json", "/openapi.json"):
                if ref.startswith(prefix + "#"):
                    result["$ref"] = schema_url + ref[len(prefix):]
                    break
        return result
    return value


class CommerceAPI:
    def __init__(self, base_url: str, http: httpx.AsyncClient | None = None,
                 schema_url: str = "commerce://openapi", manifest_url: str = "commerce://capabilities"):
        self.base_url = validate_api_url(base_url)
        self.http = http
        self.schema_url = schema_url
        self.manifest_url = manifest_url

    @asynccontextmanager
    async def client(self):
        if self.http is not None:
            yield self.http
        else:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=30, follow_redirects=False) as client:
                yield client

    async def request(self, method: str, path: str, *, body=None, key=None) -> dict:
        headers = {"Idempotency-Key": key} if key else {}
        try:
            async with self.client() as client:
                response = await client.request(method, path, json=body, headers=headers)
            try:
                result = response.json()
            except ValueError:
                result = {}
            if not 200 <= response.status_code < 300:
                message = result.get("message") or result.get("detail") or "Commerce API refused the request"
                raise ToolError(f"Commerce API HTTP {response.status_code}: {str(message)[:500]}")
            if not isinstance(result, dict):
                raise ToolError("Commerce API returned an invalid response")
            return result
        except httpx.HTTPError:
            raise ToolError("Commerce API is unreachable. Start the existing demo API before using these tools.") from None

    async def checkout(self, deal_id: UUID | None = None) -> CheckoutStatusResponse:
        path = f"/api/demo/orders/{deal_id}" if deal_id else "/api/demo/status"
        result = await self.request("GET", path)
        result["actions"] = rewrite_schema_links(build_order_actions(result, self.base_url), self.base_url, self.schema_url)
        result["links"] = self.links(result.get("deal_id"))
        return CheckoutStatusResponse.model_validate(result)


    def links(self, deal_id: str | None) -> dict[str, str]:
        links = {name: self.base_url + path for name, path in checkout_links(deal_id).items()}
        links["discovery"] = self.manifest_url
        return links

    async def mutation(self, path: str, *, body: dict, key: str) -> CheckoutMutationResponse:
        result = await self.request("POST", path, body=body, key=key)
        result["links"] = self.links(result["deal_id"])
        return CheckoutMutationResponse.model_validate(result)

    async def confirm_payment(self, deal_id: UUID, confirm: bool, expected_price_minor: int,
                              expected_currency: str) -> None:
        if confirm is not True:
            raise ToolError("Explicit confirmation is required. Ask the user to approve this checkout's quoted amount and action before setting confirm=true.")
        status = await self.checkout(deal_id)
        terms = status.terms or {}
        if terms.get("price_minor") != expected_price_minor or terms.get("currency") != expected_currency:
            raise ToolError("The confirmed amount or currency does not match the current checkout terms. Read and approve the current quote again.")
        # The backend owns state validation and checks idempotent replays first.
        # A retry after success must not be rejected merely because state advanced.


def create_mcp_server(api_url: str = DEFAULT_API_URL, *, http: httpx.AsyncClient | None = None,
                      port: int = 8094, mcp_endpoint: str | None = None,
                      transport: Literal["stdio", "streamable-http"] = "streamable-http") -> FastMCP:
    endpoint = (mcp_endpoint or f"http://127.0.0.1:{port}/mcp") if transport == "streamable-http" else None
    public_root = endpoint.rsplit("/", 1)[0] if endpoint else ""
    schema_url = public_root + "/openapi.json" if endpoint else "commerce://openapi"
    manifest_url = public_root + "/api" if endpoint else "commerce://capabilities"
    skill_url = public_root + "/agent-skill.md" if endpoint else "commerce://skill"
    api = CommerceAPI(api_url, http, schema_url, manifest_url)
    server = FastMCP(
        "Cogit Commerce", host="127.0.0.1", port=port,
        json_response=True, stateless_http=True,
        instructions=(
            "Discover services and input_schema before preparing a checkout. "
            "This adapter uses an existing local commerce API and simulated funds. "
            "Preparing, funding, delivery and releasing payment are separate operations. "
            "Read checkout status and available actions after each mutation. "
            "Only set confirm=true after user authorization of the current amount and action. "
            "Reuse the same idempotency key on retries. A processing response is not settlement. "
            "Read commerce://skill for the complete workflow."
        ),
    )

    def contract() -> dict:
        return {**build_commerce_openapi(), "servers": [{"url": api.base_url}]}

    def manifest() -> dict:
        result = describe_openapi(contract(), api.base_url, mcp_endpoint=endpoint,
                                  skill_url=skill_url)
        result["links"].update(discovery=manifest_url, openapi=schema_url)
        result["links"].pop("docs", None)
        return rewrite_schema_links(result, api.base_url, schema_url)

    @server.tool(annotations=READ)
    async def commerce_discover() -> DiscoveryResponse:
        """Discover the HTTP contract, resources, and separate checkout stages."""
        return DiscoveryResponse(
            name="Cogit Commerce", api_base_url=api.base_url,
            api_manifest_url=manifest_url, openapi_url=schema_url,
            mcp_endpoint=endpoint, protocol_version="2025-11-25", simulation=True,
            workflow=["discover", "prepare", "review", "fund", "deliver", "review", "release", "verify settlement"],
            resources={"skill": "commerce://skill", "openapi": "commerce://openapi", "capabilities": "commerce://capabilities"},
            api_contract=manifest(),
        )

    @server.tool(annotations=READ)
    async def commerce_list_companies() -> CatalogResponse:
        """List public Delta Campus companies and their published offerings."""
        return CatalogResponse.model_validate(await api.request("GET", "/api/catalog"))

    @server.tool(annotations=READ)
    async def commerce_list_offers(company_id: str | None = None) -> ProviderOffersResponse:
        """Read published offers. Their public IDs are not necessarily checkout service IDs."""
        result = await api.request("GET", "/api/provider-offers")
        if company_id is not None:
            result["offers"] = [offer for offer in result["offers"] if offer["company_id"] == company_id]
        return ProviderOffersResponse.model_validate(result)

    @server.tool(annotations=READ)
    async def commerce_list_services(company_id: str | None = None) -> ServiceListResponse:
        """Discover checkout services, exact seller_org_id/offer_id, prices, deliverables and input_schema."""
        result = await api.request("GET", "/api/demo/services")
        if company_id is not None:
            result["services"] = [row for row in result["services"] if row.get("provider_company_id") == company_id]
        for service in result["services"]:
            action = prepare_action(service)
            action["href"] = api.base_url + action["href"]
            service["actions"] = rewrite_schema_links([action], api.base_url, schema_url)
        return ServiceListResponse.model_validate(result)

    @server.tool(annotations=READ)
    async def commerce_list_deals() -> DealsResponse:
        """List current and archived demo deals, their state and agreed price."""
        return DealsResponse.model_validate(await api.request("GET", "/api/deals"))

    @server.tool(annotations=READ)
    async def commerce_get_deal(deal_id: UUID) -> DealViewResponse:
        """Read the deal timeline, held funds, delivery attempts and independent verdicts."""
        return DealViewResponse.model_validate(await api.request("GET", f"/api/deals/{deal_id}"))

    @server.tool(annotations=READ)
    async def commerce_get_checkout(deal_id: UUID | None = None) -> CheckoutStatusResponse:
        """Poll a checkout. Use running, error and actions to decide the next step."""
        return await api.checkout(deal_id)

    @server.tool(annotations=READ)
    async def commerce_get_evidence(deal_id: UUID) -> BorisReportResponse:
        """Read this deal's Boris requests and responses. Configuration alone is not execution proof."""
        return BorisReportResponse.model_validate(await api.request("GET", f"/api/demo/boris?deal_id={deal_id}"))

    @server.tool(annotations=READ)
    async def commerce_get_delivery(deal_id: UUID) -> DeliveryResponse:
        """Return the deliverable URL, byte count and SHA-256 without embedding binary contents."""
        path = f"/api/demo/deals/{deal_id}/delivery"
        try:
            async with api.client() as client:
                async with client.stream("GET", path) as response:
                    if response.status_code == 404:
                        return DeliveryResponse(deal_id=str(deal_id), available=False, download_url=api.base_url + path)
                    if not 200 <= response.status_code < 300:
                        raise ToolError(f"Delivery download refused (HTTP {response.status_code})")
                    digest, length = hashlib.sha256(), 0
                    async for chunk in response.aiter_bytes():
                        length += len(chunk)
                        if length > MAX_DELIVERY_BYTES:
                            raise ToolError("Delivery exceeds the metadata inspection limit; use its download URL directly")
                        digest.update(chunk)
                    return DeliveryResponse(
                        deal_id=str(deal_id), available=True, download_url=api.base_url + path,
                        media_type=response.headers.get("content-type"), size_bytes=length, sha256=digest.hexdigest(),
                        filename=response.headers.get("content-disposition", "").split("filename=")[-1].strip('"') or None,
                    )
        except httpx.HTTPError:
            raise ToolError("Commerce API is unreachable while reading delivery metadata") from None

    @server.tool(annotations=WRITE)
    async def commerce_prepare_checkout(
        seller_org_id: Annotated[str, Field(min_length=1, max_length=128)],
        offer_id: Annotated[str, Field(min_length=1, max_length=128)],
        inputs: dict[str, Any], idempotency_key: Key, demo_price_minor: Amount | None = None,
    ) -> CheckoutMutationResponse:
        """Prepare a quote using IDs from commerce_list_services and inputs matching its input_schema. Does not fund the purchase."""
        body = {"seller_org_id": seller_org_id, "offer_id": offer_id, "inputs": inputs}
        if demo_price_minor is not None:
            body["demo_price_minor"] = demo_price_minor
        return await api.mutation("/api/demo/orders", body=body, key=idempotency_key)

    @server.tool(annotations=PAYMENT)
    async def commerce_fund_escrow(
        deal_id: UUID, idempotency_key: Key, confirm: StrictBool,
        expected_price_minor: Amount, expected_currency: Literal["EUR"],
    ) -> CheckoutMutationResponse:
        """Fund simulated escrow only after user approval of its quoted total. Reuse the same key on retries."""
        await api.confirm_payment(deal_id, confirm, expected_price_minor, expected_currency)
        return await api.mutation(f"/api/demo/orders/{deal_id}/fund", body={}, key=idempotency_key)

    @server.tool(annotations=WRITE)
    async def commerce_deliver_work(
        deal_id: UUID, idempotency_key: Key, scenario: Literal["happy", "rework"] = "happy",
    ) -> CheckoutMutationResponse:
        """Run demo delivery and independent checks. Does not release payment. Poll checkout status afterwards."""
        return await api.mutation(f"/api/demo/orders/{deal_id}/deliver", body={"scenario": scenario}, key=idempotency_key)

    @server.tool(annotations=PAYMENT)
    async def commerce_release_payment(
        deal_id: UUID, idempotency_key: Key, confirm: StrictBool,
        expected_price_minor: Amount, expected_currency: Literal["EUR"],
    ) -> CheckoutMutationResponse:
        """Release approved simulated escrow only after user authorization. Review delivery verdicts and current terms first."""
        await api.confirm_payment(deal_id, confirm, expected_price_minor, expected_currency)
        return await api.mutation(f"/api/demo/orders/{deal_id}/release", body={}, key=idempotency_key)

    @server.resource("commerce://openapi", mime_type="application/json")
    def openapi_resource() -> str:
        """Complete REST contract for the connected API."""
        return json.dumps(contract(), ensure_ascii=False)

    @server.resource("commerce://capabilities", mime_type="application/json")
    def capabilities_resource() -> str:
        """HTTP operations, required headers and MCP endpoint."""
        return json.dumps(manifest(), ensure_ascii=False)

    @server.resource("commerce://skill", mime_type="text/markdown")
    def skill_resource() -> str:
        """Agent instructions for discovering services and completing a reviewed checkout."""
        if not SKILL_FILE.is_file():
            raise ValueError("The commerce skill is unavailable in this checkout")
        return SKILL_FILE.read_text(encoding="utf-8")

    @server.custom_route("/api", methods=["GET"])
    async def discovery_route(_: Request):
        return JSONResponse(manifest())

    @server.custom_route("/.well-known/agent.json", methods=["GET"])
    async def well_known_route(_: Request):
        return JSONResponse(manifest())

    @server.custom_route("/openapi.json", methods=["GET"])
    async def openapi_route(_: Request):
        return JSONResponse(contract())

    @server.custom_route("/agent-skill.md", methods=["GET"])
    async def skill_route(_: Request):
        if not SKILL_FILE.is_file():
            return PlainTextResponse("Commerce skill is unavailable", status_code=404)
        return PlainTextResponse(SKILL_FILE.read_text(encoding="utf-8"), media_type="text/markdown")

    return server


def register_mcp(app: FastAPI, *, api_url: str = DEFAULT_API_URL) -> FastMCP:
    """Opt-in /mcp mount; do not invoke this from the schema-only checkout factory."""
    if getattr(app.state, "mcp_enabled", False):
        return app.state.mcp_server
    api_url = validate_api_url(api_url)
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=api_url)
    server = create_mcp_server(api_url, http=client, mcp_endpoint=api_url + "/mcp")
    mcp_app = server.streamable_http_app()
    app.router.routes.extend(route for route in mcp_app.routes if getattr(route, "path", None) == "/mcp")
    previous = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        async with previous(application):
            async with server.session_manager.run():
                try:
                    yield
                finally:
                    await client.aclose()

    app.router.lifespan_context = lifespan
    app.state.mcp_enabled = True
    app.state.mcp_endpoint = api_url + "/mcp"
    app.state.mcp_server = server
    app.openapi_schema = None
    return server
