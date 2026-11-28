"""Write contracts/messages/finance.<name>.v1.json from the definitions below.

Schemas stay inside AgentDb's assertion dialect (SPEC §6.1): type, properties, required,
additionalProperties: false, items, enum, minLength, maxLength, minimum, maximum,
minItems, maxItems, description and nullable unions. No $ref: shared objects are inlined.
Run: python scripts/gen_message_schemas.py
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "contracts" / "messages"


def text(minimum: int = 1, maximum: int = 512, description: str | None = None) -> dict:
    schema: dict = {"type": "string", "minLength": minimum, "maxLength": maximum}
    if description:
        schema["description"] = description
    return schema


def integer(minimum: int = 0, maximum: int | None = None) -> dict:
    schema: dict = {"type": "integer", "minimum": minimum}
    if maximum is not None:
        schema["maximum"] = maximum
    return schema


def enum(*values: str) -> dict:
    return {"type": "string", "enum": list(values)}


def array(items: dict, minimum: int = 0, maximum: int | None = None) -> dict:
    schema: dict = {"type": "array", "items": items, "minItems": minimum}
    if maximum is not None:
        schema["maxItems"] = maximum
    return schema


def obj(**properties: dict) -> dict:
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def nullable(schema: dict) -> dict:
    return {**schema, "type": [schema["type"], "null"]}


FREE = {"type": "object", "description": "Free-form JSON object"}
TS = text(20, 20, "UTC timestamp, YYYY-MM-DDTHH:MM:SSZ")
HASH = text(64, 64, "Lower-case hex SHA-256")
UUID = text(36, 36, "UUID")
DID = text(8, 256, "Agent DID")
ID = text(1, 256)
MONEY = integer(0, 9_000_000_000_000)
CURRENCY = enum("EUR")

ARTIFACT = obj(artifact_id=ID, sha256=HASH, byte_length=integer(0), media_type=text(1, 128))
ACCEPTANCE = obj(
    evaluators=array(obj(evaluator_id=ID, version=integer(1), params=FREE), 1, 16),
    policy=enum("all", "any"),
    max_attempts=integer(1, 5),
)
TIMERS = obj(
    quote_ttl_s=integer(1),
    funding_due_s=integer(1),
    delivery_time_s=integer(1),
    rework_window_s=integer(1),
    dispute_window_s=integer(1),
    evaluator_respond_s=integer(1),
)
TERMS = obj(
    deal_id=UUID,
    buyer_org_id=ID,
    seller_org_id=ID,
    buyer_did=DID,
    seller_did=DID,
    escrow_did=DID,
    offer_id=ID,
    inputs=FREE,
    price_minor=integer(1, 9_000_000_000_000),
    currency=CURRENCY,
    fee_bps=integer(0, 10_000),
    delivery_deadline=TS,
    acceptance=ACCEPTANCE,
    timers=TIMERS,
)
ENVELOPE = obj(
    envelope_version=integer(1, 1),
    message_id=UUID,
    type_key=text(1, 128),
    type_version=integer(1),
    sender_did=DID,
    recipient_did=DID,
    conversation_id=ID,
    causation_id=nullable(UUID),
    created_at=TS,
    body=FREE,
    signature=text(1, 256),
)

MESSAGES: dict[str, tuple[str, dict]] = {
    "service_request": (
        "buyer -> E. Opens a deal; conversation_id is the new deal_id.",
        obj(seller_org_id=ID, offer_id=ID, inputs=FREE, max_price_minor=MONEY, currency=CURRENCY),
    ),
    "decline": ("buyer or seller -> E. Decline the proposed deal.", obj(reason=text(1, 500))),
    "cancel": ("buyer -> E. Cancel an unfunded deal.", obj(reason=text(1, 500))),
    "dispute": ("buyer or seller -> E. Contest a rejection.", obj(reason=text(1, 500))),
    "ruling": ("operator -> E. Resolve a disputed deal.", obj(outcome=enum("release", "refund"), reason=text(1, 500))),
    "refund_confirmed": ("E -> buyer, seller. The bank confirmed the refund.",
                         obj(amount_minor=MONEY, currency=CURRENCY, bank_ref=ID)),
    "quote": (
        "seller -> E. Price, deadline and acceptance spec for one request.",
        obj(price_minor=integer(1, 9_000_000_000_000), currency=CURRENCY, delivery_deadline=TS, valid_until=TS, acceptance=ACCEPTANCE),
    ),
    "terms_proposed": ("E -> buyer, seller. The deal terms to accept.", obj(terms=TERMS, terms_hash=HASH)),
    "accept_terms": ("buyer, seller -> E. Accept exactly these terms.", obj(terms_hash=HASH)),
    "terms_countersigned": (
        "E -> buyer, seller. Both parties accepted.",
        obj(terms_hash=HASH, accepted_by=array(UUID, 2, 2)),
    ),
    "payment_request": (
        "E -> buyer. Pay exactly this amount with this reference.",
        obj(to_iban=text(5, 34), amount_minor=MONEY, currency=CURRENCY, reference=text(1, 140), funding_due_by=TS),
    ),
    "funding_confirmed": (
        "E -> buyer, seller. The money is held; the seller can start.",
        obj(amount_minor=MONEY, currency=CURRENCY, bank_event_id=ID, delivery_deadline=TS),
    ),
    "delivery": ("seller -> E. One delivery attempt.", obj(attempt=integer(1, 5), artifact=ARTIFACT)),
    "evaluation_request": (
        "E -> evaluator. Judge one delivery.",
        obj(
            evaluation_request_id=ID,
            terms_hash=HASH,
            delivery_id=ID,
            artifact=ARTIFACT,
            evaluator_id=ID,
            evaluator_version=integer(1),
            params=FREE,
            delivered_at=TS,
            respond_by=TS,
        ),
    ),
    "verdict": (
        "evaluator -> E. Signed verdict on one evaluation request.",
        obj(
            evaluation_request_id=ID,
            terms_hash=HASH,
            delivery_id=ID,
            artifact_sha256=HASH,
            evaluator_id=ID,
            evaluator_version=integer(1),
            outcome=enum("pass", "fail", "error"),
            reasons=array(text(1, 500), 0, 20),
        ),
    ),
    "decision": (
        "E -> buyer, seller. Outcome of the evaluation of one delivery.",
        obj(
            delivery_id=ID,
            outcome=enum("approve", "reject"),
            attempts_left=integer(0, 5),
            rework_deadline=nullable(TS),
            reasons=array(text(1, 500), 0, 50),
        ),
    ),
    "payout_confirmed": (
        "E -> buyer, seller. The bank confirmed the payout.",
        obj(payout_minor=MONEY, fee_minor=MONEY, currency=CURRENCY, bank_ref=ID),
    ),
    "receipt": (
        "E -> buyer, seller. Signed receipt; head_seq and head_hash name the deal head it attests.",
        obj(
            outcome=enum("settled", "refunded"),
            price_minor=MONEY,
            fee_minor=MONEY,
            payout_minor=MONEY,
            currency=CURRENCY,
            terms_hash=HASH,
            head_seq=integer(1),
            head_hash=HASH,
        ),
    ),
    "relay": (
        "E -> buyer or seller. Passes on another party's signed envelope with the deal head (SPEC §6.3).",
        obj(relayed=ENVELOPE, deal=obj(deal_id=UUID, seq=integer(1), state=text(1, 32))),
    ),
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, (description, schema) in MESSAGES.items():
        document = {"description": description, **schema}
        path = OUT / f"finance.{name}.v1.json"
        path.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    # V1 is immutable. Quorum extends acceptance in new quote/terms versions.
    for name in ("quote", "terms_proposed"):
        description, original = MESSAGES[name]
        schema = deepcopy(original)
        props = schema["properties"] if name == "quote" else schema["properties"]["terms"]["properties"]
        props["acceptance"]["properties"]["policy"] = enum("all", "any", *(f"quorum {k}" for k in range(1, 17)))
        (OUT / f"finance.{name}.v2.json").write_text(
            json.dumps({"description": description, **schema}, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(MESSAGES) + 2} schemas to {OUT}")


if __name__ == "__main__":
    main()
