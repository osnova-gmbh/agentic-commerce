# sim-bank

Stands in for the partner bank in the escrow demo. It has the three properties SPEC §10.3
needs from a bank: idempotency keys, lookup by key and credit events with stable IDs. The
API is frozen in [contracts/sim-bank.md](../../contracts/sim-bank.md).

The ledger is in memory and double-entry: every transfer debits one account and credits
another under one lock, so the sum of all balances never changes. Money is integer minor
units. Nothing survives a restart.

## Run

```sh
scripts/dev-install.sh                 # once, from the repository root
.venv/bin/python -m sim_bank           # http://127.0.0.1:8080
```

| Variable | Default | Meaning |
| --- | --- | --- |
| `SIM_BANK_PORT` | `8080` | Port |
| `SIM_BANK_HOST` | `127.0.0.1` | Bind address (`0.0.0.0` in the Docker image) |
| `SIM_BANK_SEED` | packaged copy of `data/demo/bank.yaml` | YAML file with the opening balances |
| `SIM_BANK_LOG_LEVEL` | `info` | Uvicorn log level |

In code: `sim_bank.create_app(seed_file: Path | None = None) -> FastAPI`. Agents talk to it
through `cogit_finance_seams.SimBankClient.from_url(url)`; tests use
`SimBankClient(TestClient(create_app()))`.

```sh
curl -s localhost:8080/accounts
curl -s -X POST localhost:8080/transfers -H 'Idempotency-Key: pay:demo' -H 'Content-Type: application/json' \
  -d '{"from_iban":"DE00EXAMPLE0000000010","to_iban":"DE00EXAMPLE0000000001","amount_minor":50000,"currency":"EUR","reference":"ESCROW-demo"}'
curl -s 'localhost:8080/events?iban=DE00EXAMPLE0000000001&after=0'
curl -s -X POST localhost:8080/admin/reset
```

Docker (not exercised in the cloud build): `docker build -t sim-bank apps/sim-bank && docker run -p 8080:8080 sim-bank`.

## Behaviour beyond the contract table

- Checks run in this order: idempotency key present, body valid, key already used (replay
  or `idempotency_conflict`), accounts known, funds sufficient. A replay therefore still
  answers with the first transfer when the payer has since been emptied.
- A refused transfer books nothing and does not use up its key.
- `POST /admin/reset` reads the seed file again. Event IDs keep counting across a reset, so
  no ID is used twice by one process. They start at `1` again after a restart.
- `GET /events` for an IBAN that is not an account answers `404 unknown_account`; an
  `after` that is not a non-negative integer answers `400 invalid_request`.
- Unknown routes and wrong methods also answer `{"error", "message"}` (`not_found`,
  `method_not_allowed`).

## Test

```sh
scripts/test.sh apps/sim-bank          # or: cd apps/sim-bank && ../../.venv/bin/python -m pytest
```
