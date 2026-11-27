"""Machine clients can discover contracts and executable checkout actions."""
from pathlib import Path

from fastapi.testclient import TestClient

from cogit_finance_seams import SimBankClient
from dashboard import FixtureSource, create_app
from dashboard.checkout import CatalogDemoEngine, create_checkout_app
from dashboard.discovery import build_commerce_openapi, checkout_actions, describe_openapi, prepare_action
from sim_bank import create_app as create_bank_app

ROOT = Path(__file__).resolve().parents[2]

def test_readonly_api_is_discoverable_without_advertising_mutations():
    with TestClient(create_app(FixtureSource(ROOT / "apps/dashboard/fixtures/happy"))) as client:
        response = client.get("/api")
        assert response.status_code == 200
        discovery = response.json()
        assert discovery["mode"] == "read-only"
        assert all(operation["method"] == "GET" for operation in discovery["operations"])
        assert "services" not in discovery["links"]
        assert "mcp" not in discovery["links"]
        assert client.get("/.well-known/agent.json").json() == discovery
        schema = client.get(discovery["links"]["openapi"]).json()
        assert schema["paths"]["/api/deals"]["get"]["operationId"] == "list_deals"
        output = schema["paths"]["/api/deals"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
        assert output["$ref"].endswith("/DealsResponse")
        assert "service-desc" in client.get("/").headers["Link"]
        docs = client.get(discovery["links"]["docs"])
        assert docs.status_code == 200
        assert "<script" not in docs.text

def test_schema_only_factory_describes_headers_and_typed_responses():
    schema = build_commerce_openapi()
    operations = [operation for path in schema["paths"].values() for method, operation in path.items() if method in {"get", "post"}]
    assert len({operation["operationId"] for operation in operations}) == len(operations)
    assert "/api/demo/purchases" not in schema["paths"]
    for path in ("/api/demo/orders", "/api/demo/orders/{deal_id}/fund", "/api/demo/orders/{deal_id}/deliver", "/api/demo/orders/{deal_id}/release"):
        operation = schema["paths"][path]["post"]
        header = next(parameter for parameter in operation["parameters"] if parameter["in"] == "header")
        assert header["name"].lower() == "idempotency-key" and header["required"] is True
        output = operation["responses"]["202"]["content"]["application/json"]["schema"]
        assert output["$ref"].endswith("/CheckoutMutationResponse")
    assert schema["paths"]["/api/demo/orders/{deal_id}/fund"]["post"]["x-requires-confirmation"] is True
    assert schema["paths"]["/api/demo/orders/{deal_id}/release"]["post"]["x-requires-confirmation"] is True
    discovery = describe_openapi(schema, "http://127.0.0.1:8091", "http://127.0.0.1:8094/mcp")
    assert discovery["links"]["mcp"] == "http://127.0.0.1:8094/mcp"
    prepare = next(operation for operation in discovery["operations"] if operation["name"] == "prepare_checkout")
    assert prepare["input_schema"]["properties"]["offer_id"]["type"] == "string"

def test_services_supply_exact_offer_schema_and_executable_status_links():
    with TestClient(create_bank_app()) as bank:
        engine = CatalogDemoEngine(ROOT, bank=SimBankClient(bank), step_delay=0)
        try:
            with TestClient(create_checkout_app(engine)) as client:
                discovery = client.get("/api").json()
                assert discovery["mode"] == "local-simulation"
                service = next(row for row in client.get(discovery["links"]["services"]).json()["services"] if row["offer_id"] == "offer-1")
                prepare = service["actions"][0]
                assert prepare["name"] == "prepare" and prepare["method"] == "POST"
                assert prepare["input_schema"]["properties"]["inputs"] == service["input_schema"]
                assert prepare["input_schema"]["properties"]["offer_id"]["const"] == "offer-1"
                assert prepare["required_headers"][0]["name"] == "Idempotency-Key"
                created = engine.prepare("seller-co", "offer-1", {"topic": "API discovery"}, "discover-test", background=False)
                engine.run_phase({"QUOTED"})
                status = client.get("/api/demo/orders/" + created["deal_id"]).json()
                assert status["allowed_actions"] == ["fund"]
                fund = status["actions"][0]
                assert fund["name"] == "fund"
                assert fund["href"] == "/api/demo/orders/" + created["deal_id"] + "/fund"
                assert fund["requires_confirmation"] is True
                assert client.get(status["links"]["deal"]).status_code == 200
                invalid = client.post(fund["href"], json={})
                assert invalid.status_code == 422
                assert invalid.json()["error"] == "validation_error"
        finally:
            engine.close()

def test_actions_disappear_while_another_step_is_running():
    assert checkout_actions({"deal_id": "test", "allowed_actions": ["fund"], "server_busy": True}) == []
    assert checkout_actions({"deal_id": "test", "allowed_actions": ["release"], "running": True}) == []
    action = prepare_action({"seller_org_id": "s", "offer_id": "o", "input_schema": {"type": "object"}, "requires_demo_amount": True})
    assert "demo_price_minor" in action["input_schema"]["required"]
    action = checkout_actions({"deal_id": "abc", "allowed_actions": ["fund"]}, "http://localhost:8091")[0]
    assert action["href"] == "http://localhost:8091/api/demo/orders/abc/fund"
