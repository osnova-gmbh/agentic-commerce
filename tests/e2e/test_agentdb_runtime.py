"""Durable admission behavior and the real agents' inbox command path."""

import json

import httpx
import pytest

from cogit_finance_seams import ModuleError
from cogit_finance_seams.native import decode_result, encode_args
from dashboard.agentdb import AgentDbClient, PersistentScheduler, create_agentdb_app
from fastapi.testclient import TestClient
from world import BUYER, EVALUATOR, ESCROW, SELLER, DemoWorld


def test_root_command_reuses_purchase_identity_after_execution_retry(tmp_path):
    from buyer_agent import Agent
    from cogit_agent_sdk import AgentServices
    from cogit_agent_sdk.types import Context, RunRequest
    from cogit_finance_seams.cogit_host import LocalRunHandle

    world = DemoWorld(tmp_path)
    try:
        world.tick()
        world.act(SELLER, "publish_catalog")
        agent = Agent()
        agent.configure(AgentServices())
        context = Context(
            tenant_id="test", correlation_id="same-admitted-run", agent_id=BUYER
        )
        request = RunRequest(
            instruction="commerce",
            context=context,
            input={"text": json.dumps({"command": "start_purchase", "payload": {}})},
        )

        def execute():
            handle = LocalRunHandle(
                "attempt",
                context,
                modules=world.bus.host.port(BUYER),
                artifacts=world.bus.artifacts,
            )
            return agent.handle_run(request, context, handle)

        first, second = execute(), execute()
        assert first["deal_id"] == second["deal_id"]
        messages = world.bus.host.port("dashboard", "operator_ro").module_query(
            "cogit-messaging",
            "conversation.read",
            {"conversation_id": first["deal_id"]},
        )["messages"]
        assert len(messages) == 1
        with pytest.raises(ValueError, match="Unsupported commerce command"):
            agent.handle_run(
                RunRequest(
                    instruction="invalid",
                    context=context,
                    input={"command": "apply_resolution"},
                ),
                context,
                None,
            )
    finally:
        world.close()


@pytest.mark.parametrize("mode", ["ok", "broken"])
def test_real_agent_inbox_actions_complete_the_deal(tmp_path, mode):
    world = DemoWorld(tmp_path, mode)
    try:
        world.tick()
        world.act(SELLER, "publish_catalog")
        deal_id = world.act(BUYER, "start_purchase")["deal_id"]
        for _ in range(30):
            for role in (BUYER, SELLER, EVALUATOR, ESCROW):
                result = world.act(role, "drain_inbox")
                assert result["released"] == 0
            world.tick()
            if world.deal(deal_id)["deal"]["state"] == "SETTLED":
                break
        assert world.deal(deal_id)["deal"]["state"] == "SETTLED"
        assert world.balances(deal_id) == {
            "held": 0,
            "seller": 49500,
            "fee": 500,
            "buyer_refund": 0,
            "returned": 0,
        }
    finally:
        world.close()


def test_native_carrier_preserves_signed_json_and_reports_domain_failures():
    payload = {"unicode": "€ — 你好", "nested": {"null": None, "number": 100}}
    assert json.loads(encode_args(payload)["payload"]) == payload
    assert decode_result({"result": json.dumps(payload)}) == payload
    with pytest.raises(ModuleError, match="head_mismatch"):
        decode_result({"result": '{"_module_error":"head_mismatch"}'})
    with pytest.raises(ModuleError, match="payload_too_large"):
        encode_args({"x": "a" * 65537})


class AdmissionServer:
    def __init__(self):
        self.requests = []
        self.keys = {}
        self.fail_after_commit = True

    def admit(self, installation_id, command, payload, key):
        self.requests.append((installation_id, command, payload, key))
        run_id = self.keys.setdefault(key, "00000000-0000-4000-8000-000000000001")
        if self.fail_after_commit:
            self.fail_after_commit = False
            raise TimeoutError("The response was lost after admission committed")
        return run_id


def test_scheduler_recovers_uncertain_admission_with_the_identical_key(tmp_path):
    server = AdmissionServer()
    routes = {BUYER: {"installationId": "buyer-installation"}}
    journal = tmp_path / "scheduler.json"
    first = PersistentScheduler(server, routes, journal)
    with pytest.raises(TimeoutError):
        first.schedule("buyer-inbox", BUYER, "drain_inbox")
    recovered = PersistentScheduler(server, routes, journal)
    assert recovered.schedule("buyer-inbox", BUYER, "drain_inbox")
    assert len(server.keys) == 1
    assert server.requests[0] == server.requests[1]


def test_http_admission_uses_the_real_query_contract():
    seen = []

    def respond(request):
        seen.append(request)
        return httpx.Response(
            202, json={"runId": "00000000-0000-4000-8000-000000000001"}
        )

    client = AgentDbClient(
        "http://127.0.0.1:18080",
        "test-token",
        "00000000-0000-4000-8000-000000000002",
        transport=httpx.MockTransport(respond),
    )
    try:
        client.admit("buyer-id", "start_purchase", {}, "purchase-request")
        assert seen[0].url.path == "/v1/queries"
        body = json.loads(seen[0].content)
        assert body["installationId"] == "buyer-id"
        assert json.loads(body["input"]["text"]) == {
            "command": "start_purchase",
            "payload": {},
        }
        assert seen[0].headers["Idempotency-Key"] == "purchase-request"
    finally:
        client.close()


def test_worker_output_is_decoded_from_artifact_content():
    run_id = "00000000-0000-4000-8000-000000000001"
    artifact_id = "00000000-0000-4000-8000-000000000002"

    def respond(request):
        if request.url.path == f"/v1/runs/{run_id}/result":
            return httpx.Response(200, json={"resultArtifactId": artifact_id})
        assert request.url.path == f"/v1/artifacts/{artifact_id}/content"
        return httpx.Response(
            200,
            json={
                "content": json.dumps(
                    {"status": "completed", "output": {"deal_id": "settled-deal"}}
                )
            },
        )

    client = AgentDbClient(
        "http://127.0.0.1:18080",
        "test-token",
        run_id,
        transport=httpx.MockTransport(respond),
    )
    try:
        assert client.output(run_id) == {"deal_id": "settled-deal"}
    finally:
        client.close()


def test_native_dashboard_has_an_explicit_purchase_api():
    class Engine:
        source = None

        def status(self):
            return {"mode": "agentdb"}

        def start(self, scenario, key):
            return {"scenario": scenario, "request": key}

    with TestClient(create_agentdb_app(Engine())) as client:
        assert client.get("/demo").status_code == 200
        response = client.post(
            "/api/demo/purchases",
            headers={"Idempotency-Key": "unique"},
            json={"scenario": "happy"},
        )
        assert response.status_code == 202
        assert response.json()["request"] == "unique"
