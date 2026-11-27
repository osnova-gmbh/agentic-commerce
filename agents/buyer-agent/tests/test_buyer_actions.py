# pyright: basic
"""The bound buyer actions on a local run handle, wired from the environment."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from agent_helpers import configured_buyer_agent
from buyer_fakes import (
    BUYER_IBAN,
    ESCROW_IBAN,
    ESCROW_KEY,
    MESSAGING,
    FakeModules,
    offer,
    payment_request,
    seller,
    terms,
    terms_proposed,
)
from cogit_agent_sdk.types import Context
from cogit_finance_seams import BankError, LocalArtifacts, SimBankClient
from cogit_finance_seams.cogit_host import LocalRunHandle, invoke_action
from cogit_messaging_shim import AgentKey, verify_envelope

from buyer_agent.buyer_core import BuyerSettings
from buyer_agent.buyer_operations import settings_from_env

BUYER_VARIABLES = (
    "ESCROW_DID",
    "SIM_BANK_URL",
    "BUYER_ORG_ID",
    "BUYER_IBAN",
    "BUYER_CATEGORY",
    "BUYER_MAX_PRICE_MINOR",
)


class RecordingBank:
    """The sim bank's ``POST /transfers`` behind an httpx mock transport."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.transport = httpx.MockTransport(self.answer)

    def answer(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        body = json.loads(request.content)
        return httpx.Response(200, json={**body, "status": "booked"})


@pytest.fixture
def bank(monkeypatch: pytest.MonkeyPatch) -> RecordingBank:
    recording = RecordingBank()

    def from_url(base_url: str, timeout: float = 5.0) -> SimBankClient:
        client = httpx.Client(base_url=base_url, transport=recording.transport)
        return SimBankClient(client)

    monkeypatch.setattr(SimBankClient, "from_url", from_url)
    return recording


@pytest.fixture
def key_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    for name in BUYER_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    path = tmp_path / "keys" / "buyer-agent.key"
    monkeypatch.setenv("AGENT_KEY_FILE", str(path))
    return path


def test_bound_actions_run_on_a_local_run_handle(
    bank: RecordingBank, key_file: Path
) -> None:
    modules = FakeModules(
        sellers=[seller()],
        offers={"seller-co": [offer()]},
        escrow_did=ESCROW_KEY.did,
    )
    agent = configured_buyer_agent()
    context = Context(tenant_id="demo", correlation_id="run-1", agent_id="buyer-agent")
    handle = LocalRunHandle(
        "run-1", context, modules=modules, artifacts=LocalArtifacts()
    )

    purchase = invoke_action(
        agent, "start_purchase", {}, handle, idempotency_key="demo:purchase-1"
    )

    buyer_did = AgentKey.load_or_create(key_file).did
    deal_id = purchase["deal_id"]
    assert purchase == {
        "status": "requested",
        "deal_id": deal_id,
        "seller_org_id": "seller-co",
        "offer_id": "offer-1",
        "sellers_seen": 1,
        "offers_seen": 1,
    }
    module, export, args, idempotency_key = modules.commands[0]
    request = args["envelope"]
    assert (module, export) == (MESSAGING, "message.send")
    assert idempotency_key == f"send:{request['message_id']}"
    assert verify_envelope(request)
    assert request["type_key"] == "finance.service_request"
    assert (request["sender_did"], request["recipient_did"]) == (
        buyer_did,
        ESCROW_KEY.did,
    )
    assert request["conversation_id"] == deal_id
    # The run keeps the discovery evidence of SPEC §13.1 with its step.
    step = handle.steps[-1]
    assert (step.name, step.status) == ("start_purchase", "completed")
    assert step.data == purchase

    proposal = terms_proposed(
        terms(deal_id=deal_id, buyer_did=buyer_did), deal_id=deal_id
    )
    accepted = invoke_action(
        agent,
        "handle_message",
        {"envelope": proposal},
        handle,
        idempotency_key=f"msg:{proposal['message_id']}",
    )

    assert accepted == {"status": "processed", "reason": None}
    assert handle.steps[-1].data == {
        "message_id": proposal["message_id"],
        "type_key": "finance.terms_proposed",
        "status": "processed",
        "reason": None,
    }
    accept = modules.commands[1][2]["envelope"]
    assert verify_envelope(accept)
    assert accept["type_key"] == "finance.accept_terms"
    assert accept["sender_did"] == buyer_did
    assert accept["causation_id"] == proposal["message_id"]
    assert accept["body"] == {"terms_hash": proposal["body"]["terms_hash"]}

    paid = invoke_action(
        agent,
        "handle_message",
        {"envelope": payment_request(deal_id=deal_id)},
        handle,
    )

    assert paid == {"status": "processed", "reason": None}
    (transfer,) = bank.requests
    assert (transfer.method, str(transfer.url)) == (
        "POST",
        "http://localhost:8080/transfers",
    )
    assert transfer.headers["Idempotency-Key"] == f"pay:{deal_id}"
    assert json.loads(transfer.content) == {
        "from_iban": BUYER_IBAN,
        "to_iban": ESCROW_IBAN,
        "amount_minor": 50000,
        "currency": "EUR",
        "reference": f"ESCROW-{deal_id}",
    }

    stranger = payment_request(deal_id=deal_id, key=AgentKey.generate())
    refused = invoke_action(agent, "handle_message", {"envelope": stranger}, handle)

    assert refused == {"status": "rejected", "reason": "unexpected_sender"}
    assert len(bank.requests) == 1


def test_a_bank_error_fails_the_bound_action(
    monkeypatch: pytest.MonkeyPatch, bank: RecordingBank, key_file: Path
) -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        return httpx.Response(409, json={"error": "insufficient_funds"})

    bank.transport = httpx.MockTransport(refuse)
    monkeypatch.setenv("ESCROW_DID", ESCROW_KEY.did)
    monkeypatch.setenv("SIM_BANK_URL", "http://sim-bank.test:8080")
    context = Context(tenant_id="demo", correlation_id="run-2", agent_id="buyer-agent")
    handle = LocalRunHandle(
        "run-2", context, modules=FakeModules(), artifacts=LocalArtifacts()
    )

    with pytest.raises(BankError, match="409 insufficient_funds"):
        invoke_action(
            configured_buyer_agent(),
            "handle_message",
            {"envelope": payment_request()},
            handle,
        )
    assert handle.steps[-1].status == "failed"


def test_settings_come_from_the_environment_with_the_demo_defaults() -> None:
    assert settings_from_env({}) == BuyerSettings(
        org_id="buyer-co",
        iban="DE00EXAMPLE0000000010",
        category="reports",
        max_price_minor=60000,
        escrow_did=None,
    )
    assert settings_from_env(
        {
            "BUYER_ORG_ID": "acme",
            "BUYER_IBAN": "DE00EXAMPLE0000000099",
            "BUYER_CATEGORY": "audits",
            "BUYER_MAX_PRICE_MINOR": "12345",
            "ESCROW_DID": ESCROW_KEY.did,
        }
    ) == BuyerSettings("acme", "DE00EXAMPLE0000000099", "audits", 12345, ESCROW_KEY.did)
    # An empty variable counts as unset.
    assert (
        settings_from_env({"BUYER_CATEGORY": "", "ESCROW_DID": ""}) == BuyerSettings()
    )
