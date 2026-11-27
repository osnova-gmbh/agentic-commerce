"""Generate the dashboard's fixture sets: ``python -m dashboard.make_fixtures``.

Plays the happy path and the broken run (contracts/fixtures/*.events.json) as a tiny
simulation and writes what the deals module and the bank would return. Envelopes are
really signed and the event hashes chain, so it needs ``cogit-messaging-shim``. The keys
are made up on every run and thrown away: DIDs, signatures and hashes change each time.

``--until N`` stops after event N, to look at an intermediate state.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import uuid
import zipfile
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .sources import dump_source, empty_read

ESCROW_IBAN, FEE_IBAN = "DE00EXAMPLE0000000001", "DE00EXAMPLE0000000002"
BUYER_IBAN, SELLER_IBAN = "DE00EXAMPLE0000000010", "DE00EXAMPLE0000000020"
OWNERS = {ESCROW_IBAN: "escrow held", FEE_IBAN: "escrow fees", BUYER_IBAN: "buyer-co", SELLER_IBAN: "seller-co"}
PRICE, FEE_BPS = 50000, 100
FEE = (PRICE * FEE_BPS + 5000) // 10000
FILES = ["report.md", "data.csv", "summary.json"]
EVALUATORS = ("integrity", "required-files", "deadline")
TIMERS = {"quote_ttl_s": 600, "funding_due_s": 900, "delivery_time_s": 60, "rework_window_s": 600,
          "dispute_window_s": 3600, "evaluator_respond_s": 60}  # fmt: skip
RUNS = {  # name -> (deal ID, start)
    "happy": ("3f6c2a1e-7b4d-4c58-9a10-5d2e8f4b6c01", datetime(2026, 11, 27, 10, 0, 0, tzinfo=timezone.utc)),
    "broken": ("9d1b7e44-2c3a-4f6e-8b21-0a7c5e9d3f02", datetime(2026, 11, 27, 10, 5, 0, tzinfo=timezone.utc)),
}
DEFAULT_OUT = Path(__file__).resolve().parents[2] / "fixtures"


def ts(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


class Run:
    """State of one simulated deal; also a data source, so ``dump_source`` can write it."""

    def __init__(self, deal_id: str, start: datetime) -> None:
        import cogit_messaging_shim as shim  # only needed to regenerate fixtures

        self.shim, self.deal_id, self.now = shim, deal_id, start
        self.keys = {role: shim.AgentKey.generate() for role in ("buyer", "seller", "escrow", "evaluator")}
        self.events: list[dict] = []
        self.deliveries: list[dict] = []
        self.evaluations: list[dict] = []
        self.intents: list[dict] = []
        self.credits: list[dict] = []
        self.ledger = {"held": 0, "seller": 0, "fee": 0, "buyer_refund": 0, "returned": 0}
        self.bank = {ESCROW_IBAN: 0, FEE_IBAN: 0, BUYER_IBAN: 1000000, SELLER_IBAN: 0}
        self.terms: dict | None = None
        self.terms_hash: str | None = None

    def did(self, role: str) -> str:
        return self.keys[role].did

    def record(self, event_type: str, actor: str, body: dict, state: str, wait: int, source_message_id: str | None = None):
        self.now += timedelta(seconds=wait)
        event = {
            "deal_id": self.deal_id,
            "seq": len(self.events) + 1,
            "prev_hash": self.events[-1]["hash"] if self.events else self.shim.ZERO_HASH,
            "event_type": event_type,
            "source_message_id": source_message_id,
            "actor_did": self.did(actor),
            "body": body,
            "state_after": state,
        }
        event["hash"] = self.shim.event_hash(event)
        event["recorded_at"] = ts(self.now)
        self.events.append(event)

    def message(self, sender: str, kind: str, body: dict, state: str, wait: int = 2) -> str:
        """A signed message from a party to E, recorded as a deal event."""
        seq = len(self.events) + 1
        message_id = str(uuid.uuid5(uuid.UUID(self.deal_id), f"{seq}:{kind}:{sender}"))
        causation_id = str(uuid.uuid5(uuid.UUID(self.deal_id), f"cause:{seq}")) if seq > 1 else None
        envelope = self.shim.build_envelope(
            self.keys[sender], self.did(sender), f"finance.{kind}", 1, self.did("escrow"), self.deal_id, body,
            causation_id, message_id=message_id, created_at=ts(self.now + timedelta(seconds=max(wait - 1, 0))),
        )  # fmt: skip
        self.record(kind, sender, {"envelope": envelope}, state, wait, message_id)
        return message_id

    def escrow(self, event_type: str, body: dict, state: str, wait: int = 1) -> None:
        self.record(event_type, "escrow", body, state, wait)

    def move(self, from_iban: str, to_iban: str, amount: int) -> None:
        self.bank[from_iban] -= amount
        self.bank[to_iban] += amount

    # the data source the dashboard reads
    def deals(self) -> list[dict]:
        head, terms = self.events[-1], self.terms or {}
        return [{
            "deal_id": self.deal_id, "state": head["state_after"], "buyer_org_id": "buyer-co",
            "seller_org_id": "seller-co", "offer_id": "offer-1", "head_seq": head["seq"],
            "price_minor": terms.get("price_minor"), "currency": terms.get("currency"),
            "created_at": self.events[0]["recorded_at"], "updated_at": head["recorded_at"],
        }]  # fmt: skip

    def deal(self, deal_id: str) -> dict:
        if deal_id != self.deal_id:
            return empty_read()
        row = self.deals()[0]
        deal = {name: row[name] for name in ("deal_id", "buyer_org_id", "seller_org_id", "offer_id", "state", "head_seq")}
        deal.update(head_hash=self.events[-1]["hash"], terms=self.terms, terms_hash=self.terms_hash,
                    created_at=row["created_at"], updated_at=row["updated_at"])  # fmt: skip
        return {"deal": deal, "events": self.events, "deliveries": self.deliveries, "evaluations": self.evaluations,
                "intents": self.intents, "credits": self.credits}  # fmt: skip

    def balances(self, deal_id: str | None = None) -> dict:
        return dict(self.ledger) if deal_id in (None, self.deal_id) else dict.fromkeys(self.ledger, 0)

    def accounts(self) -> list[dict]:
        return [{"iban": iban, "owner": OWNERS[iban], "balance_minor": self.bank[iban]} for iban in sorted(self.bank)]


def archive(names: list[str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        for name in names:
            bundle.writestr(zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0)), f"demo content of {name}\n")
    return buffer.getvalue()


def script(run: Run, broken: bool) -> Iterator[None]:
    """One deal, one ``yield`` after every deal event."""
    deal_id = run.deal_id

    def later(seconds: int) -> str:
        return ts(run.now + timedelta(seconds=seconds))

    request = {"seller_org_id": "seller-co", "offer_id": "offer-1", "inputs": {"topic": "Agent escrow services"},
               "max_price_minor": 60000, "currency": "EUR"}  # fmt: skip
    run.message("buyer", "service_request", request, "REQUESTED", wait=0)
    yield
    deadline = later(62)
    acceptance = {"policy": "all", "max_attempts": 2, "evaluators": [
        {"evaluator_id": "integrity", "version": 1, "params": {}},
        {"evaluator_id": "required-files", "version": 1, "params": {"required_files": FILES}},
        {"evaluator_id": "deadline", "version": 1, "params": {"delivery_deadline": deadline}},
    ]}  # fmt: skip
    quote = {"price_minor": PRICE, "currency": "EUR", "delivery_deadline": deadline, "valid_until": later(602),
             "acceptance": acceptance}  # fmt: skip
    run.message("seller", "quote", quote, "QUOTED")
    yield
    run.terms = {
        "deal_id": deal_id, "buyer_org_id": "buyer-co", "seller_org_id": "seller-co", "buyer_did": run.did("buyer"),
        "seller_did": run.did("seller"), "escrow_did": run.did("escrow"), "offer_id": "offer-1",
        "inputs": request["inputs"], "price_minor": PRICE, "currency": "EUR", "fee_bps": FEE_BPS,
        "delivery_deadline": deadline, "acceptance": acceptance, "timers": TIMERS,
    }  # fmt: skip
    run.terms_hash = run.shim.canonical_hash(run.terms)
    run.escrow("terms_proposed", {"terms": run.terms, "terms_hash": run.terms_hash}, "QUOTED")
    yield
    accepted = []
    for party in ("buyer", "seller"):
        accepted.append(run.message(party, "accept_terms", {"terms_hash": run.terms_hash}, "QUOTED"))
        yield
    run.escrow("terms_countersigned", {"terms_hash": run.terms_hash, "accepted_by": accepted}, "ACCEPTED")
    yield
    reference = f"ESCROW-{deal_id}"
    payment = {"to_iban": ESCROW_IBAN, "amount_minor": PRICE, "currency": "EUR", "reference": reference,
               "funding_due_by": later(900)}  # fmt: skip
    run.escrow("payment_request", payment, "FUNDING_REQUESTED", wait=0)
    yield
    credit = {"bank_event_id": "1", "reference": reference, "amount_minor": PRICE, "from_iban": BUYER_IBAN}
    run.move(BUYER_IBAN, ESCROW_IBAN, PRICE)  # the buyer pays, E's tick sees the credit
    run.ledger["held"] += PRICE
    run.escrow("funding_received", {**credit, "currency": "EUR"}, "FUNDED", wait=4)
    run.credits.append({**credit, "deal_id": deal_id, "received_at": ts(run.now), "disposition": "funded"})
    yield
    for attempt in (1, 2) if broken else (1,):
        complete = not (broken and attempt == 1)
        yield from evaluate(run, attempt, complete)
    payout = PRICE - FEE
    for kind, amount, iban in (("payout", payout, SELLER_IBAN), ("fee", FEE, FEE_IBAN)):
        run.intents.append({"intent_id": f"{deal_id}:{kind}", "deal_id": deal_id, "kind": kind, "amount_minor": amount,
                            "currency": "EUR", "to_iban": iban, "status": "prepared", "bank_ref": None})  # fmt: skip
    summary = [{name: intent[name] for name in ("intent_id", "kind", "amount_minor", "to_iban")} for intent in run.intents]
    run.escrow("payout_submitted", {"intents": summary}, "RELEASING")
    for intent in run.intents:
        intent.update(created_at=ts(run.now), updated_at=ts(run.now))
    yield
    for number, intent in enumerate(run.intents, start=2):
        run.move(ESCROW_IBAN, intent["to_iban"], intent["amount_minor"])
        run.ledger["held"] -= intent["amount_minor"]
        run.ledger["seller" if intent["kind"] == "payout" else "fee"] += intent["amount_minor"]
        intent.update(status="confirmed", bank_ref=f"tr-{number:06d}", updated_at=ts(run.now + timedelta(seconds=2)))
    paid = {"payout_minor": payout, "fee_minor": FEE, "currency": "EUR", "bank_ref": run.intents[0]["bank_ref"]}
    run.escrow("payout_confirmed", paid, "SETTLED", wait=2)
    yield
    head = run.events[-1]
    receipt = {"outcome": "settled", "price_minor": PRICE, "fee_minor": FEE, "payout_minor": payout, "currency": "EUR",
               "terms_hash": run.terms_hash, "head_seq": head["seq"], "head_hash": head["hash"]}  # fmt: skip
    run.escrow("receipt", receipt, "SETTLED")
    yield


def evaluate(run: Run, attempt: int, complete: bool) -> Iterator[None]:
    """Delivery, evaluation requests, verdicts and the decision for one attempt."""
    delivery_id = f"{run.deal_id}:d{attempt}"
    data = archive(FILES if complete else FILES[:2])
    digest = hashlib.sha256(data).hexdigest()
    artifact = {"artifact_id": f"art_{digest[:24]}", "sha256": digest, "byte_length": len(data), "media_type": "application/zip"}
    run.message("seller", "delivery", {"attempt": attempt, "artifact": artifact}, "DELIVERED", wait=8)
    run.deliveries.append({"delivery_id": delivery_id, "deal_id": run.deal_id, "attempt": attempt, **artifact,
                           "delivered_at": ts(run.now), "status": "delivered"})  # fmt: skip
    yield
    respond_by = ts(run.now + timedelta(seconds=61))
    for name in EVALUATORS:
        run.evaluations.append({"evaluation_request_id": f"{delivery_id}:{name}@1", "delivery_id": delivery_id,
                                "evaluator_id": name, "evaluator_version": 1, "evaluator_did": run.did("evaluator"),
                                "respond_by": respond_by, "resends": 0, "verdict_message_id": None, "outcome": None})  # fmt: skip
    requested = [row["evaluation_request_id"] for row in run.evaluations if row["delivery_id"] == delivery_id]
    run.escrow("evaluation_requested", {"delivery_id": delivery_id, "evaluation_request_ids": requested}, "EVALUATING")
    yield
    reasons: list[str] = []
    for row in [row for row in run.evaluations if row["delivery_id"] == delivery_id]:
        failed = row["evaluator_id"] == "required-files" and not complete
        verdict = {"evaluation_request_id": row["evaluation_request_id"], "terms_hash": run.terms_hash,
                   "delivery_id": delivery_id, "artifact_sha256": digest, "evaluator_id": row["evaluator_id"],
                   "evaluator_version": 1, "outcome": "fail" if failed else "pass",
                   "reasons": ["missing file: summary.json"] if failed else []}  # fmt: skip
        row["verdict_message_id"] = run.message("evaluator", "verdict", verdict, "EVALUATING", wait=1)
        row["outcome"] = verdict["outcome"]
        yield
        if failed:  # policy "all" decides on the first fail; the deadline verdict comes too late to count
            reasons = [f"required-files@1: {reason}" for reason in verdict["reasons"]]
            break
    outcome = "reject" if reasons else "approve"
    decision = {"delivery_id": delivery_id, "outcome": outcome, "attempts_left": 2 - attempt,
                "rework_deadline": run.terms["delivery_deadline"] if reasons else None, "reasons": reasons}  # fmt: skip
    run.escrow("decision", decision, "REJECTED" if reasons else "APPROVED")
    run.deliveries[-1]["status"] = "rejected" if reasons else "approved"
    yield


def play(name: str, until: int | None = None) -> Run:
    """Run ``happy`` or ``broken``, stopping after ``until`` events when given."""
    deal_id, start = RUNS[name]
    run = Run(deal_id, start)
    for _ in script(run, broken=name == "broken"):
        if until is not None and len(run.events) >= until:
            break
    return run


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m dashboard.make_fixtures", description=__doc__.split("\n")[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="parent directory of the fixture sets")
    parser.add_argument("--run", choices=sorted(RUNS), action="append", help="only this run (default: both)")
    parser.add_argument("--until", type=int, help="stop after this many events")
    args = parser.parse_args(argv)
    for name in args.run or sorted(RUNS):
        run = play(name, args.until)
        print(f"{dump_source(run, args.out / name)}: {len(run.events)} events, {run.events[-1]['state_after']}")


if __name__ == "__main__":
    main()
