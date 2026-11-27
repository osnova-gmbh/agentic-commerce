"""Exercise the real official MCP client against commerce tools and isolated stores."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.shared.memory import create_connected_server_and_client_session

from cogit_finance_seams import SimBankClient
from dashboard.boris import BorisGateway
from dashboard.checkout import CatalogDemoEngine, create_checkout_app
from dashboard.mcp_server import create_mcp_server, register_mcp
from sim_bank import create_app as create_bank_app

ROOT = Path(__file__).resolve().parents[2]


async def call(session, name, arguments=None):
    result = await session.call_tool(name, arguments or {})
    assert not result.isError, result.content
    if result.structuredContent is not None:
        return result.structuredContent
    return json.loads(result.content[0].text)


async def wait_order(session, deal_id, state):
    for _ in range(400):
        result = await call(session, "commerce_get_checkout", {"deal_id": deal_id})
        if not result["running"]:
            assert result["error"] is None, result["error"]
            assert result["state"] == state, result
            return result
        await asyncio.sleep(.01)
    raise AssertionError("Checkout did not finish")


@pytest.mark.asyncio
async def test_official_mcp_client_can_discover_and_complete_checkout_once():
    exchanges = []
    def echo(agent, payload, request_id):
        exchanges.append((agent, payload))
        return payload
    gateway = BorisGateway("https://example.test/echo", echo, transport_kind="test")
    with TestClient(create_bank_app()) as bank_http:
        engine = CatalogDemoEngine(ROOT, bank=SimBankClient(bank_http), step_delay=0, boris=gateway)
        app = create_checkout_app(engine)
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as http:
                server = create_mcp_server("http://127.0.0.1", http=http)
                async with create_connected_server_and_client_session(server) as session:
                    tools = (await session.list_tools()).tools
                    by_name = {tool.name: tool for tool in tools}
                    assert len(by_name) == 13
                    assert by_name["commerce_list_services"].annotations.readOnlyHint is True
                    assert by_name["commerce_fund_escrow"].annotations.destructiveHint is True
                    assert by_name["commerce_fund_escrow"].annotations.idempotentHint is True
                    assert "confirm" in by_name["commerce_fund_escrow"].inputSchema["required"]
                    assert by_name["commerce_get_checkout"].outputSchema
                    discovered = await call(session, "commerce_discover")
                    assert discovered["protocol_version"] == "2025-11-25"
                    assert discovered["api_contract"]["links"]["openapi"] == "http://127.0.0.1:8094/openapi.json"
                    services = (await call(session, "commerce_list_services"))["services"]
                    chosen = next(row for row in services if row["offer_id"] == "offer-1")
                    assert chosen["actions"][0]["href"] == "http://127.0.0.1/api/demo/orders"
                    assert chosen["actions"][0]["response_schema"]["$ref"].startswith("http://127.0.0.1:8094/openapi.json#")
                    prepared = await call(session, "commerce_prepare_checkout", {
                        "seller_org_id": chosen["seller_org_id"], "offer_id": chosen["offer_id"],
                        "inputs": {"topic": "MCP test"}, "idempotency_key": "mcp-prepare",
                    })
                    deal = prepared["deal_id"]
                    assert prepared["links"]["status"] == "http://127.0.0.1/api/demo/orders/" + deal
                    quoted = await wait_order(session, deal, "QUOTED")
                    assert any(action["name"] == "fund" for action in quoted["actions"])
                    initial_accounts = engine.bank.accounts()
                    denied = await session.call_tool("commerce_fund_escrow", {
                        "deal_id": deal, "idempotency_key": "mcp-fund", "confirm": False,
                        "expected_price_minor": chosen["price_minor"], "expected_currency": "EUR",
                    })
                    assert denied.isError
                    assert engine.bank.accounts() == initial_accounts
                    mismatch = await session.call_tool("commerce_fund_escrow", {
                        "deal_id": deal, "idempotency_key": "mcp-fund", "confirm": True,
                        "expected_price_minor": chosen["price_minor"] + 1, "expected_currency": "EUR",
                    })
                    assert mismatch.isError
                    assert engine.bank.accounts() == initial_accounts
                    funding_args = {"deal_id": deal, "idempotency_key": "mcp-fund", "confirm": True,
                                    "expected_price_minor": chosen["price_minor"], "expected_currency": "EUR"}
                    funded = await call(session, "commerce_fund_escrow", funding_args)
                    await wait_order(session, deal, "FUNDED")
                    accounts = engine.bank.accounts()
                    assert await call(session, "commerce_fund_escrow", funding_args) == funded
                    assert engine.bank.accounts() == accounts
                    too_early = await session.call_tool("commerce_release_payment", {
                        **funding_args, "idempotency_key": "mcp-premature-release",
                    })
                    assert too_early.isError
                    assert engine.bank.accounts() == accounts
                    await call(session, "commerce_deliver_work", {"deal_id": deal, "idempotency_key": "mcp-deliver"})
                    await wait_order(session, deal, "APPROVED")
                    delivery = await call(session, "commerce_get_delivery", {"deal_id": deal})
                    assert delivery["available"] and len(delivery["sha256"]) == 64
                    release_args = {**funding_args, "idempotency_key": "mcp-release"}
                    released = await call(session, "commerce_release_payment", release_args)
                    await wait_order(session, deal, "SETTLED")
                    settled = engine.bank.accounts()
                    assert await call(session, "commerce_release_payment", release_args) == released
                    assert engine.bank.accounts() == settled
                    evidence = await call(session, "commerce_get_evidence", {"deal_id": deal})
                    assert evidence["transport_kind"] == "test"
                    assert {agent for agent, _ in exchanges} == {"buyer-agent", "seller-agent", "cogit-finance"}
                    view = await call(session, "commerce_get_deal", {"deal_id": deal})
                    assert view["deal"]["state"] == "SETTLED"
        finally:
            engine.close()


@pytest.mark.asyncio
async def test_stdio_initialization_and_resources_do_not_require_a_running_backend():
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(ROOT / "scripts/run_mcp.py"), "--api-url", "http://127.0.0.1:1"],
    )
    async with stdio_client(params) as streams:
        async with ClientSession(*streams) as session:
            initialized = await session.initialize()
            assert initialized.serverInfo.name == "Cogit Commerce"
            discovery = await call(session, "commerce_discover")
            assert discovery["mcp_endpoint"] is None
            assert discovery["openapi_url"] == "commerce://openapi"
            assert discovery["api_manifest_url"] == "commerce://capabilities"
            assert "mcp" not in discovery["api_contract"]["links"]
            tools = await session.list_tools()
            assert any(tool.name == "commerce_prepare_checkout" for tool in tools.tools)
            resources = await session.list_resources()
            assert {str(resource.uri) for resource in resources.resources} == {
                "commerce://openapi", "commerce://capabilities", "commerce://skill",
            }
            schema = await session.read_resource("commerce://openapi")
            assert "/api/demo/orders" in json.loads(schema.contents[0].text)["paths"]


def test_http_sidecar_serves_discovery_even_when_old_backend_has_no_openapi():
    app = create_mcp_server("http://127.0.0.1:8091").streamable_http_app()
    with TestClient(app, base_url="http://127.0.0.1:8094") as client:
        manifest = client.get("/api").json()
        assert manifest["links"]["openapi"] == "http://127.0.0.1:8094/openapi.json"
        assert "docs" not in manifest["links"]
        assert manifest["links"]["mcp"] == "http://127.0.0.1:8094/mcp"
        assert any(row["href"] == "http://127.0.0.1:8091/api/demo/orders" for row in manifest["operations"])
        schema = client.get("/openapi.json").json()
        assert schema["servers"] == [{"url": "http://127.0.0.1:8091"}]
        response = client.post("/mcp", headers={"Accept": "application/json, text/event-stream"},
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize",
                  "params": {"protocolVersion": "2025-11-25", "capabilities": {},
                             "clientInfo": {"name": "pytest", "version": "1"}}})
        assert response.status_code == 200, response.text
        assert response.json()["result"]["protocolVersion"] == "2025-11-25"


def test_remote_api_targets_are_rejected():
    with pytest.raises(ValueError, match="loopback"):
        create_mcp_server("https://example.com")
    with pytest.raises(ValueError, match="credentials"):
        create_mcp_server("http://user:password@localhost:8091")


def test_mounted_mcp_uses_the_real_api_origin_and_does_not_recurse():
    with TestClient(create_bank_app()) as bank_http:
        engine = CatalogDemoEngine(ROOT, bank=SimBankClient(bank_http), step_delay=0)
        app = create_checkout_app(engine)
        register_mcp(app, api_url="http://127.0.0.1:8091")
        try:
            with TestClient(app, base_url="http://127.0.0.1:8091") as client:
                manifest = client.get("/api").json()
                assert manifest["links"]["mcp"] == "http://127.0.0.1:8091/mcp"
                response = client.post("/mcp", headers={"Accept": "application/json, text/event-stream"},
                    json={"jsonrpc": "2.0", "id": 1, "method": "initialize",
                          "params": {"protocolVersion": "2025-11-25", "capabilities": {},
                                     "clientInfo": {"name": "pytest", "version": "1"}}})
                assert response.status_code == 200, response.text
                assert response.json()["result"]["serverInfo"]["name"] == "Cogit Commerce"
        finally:
            engine.close()


def test_api_url_must_not_include_a_path():
    with pytest.raises(ValueError, match="origin"):
        create_mcp_server("http://127.0.0.1:8091/unrelated")
