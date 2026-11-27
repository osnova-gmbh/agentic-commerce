# pyright: basic
# The shared ports ship without type stubs.
"""The buyer's actions: build the core from the run handle and the environment.

Settings are read when an operation runs (build guide §4):

| Variable | Default |
| --- | --- |
| ``AGENT_KEY_FILE`` | ``.state/keys/buyer-agent.key`` (created on first use) |
| ``ESCROW_DID`` | resolved with ``identity.resolve {"role": "escrow"}`` |
| ``SIM_BANK_URL`` | ``http://localhost:8080`` |
| ``BUYER_ORG_ID`` | ``buyer-co`` |
| ``BUYER_IBAN`` | ``DE00EXAMPLE0000000010`` |
| ``BUYER_CATEGORY`` | ``reports`` |
| ``BUYER_MAX_PRICE_MINOR`` | ``60000`` |
"""

from __future__ import annotations

import os
from collections.abc import Mapping

from cogit_agent_sdk import OperationInvocation
from cogit_finance_seams import BankPort, SimBankClient
from cogit_finance_seams.cogit_host import HandleModules
from cogit_messaging_shim import AgentKey, ShimMessaging

from buyer_agent.buyer_core import BuyerCore, BuyerSettings
from buyer_agent.schemas import (
    HandleMessageInput,
    HandleMessageOutput,
    StartPurchaseInput,
    StartPurchaseOutput,
)

DEFAULT_KEY_FILE = ".state/keys/buyer-agent.key"
DEFAULT_SIM_BANK_URL = "http://localhost:8080"


def settings_from_env(environ: Mapping[str, str] | None = None) -> BuyerSettings:
    """Buyer settings from the environment; an empty variable counts as unset."""
    env = os.environ if environ is None else environ
    defaults = BuyerSettings()
    return BuyerSettings(
        org_id=env.get("BUYER_ORG_ID") or defaults.org_id,
        iban=env.get("BUYER_IBAN") or defaults.iban,
        category=env.get("BUYER_CATEGORY") or defaults.category,
        max_price_minor=int(
            env.get("BUYER_MAX_PRICE_MINOR") or defaults.max_price_minor
        ),
        escrow_did=env.get("ESCROW_DID") or None,
    )


def build_bank(environ: Mapping[str, str] | None = None) -> BankPort:
    """The sim bank at ``SIM_BANK_URL``. Tests and the offline run replace this."""
    env = os.environ if environ is None else environ
    return SimBankClient.from_url(env.get("SIM_BANK_URL") or DEFAULT_SIM_BANK_URL)


def build_buyer(invocation: OperationInvocation) -> BuyerCore:
    """Wire the core to the run handle: modules, signed messaging and the bank."""
    modules = HandleModules(invocation.handle)
    key = AgentKey.load_or_create(os.environ.get("AGENT_KEY_FILE") or DEFAULT_KEY_FILE)
    return BuyerCore(
        modules, ShimMessaging(key, modules), build_bank(), settings_from_env()
    )


def start_purchase(
    request: StartPurchaseInput,
    invocation: OperationInvocation,
) -> StartPurchaseOutput:
    """Discover an offer and send ``finance.service_request`` to E."""
    with invocation.handle.step("action", "start_purchase") as step:
        result = build_buyer(invocation).start_purchase(
            request.category, request.max_price_minor
        )
        output = StartPurchaseOutput(
            status=result.status,
            deal_id=result.deal_id,
            seller_org_id=result.seller_org_id,
            offer_id=result.offer_id,
            sellers_seen=result.sellers_seen,
            offers_seen=result.offers_seen,
        )
        # Discovery evidence of SPEC §13.1, kept with the run.
        step.set_data(output.model_dump(mode="json"))
    return output


def handle_message(
    request: HandleMessageInput,
    invocation: OperationInvocation,
) -> HandleMessageOutput:
    """Handle one inbound envelope; a raised error asks the loop to retry."""
    with invocation.handle.step("action", "handle_message") as step:
        result = build_buyer(invocation).handle_message(request.envelope)
        output = HandleMessageOutput(status=result.status, reason=result.reason)
        step.set_data(
            {
                "message_id": request.envelope.get("message_id"),
                "type_key": request.envelope.get("type_key"),
                **output.model_dump(mode="json"),
            }
        )
    return output
