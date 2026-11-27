# cogit-finance-catalog

The catalog module of the escrow demo (SPEC §11.3): the companies known to the operator,
the offers each seller publishes and the evaluators that may be named in a deal's
acceptance spec. Adding a company, an offer or an evaluator is a data change only.

This package is the module's reference implementation: Python over SQLite, on
`cogit_finance_seams.SqliteModule`, behind the frozen export contract in
[contracts/module-exports.md](../../contracts/module-exports.md).

```python
from cogit_finance_seams import LocalModuleHost
from cogit_finance_catalog_module import CatalogModule

host = LocalModuleHost()
host.install(CatalogModule())
operator = host.port("operator", "operator")
operator.module_command(
    "cogit-finance-catalog", "company.upsert", {"company": {...}}, idempotency_key="seed:company:seller-co"
)
host.port("buyer-agent").module_query("cogit-finance-catalog", "sellers.list", {"category": "reports"})
```

## Tables

The additive migration `000002__company_profiles.sql` stores public descriptions
and prospect-gifting programme details in the company's JSON `profile`.
The read-only `companies.list` query lists all companies, optionally filtered by
`role: buyer` or `role: seller`. Existing rows default to an empty profile.

DDL: [migrations/000001__init.sql](migrations/000001__init.sql), in the subset SQLite and
PostgreSQL share (the file was run unchanged on PostgreSQL 16). Lists and objects are JSON
text, booleans are 0 or 1, money is integer minor units in `BIGINT` columns.

| Table | Key | Content |
| --- | --- | --- |
| `cat_companies` | `org_id` | Legal data, `roles` (`buyer`, `seller`), `categories`, IBAN, KYB flag, spending limit |
| `cat_offers` | `seller_org_id`, `offer_id` | Title, category, price, delivery time, input schema, deliverable, default acceptance, `active` |
| `cat_evaluators` | `evaluator_id`, `version` | Owning org, DID, description, `deterministic`, accepted media types, params schema |

## Exports

| Export | Kind | Caller | Result |
| --- | --- | --- | --- |
| `company.upsert` | command | operator | `{org_id}`; replaces the whole row |
| `company.read` | query | any | `{company}`: the row or null |
| `evaluator.upsert` | command | operator | `{evaluator_id, version}`; replaces the whole row |
| `catalog.publish` | command | any installation | `{count}`; replaces that seller's offers, `unknown_seller` without a company with role `seller` |
| `sellers.list` | query | any | `{sellers}`: companies with role `seller`, optionally with a category, sorted by `org_id` |
| `catalog.read` | query | any | `{offers}` of one seller, sorted by `offer_id`, inactive ones included |
| `evaluators.list` | query | any | `{evaluators}`, sorted by `evaluator_id`, `version` |

Lists, objects and booleans come back as JSON values. An empty catalog returns empty
lists. A malformed object (missing required field, wrong type, a float where an integer
belongs, an unknown field) fails with `invalid_argument` and changes nothing.

## Tests

```sh
scripts/test.sh modules/cogit-finance-catalog          # from the repository root
../../.venv/bin/python -m pytest -q                    # from this folder
```

## AgentDb packaging

The native implementation is in `agentdb/`: PL/pgSQL functions and an AgentDb
manifest. Build it with `python scripts/build_agentdb_modules.py`; deployment
and live acceptance are described in [the runtime guide](../../docs/AGENTDB-RUNTIME.md).
The Python/SQLite implementation remains the behavioral reference. Native
exports use the lossless JSON carrier in `cogit_finance_seams.native`.
