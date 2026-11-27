"""The whole demo in one process, without AgentDb.

Real: the four Cogit agents (their bound operations, invoked like a run host does), the
three module reference implementations, the delivery loops, signed envelopes and the
sim bank's HTTP API. Stand-ins: the module host (SQLite), the artifact store and work
admission, from ``cogit_finance_seams``.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml
from cogit_agent_sdk import AgentServices
from cogit_finance_catalog_module import CatalogModule
from cogit_finance_deals_module import DealsModule
from cogit_finance_seams import SimBankClient
from cogit_finance_seams.cogit_host import agent_invoker
from cogit_messaging_shim import AgentKey, event_hash
from cogit_messaging_shim.testing import LocalBus
from fastapi.testclient import TestClient

REPO = Path(__file__).resolve().parents[2]
ESCROW, BUYER, SELLER, EVALUATOR = "cogit-finance", "buyer-agent", "seller-agent", "evaluator-agent"
INSTALLATIONS = {  # installation -> (org, role)
    ESCROW: ("operator-co", "escrow"),
    BUYER: ("buyer-co", "buyer"),
    SELLER: ("seller-co", "seller"),
    EVALUATOR: ("operator-co", "evaluator"),
}
_CLEARED_ENV = (
    "AGENT_KEY_FILE", "ESCROW_DID", "COGIT_FINANCE_OPERATOR_CONFIG", "FINANCE_CONTRACTS_DIR", "SIM_BANK_URL",
    "BUYER_ORG_ID", "BUYER_IBAN", "BUYER_CATEGORY", "BUYER_MAX_PRICE_MINOR",
    "SELLER_ORG_ID", "SELLER_OFFERS_FILE", "SELLER_DELAY_S",
)  # fmt: skip


def _load(name: str) -> Any:
    return yaml.safe_load((REPO / "data" / "demo" / name).read_text(encoding="utf-8"))


class DemoWorld:
    """Build with ``DemoWorld(workdir, seller_mode)``; call ``close()`` when done."""

    def __init__(self, workdir: Path, seller_mode: str = "ok") -> None:
        import buyer_agent
        import cogit_finance
        import evaluator_agent
        import seller_agent
        import sim_bank
        from buyer_agent import buyer_operations
        from cogit_finance import escrow_operations

        self._restore: list[Any] = []
        self._ticks = 0
        self._enter(workdir, seller_mode)

        self.bus = LocalBus()
        self.bus.host.install(CatalogModule())
        self.bus.host.install(DealsModule())
        for installation, (org, role) in INSTALLATIONS.items():
            key = AgentKey.load_or_create(workdir / ".state" / "keys" / f"{installation}.key")
            self.bus.add_agent(installation, org, role, key)
        self._seed_catalog()

        self.bank_http = TestClient(sim_bank.create_app(REPO / "data" / "demo" / "bank.yaml"))
        self.bank = SimBankClient(self.bank_http)
        self._patch(escrow_operations, "bank_factory", lambda config: self.bank)
        self._patch(buyer_operations, "build_bank", lambda environ=None: self.bank)

        for installation, package in (
            (ESCROW, cogit_finance), (BUYER, buyer_agent), (SELLER, seller_agent), (EVALUATOR, evaluator_agent),
        ):  # fmt: skip
            agent = package.Agent()
            agent.configure(AgentServices())
            invoker = agent_invoker(
                agent, installation, modules=self.bus.host.port(installation), artifacts=self.bus.artifacts
            )
            self.bus.runtime.register(installation, invoker)

    # -- setup -----------------------------------------------------------------

    def _enter(self, workdir: Path, seller_mode: str) -> None:
        previous_dir = Path.cwd()
        os.chdir(workdir)  # agents keep their keys under ./.state/keys/
        self._restore.append(lambda: os.chdir(previous_dir))
        for name in _CLEARED_ENV:
            self._setenv(name, None)
        self._setenv("SELLER_MODE", seller_mode)

    def _setenv(self, name: str, value: str | None) -> None:
        previous = os.environ.get(name)
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value
        self._restore.append(
            lambda: os.environ.pop(name, None) if previous is None else os.environ.__setitem__(name, previous)
        )

    def _patch(self, target: Any, name: str, value: Any) -> None:
        previous = getattr(target, name)
        setattr(target, name, value)
        self._restore.append(lambda: setattr(target, name, previous))

    def _seed_catalog(self) -> None:
        operator = self.bus.host.port("operator", "operator")
        for company in _load("companies.yaml")["companies"]:
            operator.module_command(
                "cogit-finance-catalog", "company.upsert", {"company": company},
                idempotency_key=f"seed:company:{company['org_id']}",
            )  # fmt: skip
        for evaluator in _load("evaluators.yaml")["evaluators"]:
            row = {**evaluator, "did": self.bus.keys[EVALUATOR].did}
            operator.module_command(
                "cogit-finance-catalog", "evaluator.upsert", {"evaluator": row},
                idempotency_key=f"seed:evaluator:{row['evaluator_id']}:{row['version']}",
            )  # fmt: skip

    def close(self) -> None:
        self.bank_http.close()
        while self._restore:
            self._restore.pop()()

    # -- driving ---------------------------------------------------------------

    def act(self, installation: str, action: str, payload: dict | None = None, key: str | None = None) -> dict:
        """Admit one action and return its output; a failed run raises with its error."""
        self._ticks += 1
        run_id = self.bus.runtime.admit(
            installation, action, payload or {}, idempotency_key=key or f"{action}:{self._ticks}"
        )
        record = self.bus.runtime.runs[run_id]
        if record.status != "succeeded":
            raise AssertionError(f"{installation}.{action} failed: {record.error}\n{record.trace}")
        return record.output or {}

    def tick(self) -> dict:
        return self.act(ESCROW, "tick")

    def run(self, deal_id: str, until: str = "SETTLED", max_rounds: int = 40) -> str:
        """Deliver messages and tick E until the deal reaches ``until`` or nothing moves."""
        state, idle = "", 0
        for _ in range(max_rounds):
            handled = self.bus.pump()
            tick = self.tick()
            self.assert_no_failed_runs()
            state = (self.deal(deal_id)["deal"] or {}).get("state", "")
            if state == until:
                if until == "SETTLED":
                    self.bus.pump()  # let the last notifications reach their recipients
                return state
            moved = handled + tick["deals_funded"] + tick["outbox_sent"]
            idle = 0 if moved else idle + 1
            if idle >= 3:
                break
        return state

    def assert_no_failed_runs(self) -> None:
        failed = [run for run in self.bus.runtime.runs.values() if run.status == "failed"]
        if failed:
            details = "\n".join(f"{run.installation_id}.{run.action}: {run.error}\n{run.trace}" for run in failed)
            raise AssertionError(f"{len(failed)} run(s) failed:\n{details}")

    # -- reading (as the read-only operator identity, like the dashboard) ------

    @property
    def reader(self):
        return self.bus.host.port("dashboard", "operator_ro")

    def deal(self, deal_id: str) -> dict:
        return self.reader.module_query("cogit-finance-deals", "deal.read", {"deal_id": deal_id})

    def balances(self, deal_id: str | None = None) -> dict:
        return self.reader.module_query("cogit-finance-deals", "ledger.balances", {"deal_id": deal_id} if deal_id else {})

    def conversation(self, deal_id: str) -> list[dict]:
        return self.reader.module_query("cogit-messaging", "conversation.read", {"conversation_id": deal_id})["messages"]

    def accounts(self) -> dict[str, int]:
        return {account["iban"]: account["balance_minor"] for account in self.bank.accounts()}


def sequence_matches(events: list[dict], fixture: dict) -> bool:
    """True when the deal's event types follow the fixture's sequence (contracts/fixtures)."""
    pattern = "".join(f"(?:{step['event_type']},){{{step['min']},{step['max']}}}" for step in fixture["events"])
    return re.fullmatch(pattern, "".join(f"{event['event_type']}," for event in events)) is not None


def chain_is_valid(events: list[dict]) -> bool:
    previous = "0" * 64
    for index, event in enumerate(events, start=1):
        if event["seq"] != index or event["prev_hash"] != previous or event_hash(event) != event["hash"]:
            return False
        previous = event["hash"]
    return True
