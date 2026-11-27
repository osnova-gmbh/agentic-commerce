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
| 404 | `unknown_account` | Either IBAN is not an account |
| 404 | `unknown_transfer` | No transfer under that key |
| 409 | `idempotency_conflict` | The key was used with a different body |
| 409 | `insufficient_funds` | The payer's balance is too low |

The ledger is double-entry: every transfer debits one account and credits another, so the
sum of all balances never changes.
