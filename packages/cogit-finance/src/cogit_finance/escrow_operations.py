# pyright: basic
"""E's bound operations: build the core from the run handle and run it.

Settings are read from the environment when an operation runs:
``AGENT_KEY_FILE``, ``COGIT_FINANCE_OPERATOR_CONFIG``, ``FINANCE_CONTRACTS_DIR``
and ``SIM_BANK_URL`` (build guide §4).
"""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import datetime
from typing import Any

from cogit_agent_sdk import ActionBinding, OperationInvocation, bind_action, operation
from cogit_finance_seams import BankPort, SimBankClient, utcnow
from cogit_finance_seams.cogit_host import HandleArtifacts, HandleModules

from cogit_finance.escrow import EscrowCore, settings
from cogit_finance.identity import identity
from cogit_finance.schemas import (
    HandleMessageInput,
    HandleMessageOutput,
    TickInput,
    TickOutput,
)

AGENT_KEY_FILE_ENV = "AGENT_KEY_FILE"
DEFAULT_KEY_FILE = ".state/keys/cogit-finance.key"
SIM_BANK_URL_ENV = "SIM_BANK_URL"

_banks: dict[str, SimBankClient] = {}


def sim_bank(config: dict[str, Any]) -> BankPort:
    """The sim bank at ``SIM_BANK_URL``, else at the config's ``rail.sim.base_url``."""
    url = os.environ.get(SIM_BANK_URL_ENV) or config["rail"].get("sim", {}).get(
        "base_url"
    )
    if not url:
        raise ValueError("no sim bank URL: set SIM_BANK_URL or rail.sim.base_url")
    if url not in _banks:
        _banks[url] = SimBankClient.from_url(url)
    return _banks[url]


# A host that has the bank or the clock in process (tests, the offline demo)
# replaces these two before it invokes an action.
bank_factory: Callable[[dict[str, Any]], BankPort] = sim_bank
clock: Callable[[], datetime] = utcnow


def build_core(invocation: OperationInvocation) -> EscrowCore:
    config = settings.load_operator_config()
    return EscrowCore(
        HandleModules(invocation.handle),
        bank_factory(config),
        HandleArtifacts(invocation.handle),
        identity.load_key(),
        config,
        settings.contracts_dir(),
        clock,
    )


def handle_message(
    request: HandleMessageInput, invocation: OperationInvocation
) -> HandleMessageOutput:
    """Entry point for every inbound ``finance.*`` message."""
    with invocation.handle.step("action", "handle_message"):
        result = build_core(invocation).handle_message(request.envelope)
    return HandleMessageOutput.model_validate(result)


def tick(request: TickInput, invocation: OperationInvocation) -> TickOutput:
    """Register message types, fund deals from bank credits, re-send the outbox."""
    del request
    with invocation.handle.step("action", "tick"):
        result = build_core(invocation).tick()
    return TickOutput.model_validate(result)


def escrow_action_bindings() -> list[ActionBinding[Any, Any]]:
    return [
        bind_action(
            operation(handle_message),
            name="handle_message",
            description="Process one signed finance.* message addressed to E.",
            risk="write",
            idempotency="inherent",
        ),
        bind_action(
            operation(tick),
            name="tick",
            description=(
                "Register the finance.* message types, fund deals from new bank "
                "credits and re-send the pending outbox."
            ),
            risk="write",
            idempotency="inherent",
        ),
    ]
