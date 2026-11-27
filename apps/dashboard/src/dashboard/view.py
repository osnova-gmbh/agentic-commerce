"""What the page shows, computed from module results. Pure functions; the page stays dumb."""

from __future__ import annotations

import json

from .steps import compute_steps, decision_outcome, find_dict, progress

LEDGER_ACCOUNTS = ("held", "seller", "fee", "buyer_refund", "returned")
STATE_TONES = {"SETTLED": "done", "REJECTED": "failed", "DISPUTED": "failed"}
CLOSED_STATES = ("REFUNDED", "DECLINED", "EXPIRED", "CANCELLED")
ESCROW_EVENTS = (
    "terms_proposed", "terms_countersigned", "payment_request", "funding_received", "evaluation_requested",
    "decision", "payout_submitted", "payout_confirmed", "receipt",
)  # fmt: skip
SENDER_ROLES = {"service_request": "buyer", "quote": "seller", "delivery": "seller", "verdict": "evaluator"}
SENDER_ROLES.update(dict.fromkeys(ESCROW_EVENTS, "escrow"))
EVENT_TONES = {"funding_received": "held", "payout_confirmed": "released"}


def format_minor(amount_minor: int | None, currency: str | None = "EUR") -> str:
    """``50000`` -> ``EUR 500.00``. Integer arithmetic only."""
    if amount_minor is None:
        return "—"
    units, cents = divmod(abs(int(amount_minor)), 100)
    return f"{'-' if amount_minor < 0 else ''}{currency or 'EUR'} {units:,}.{cents:02d}"


def clock(timestamp: str | None) -> str:
    """``2026-11-27T10:00:05Z`` -> ``10:00:05`` (UTC)."""
    return timestamp[11:19] if isinstance(timestamp, str) and len(timestamp) >= 19 else ""


def short_did(did: str | None) -> str:
    if not did:
        return ""
    head, _, key = did.rpartition(":")
    return did if len(key) <= 12 else f"{head}:{key[:6]}…{key[-4:]}"


def state_tone(state: str | None) -> str:
    return STATE_TONES.get(state or "", "muted" if state in CLOSED_STATES else "active")


def _events(read: dict) -> list[dict]:
    return sorted(read.get("events") or [], key=lambda event: event["seq"])


def _message(event: dict) -> dict:
    """Body of the signed message behind a message-sourced event, else ``{}``."""
    body = event.get("body")
    envelope = body.get("envelope") if isinstance(body, dict) else None
    message = envelope.get("body") if isinstance(envelope, dict) else None
    return message if isinstance(message, dict) else {}


def _field(event: dict, key: str) -> object:
    """A value from an event body whose exact shape E decides: found wherever it sits."""
    return (find_dict(event.get("body"), key) or {}).get(key)


def actor_roles(read: dict) -> dict[str, str]:
    """DID -> role: from the terms, the evaluation rows, then the event types."""
    roles: dict[str, str] = {}
    terms = (read.get("deal") or {}).get("terms") or {}
    for role in ("buyer", "seller", "escrow"):
        if terms.get(f"{role}_did"):
            roles[terms[f"{role}_did"]] = role
    for row in read.get("evaluations") or []:
        if row.get("evaluator_did"):
            roles.setdefault(row["evaluator_did"], "evaluator")
    for event in _events(read):
        role = SENDER_ROLES.get(event["event_type"])
        if role and event.get("actor_did"):
            roles.setdefault(event["actor_did"], role)
    return roles


def event_detail(event: dict, currency: str = "EUR") -> str:
    """One short line of what the event says, for the timeline."""
    kind, message = event["event_type"], _message(event)
    amount = _field(event, "amount_minor")
    if kind == "service_request" and message:
        return f"{message.get('offer_id')} from {message.get('seller_org_id')}"
    if kind == "quote" and message:
        return f"{format_minor(message.get('price_minor'), currency)}, due {clock(message.get('delivery_deadline'))}"
    if kind == "delivery" and message:
        return f"attempt {message.get('attempt')}"
    if kind == "verdict" and message:
        reasons = message.get("reasons") or []
        return f"{message.get('evaluator_id')}: {message.get('outcome')}" + (f" ({reasons[0]})" if reasons else "")
    if kind == "decision":
        return {"approve": "approved", "reject": "rejected"}.get(decision_outcome(event) or "", "")
    if kind == "payment_request" and isinstance(amount, int):
        return f"{format_minor(amount, currency)} requested"
    if kind == "funding_received":
        return f"{format_minor(amount, currency)} held" if isinstance(amount, int) else "money held"
    if kind == "payout_confirmed":
        payout = _field(event, "payout_minor")
        return f"{format_minor(payout, currency)} paid out" if isinstance(payout, int) else "money released"
    return ""


def timeline(read: dict) -> list[dict]:
    roles = actor_roles(read)
    currency = ((read.get("deal") or {}).get("terms") or {}).get("currency") or "EUR"
    rows = []
    for event in _events(read):
        did = event.get("actor_did") or ""
        failed = (event["event_type"] == "decision" and decision_outcome(event) == "reject") or (
            event["event_type"] == "verdict" and _message(event).get("outcome") in ("fail", "error")
        )
        rows.append(
            {
                "seq": event["seq"],
                "event_type": event["event_type"],
                "detail": event_detail(event, currency),
                "actor": roles.get(did) or short_did(did),
                "actor_did": did,
                "state_after": event.get("state_after") or "",
                "hash8": (event.get("hash") or "")[:8],
                "time": clock(event.get("recorded_at")),
                "tone": "failed" if failed else EVENT_TONES.get(event["event_type"], ""),
            }
        )
    return rows


def attempts(read: dict) -> list[dict]:
    """Verdicts grouped by delivery attempt, with the decision on each."""
    deal = read.get("deal") or {}
    named = [item.get("evaluator_id") for item in ((deal.get("terms") or {}).get("acceptance") or {}).get("evaluators") or []]
    groups: list[dict] = []
    for event in _events(read):
        kind, message = event["event_type"], _message(event)
        if kind == "delivery":
            number = message.get("attempt") or len(groups) + 1
            groups.append(
                {
                    "attempt": number,
                    "delivery_id": f"{deal.get('deal_id') or event.get('deal_id')}:d{number}",
                    "delivered_at": clock(event.get("recorded_at")),
                    "decision": None,
                    "reasons": [],
                    "verdicts": [],
                }
            )
        elif kind == "verdict" and groups:
            group = next((g for g in groups if g["delivery_id"] == message.get("delivery_id")), groups[-1])
            group["verdicts"].append(
                {
                    "evaluator": message.get("evaluator_id") or short_did(event.get("actor_did")),
                    "version": message.get("evaluator_version"),
                    "outcome": message.get("outcome") or "",
                    "reasons": [str(reason) for reason in message.get("reasons") or []],
                }
            )
        elif kind == "decision" and groups:
            groups[-1]["decision"] = decision_outcome(event)
            reasons = _field(event, "reasons")
            groups[-1]["reasons"] = [str(reason) for reason in reasons] if isinstance(reasons, list) else []
    for row in read.get("evaluations") or []:  # evaluators that were asked and left no verdict event
        group = next((g for g in groups if g["delivery_id"] == row.get("delivery_id")), None)
        if group and not any(verdict["evaluator"] == row.get("evaluator_id") for verdict in group["verdicts"]):
            outcome = "none" if group["decision"] else "waiting"
            group["verdicts"].append(
                {"evaluator": row.get("evaluator_id"), "version": row.get("evaluator_version"), "outcome": outcome, "reasons": []}
            )
    for group in groups:
        group["verdicts"].sort(key=lambda v: named.index(v["evaluator"]) if v["evaluator"] in named else len(named))
    return groups


def money(read: dict, balances: dict) -> dict:
    """Where the deal's money is: the phase, one headline and the ledger tiles."""
    deal = read.get("deal") or {}
    terms = deal.get("terms") or {}
    events = _events(read)
    p = progress(events)
    currency, price = terms.get("currency") or "EUR", terms.get("price_minor")
    buyer, seller = deal.get("buyer_org_id") or "the buyer", deal.get("seller_org_id") or "the seller"
    amounts = {name: int(balances.get(name) or 0) for name in LEDGER_ACCOUNTS}

    def eur(amount: int | None) -> str:
        return format_minor(amount, currency)

    def at(event_type: str) -> str:
        return next((clock(e.get("recorded_at")) for e in reversed(events) if e["event_type"] == event_type), "")

    if p.paid:
        phase, headline = "released", f"{eur(price)} released"
        paid_out, fee = eur(amounts["seller"]), eur(amounts["fee"])
        detail = f"{paid_out} paid to {seller}, {fee} fee to the operator, at {at('payout_confirmed')}."
    elif p.funded:
        phase, headline = "held", f"{eur(amounts['held'] or price)} held in escrow"
        if p.outcome == "reject":
            detail = "The delivery was rejected. The money stays held until a redelivery is approved."
        elif p.outcome == "approve":
            detail = f"The delivery is approved. Payout to {seller} is on its way."
        else:
            detail = (
                f"Paid in by {buyer} at {at('funding_received')}. "
                f"Released to {seller} only when the evaluators approve the delivery."
            )
    elif p.payment_requested:
        phase, headline = "requested", f"Waiting for {buyer} to pay {eur(price)}"
        detail = "Nothing is held yet. The seller starts work once the money is in escrow."
    else:
        phase, headline = "none", "No money has moved yet"
        detail = f"Price {eur(price)}." if price is not None else "The price is fixed when the terms are proposed."
    tiles = [
        {"key": "held", "label": "Held in escrow", "amount_minor": amounts["held"]},
        {"key": "seller", "label": f"Paid to {seller}", "amount_minor": amounts["seller"]},
        {"key": "fee", "label": "Operator fee", "amount_minor": amounts["fee"]},
    ]
    for tile in tiles:
        tile["display"] = eur(tile["amount_minor"])
    return {"phase": phase, "headline": headline, "detail": detail, "tiles": tiles}


def deal_summary(row: dict) -> dict:
    """One entry of the deal list, from a ``deal.list`` row or a ``deal.read`` deal row."""
    terms = row.get("terms") or {}
    price = row.get("price_minor", terms.get("price_minor"))
    currency = row.get("currency") or terms.get("currency") or "EUR"
    return {
        "deal_id": row["deal_id"],
        "state": row.get("state") or "",
        "tone": state_tone(row.get("state")),
        "buyer_org_id": row.get("buyer_org_id") or "",
        "seller_org_id": row.get("seller_org_id") or "",
        "offer_id": row.get("offer_id") or "",
        "head_seq": row.get("head_seq") or 0,
        "price_minor": price,
        "currency": currency,
        "price": format_minor(price, currency),
        "created_at": row.get("created_at") or "",
        "updated_at": row.get("updated_at") or "",
        "updated_time": clock(row.get("updated_at")),
    }


def _decoded(value: object) -> object:
    """JSON columns arrive as objects; tolerate a host that hands back the stored text."""
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except ValueError:
        return None


def deal_view(read: dict, balances: dict) -> dict:
    """Everything the page shows for one deal."""
    deal = {**read["deal"], "terms": _decoded(read["deal"].get("terms"))}
    events = [{**event, "body": _decoded(event.get("body"))} for event in read.get("events") or []]
    read = {**read, "deal": deal, "events": events}
    return {
        "deal": deal_summary(read["deal"]),
        "steps": compute_steps(read.get("events") or []),
        "money": money(read, balances),
        "attempts": attempts(read),
        "timeline": timeline(read),
    }


def balances_view(balances: dict, deal_id: str | None = None) -> dict:
    amounts = {name: int(balances.get(name) or 0) for name in LEDGER_ACCOUNTS}
    return {"deal_id": deal_id, "balances": amounts, "display": {name: format_minor(value) for name, value in amounts.items()}}


def accounts_view(accounts: list[dict]) -> dict:
    return {"accounts": [{**account, "balance": format_minor(account.get("balance_minor"))} for account in accounts]}
