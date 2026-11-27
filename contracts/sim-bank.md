# Sim bank API (demo v0)

Stands in for the partner bank. It has the three properties SPEC §10.3 needs: idempotency
keys, lookup by key and credit events with stable IDs. JSON over HTTP, port 8080.
Accounts are seeded from `data/demo/bank.yaml`. Money is integer minor units.

| Call | Behaviour |
| --- | --- |
| `POST /transfers` with header `Idempotency-Key` | Body `from_iban`, `to_iban`, `amount_minor`, `currency`, `reference`. Books the transfer and answers `200` with the transfer. The same key with the same body answers `200` with the first transfer and books nothing |
| `GET /transfers/by-key/{key}` | The transfer booked under that key, or `404` |
| `GET /events?iban=<iban>&after=<event_id>` | `{"events": [...]}`: credits to that IBAN with an event ID greater than `after` (default `0`), oldest first |
| `GET /accounts` | `{"accounts": [{"iban", "owner", "balance_minor"}]}`, sorted by IBAN |
| `POST /admin/reset` | Reseed accounts and forget all transfers. Answers `{"ok": true}` |
| `POST /admin/fund` with header `Idempotency-Key` | Demo-only budget replenishment. Body `iban`, `minimum_balance_minor` (integer from 1 to 1,000,000,000). Raises the account to that minimum; answers `{"iban", "credited_minor", "balance_minor"}`. Replaying the same key returns the original receipt and adds nothing |
| `GET /health` | `{"status": "ok"}` |

Transfer: `transfer_id`, `event_id`, `status` (`booked`), `from_iban`, `to_iban`,
`amount_minor`, `currency`, `reference`, `idempotency_key`, `booked_at`.

Event: `event_id`, `transfer_id`, `from_iban`, `to_iban`, `amount_minor`, `currency`,
`reference`, `booked_at`. `event_id` is an increasing integer written as a string
(`"1"`, `"2"`, …), one per transfer, never reused.

Errors answer `{"error": "<code>", "message": "..."}`:

| Status | Code | When |
| --- | --- | --- |
| 400 | `missing_idempotency_key` | No `Idempotency-Key` header |
| 400 | `invalid_transfer` | Missing field, `amount_minor` not a positive integer, same account on both sides, currency not `EUR` |
| 400 | `invalid_funding` | Funding body does not contain exactly `iban` and a valid `minimum_balance_minor` |
| 404 | `unknown_account` | Either IBAN is not an account |
| 404 | `unknown_transfer` | No transfer under that key |
| 409 | `idempotency_conflict` | The key was used with a different body |
| 409 | `insufficient_funds` | The payer's balance is too low |

The ledger is double-entry: every transfer debits one account and credits another, so
transfers preserve the sum of balances. The explicit `/admin/fund` operation supplies
additional simulated budget; it is not a bank payment. It leaves all booked transfers,
their idempotency records and all other account balances intact, and emits no `/events`
credit that an escrow watcher could mistake for buyer funding. Funding keys are scoped
to this administrative operation; changing its account or minimum under the same key
returns `409 idempotency_conflict`. `/admin/reset` also clears funding receipts.
