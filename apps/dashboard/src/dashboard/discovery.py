"""Discoverable HTTP capabilities and state-specific checkout affordances."""
from __future__ import annotations

from copy import deepcopy
from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, Request
from fastapi.openapi.utils import get_openapi
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from .api_models import APIError, DiscoveryResponse

API_ERRORS = {
    code: {"model": APIError, "description": description}
    for code, description in {
        400: "Invalid request.", 404: "The requested resource does not exist.",
        409: "The current state, idempotency key or upstream service prevents this action.",
        422: "The request does not match its schema or the selected offer.",
        502: "A required backing service is unavailable.",
    }.items()
}
IDEMPOTENCY_HEADER = {
    "name": "Idempotency-Key", "required": True,
    "description": "Choose a unique key for one logical action. Reuse it only to retry exactly the same request.",
    "schema": {"type": "string", "minLength": 1, "maxLength": 200},
}
EMPTY_OBJECT = {"type": "object", "properties": {}, "additionalProperties": False}

def action_descriptor(name: str, method: str, href: str, *,
                      input_schema: dict | None = None, preconditions: list[str] | None = None,
                      side_effects: list[str] | None = None, confirmation: bool = False,
                      response_model: str = "CheckoutMutationResponse") -> dict:
    mutation = method != "GET"
    return {
        "name": name, "method": method, "href": href,
        "input_schema": deepcopy(input_schema or EMPTY_OBJECT),
        "response_schema": {"$ref": f"/openapi.json#/components/schemas/{response_model}"},
        "required_headers": [deepcopy(IDEMPOTENCY_HEADER)] if mutation else [],
        "idempotency": {"required": mutation, "header": "Idempotency-Key" if mutation else None,
                        "replay": "Reuse the same key and identical body until the outcome is known." if mutation else "Read-only; safe to repeat."},
        "side_effects": side_effects or [], "preconditions": preconditions or [],
        "requires_confirmation": confirmation,
    }

def prepare_action(service: dict | None = None) -> dict:
    properties: dict[str, Any] = {
        "seller_org_id": {"type": "string", "minLength": 1, "maxLength": 128},
        "offer_id": {"type": "string", "minLength": 1, "maxLength": 128},
        "inputs": {"type": "object"},
        "demo_price_minor": {"type": ["integer", "null"], "minimum": 1,
                             "description": "Explicit simulated amount in EUR cents; required for quote-only, free, or waitlisted provider offers."},
    }
    required = ["seller_org_id", "offer_id"]
    if service:
        properties["seller_org_id"]["const"] = service["seller_org_id"]
        properties["offer_id"]["const"] = service["offer_id"]
        properties["inputs"] = deepcopy(service["input_schema"])
        required.append("inputs")
        maximum = service.get("demo_max_price_minor")
        if maximum:
            properties["demo_price_minor"]["maximum"] = maximum
        if service.get("requires_demo_amount"):
            properties["demo_price_minor"]["type"] = "integer"
            required.append("demo_price_minor")
    return action_descriptor(
        "prepare", "POST", "/api/demo/orders",
        input_schema={"type": "object", "properties": properties, "required": required, "additionalProperties": False},
        preconditions=["No checkout step is currently running.", "Inputs must satisfy the selected service's input_schema."],
        side_effects=["Creates a simulated checkout and requests a quote; does not fund or purchase from a real provider."],
    )

def checkout_actions(status: dict, api_base: str = "") -> list[dict]:
    """Only advertise mutations that this checkout can currently execute."""
    if status.get("running") or status.get("server_busy"):
        return []
    deal_id = status.get("deal_id")
    if not deal_id:
        return []
    base = "/api/demo/orders/" + quote(str(deal_id), safe="")
    actions = []
    for name in status.get("allowed_actions", []):
        if name == "browse":
            actions.append(action_descriptor("browse", "GET", "/api/demo/services", response_model="ServiceListResponse"))
        elif name == "fund":
            actions.append(action_descriptor(
                "fund", "POST", base + "/fund", confirmation=True,
                preconditions=["State is QUOTED or FUNDING_REQUESTED.", "The user authorized this offer, amount and simulated escrow funding."],
                side_effects=["Accepts the quoted terms and transfers the agreed simulated amount from buyer to escrow."],
            ))
        elif name == "deliver":
            actions.append(action_descriptor(
                "deliver", "POST", base + "/deliver",
                input_schema={"type": "object", "properties": {"scenario": {"type": "string", "enum": ["happy", "rework"], "default": "happy"}}, "additionalProperties": False},
                preconditions=["State is FUNDED or REJECTED."],
                side_effects=["Runs simulated delivery and independent acceptance checks; does not release payment."],
            ))
        elif name == "release":
            actions.append(action_descriptor(
                "release", "POST", base + "/release", confirmation=True,
                preconditions=["State is APPROVED.", "The user authorized release after reviewing delivery and evaluation results."],
                side_effects=["Releases simulated escrow funds to the seller and books the operator fee."],
            ))
    if api_base:
        for action in actions:
            action["href"] = api_base.rstrip("/") + action["href"]
            action["response_schema"]["$ref"] = api_base.rstrip("/") + action["response_schema"]["$ref"]
    return actions

build_order_actions = checkout_actions

def checkout_links(deal_id: str | None) -> dict[str, str]:
    links = {"discovery": "/api", "services": "/api/demo/services", "deals": "/api/deals"}
    if deal_id:
        encoded = quote(str(deal_id), safe="")
        links.update(status=f"/api/demo/orders/{encoded}", deal=f"/api/deals/{encoded}",
                     delivery=f"/api/demo/deals/{encoded}/delivery", evidence=f"/api/demo/boris?deal_id={encoded}")
    return links

def _expanded(schema: Any, document: dict, seen: frozenset[str] = frozenset()) -> Any:
    if isinstance(schema, list):
        return [_expanded(item, document, seen) for item in schema]
    if not isinstance(schema, dict):
        return schema
    reference = schema.get("$ref", "")
    if reference.startswith("#/components/schemas/") and reference not in seen:
        name = reference.rsplit("/", 1)[-1]
        target = document.get("components", {}).get("schemas", {}).get(name)
        if target is not None:
            return _expanded({**target, **{key: value for key, value in schema.items() if key != "$ref"}}, document, seen | {reference})
    return {key: _expanded(value, document, seen) for key, value in schema.items()}

def describe_openapi(schema: dict, api_base: str = "", mcp_endpoint: str | None = None,
                     skill_url: str | None = None) -> dict:
    """Describe the actual OpenAPI routes; also usable by a separate MCP sidecar."""
    operations = []
    for path, methods in schema.get("paths", {}).items():
        if not path.startswith("/api/") and path != "/health":
            continue
        for method, operation in methods.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            body = operation.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema", EMPTY_OBJECT)
            headers = [
                {"name": parameter["name"], "required": parameter.get("required", False),
                 "description": parameter.get("description", ""), "schema": _expanded(parameter.get("schema", {}), schema)}
                for parameter in operation.get("parameters", []) if parameter.get("in") == "header"
            ]
            operations.append({
                "name": operation.get("operationId"), "method": method.upper(),
                "href": api_base.rstrip("/") + path,
                "summary": operation.get("summary", ""), "description": operation.get("description", ""),
                "input_schema": _expanded(body, schema), "required_headers": headers,
                "parameters": _expanded(operation.get("parameters", []), schema),
                "responses": _expanded(operation.get("responses", {}), schema),
                "side_effects": operation.get("x-side-effects", []),
                "requires_confirmation": operation.get("x-requires-confirmation", False),
            })
    writable = any(operation["method"] != "GET" for operation in operations)
    base = api_base.rstrip("/")
    links = {"discovery": base + "/api", "openapi": base + "/openapi.json", "docs": base + "/docs",
             "catalog": base + "/api/catalog", "provider_offers": base + "/api/provider-offers",
             "deals": base + "/api/deals", "accounts": base + "/api/accounts"}
    if writable:
        links.update(services=base + "/api/demo/services", status=base + "/api/demo/status")
    if mcp_endpoint:
        links["mcp"] = mcp_endpoint
    if skill_url:
        links["skill"] = skill_url
    return {
        "name": "Cogit Finance", "version": "1.0.0", "api_base": base,
        "mode": "local-simulation" if writable else "read-only",
        "description": "Discover provider offers and inspect escrow records. Checkout operations transfer simulated funds only." if writable else "Read-only provider directory and escrow records.",
        "authentication": {"type": "none", "scope": "Local operator API; no internet deployment or identity authorization is implied."},
        "links": links, "operations": operations,
        "workflow": ["discover offers", "prepare quote", "poll status", "fund escrow", "deliver and evaluate", "release payment"] if writable else ["discover offers", "read deals"],
        "safety": {"real_money": False, "automatic_release": False, "confirm_actions": ["fund", "release"] if writable else [],
                   "idempotency": "Every POST requires Idempotency-Key. Reuse a key only with an identical request." if writable else "All operations are read-only."},
    }

def register_discovery(app: FastAPI) -> None:
    def live_openapi() -> dict:
        # Factories may register routes later; do not cache an incomplete schema.
        return get_openapi(title=app.title, version=app.version, description=app.description,
                           routes=app.routes, servers=[{"url": "/"}])
    app.openapi = live_openapi

    def skill_path() -> Path:
        return Path(__file__).resolve().parents[4] / ".agents/skills/use-agentic-commerce/SKILL.md"

    def document(request: Request) -> dict:
        endpoint = getattr(app.state, "mcp_endpoint", None)
        if endpoint is None and getattr(app.state, "mcp_enabled", False):
            endpoint = str(request.base_url).rstrip("/") + "/mcp"
        skill_url = str(request.base_url).rstrip("/") + "/agent-skill.md" if skill_path().is_file() else None
        return describe_openapi(app.openapi(), str(request.base_url).rstrip("/"), endpoint, skill_url)

    @app.get("/api", operation_id="discover_api", tags=["Discovery"], response_model=DiscoveryResponse,
             summary="Discover API capabilities and machine-readable operation contracts")
    def discover(request: Request) -> dict:
        return document(request)

    @app.get("/.well-known/agent.json", include_in_schema=False)
    def agent_manifest(request: Request) -> dict:
        return document(request)

    @app.get("/agent-skill.md", include_in_schema=False)
    def agent_skill():
        from fastapi import HTTPException
        if not skill_path().is_file():
            raise HTTPException(404, "The commerce skill is not installed in this checkout")
        return FileResponse(skill_path(), media_type="text/markdown; charset=utf-8")

    @app.get("/docs", include_in_schema=False, response_class=HTMLResponse)
    def docs() -> HTMLResponse:
        rows = []
        for path, methods in app.openapi().get("paths", {}).items():
            for method, operation in methods.items():
                rows.append(f"<tr><td>{escape(method.upper())}</td><td><code>{escape(path)}</code></td><td>{escape(operation.get('summary', ''))}</td></tr>")
        return HTMLResponse("<!doctype html><html lang='en'><meta charset='utf-8'><meta name='viewport' content='width=device-width'><title>Cogit Finance API</title><h1>Cogit Finance API</h1><p><a href='/api'>Machine-readable discovery</a> · <a href='/openapi.json'>Complete OpenAPI schema</a></p><p>Local demo mutations transfer simulated funds. Read each action's schema and confirmation requirements before calling it.</p><table><thead><tr><th>Method</th><th>Path</th><th>Purpose</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table></html>")

    @app.get("/redoc", include_in_schema=False)
    def redoc() -> RedirectResponse:
        return RedirectResponse("/docs")

def build_commerce_openapi() -> dict:
    """Schema-only checkout factory: no bank, workers, keys or network calls."""
    from .checkout import create_checkout_app

    class SchemaEngine:
        source = None
        archived_views: dict = {}

        @staticmethod
        def services() -> list:
            return []

    return create_checkout_app(SchemaEngine()).openapi()
