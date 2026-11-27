"""Shared values and helpers of the sim bank tests."""

from fastapi.testclient import TestClient

ESCROW = "DE00EXAMPLE0000000001"
FEES = "DE00EXAMPLE0000000002"
BUYER = "DE00EXAMPLE0000000010"
SELLER = "DE00EXAMPLE0000000020"


def payment(**changes) -> dict:
    body = {"from_iban": BUYER, "to_iban": ESCROW, "amount_minor": 50000, "currency": "EUR", "reference": "ESCROW-d1"}
    body.update(changes)
    return body


def pay(http: TestClient, key: str = "pay:d1", **changes):
    return http.post("/transfers", json=payment(**changes), headers={"Idempotency-Key": key})


def balances(http: TestClient) -> dict:
    return {account["iban"]: account["balance_minor"] for account in http.get("/accounts").json()["accounts"]}
