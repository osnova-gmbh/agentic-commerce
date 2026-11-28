"""The same escrow recovery contract against reference and native SQL modules.

Native execution uses COMMERCE_SQL_TEST_DSN. These are domain/module tests, not
proof of the separate four-process AgentDb worker admission protocol.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from cogit_finance.escrow import EscrowCore, settings
from cogit_finance_catalog_module import CatalogModule
from cogit_finance_deals_module import DealsModule
from cogit_finance_seams import ModuleError
from cogit_messaging_module import MessagingModule
from test_native_postgres import DSN, native_host as postgres_fixture

native_host = postgres_fixture

pytestmark = pytest.mark.skipif(not DSN, reason="COMMERCE_SQL_TEST_DSN is required")

sys.path.insert(
    0, str(Path(__file__).resolve().parents[2] / "packages/cogit-finance/tests")
)
from escrow_data import BUYER_IBAN, ESCROW_IBAN, HAPPY_DEAL, PRICE  # noqa: E402
from escrow_world import World  # noqa: E402


class NativePort:
    def __init__(self, host: Any) -> None:
        self.port = host.port("cogit-finance")
        self.reader = host.port("reader", "operator_ro")

    def module_query(self, *args: Any, **kwargs: Any) -> dict:
        return self.port.module_query(*args, **kwargs)

    def module_command(self, *args: Any, **kwargs: Any) -> dict:
        return self.port.module_command(*args, **kwargs)

    @property
    def messages(self) -> dict:
        rows = self.reader.module_query(
            "cogit-messaging", "conversation.read", {"conversation_id": HAPPY_DEAL}
        )["messages"]
        return {row["message_id"]: row["envelope"] for row in rows}


@pytest.fixture
def native_world(native_host: Any) -> World:
    w = World()
    for module in (MessagingModule(), CatalogModule(), DealsModule()):
        native_host.install(module)
    operator = native_host.port("operator", "operator")
    for row in w.modules.identities.values():
        operator.module_command(
            "cogit-messaging",
            "identity.register",
            {k: row[k] for k in ("did", "installation_id", "org_id", "role")},
            idempotency_key=row["did"],
        )
    for row in w.modules.companies.values():
        operator.module_command(
            "cogit-finance-catalog",
            "company.upsert",
            {"company": row},
            idempotency_key=row["org_id"],
        )
    for row in w.modules.evaluators:
        operator.module_command(
            "cogit-finance-catalog",
            "evaluator.upsert",
            {"evaluator": row},
            idempotency_key=row["evaluator_id"],
        )
    native_host.port("seller-agent").module_command(
        "cogit-finance-catalog",
        "catalog.publish",
        {"seller_org_id": "seller-co", "offers": w.modules.offers["seller-co"]},
        idempotency_key="offers",
    )
    w.modules = NativePort(native_host)
    w.core = EscrowCore(
        w.modules,
        w.bank,
        w.artifacts,
        w.escrow,
        w.config,
        settings.PACKAGED_CONTRACTS_DIR,
        w.clock.now,
    )
    w.handle, w.run_tick = w.core.handle_message, w.core.tick
    w.run_tick()
    return w


@pytest.mark.parametrize("point", ["before_submit", "after_bank", "before_ledger"])
def test_native_payout_crash_matrix(
    native_world: World, native_host: Any, monkeypatch: pytest.MonkeyPatch, point: str
) -> None:
    w = native_world
    transfer, call = w.bank.transfer, native_host.call

    def fault_transfer(**args: Any) -> dict:
        if args["idempotency_key"] == f"{HAPPY_DEAL}:payout":
            monkeypatch.setattr(w.bank, "transfer", transfer)
            if point == "before_submit":
                raise TimeoutError("before submit")
            result = transfer(**args)
            if point == "after_bank":
                raise TimeoutError("after bank commit")
            return result
        return transfer(**args)

    def fault_call(
        caller: Any,
        kind: str,
        module: str,
        export: str,
        args: Any = None,
        key: Any = None,
    ) -> dict:
        if (
            point == "before_ledger"
            and export == "intent.update"
            and args.get("status") == "confirmed"
        ):
            monkeypatch.setattr(native_host, "call", call)
            raise ModuleError("unavailable")
        return call(caller, kind, module, export, args, key)

    monkeypatch.setattr(w.bank, "transfer", fault_transfer)
    monkeypatch.setattr(native_host, "call", fault_call)
    if point == "before_ledger":
        with pytest.raises(ModuleError, match="unavailable"):
            w.happy_path()
    else:
        w.happy_path()
    assert w.state(HAPPY_DEAL) == "RELEASING"
    w.run_tick()
    w.run_tick()
    assert w.state(HAPPY_DEAL) == "SETTLED"
    assert len(w.bank.transfers) == 3
    assert w.bank.balances[ESCROW_IBAN] == 0
    balances = w.modules.module_query("cogit-finance-deals", "ledger.balances", {})
    assert (balances["held"], balances["seller"], balances["fee"]) == (0, 49500, 500)


def test_native_deadline_refund(native_world: World) -> None:
    w = native_world
    w.open_deal(HAPPY_DEAL)
    w.clock.tick(61)
    w.run_tick()
    w.run_tick()
    assert w.state(HAPPY_DEAL) == "REFUNDED"
    assert len(w.bank.transfers) == 2
    assert w.bank.balances[BUYER_IBAN] == 1000000


def test_native_unknown_credit_return_is_atomic_and_replay_safe(
    native_world: World,
) -> None:
    w = native_world
    w.bank.transfer(
        from_iban=BUYER_IBAN,
        to_iban=ESCROW_IBAN,
        amount_minor=PRICE,
        currency="EUR",
        reference="unknown",
        idempotency_key="unmatched",
    )
    w.run_tick()
    w.run_tick()
    assert len(w.bank.transfers) == 2
    assert w.bank.balances[BUYER_IBAN] == 1000000
    assert (
        w.modules.module_query("cogit-finance-deals", "ledger.balances", {})["returned"]
        == PRICE
    )


def test_native_participant_reads_and_readonly_commands(
    native_world: World, native_host: Any
) -> None:
    w = native_world
    w.open_deal(HAPPY_DEAL)
    for role in ("buyer-agent", "seller-agent", "cogit-finance"):
        port = native_host.port(role)
        assert port.module_query(
            "cogit-finance-deals", "deal.read", {"deal_id": HAPPY_DEAL}
        )["deal"]
    native_host.port("operator", "operator").module_command(
        "cogit-messaging",
        "identity.register",
        {
            "did": "did:key:another-buyer",
            "installation_id": "stranger",
            "org_id": "buyer-co",
            "role": "buyer",
        },
        idempotency_key="same-org-not-a-participant",
    )
    outsider = native_host.port("stranger")
    with pytest.raises(ModuleError, match="forbidden"):
        outsider.module_query(
            "cogit-finance-deals", "deal.read", {"deal_id": HAPPY_DEAL}
        )
    assert outsider.module_query("cogit-finance-deals", "deal.list", {}) == {
        "deals": []
    }
    assert (
        outsider.module_query("cogit-finance-deals", "ledger.balances", {})["held"] == 0
    )
    with pytest.raises(ModuleError, match="forbidden"):
        outsider.module_query(
            "cogit-messaging", "conversation.read", {"conversation_id": HAPPY_DEAL}
        )
    reader = native_host.port("reader", "operator_ro")
    assert (
        reader.module_query("cogit-finance-deals", "ledger.balances", {})["held"]
        == PRICE
    )
    # Bypass the reference host's operator_ro shortcut: the SQL dispatcher itself
    # must deny the configured reader principal for every privileged module.
    readonly = native_host.port("reader", "viewer")
    for module, export in (
        ("cogit-finance-deals", "intent.update"),
        ("cogit-messaging", "identity.register"),
        ("cogit-finance-catalog", "company.upsert"),
    ):
        with pytest.raises(ModuleError, match="forbidden"):
            readonly.module_command(module, export, {}, idempotency_key="denied")


def test_native_evaluator_timeout_retries_once_then_disputes(
    native_world: World,
) -> None:
    w = native_world
    w.open_deal(HAPPY_DEAL)
    w.deliver(HAPPY_DEAL)
    w.clock.tick(61)
    w.run_tick()
    assert len(w.requests(HAPPY_DEAL, 1)) == 6
    w.clock.tick(61)
    w.run_tick()
    assert w.state(HAPPY_DEAL) == "DISPUTED"
    assert len(w.bank.transfers) == 1
    assert w.read(HAPPY_DEAL)["intents"] == []
