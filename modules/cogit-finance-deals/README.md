# cogit-finance-deals

The deals module of the escrow demo (SPEC §11.4): the hash-chained event log of every
deal, the outbox of envelopes E has signed, deliveries and evaluations, payment intents,
bank credits and the ledger. The module enforces the expected head, the chain links and
the uniqueness constraints. E decides which transitions are legal and computes the event
hashes; the module stores them and keeps them unique.

This package is the module's reference implementation: Python over SQLite, on
`cogit_finance_seams.SqliteModule`, behind the frozen export contract in
[contracts/module-exports.md](../../contracts/module-exports.md).

```python
from cogit_finance_seams import LocalModuleHost
from cogit_finance_deals_module import DealsModule

host = LocalModuleHost()
host.install(DealsModule(), {"escrow_installation_id": "cogit-finance"})  # the default
escrow = host.port("cogit-finance")
escrow.module_command("cogit-finance-deals", "deal.commit", {...}, idempotency_key="evt:<message_id>")
host.port("dashboard", "operator_ro").module_query("cogit-finance-deals", "deal.list")
```

## Tables

DDL: [migrations/000001__init.sql](migrations/000001__init.sql), in the subset SQLite and
PostgreSQL share (the file was run unchanged on PostgreSQL 16, with the same constraint
violations as on SQLite). Objects are JSON text, timestamps are `YYYY-MM-DDTHH:MM:SSZ` text,
money is integer minor units in `BIGINT` columns. Every table references `deal_deals`;
SQLite enforces that only with `PRAGMA foreign_keys = ON`, and the module writes in an
order that satisfies it either way.

| Table | Key | Constraints beyond the key |
| --- | --- | --- |
| `deal_deals` | `deal_id` | |
| `deal_events` | `deal_id`, `seq` | `hash` unique; `source_message_id` unique where not null |
| `deal_outbox` | `outbox_id` | `status` is `pending` or `sent` |
| `deal_deliveries` | `delivery_id` | |
| `deal_evaluations` | `evaluation_request_id` | `outcome` is null, `pass`, `fail` or `error` |
| `deal_payment_intents` | `intent_id` | One active (`prepared`, `submitted`, `unknown`) `payout` or `refund` per deal, as a partial unique index |
| `deal_bank_credits` | `bank_event_id` | |
| `deal_ledger_postings` | `posting_id` | `source_id` + `account` unique |

Two tables carry columns that SPEC §11.4 does not list: `deal_outbox.created_at` and
`deal_outbox.ordinal` (the "oldest first" order of `outbox.pending`) and
`deal_evaluations.deal_id` (which deal a request belongs to). No export returns them.

## Exports

Commands belong to the installation named by the module setting `escrow_installation_id`
(default `cogit-finance`); every other caller gets `forbidden`. Queries are open in the demo.

| Export | Kind | Result |
| --- | --- | --- |
| `deal.commit` | command | `{seq, hash, duplicate}`; errors `head_mismatch`, `bad_event`, `intent_conflict`, `duplicate_credit` |
| `outbox.pending` | query | `{entries: [{outbox_id, deal_id, seq, envelope}]}`, oldest first, `limit` 50 by default |
| `outbox.mark_sent` | command | `{}`; repeating it is harmless |
| `intent.update` | command | `{}`; writes the given postings in the same transaction and skips a `source_id` + `account` that exists; error `unknown_intent` |
| `deal.read` | query | `{deal, events, deliveries, evaluations, intents, credits}`; null and empty lists for an unknown deal |
| `deal.list` | query | `{deals}`, newest first, with `price_minor` and `currency` from the terms |
| `ledger.balances` | query | `{held, seller, fee, buyer_refund, returned}`, for one deal or for all |

`deal.commit` is one transaction and applies these rules in order:

1. A `source_message_id` that already has an event returns that event's `seq` and `hash`
   with `duplicate: true` and writes nothing, whatever head the caller names.
2. `expected_seq` and `expected_hash` must be the deal's head, else `head_mismatch`. An
   unknown deal has head 0 and 64 zeros and needs `deal.buyer_org_id`, `deal.seller_org_id`
   and `deal.offer_id` (`head_mismatch` without them).
3. `event.seq` must be `expected_seq + 1` and `event.prev_hash` must be `expected_hash`,
   else `bad_event`. A malformed event or a hash that is already recorded is a `bad_event` too.
4. The head moves, the event is written, `deal.terms` and `deal.terms_hash` are applied
   when given and not null, the outbox entries are inserted as `pending`, `deliveries` and
   `evaluations` are upserted by their ID (an existing row changes only in the fields the
   argument names).
5. `intents`, `credits` and `postings` are inserted. A second active `payout` or `refund`
   intent, or an intent ID that exists, is an `intent_conflict`; a known `bank_event_id` is a
   `duplicate_credit`; a known posting ID or `source_id` + `account` is a `duplicate_posting`.

A malformed argument (missing field, wrong type, a float, an unknown field) fails with
`invalid_argument`. Any failure rolls the whole commit back.

## Tests

```sh
scripts/test.sh modules/cogit-finance-deals            # from the repository root
../../.venv/bin/python -m pytest -q                    # from this folder
```

## AgentDb packaging

The AgentDb-native packaging of this module, as PL/pgSQL functions
`fn(ctx jsonb, input jsonb) returns jsonb` with a `manifest.json`, is a later port and not
part of this build. This implementation is the specification for that port: the tables and
indexes in `migrations/`, the export names and kinds in `DealsModule.queries` and
`DealsModule.commands`, the order of the `deal.commit` rules in `commit.py`, and the
behaviour pinned by the tests. In the port the head check is the compare-and-swap that
`commit.py` already performs on `deal_deals` (`UPDATE … WHERE head_seq = … AND head_hash = …`),
so that two concurrent writers cannot append to the same link.
