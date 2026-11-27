# Build guide (demo v0)

How the pieces fit in code. Read with [PARALLEL-PLAN.md](../PARALLEL-PLAN.md) §1, §4, §5 and
[SPEC.md](../SPEC.md). Where this file is more specific than the plan, this file wins.

## 1. What runs where

| Piece | Form | Proven by |
| --- | --- | --- |
| Four agents | Real Cogit resident agents: `cogit init`, business code in place | `cogit check`, `cogit agent validate`, `cogit test` |
| Three modules | Reference implementation in Python over SQLite, behind the frozen export contract, plus the table DDL | pytest |
| Messaging | `cogit-messaging-shim`: signed envelopes, `send()`, delivery loop | pytest |
| Sim bank, dashboard | FastAPI apps | pytest, screenshot |
| Whole flow | Offline end-to-end run: real bound operations of all four agents on the in-process stand-ins | `tests/e2e` |

Not part of this build: Docker, a live AgentDb, `cogit work`, and the AgentDb-native
packaging of the modules (PL/pgSQL functions `fn(ctx jsonb, input jsonb) returns jsonb`
with a `manifest.json`). The reference implementations are the specification for that port.

## 2. Shared packages (already written; do not edit outside lane A / L0)

`packages/cogit-finance-seams` (`cogit_finance_seams`):

```python
ModuleError(code, message="")            # .code is part of the contract
Caller(installation_id, principal)       # principal: installation | operator | operator_ro
class ModulePort:                        # mirror of the SDK's DatabaseSeams
    def module_query(module, export, args=None) -> dict
    def module_command(module, export, args=None, *, idempotency_key: str) -> dict
class ArtifactPort:
    def put(data: bytes, media_type: str) -> dict   # {artifact_id, sha256, byte_length, media_type}
    def get(artifact_id) -> bytes
    def stat(artifact_id) -> dict | None
class WorkPort:
    def admit(installation_id, action, input, *, idempotency_key) -> str   # run_id; same key, same run
    def result(run_id) -> RunResult                # .status succeeded|failed, .output, .error
class BankPort:                                    # SimBankClient(http) / SimBankClient.from_url(url)
    def transfer(*, from_iban, to_iban, amount_minor, currency, reference, idempotency_key) -> dict
    def lookup(idempotency_key) -> dict | None
    def credits(iban, after="0") -> list[dict]
    def accounts() -> list[dict]
# in-process stand-ins
LocalModuleHost(clock=utcnow)   .install(module, settings=None)   .port(installation_id, principal="installation")
SqliteModule                    # base class of a module reference implementation
LocalArtifacts()                # ArtifactPort
LocalRuntime()                  # WorkPort; .register(installation_id, object_or_invoker)
# cogit_finance_seams.cogit_host (needs cogit-agent-sdk)
HandleModules(invocation.handle)       # ModulePort over the run handle
HandleArtifacts(invocation.handle)     # ArtifactPort over the run handle
LocalRunHandle, invoke_action, agent_invoker, contract_id
```

`packages/cogit-messaging-shim` (`cogit_messaging_shim`):

```python
canonical_bytes(obj) -> bytes; canonical_hash(obj) -> str; sha256_hex(data) -> str
event_hash(event) -> str; ZERO_HASH
AgentKey.generate() / .from_seed(seed) / .load_or_create(path);  key.did;  key.sign(data)
build_envelope(key, sender_did, type_key, type_version, recipient_did, conversation_id, body,
               causation_id=None, *, message_id=None, created_at=None) -> dict
verify_envelope(envelope) -> bool
reply_message_id(causation_id, type_key, recipient_did) -> str
now_ts(); to_ts(datetime); parse_ts(text)
class MessagingSeams: send(type_key, type_version, recipient_did, conversation_id, body, causation_id=None) -> str
ShimMessaging(key, modules)             # MessagingSeams over the cogit-messaging module
send_envelope(modules, envelope) -> str # queue an already signed envelope
cogit_messaging_shim.testing.RecordingMessaging   # test double, keeps .sent
```

## 3. Module reference implementations (lanes A and B)

One Python package per module folder:

| Folder | Import name | Class | Module name |
| --- | --- | --- | --- |
| `modules/cogit-messaging` | `cogit_messaging_module` | `MessagingModule` | `cogit-messaging` |
| `modules/cogit-finance-catalog` | `cogit_finance_catalog_module` | `CatalogModule` | `cogit-finance-catalog` |
| `modules/cogit-finance-deals` | `cogit_finance_deals_module` | `DealsModule` | `cogit-finance-deals` |

Layout: `pyproject.toml` (hatchling, depends on `cogit-finance-seams`), `migrations/000001__init.sql`,
`src/<import name>/`, `tests/`, `README.md`. The class subclasses `SqliteModule`, sets
`name`, `migrations_dir`, `queries` and `commands` (export name → method name), and each
handler is `def handler(self, args: dict, caller: Caller) -> dict`. Exports, fields,
access rules and error codes: [module-exports.md](module-exports.md).

Write the DDL in the subset SQLite and PostgreSQL share (TEXT, INTEGER, JSON as TEXT,
`CREATE UNIQUE INDEX … WHERE`), table names prefixed (`msg_`, `cat_`, `deal_`). Use
`self.now_ts()` for timestamps so tests can move the clock. No float columns.

## 4. Agents (lanes C and E)

Create each project with the official CLI and keep what it generates
(`.agents/skills/bootstrap-cogit-agent/SKILL.md` in the project is the Build skill):

```sh
export PATH="$HOME/.local/bin:$PATH"
cogit init <dir> --id <id> --name "<Name>" \
  --template /home/claude/cogit/cogit-agent-template --ref 608927972743dc59bd1e9dad0dd4f176bbc41c93
python scripts/vendor_wheels.py <dir>      # shared packages into vendor/wheels + cohort receipt
(cd <dir> && uv lock) && cogit install --project <dir>
# after code changes:
cogit check --project <dir> --fix
cogit agent contract sync --project <dir>
cogit install --project <dir> && cogit agent validate --project <dir> && cogit test --project <dir>
```

| Agent | Directory | `--id` | Package | Actions |
| --- | --- | --- | --- | --- |
| E | `packages/cogit-finance` | `cogit-finance` | `cogit_finance` | `handle_message`, `tick` |
| Buyer | `agents/buyer-agent` | `buyer-agent` | `buyer_agent` | `handle_message`, `start_purchase` |
| Seller | `agents/seller-agent` | `seller-agent` | `seller_agent` | `handle_message`, `publish_catalog` |
| Evaluator | `agents/evaluator-agent` | `evaluator-agent` | `evaluator_agent` | `handle_message` |

Rules:

- Keep the generated agent class, `main.py`, the entrypoint in `cogit.yaml` and the Runtime
  wiring. Never pass `--entrypoint` to contract sync. Leave the template's reference
  actions, module and tests in place; add ours next to them.
- Business code goes into the generated package: schemas in `schemas.py`, bindings in
  `operations.py` (`bind_action(operation(fn), name=…, description=…, risk="write",
  idempotency="inherent")`, added to `build_domain_action_bindings`), behaviour in
  `domain.py` or further modules beside it. The package must not import `cogit_runtime`,
  `fastapi`, `starlette`, `uvicorn`, `sqlalchemy`, `openai` or `anthropic` (`.importlinter`).
- Shape: one core class per agent that takes ports in its constructor and has no SDK
  import, so it is unit-tested with fakes. The operation builds it from the run handle:
  `HandleModules(invocation.handle)`, `HandleArtifacts(invocation.handle)`,
  `ShimMessaging(key, modules)`, settings from the environment.
- Leave `database_packages` in `cogit.yaml` as generated. Our modules are declared there
  once they exist as AgentDb packages.
- `cogit check` must pass for Ruff. Pyright runs in strict mode; fix what is cheap and put
  `# pyright: basic` at the top of a business module where strict typing of JSON costs too
  much. Say in your report where you did.
- Product tests go in `tests/` with new file names; run them through `cogit test`.

Action contracts (Pydantic models, `extra="forbid"`):

| Action | Input | Output |
| --- | --- | --- |
| `handle_message` | `envelope: dict` | `status: "processed" \| "rejected"`, `reason: str \| None` |
| `tick` (E) | none | `types_registered: int`, `credits_seen: int`, `deals_funded: int`, `outbox_sent: int` |
| `start_purchase` (buyer) | `category: str \| None`, `max_price_minor: int \| None` | `status: "requested" \| "no_offer"`, `deal_id: str \| None`, `seller_org_id: str \| None`, `offer_id: str \| None`, `sellers_seen: int`, `offers_seen: int` |
| `publish_catalog` (seller) | none | `count: int` |

`handle_message` returns `rejected` with a reason for a message it refuses (bad signature,
unexpected sender, illegal in this state, stale verdict). It raises only for failures worth
retrying. The delivery loop maps the status to the acknowledgement.

Settings come from environment variables, read when an operation runs:

| Variable | Used by | Default |
| --- | --- | --- |
| `AGENT_KEY_FILE` | all | `.state/keys/<agent id>.key` (created on first use) |
| `ESCROW_DID` | buyer, seller, evaluator | resolved with `identity.resolve {"role": "escrow"}` |
| `COGIT_FINANCE_OPERATOR_CONFIG` | E | `config/operator.example.yaml` values |
| `FINANCE_CONTRACTS_DIR` | E | the message schemas packaged with E |
| `SIM_BANK_URL` | E, buyer | `rail.sim.base_url` for E; `http://localhost:8080` for the buyer |
| `BUYER_ORG_ID`, `BUYER_IBAN`, `BUYER_CATEGORY`, `BUYER_MAX_PRICE_MINOR` | buyer | `buyer-co`, `DE00EXAMPLE0000000010`, `reports`, `60000` |
| `SELLER_ORG_ID`, `SELLER_OFFERS_FILE`, `SELLER_MODE`, `SELLER_DELAY_S` | seller | `seller-co`, packaged copy of `data/demo/offers.seller-co.yaml`, `ok`, `0` |

## 5. Protocol conventions every lane relies on

1. `deal_id` = `conversation_id` = UUID chosen by the buyer in `service_request`.
   `delivery_id` = `<deal_id>:d<attempt>`. `evaluation_request_id` =
   `<delivery_id>:<evaluator_id>@<version>`. Payment reference = `ESCROW-<deal_id>`.
   Intent IDs = `<deal_id>:payout`, `<deal_id>:fee`; the bank idempotency key is the intent
   ID. The buyer pays with `Idempotency-Key: pay:<deal_id>`.
2. Buyer, seller and evaluator send every finance message to E and accept finance
   messages only from E (`unexpected_sender` otherwise).
3. Replies pass the inbound `message_id` as `causation_id`; `send()` then derives a stable
   reply ID, so processing a message twice sends the same reply. E builds its own envelopes
   with explicit, deterministic IDs: UUIDv5 over the deal ID and `<seq>:<type>:<recipient>:<n>`.
4. Relays: E wraps the original signed envelope in `finance.relay` (`relayed`, `deal`). The
   recipient verifies the inner signature too and acts on `relayed.type_key`. E relays
   `service_request` to the seller and `quote` and `delivery` to the buyer.
5. Terms: E builds `terms` from the request, the quote, the offer and the operator config
   (`fee_bps`, timers plus the offer's `delivery_time_s`). `terms_hash` =
   `canonical_hash(terms)`.
6. Quote: the seller copies the offer's `default_acceptance` and sets
   `params.delivery_deadline` of the `deadline` evaluator to the quoted deadline
   (now + `delivery_time_s`). `valid_until` = now + 600 s.
7. Evaluator checks. `integrity`: the stored bytes hash to `artifact.sha256` and have
   `byte_length`. `required-files`: every name in `params.required_files` is in the zip.
   `deadline`: `delivered_at` ≤ `params.delivery_deadline`. Outcome `pass` or `fail` with
   reasons; `error` only when the check cannot run.
8. Deliverable: a zip (`application/zip`) with `report.md`, `data.csv`, `summary.json`,
   built deterministically (fixed timestamps). Broken mode omits `summary.json` on attempt 1.
   On `decision` = `reject` with `attempts_left` > 0 the seller redelivers with the next
   attempt number, complete.
9. Deal events (SPEC §13.1): a message-sourced event has body `{"envelope": <verbatim>}`
   and `actor_did` = sender. An E-originated event has `actor_did` = E's DID and a body with
   what E decided or sent. `funding_received`, `payout_submitted` and the other E events
   carry no `source_message_id`.
10. E decides with policy `all` as soon as the outcome is certain: the first `fail`
    rejects. A verdict that arrives after the decision, or for a superseded delivery, is
    `rejected` with reason `stale_verdict` and leaves no event.
11. E's `tick` registers the `finance.*` types (idempotent), reads new credits on the
    escrow IBAN and funds matching deals, and re-sends pending outbox entries. Nothing else.
12. Fee: `fee_minor = (price_minor * fee_bps + 5000) // 10000`; `payout_minor = price_minor - fee_minor`.

## 6. Apps (lane D)

- `apps/sim-bank`: package `sim_bank`; `create_app(seed_file: Path | None = None) -> FastAPI`;
  `python -m sim_bank` serves on `SIM_BANK_PORT` (8080) with `SIM_BANK_SEED`
  (`data/demo/bank.yaml`). API: [sim-bank.md](sim-bank.md).
- `apps/dashboard`: package `dashboard`; `create_app(source) -> FastAPI`;
  `FixtureSource(directory)` and `ModuleSource(modules: ModulePort, bank: BankPort | None)`,
  both with `deals() -> list[dict]` (`deal.list`), `deal(deal_id) -> dict` (`deal.read`),
  `balances(deal_id=None) -> dict` (`ledger.balances`), `accounts() -> list[dict]`.
  `python -m dashboard --fixtures <dir>` serves on `DASHBOARD_PORT` (8090).

## 7. Tooling

- Root environment for the plain packages: `scripts/dev-install.sh`, then `scripts/test.sh`
  (one pytest process per package).
- Python 3.11 or newer everywhere; `from __future__ import annotations` in new files.
- Commit on your lane branch with conventional messages (`feat(escrow): …`), small and often.
