# Parallel build plan: hackathon demo

Status: plan, 2026-11-27. Companion to [SPEC.md](SPEC.md), which stays authoritative except for
the demo cuts in §1.

Six Claude Code sessions on the laptop, one git worktree each, exclusive paths, contracts
frozen up front so nobody waits. An optional seventh session ports messaging into the
framework, off the critical path.

## 1. Target and cut line

One deal runs from discovery to `SETTLED` with the SPEC §13.1 event sequence and correct
balances. A second run is rejected at evaluation, redelivered and settled. The dashboard shows
both. This is SPEC milestones M0–M4 and M6, plus the broken-delivery test from M5.

| In | Out (leave as table data or an explicit "not in demo" rejection) |
| --- | --- |
| Happy path: 17 events, `SETTLED`, balances per SPEC §13.2 | `DISPUTED`, `REFUNDING`/`REFUNDED`, `DECLINED`, `EXPIRED`, `CANCELLED` and the messages `decline`, `dispute`, `ruling`, `cancel`, `refund_confirmed` |
| Broken run: attempt 1 lacks one file, `REJECTED`, redelivery, `SETTLED` | Timers (SPEC §5.3), evaluator re-request, intent reconcile (`unknown`), `return_unmatched` |
| Four Cogit resident agents, one AgentDb, one tenant; `cogit agent validate` and `cogit test` pass | Crash-recovery tests, full access-rule matrix (SPEC §6.5), replay window, dead-lettering, runtime routes |
| Three AgentDb modules, signed envelopes, hash-chained deal log, outbox, payment intents with idempotency keys | Affinidi (M7), SEPA and card adapters, containerised agents |
| Sim bank and read-only dashboard | Anything in SPEC §16 |
| Unit-tested guards only: illegal message, duplicate message, stale verdict, evaluator from a party's company | |

Demo deviations from SPEC, all deliberate:

1. Messaging runs through an in-repo shim with the SPEC §11.2 `send()` signature and the §7 loop. The SDK and runtime version is lane F and is swapped in only at gate G6.
2. One extra message type, `finance.relay`, carries the SPEC §6.3 relays.
3. E computes event hashes; the deals module enforces the expected head and uniqueness.
4. E's loop admits `tick` every 2 s. `tick` only registers types, polls bank credits and re-sends the outbox.
5. Access checks: `message.send` and `message.claim` caller checks only. The dashboard uses a read-only identity if L0 finds one quickly, otherwise the operator principal (queries only, never SQL).

## 2. Lanes

| Lane | Branch | Owns (exclusive paths) | Delivers |
| --- | --- | --- | --- |
| L0 Lead | `demo` (main checkout) | `contracts/`, `config/`, `data/demo/`, `scripts/`, `deploy/`, `tests/e2e/`, `docs/`, root files | Contracts, environment, AgentDb notes, seed, merges, end-to-end tests, demo run |
| A Messaging | `lane/messaging` | `modules/cogit-messaging/`, `packages/cogit-messaging-shim/` | Module, signing, `send()`, delivery loop |
| B Modules | `lane/modules` | `modules/cogit-finance-catalog/`, `modules/cogit-finance-deals/` | Tables and exports |
| C Escrow | `lane/escrow` | `packages/cogit-finance/` | E: domain, `handle_message`, `tick`, sim payment adapter |
| D Apps | `lane/apps` | `apps/sim-bank/`, `apps/dashboard/` | Sim bank first, then dashboard |
| E Agents | `lane/agents` | `agents/buyer-agent/`, `agents/seller-agent/`, `agents/evaluator-agent/` | Three demo agents and the deliverables |
| F Port (optional) | `feature/agent-messaging` | New worktrees of `cogit-agent-sdk` and `cogit-runtime` only | `MessagingSeams` in the SDK, loop in the runtime |

Critical path: L0 environment → A live messaging → C wired to real ports → L0 integration.
B, D and E feed it. L0 is the session the human sits with.

## 3. Waves and gates

Times are targets for an eight-hour slot; scale them.

| Wave | Target | Who | Gate |
| --- | --- | --- | --- |
| 0 Freeze | 0:00–0:30 | L0 alone | **G0** `demo` has this plan, the folder skeleton, `contracts/`, `data/demo/`, `config/`; worktrees exist |
| 1 Build on fakes | 0:30–3:30 | A–E in parallel; L0 on the environment | **G1** (L0, by 1:30) AgentDb up, `docs/agentdb-notes.md` written. **G2** (C) happy path and broken run replay in memory. **G3** (A) one signed message sent, claimed, admitted and acknowledged exactly once on live AgentDb, also after killing the loop mid-delivery (SPEC M1) |
| 2 Integrate | 3:30–5:30 | L0 merges, lanes fix | **G4** happy path live: `SETTLED`, balances correct (SPEC M4) |
| 3 Demo | 5:30–7:00 | L0, D, E | **G5** broken run live; dashboard on live data (SPEC M6). **G6** port swap decision |
| Buffer | 7:00–8:00 | L0 | Two clean runs of `scripts/demo` in a row |

Early merges into `demo`, as soon as they exist: A's first push (canonical JSON, keys,
envelope, `MessagingSeams`), D's sim bank, B's export shapes.

## 4. Rules for every agent

1. SPEC.md is authoritative; §1 lists the cuts. Build nothing from the Out column.
2. Edit only your own paths. If §5 or `contracts/` is wrong or incomplete, tell the human; L0 changes it and every lane merges `demo`.
3. Build against §5 with fakes first. Never wait for another lane.
4. Python, `uv`, `pytest`. Dependencies: the pinned Cogit cohort (Template 0.1.25 → SDK 0.5.16, Runtime 0.3.31, AgentDb client 0.2.13, vendored wheels) plus `fastapi`, `uvicorn`, `httpx`, `pydantic`, `cryptography`, `base58`, `pyyaml`, `jsonschema`.
5. Cogit commands, the module format and API shapes come from `C:\index.md`, cogit-core and `docs/agentdb-notes.md`. Do not guess them. Agents are built with the cogit.foundation skills; the generated agent class and entrypoint stay in place.
6. Leave the existing `cogit-agent-sdk` and `cogit-runtime` checkouts and all existing Docker containers and volumes alone. No reset, no prune (see [WSL-HANDOVER.md](WSL-HANDOVER.md)).
7. Keys live in `.state/keys/` (gitignored). Never in commits, logs or prompts.
8. Small commits on your lane branch. Tests for what you build and nothing more. Files under about 300 lines.

## 5. Frozen contracts (demo v0)

Written out in `contracts/`: message schemas, [module exports](contracts/module-exports.md),
[sim bank](contracts/sim-bank.md) and the [build guide](contracts/build-guide.md), which is
more specific than this section and wins where they differ.

### 5.1 Names and values

| Thing | Value |
| --- | --- |
| Orgs | `buyer-co`, `seller-co`, `operator-co` (placeholders; real names are data, added last) |
| Installations | `buyer-agent`, `seller-agent`, `evaluator-agent`, `cogit-finance` |
| Modules | `cogit-messaging`, `cogit-finance-catalog`, `cogit-finance-deals` |
| Actions | Every agent: `handle_message(envelope)`. E: `tick()`. Buyer: `start_purchase(category, max_price_minor)`. Seller: `publish_catalog()` |
| Evaluators | `integrity@1`, `required-files@1`, `deadline@1`; org `operator-co`; all signed by the evaluator agent's DID; policy `all`; `max_attempts` 2 |
| Offer | `seller-co` / `offer-1`, category `reports`, 50000 minor EUR, `delivery_time_s` 60, `application/zip` with `report.md`, `data.csv`, `summary.json` |
| Fee | 100 bps: fee 500, payout 49500 |
| IBANs | Escrow `DE00EXAMPLE0000000001`, fees `DE00EXAMPLE0000000002`, buyer `DE00EXAMPLE0000000010` (opens with 1000000), seller `DE00EXAMPLE0000000020` |
| Ports | Sim bank 8080, dashboard 8090 |
| Environment | `COGIT_FINANCE_OPERATOR_CONFIG`, `SIM_BANK_URL`, `SELLER_OFFERS_FILE`, `SELLER_MODE` (`ok` or `broken`), `SELLER_DELAY_S` |

### 5.2 Encoding

- `deal_id` = `conversation_id` = a UUID chosen by the buyer in `service_request`.
- Canonical bytes: `json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")`.
- Signature: Ed25519 over the canonical bytes of the envelope without `signature`; base64url without padding.
- DID: `did:key:z` + base58btc(`0xed01` + 32-byte public key).
- `terms_hash` = SHA-256 of canonical `terms`. Event `hash` = SHA-256 of `prev_hash` + canonical `{deal_id, seq, prev_hash, event_type, source_message_id, actor_did, body, state_after}`. The first `prev_hash` is 64 zeros. Hashes are lower-case hex.
- Timestamps: ISO-8601 UTC, whole seconds, suffix `Z`. Money: integer minor units. No floats anywhere.
- Idempotency keys as in SPEC §7: `msg:<message_id>`, `evt:<message_id>`, `out:<outbox_id>`, and `intent_id` at the bank.

### 5.3 Messaging shim (`cogit_messaging_shim`)

```python
class MessagingSeams(Protocol):
    def send(self, type_key: str, type_version: int, recipient_did: str,
             conversation_id: str, body: dict, causation_id: str | None = None) -> str: ...

def build_envelope(key, sender_did, type_key, type_version, recipient_did,
                   conversation_id, body, causation_id=None) -> dict: ...
def verify_envelope(envelope: dict) -> bool: ...
def send_envelope(envelope: dict) -> str: ...   # idempotent on message_id; E's outbox uses it
```

Loop: `python -m cogit_messaging_shim.loop --agent <installation> [--tick-every 2]` claims,
verifies, admits `handle_message` with key `msg:<message_id>`, waits for the run and
acknowledges. Agents import messaging from this one package, so the swap to the SDK seam is a
one-line change.

### 5.4 Message bodies (all version 1)

Schemas use AgentDb's assertion dialect (SPEC §6.1): no `$ref`, shared objects inlined.

| Type | Body fields |
| --- | --- |
| `finance.service_request` | `seller_org_id`, `offer_id`, `inputs`, `max_price_minor`, `currency` |
| `finance.quote` | `price_minor`, `currency`, `delivery_deadline`, `valid_until`, `acceptance` |
| `finance.terms_proposed` | `terms`, `terms_hash` |
| `finance.accept_terms` | `terms_hash` |
| `finance.terms_countersigned` | `terms_hash`, `accepted_by` (the two `message_id`s) |
| `finance.payment_request` | `to_iban`, `amount_minor`, `currency`, `reference`, `funding_due_by` |
| `finance.funding_confirmed` | `amount_minor`, `currency`, `bank_event_id`, `delivery_deadline` |
| `finance.delivery` | `attempt`, `artifact` |
| `finance.evaluation_request` | `evaluation_request_id`, `terms_hash`, `delivery_id`, `artifact`, `evaluator_id`, `evaluator_version`, `params`, `delivered_at`, `respond_by` |
| `finance.verdict` | `evaluation_request_id`, `terms_hash`, `delivery_id`, `artifact_sha256`, `evaluator_id`, `evaluator_version`, `outcome` (`pass`, `fail`, `error`), `reasons` |
| `finance.decision` | `delivery_id`, `outcome` (`approve`, `reject`), `attempts_left`, `rework_deadline` (nullable), `reasons` |
| `finance.payout_confirmed` | `payout_minor`, `fee_minor`, `currency`, `bank_ref` |
| `finance.receipt` | `outcome` (`settled`), `price_minor`, `fee_minor`, `payout_minor`, `currency`, `terms_hash`, `head_seq`, `head_hash` |
| `finance.relay` (new) | `relayed` (the original signed envelope), `deal` (`deal_id`, `seq`, `state`) |

- `artifact` = `artifact_id`, `sha256`, `byte_length`, `media_type`.
- `acceptance` = `evaluators` (list of `evaluator_id`, `version`, `params`), `policy`, `max_attempts`.
- `terms` = `deal_id`, `buyer_org_id`, `seller_org_id`, `buyer_did`, `seller_did`, `escrow_did`, `offer_id`, `inputs`, `price_minor`, `currency`, `fee_bps`, `delivery_deadline`, `acceptance`, `timers`.
- Evaluator params: `required-files` takes `required_files`; `deadline` takes `delivery_deadline`; `integrity` takes none.
- E relays `service_request` to the seller, `quote` and `delivery` to the buyer. Relays create no deal event.

### 5.5 Module exports

Names are from SPEC §11. Arguments and results are JSON objects; row objects use the SPEC
column names. Adapt the form to AgentDb's conventions, not the fields.

| Export | Arguments → result |
| --- | --- |
| `identity.register` | `did`, `installation_id`, `org_id`, `role` → `did` |
| `identity.resolve` | `did` → identity row or null |
| `type.register` | `type_key`, `type_version`, `json_schema` → `status` (`created` or `unchanged`); different bytes fail with `type_conflict` |
| `message.send` | `envelope` → `message_id`, `status` (`queued` or `duplicate`); fails with `not_your_did`, `unknown_type`, `invalid_body`, `unknown_recipient` |
| `message.claim` | `limit` → `messages` (list of `message_id`, `envelope`, `attempts`) for the caller's DIDs, including claims older than 30 s |
| `message.ack` | `message_id`, `outcome` (`processed` or `rejected`), optional `reason`, `run_id` → empty |
| `message.release` | `message_id`, `delay_s` → empty |
| `conversation.read` | `conversation_id` → `messages`, ordered by `created_at` |
| `company.upsert`, `evaluator.upsert` | one row object → its key |
| `catalog.publish` | `seller_org_id`, `offers` → `count`; replaces that seller's offers |
| `sellers.list` | optional `category` → `sellers` (`org_id`, `legal_name`, `categories`), sorted by `org_id` |
| `catalog.read` | `seller_org_id` → `offers` |
| `evaluators.list` | none → `evaluators` |
| `deal.commit` | `deal_id`, `expected_seq`, `expected_hash`, `event`, optional `deal`, `outbox`, `deliveries`, `evaluations`, `intents`, `credits`, `postings` → `seq`, `hash`, `duplicate`; fails with `head_mismatch`. A new deal uses `expected_seq` 0 and 64 zeros. A known `source_message_id` returns the original result with `duplicate` true |
| `outbox.pending` | `limit` → `entries` (`outbox_id`, `envelope`) |
| `outbox.mark_sent` | `outbox_id` → empty |
| `intent.update` | `intent_id`, `status`, optional `bank_ref`, `postings` → empty; `confirmed` writes the postings in the same transaction |
| `deal.read` | `deal_id` → `deal`, `events`, `deliveries`, `evaluations`, `intents`, `credits` |
| `deal.list` | none → `deals` (`deal_id`, `state`, `buyer_org_id`, `seller_org_id`, `offer_id`, `head_seq`, `updated_at`) |
| `ledger.balances` | optional `deal_id` → `held`, `seller`, `fee`, `buyer_refund`, `returned` |

Postings: bank credit → `held` +price. Payout intent → `held` −payout, `seller` +payout. Fee
intent → `held` −fee, `fee` +fee.

### 5.6 Sim bank

| Call | Behaviour |
| --- | --- |
| `POST /transfers` with header `Idempotency-Key` | Body `from_iban`, `to_iban`, `amount_minor`, `currency`, `reference` → `transfer_id`, `event_id`, `status` `booked`. The same key returns the same answer and books nothing new |
| `GET /transfers/by-key/{key}` | The transfer, or 404 |
| `GET /events?iban=&after=` | Credits to that IBAN after the given event ID: `event_id` (increasing integer as a string), `transfer_id`, `from_iban`, `to_iban`, `amount_minor`, `currency`, `reference`, `booked_at` |
| `GET /accounts` | `iban`, `owner`, `balance_minor` for every account |
| `POST /admin/reset` | Reseed from `data/demo/bank.yaml` |

## 6. Lane briefs

### L0 Lead

- Wave 0: `git switch -c demo docs/spec-review-fixes`; commit this plan; create the folder skeleton; write `contracts/messages/<type>.v1.json` (14 files), `contracts/module-exports.md`, `contracts/sim-bank.md`, `contracts/fixtures/happy-path.events.json` and `broken-run.events.json` (sequence of event type and actor); write `data/demo/` (`companies.yaml`, `offers.seller-co.yaml`, `evaluators.yaml`, `bank.yaml`) and `config/operator.schema.json` with `config/operator.example.yaml` from SPEC §14; create the worktrees (§8).
- Wave 1: fix WSL-HANDOVER blockers 1 and 2 only (the human closes the Zed tab holding Docker's settings file); pin the cohort; start AgentDb; create the tenant and four installations. Write `docs/agentdb-notes.md` with what was proven: start commands and URLs; how to author and install a module; whether an export can read the calling installation (SPEC §17, question 2); how an agent calls `module_query` and `module_command`; how an outside process authenticates, calls exports and admits work with an idempotency key; how to create a read-only principal (SPEC §17, question 3); artifact upload and download; the `cogit` command sequence that worked for one throwaway agent.
- Then: `scripts/seed` (companies, identities, evaluators), `scripts/up` (apps, four workers, four loops), `scripts/demo happy|broken` (resets the bank, admits `start_purchase`).
- Waves 2–3: merge lanes at each gate. `tests/e2e/test_happy_path.py` asserts the SPEC §13.1 sequence through `deal.read` and the balances through `ledger.balances` and `/accounts`. `test_broken_run.py` asserts reject, redelivery, `SETTLED`; attempt 1 may record one to three verdicts before the reject, because policy `all` decides on the first fail.
- Done when: G0, G1, G4, G5 and two clean demo runs.

### A Messaging

- First push, within 30 minutes: `canonical.py`, `keys.py` (seed file, `did:key`), `envelope.py`, the `MessagingSeams` protocol and an in-memory `FakeBus`. C and E import these.
- `modules/cogit-messaging`: the three SPEC §11.1 tables and the §5.5 exports. `message.send` checks that the sender DID belongs to the caller, the type is registered and the body validates; it is idempotent on `message_id`.
- `seams.py` and `loop.py` on the existing `DatabaseSeams` and AgentDb admission (SPEC §7 steps 1, 2 and 5).
- `packages/cogit-messaging-shim/tests/contract/`: black-box tests of `send()` and the loop. Lane F must pass them unchanged.
- Done when: unit and contract tests pass on `FakeBus`; G3 on live AgentDb.
- Not now: dead-lettering, replay window, routes, `conversation.read` access rules.

### B Modules

- Copy the structure of an existing module in cogit-core's `agent-db/modules` (manifest, migrations, exports, tests).
- `cogit-finance-catalog`: three tables, six exports. An empty catalog returns empty lists.
- `cogit-finance-deals`: DDL for all eight SPEC §11.4 tables; exports as in §5.5 (no `intents.unresolved`). `deal.commit` is one transaction and enforces the expected head, unique `source_message_id`, one active payout or refund intent per deal, and unique `source_id` + `account` postings.
- Tests: commit, head mismatch, duplicate source message, empty catalog.
- Done when: both modules install into the tenant after G1, tests pass and shapes match `contracts/module-exports.md`.
- Not now: the access-rule matrix, beyond "deals commands are E's only" if the module context allows it.

### C Escrow (E)

- `cogit init` for `packages/cogit-finance`, following the Build skill.
- Domain, pure Python without I/O: the full SPEC §5.2 table as data; guards for the in-scope rows; terms builder and `terms_hash`; fee (SPEC §10.1); policy `all`; delivery and evaluation IDs (SPEC §9); stale and duplicate verdicts; receipt.
- `handle_message`: verify, load the deal, check the guard, build one `deal.commit` (event, outbox, rows), send the outbox. It talks to `DealsPort`, `CatalogPort`, `MessagingPort` and `BankPort`; tests use in-memory fakes.
- `tick`: register the `finance.*` types from `contracts/messages/`, turn new credits on the escrow IBAN into `funding_received`, flush the pending outbox.
- Sim payment adapter: prepare in the commit, submit with `Idempotency-Key: <intent_id>`, confirm with postings through `intent.update`.
- Done when: G2, with both in-memory runs dumped as `deal.read`-shaped JSON under `packages/cogit-finance/tests/fixtures/` for lane D to copy; unit tests for fee rounding, illegal message, duplicate message, stale verdict and a party-owned evaluator; `cogit agent validate` and `cogit test` pass. After G3, wire the real ports.
- Not now: other timers, `resolve_dispute`, refunds, re-requests, reconcile, SEPA, cards.

### D Apps

- `apps/sim-bank` first, merged within 45 minutes: FastAPI, in-memory double-entry ledger seeded from `data/demo/bank.yaml`, API as in §5.6, Dockerfile. Tests: idempotent replay, lookup by key, stable event IDs.
- `apps/dashboard`: FastAPI backend and one static page (plain JavaScript, 1 s polling, no build step). A `DataSource` with two implementations: `fixture` (JSON files) and `agentdb` (`deal.list`, `deal.read`, `ledger.balances`, plus the bank's `/accounts`). Views: deal list; deal page with the ten-step strip from SPEC §13 (red cross at step 8 on a reject, green again after redelivery), event timeline, verdicts per delivery, balances.
- Done when: sim bank tests pass; the dashboard renders both fixture runs, then live data after G4.
- Not now: login, any write action, a dispute view.

### E Agents

Build with the cogit.foundation skills (Specify → Build → Run), behaviour from SPEC §8, in
this order: evaluator, seller, buyer. Every agent ignores unknown message types and is
idempotent on `message_id`.

- `evaluator-agent`: on `evaluation_request`, fetch the artifact, run the check named by `evaluator_id`, send one `verdict`.
- `seller-agent`: `publish_catalog` from `SELLER_OFFERS_FILE`. On a relayed `service_request`, send `quote`. On `terms_proposed`, accept if it matches the quote. On `funding_confirmed`, wait `SELLER_DELAY_S`, build the zip, upload it and send `delivery` attempt 1. With `SELLER_MODE=broken`, attempt 1 lacks `summary.json`. On a `decision` of `reject` with attempts left, redeliver complete.
- `buyer-agent`: `start_purchase` calls `sellers.list` and `catalog.read`, then sends `service_request`. On `terms_proposed`, accept if the price is within `max_price_minor` and an evaluator is named. On `payment_request`, `POST /transfers` with `Idempotency-Key: pay:<deal_id>`.
- Done when: each agent passes `cogit agent validate` and `cogit test` with handler tests on fake ports; all three are installed after G1.
- Not now: LLM calls, declines, disputes, negotiation.

### F Port (optional)

- Start after A's first push; it never blocks anyone.
- New worktrees of `cogit-agent-sdk` and `cogit-runtime` on `feature/agent-messaging`. Put `MessagingSeams` next to `DatabaseSeams` in the SDK; signing and the delivery loop go into the runtime; the two routes only if time remains.
- Done when: A's contract tests pass unchanged against it.
- G6: swap only if those tests pass and one live happy path runs on it. Otherwise stay on the shim and record the port as not done in the README.

## 7. If blocked

| Problem | Fallback |
| --- | --- |
| Docker does not start | The human resolves the file lock. Lanes keep building on fakes; nothing in Wave 1 except G1 and G3 needs Docker |
| Exports cannot read the calling installation (SPEC §17, question 2) | Pass `installation_id` as an argument and trust it; record it as a known gap |
| No quick read-only principal (SPEC §17, question 3) | The dashboard uses the operator principal, queries only |
| The artifact API costs more than 30 minutes | The deliverable is a file in a shared `var/artifacts/` folder and `artifact_id` is its name; digest and size are still checked |
| G1 slips past 2:00 | Lane B's agent joins L0 on the environment; B's DDL waits |
| A lane finishes early | Tell the human. Next jobs in order: end-to-end fixtures for L0, dashboard polish, then the first Out rows |

## 8. Start

```powershell
cd C:\ai\_experiments\agentic-commerce
git switch -c demo docs/spec-review-fixes
git add PARALLEL-PLAN.md
git commit -m "docs(plan): add parallel build plan for the demo"
# L0 session runs Wave 0 and commits, then:
foreach ($l in 'messaging','modules','escrow','apps','agents') {
  git worktree add "..\agentic-commerce-wt\$l" -b "lane/$l" demo
}
```

Open one Claude Code session per worktree (L0 in the main checkout) and paste, with the lane
name filled in:

> You are lane **A Messaging** in PARALLEL-PLAN.md. Read SPEC.md, then PARALLEL-PLAN.md §4
> (rules), §5 (contracts) and your brief in §6. Work only in your own paths, on your branch,
> in this worktree. Start with the first item of your brief. Stop and report when your "Done
> when" checks pass or when you are blocked.

Start order: L0, then A, B and C (critical path), then D and E, then F once A's first push is
merged. Worktrees share one repository, so L0 merges with `git merge lane/<name>` and lanes
pick up changes with `git merge demo`; nothing needs pushing until the end.
