"""A small demo world for E's tests: buyer, seller, evaluator and a scripted deal.

The three other agents are played here with their own keys, the way SPEC §8
describes them. Keys are generated per run and never written anywhere.
"""

from __future__ import annotations

import io
import zipfile
from collections.abc import Callable
from typing import Any

from cogit_finance_seams import LocalArtifacts
from cogit_messaging_shim import AgentKey, build_envelope
from escrow_data import (
    BROKEN_DEAL,
    BUYER_IBAN,
    ESCROW_IBAN,
    EVALUATORS,
    FEE_IBAN,
    FILES,
    HAPPY_DEAL,
    PRICE,
    SELLER_IBAN,
    FakeClock,
    acceptance,
    zip_bytes,
)
from escrow_data import company as company_row
from escrow_data import offer as offer_row
from escrow_fake_bank import FakeBank
from escrow_fake_modules import FakeModules

from cogit_finance.escrow import EscrowCore, settings

Row = dict[str, Any]


class World:
    """E on fakes, plus the three counterparties with their own keys."""

    def __init__(self, escrow_key: AgentKey | None = None) -> None:
        self.clock = FakeClock()
        self.modules = FakeModules(self.clock.now)
        self.bank = FakeBank(
            self.clock.now,
            {ESCROW_IBAN: 0, FEE_IBAN: 0, BUYER_IBAN: 1000000, SELLER_IBAN: 0},
        )
        self.bank.owners = {
            ESCROW_IBAN: "escrow held",
            FEE_IBAN: "escrow fees",
            BUYER_IBAN: "buyer-co",
            SELLER_IBAN: "seller-co",
        }
        self.artifacts = LocalArtifacts()
        self.escrow = escrow_key or AgentKey.generate()
        self.buyer = AgentKey.generate()
        self.seller = AgentKey.generate()
        self.evaluator = AgentKey.generate()
        m = self.modules
        m.register_identity(self.escrow.did, "cogit-finance", "operator-co", "escrow")
        m.register_identity(self.buyer.did, "buyer-agent", "buyer-co", "buyer")
        m.register_identity(self.seller.did, "seller-agent", "seller-co", "seller")
        m.register_identity(
            self.evaluator.did, "evaluator-agent", "operator-co", "evaluator"
        )
        m.companies["buyer-co"] = company_row("buyer-co", ["buyer"], BUYER_IBAN, 200000)
        m.companies["seller-co"] = company_row("seller-co", ["seller"], SELLER_IBAN, 0)
        m.companies["operator-co"] = company_row("operator-co", [], ESCROW_IBAN, 0)
        m.offers["seller-co"] = [offer_row()]
        m.evaluators = [self.evaluator_row(name) for name in EVALUATORS]
        self.config = settings.load_operator_config(settings.PACKAGED_OPERATOR_CONFIG)
        self.core = EscrowCore(
            m,
            self.bank,
            self.artifacts,
            self.escrow,
            self.config,
            settings.PACKAGED_CONTRACTS_DIR,
            self.clock.now,
        )
        self.core.tick()  # registers the message types
        # Tests may route these two through the bound actions instead.
        self.handle: Callable[[Row], Row] = self.core.handle_message
        self.run_tick: Callable[[], Row] = self.core.tick

    def evaluator_row(self, name: str, org_id: str = "operator-co") -> Row:
        return {
            "evaluator_id": name,
            "version": 1,
            "org_id": org_id,
            "did": self.evaluator.did,
            "description": name,
            "deterministic": True,
            "accepts": ["application/zip"],
            "params_schema": {"type": "object"},
        }

    # messages ---------------------------------------------------------------

    def envelope(
        self,
        key: AgentKey,
        name: str,
        deal_id: str,
        body: Row,
        cause: str | None = None,
    ) -> Row:
        return build_envelope(
            key,
            key.did,
            f"finance.{name}",
            1,
            self.escrow.did,
            deal_id,
            body,
            cause,
            created_at=self.clock.ts(),
        )

    def send(
        self,
        key: AgentKey,
        name: str,
        deal_id: str,
        body: Row,
        cause: str | None = None,
    ) -> Row:
        """Sign a message to E, let E handle it, and move the clock on a second."""
        result = self.handle(self.envelope(key, name, deal_id, body, cause))
        self.clock.tick()
        return result

    def inbox(self, key: AgentKey, deal_id: str, name: str | None = None) -> list[Row]:
        """What E has sent to this party in this deal, oldest first."""
        return [
            envelope
            for envelope in self.modules.messages.values()
            if envelope["recipient_did"] == key.did
            and envelope["conversation_id"] == deal_id
            and name in (None, envelope["type_key"].removeprefix("finance."))
        ]

    def read(self, deal_id: str) -> Row:
        return self.modules.module_query(
            "cogit-finance-deals", "deal.read", {"deal_id": deal_id}
        )

    def state(self, deal_id: str) -> str:
        return self.read(deal_id)["deal"]["state"]

    def event_types(self, deal_id: str) -> list[str]:
        return [event["event_type"] for event in self.read(deal_id)["events"]]

    # the script -------------------------------------------------------------

    def request(self, deal_id: str, max_price_minor: int = 60000) -> Row:
        body = {
            "seller_org_id": "seller-co",
            "offer_id": "offer-1",
            "inputs": {"topic": "demo"},
            "max_price_minor": max_price_minor,
            "currency": "EUR",
        }
        return self.send(self.buyer, "service_request", deal_id, body)

    def quote_body(self, price_minor: int = PRICE) -> Row:
        deadline = self.clock.ts(60)
        return {
            "price_minor": price_minor,
            "currency": "EUR",
            "delivery_deadline": deadline,
            "valid_until": self.clock.ts(600),
            "acceptance": acceptance(deadline),
        }

    def quote(self, deal_id: str, body: Row | None = None) -> Row:
        relayed = self.inbox(self.seller, deal_id, "relay")[-1]
        cause = relayed["body"]["relayed"]["message_id"]
        return self.send(
            self.seller, "quote", deal_id, body or self.quote_body(), cause
        )

    def accept(self, key: AgentKey, deal_id: str) -> Row:
        proposed = self.inbox(key, deal_id, "terms_proposed")[-1]
        body = {"terms_hash": proposed["body"]["terms_hash"]}
        return self.send(key, "accept_terms", deal_id, body, proposed["message_id"])

    def pay(self, deal_id: str) -> Row:
        """The buyer pays the payment request at the bank; E's tick sees the credit."""
        request = self.inbox(self.buyer, deal_id, "payment_request")[-1]["body"]
        self.bank.transfer(
            from_iban=BUYER_IBAN,
            to_iban=request["to_iban"],
            amount_minor=request["amount_minor"],
            currency=request["currency"],
            reference=request["reference"],
            idempotency_key=f"pay:{deal_id}",
        )
        self.clock.tick()
        return self.run_tick()

    def open_deal(self, deal_id: str) -> None:
        """From the request to FUNDED."""
        assert self.request(deal_id)["status"] == "processed"
        assert self.quote(deal_id)["status"] == "processed"
        assert self.accept(self.buyer, deal_id)["status"] == "processed"
        assert self.accept(self.seller, deal_id)["status"] == "processed"
        assert self.pay(deal_id)["deals_funded"] == 1

    def deliver(
        self, deal_id: str, attempt: int = 1, names: tuple[str, ...] = FILES
    ) -> Row:
        """Attempt 1 answers ``funding_confirmed``; a redelivery answers the reject."""
        answered = "funding_confirmed" if attempt == 1 else "decision"
        cause = self.inbox(self.seller, deal_id, answered)[-1]["message_id"]
        artifact = self.artifacts.put(zip_bytes(names), "application/zip")
        body = {"attempt": attempt, "artifact": artifact}
        return self.send(self.seller, "delivery", deal_id, body, cause)

    def verdict_body(self, request: Row) -> Row:
        """The evaluator agent's three deterministic checks (build guide §5.7)."""
        ask = request["body"]
        data = self.artifacts.get(ask["artifact"]["artifact_id"])
        reasons: list[str] = []
        if ask["evaluator_id"] == "required-files":
            present = set(zipfile.ZipFile(io.BytesIO(data)).namelist())
            missing = sorted(set(ask["params"]["required_files"]) - present)
            reasons = [f"missing file: {name}" for name in missing]
        elif ask["evaluator_id"] == "deadline":
            if ask["delivered_at"] > ask["params"]["delivery_deadline"]:
                reasons = ["delivered after the deadline"]
        elif len(data) != ask["artifact"]["byte_length"]:
            reasons = ["size does not match"]
        return {
            "evaluation_request_id": ask["evaluation_request_id"],
            "terms_hash": ask["terms_hash"],
            "delivery_id": ask["delivery_id"],
            "artifact_sha256": ask["artifact"]["sha256"],
            "evaluator_id": ask["evaluator_id"],
            "evaluator_version": ask["evaluator_version"],
            "outcome": "fail" if reasons else "pass",
            "reasons": reasons,
        }

    def requests(self, deal_id: str, attempt: int) -> list[Row]:
        """The evaluation requests of one delivery, in the order E sent them."""
        return [
            envelope
            for envelope in self.inbox(self.evaluator, deal_id, "evaluation_request")
            if envelope["body"]["delivery_id"] == f"{deal_id}:d{attempt}"
        ]

    def judge(self, request: Row) -> Row:
        body = self.verdict_body(request)
        deal_id = request["conversation_id"]
        return self.send(
            self.evaluator, "verdict", deal_id, body, request["message_id"]
        )

    def evaluate(self, deal_id: str, attempt: int = 1) -> list[Row]:
        return [self.judge(request) for request in self.requests(deal_id, attempt)]

    def happy_path(self, deal_id: str = HAPPY_DEAL) -> None:
        self.open_deal(deal_id)
        assert self.deliver(deal_id)["status"] == "processed"
        results = self.evaluate(deal_id)
        assert [result["status"] for result in results] == ["processed"] * 3

    def broken_run(self, deal_id: str = BROKEN_DEAL) -> list[Row]:
        """Attempt 1 lacks summary.json; returns the three answers to its verdicts."""
        self.open_deal(deal_id)
        assert self.deliver(deal_id, 1, FILES[:2])["status"] == "processed"
        first = self.evaluate(deal_id, 1)
        assert self.deliver(deal_id, 2)["status"] == "processed"
        second = self.evaluate(deal_id, 2)
        assert [result["status"] for result in second] == ["processed"] * 3
        return first
