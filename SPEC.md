# Spec: Agentic Commerce escrow (`cogit-finance`)

Status: product specification, revision 2 (after implementation-readiness review). No code yet.
Date: 2026-11-27.

Related material in this repository: [ALICE-BOB-PLAN.md](ALICE-BOB-PLAN.md) (Affinidi identity
slice), [WSL-HANDOVER.md](WSL-HANDOVER.md) (machine setup). Background research:
[Agent Escrow Service: Research & Requirements](https://claude.ai/artifact/CZgH4hydAyPoUnaMv9WCdp).
This file is authoritative; where it and the research doc differ, this file wins.

## 1. Purpose

Companies that have never worked together let their agents trade services. An escrow
provider (E) holds the buyer's money, has independent evaluators check the delivery, then
pays the seller or refunds the buyer. An operator such as a coworking campus runs E for its
resident companies on a licensed partner's payment licence.

The first release is a demo. A buyer agent and a seller agent at one operator complete a
deal from discovery to payout on a simulated bank, with every step recorded in AgentDb.

## 2. Decisions

| Topic | Decision |
| --- | --- |
| Escrow package name | `cogit-finance` |
| Where escrow state lives | With the escrow provider, in AgentDb |
| Test topology | One shared AgentDb, one tenant, four installations (buyer, seller, evaluator, E), each with its own DID |
| Messaging | A portable messaging contract in `cogit-agent-sdk`, implemented by an extension of `cogit-runtime`, both in their own worktrees, plus a simple message queue module in AgentDb |
| Message types | A generic, immutable type registry in the messaging module; `cogit-finance` registers its `finance.*` types |
| State-transition checks | Business rules in E's code; AgentDb enforces append-only order and the expected head atomically |
| Catalog | Tables in an AgentDb module; works when empty |
| Evaluators | Agents, reached through messaging |
| Payment adapter | Part of `cogit-finance` |
| Rail priority | Simulated bank for the demo, then SEPA, then cards; on-chain last |
| Identity | A local `did:key` per agent is mandatory. Affinidi is optional and kept separate ([ALICE-BOB-PLAN.md](ALICE-BOB-PLAN.md)) |
| Dashboard data | Authenticated module queries under a read-only operator identity; no direct SQL, no worker credentials |
| Messaging module home | This repository first; it may move to `agent-db/modules` once proven |
| Operator details (e.g. Delta) | A config YAML at deploy time, not code |
| Company names and offers | Data, added at the end |
| Agents | Full Cogit resident agents built with the cogit.foundation skills. Their full specs come later; §8 fixes the minimal demo behaviour the protocol depends on |

## 3. Roles

| Role | Who | Does |
| --- | --- | --- |
| Operator | e.g. a coworking campus | Deploys E, onboards companies, connects evaluators, sets fees, rules on disputes |
| E | `cogit-finance` agent | Runs deals, requests funding, sends deliveries to evaluators, pays out or refunds, signs receipts |
| Buyer agent | Agent of a buyer company | Finds offers, requests, accepts terms, funds its own deal |
| Seller agent | Agent of a seller company | Publishes offers, quotes, delivers |
| Evaluator agent | Operator or a third party | Returns a signed verdict on one delivery |

Three rules hold everywhere. Buyers fund their own deals, but only E disburses escrowed money.
Only evaluators judge deliveries. Buyer and seller agents act only by sending signed messages.

## 4. Where the pieces live

| Piece | Location | Kind |
| --- | --- | --- |
| Escrow agent, AgentDb modules, demo agents, demo apps, config schema, deployment | This repository | Source |
| Portable messaging contract (`MessagingSeams`) | `cogit-agent-sdk` worktree, branch `feature/agent-messaging` | Framework change |
| Messaging implementation: signing, delivery loop, routes | `cogit-runtime` worktree, branch `feature/agent-messaging` | Framework change |
| Module tables and data | The shared AgentDb deployment, installed into the tenant | Runtime state |
| Operator config (e.g. Delta) | Next to the deployment, outside version control | Configuration |

The SDK owns the contract and the Runtime implements it, as the Cogit ownership guide
requires. The SDK's existing `DatabaseSeams` (`module_query`, `module_command`) is the pattern
to follow.

## 5. Deal lifecycle

### 5.1 States

`REQUESTED`, `QUOTED`, `ACCEPTED`, `FUNDING_REQUESTED`, `FUNDED`, `DELIVERED`, `EVALUATING`,
`APPROVED`, `REJECTED`, `RELEASING`, `REFUNDING`, `DISPUTED`; terminal: `SETTLED`, `REFUNDED`,
`DECLINED`, `EXPIRED`, `CANCELLED`.

### 5.2 Transitions (authoritative)

| From | Trigger | Actor | Guard | To |
| --- | --- | --- | --- | --- |
| none | `service_request` | buyer | Buyer org registered with role buyer; offer active; `max_price` ≥ offer price; within the buyer's spending limit | `REQUESTED` |
| `REQUESTED` | `quote` | seller | Seller owns the offer; every named evaluator registered and independent of both parties | `QUOTED`; E then sends `terms_proposed` |
| `REQUESTED`, `QUOTED` | `decline` | buyer or seller | none | `DECLINED` |
| `REQUESTED` | `quote_ttl` passes | E timer | none | `EXPIRED` |
| `QUOTED` | `valid_until` passes | E timer | none | `EXPIRED` |
| `QUOTED` | `accept_terms` | buyer, seller | `terms_hash` equals the proposed terms; once per party | `QUOTED` |
| `QUOTED` | both parties accepted | E | none | `ACCEPTED` (`terms_countersigned`), then at once `FUNDING_REQUESTED` (`payment_request`) |
| `REQUESTED` … `FUNDING_REQUESTED` | `cancel` | buyer | No credit received for the deal | `CANCELLED` |
| `FUNDING_REQUESTED` | Bank credit with the deal reference and the exact price | bank, via E | none | `FUNDED` |
| `FUNDING_REQUESTED` | `funding_due_by` passes | E timer | none | `CANCELLED` |
| `FUNDED` | `delivery` | seller | `attempt` = 1; before `delivery_deadline` | `DELIVERED` |
| `FUNDED` | `delivery_deadline` passes | E timer | none | `REFUNDING` |
| `DELIVERED` | E sends an `evaluation_request` to each named evaluator | E | none | `EVALUATING` |
| `EVALUATING` | `verdict` | evaluator | Correlates with the current delivery (§9) | Stays, or `APPROVED` / `REJECTED` once the policy decides |
| `EVALUATING` | `respond_by` passes after one re-send | E timer | none | `DISPUTED` (reason `evaluator_unavailable`) |
| `APPROVED` | E prepares payout and fee intents | E | none | `RELEASING` |
| `REJECTED` | `delivery` | seller | `attempts_left` > 0 and before `rework_deadline` | `DELIVERED` |
| `REJECTED` | `dispute` | buyer or seller | Within `dispute_window` | `DISPUTED` |
| `REJECTED` | No redelivery possible and `dispute_window` passed without dispute | E timer | none | `REFUNDING` |
| `DISPUTED` | `ruling` (release or refund) | operator, via E | none | `RELEASING` or `REFUNDING` |
| `RELEASING` | Bank confirms the payout intent | bank, via E | none | `SETTLED` |
| `REFUNDING` | Bank confirms the refund intent | bank, via E | none | `REFUNDED` |
| `SETTLED`, `REFUNDED` | E sends `receipt` | E | none | unchanged (terminal) |

Any message not allowed by this table is rejected with a reason and changes nothing.

### 5.3 Timers and precedence

- Timers are frozen into the deal terms from the operator defaults: `quote_ttl_s`, `funding_due_s`, `delivery_time_s` (from the offer), `rework_window_s`, `dispute_window_s`, `evaluator_respond_s`.
- `rework_deadline` = min(`delivery_deadline`, rejection time + `rework_window_s`). `max_attempts` is in the acceptance spec.
- Approval is final. There is no dispute after `APPROVED`, so payout and dispute can never race.
- A dispute raised in `REJECTED` stops the rework and refund timers until the ruling.
- Payout and refund exclude each other: the state machine allows only one of `RELEASING` or `REFUNDING`, and the deals module allows one active disbursement intent per deal (§10).
- E's `tick` action fires timers. A timer that fires twice is harmless because transitions are idempotent (§7).

## 6. Message envelope and authorization

### 6.1 Envelope

Every message is one signed envelope:

| Field | Meaning |
| --- | --- |
| `envelope_version` | `1` |
| `message_id` | UUID chosen by the sender; globally unique |
| `type_key`, `type_version` | Registered message type, e.g. `finance.quote` / `1` |
| `sender_did`, `recipient_did` | Agent DIDs |
| `conversation_id` | The deal ID for finance messages |
| `causation_id` | The `message_id` this message answers, or null |
| `created_at` | UTC timestamp |
| `body` | Validated against the registered schema for `(type_key, type_version)` |
| `signature` | Ed25519 by `sender_did` over the canonical bytes of all fields above |

Canonical bytes are UTF-8 JSON with sorted keys and no insignificant whitespace. Finance
bodies use integers only (money in minor units, §10), so there are no floating-point values.

The type registry is immutable per `(type_key, type_version)`. Registering identical bytes
again is a no-op; different bytes are a conflict. A new schema means a new version, so old
signed messages stay verifiable. Schemas must use AgentDb's supported assertion dialect
(`type`, `properties`, `required`, `additionalProperties: false`, `items`, `enum`,
`minLength`, `maxLength`, `minimum`, `maximum`, `minItems`, `maxItems`, `description`,
nullable unions); anything else is refused at registration.

### 6.2 Who verifies what

| Check | Where |
| --- | --- |
| The claimed `sender_did` belongs to the calling installation | `message.send`, from AgentDb's authoritative module context. No cryptography in SQL |
| Body matches the registered schema | `message.send` |
| Signature is valid for `sender_did` | The recipient's runtime, before admitting the message as work. A bad signature is acknowledged as rejected (`bad_signature`) |
| Signature, actor role and transition guard | E, again, before recording a deal event |

E stores every accepted envelope verbatim, signature included, in the deal log.

### 6.3 Relaying

E never signs in another party's name. To pass a message on, E sends its own envelope whose
body carries the original signed envelope (`relayed`) plus the deal head (`deal_id`, `seq`,
`state`). The recipient verifies both signatures.

### 6.4 Replay

`message_id` is unique in the queue. The recipient's runtime rejects envelopes older than
24 hours or more than 2 minutes in the future. E de-duplicates by `source_message_id` (§7).

### 6.5 Access rules in the shared tenant

The module context gives each export the calling installation. Agent DIDs are bound to
installations in `agent_identities` (§11.1); E's installation ID and the operator principal
are module settings fixed at installation.

| Export | Allowed caller |
| --- | --- |
| `message.send` | An installation, for its own DIDs only |
| `message.claim`, `message.ack`, `message.release` | The recipient DID's installation only |
| `conversation.read` | Installations whose DIDs appear in the conversation, and the read-only operator identity |
| `catalog.publish` | The seller org's own installation, for that org's offers only |
| `sellers.list`, `catalog.read`, `evaluators.list` | Any installation in the tenant, and the read-only operator identity |
| `company.upsert`, `identity.register`, `evaluator.upsert` | The operator principal |
| `type.register` | E's installation, for the `finance.*` namespace |
| All `cogit-finance-deals` commands | E's installation only |
| `deal.read`, `deal.list`, `ledger.balances` | E, the deal's buyer and seller installations, and the read-only operator identity |

## 7. Delivery and recovery

Delivery is at-least-once. Processing is made exactly-once in effect by idempotency, using
AgentDb's own admission and command replay rather than new leases.

1. **Claim.** The runtime's delivery loop calls `message.claim` for its DIDs. Claimed messages
   become `claimed`. A message claimed but not acknowledged within `redeliver_after_s` can be
   claimed again.
2. **Admit.** The loop admits each message as work with the stable idempotency key
   `msg:<message_id>` and records the run ID on the message. AgentDb returns the same run for
   a repeated admission, so a crash between claim and admission creates no duplicate run.
3. **Process.** E records each accepted message with `deal.commit`, whose idempotency key is
   `evt:<message_id>`. `deal_events.source_message_id` is unique, so a message processed twice
   yields one event and the original result.
4. **Outbox.** `deal.commit` writes the deal event and the outgoing envelopes, already signed
   by E, in one transaction (the outbox). E then sends each outbox entry with `message.send`,
   idempotency key `out:<outbox_id>`, and marks it sent. `tick` re-sends pending entries, so a
   crash after the commit never leaves a committed state without its notifications.
5. **Acknowledge.** After the run settles, the loop acknowledges `processed`, or `rejected`
   with a reason. A retryable failure calls `message.release` with a delay. After
   `max_delivery_attempts` the message is `dead` and visible to the operator.

## 8. Minimal demo behaviour of each agent

Full agent specs come later. The protocol and the end-to-end tests rely on this
deterministic behaviour.

| Agent | Behaviour |
| --- | --- |
| `buyer-agent` | Configured with a category and a `max_price`. Lists sellers in that category (sorted by `org_id`), reads the first seller's catalog, picks the first active offer at or under `max_price` and sends `service_request` with fixed inputs. Accepts terms when the price ≤ `max_price` and at least one evaluator is named. Pays the `payment_request` at the sim bank with the given reference. Never disputes |
| `seller-agent` | Publishes its offers from a data file at start (`catalog.publish`). Quotes the catalog price, a deadline of now + `delivery_time_s` and the offer's default acceptance spec. Accepts terms that match its quote. After `funding_confirmed`, waits a configured delay, uploads the deliverable (prepared or simplest real) and sends `delivery`. In broken mode, the first attempt omits one required file and the redelivery is complete |
| `evaluator-agent` | On `evaluation_request`, runs deterministic checks: the artifact's digest and size match, the required files are present, and delivery was before the deadline. Returns one signed `verdict` |
| E | As specified in §5–§10 |

## 9. Evaluation

### 9.1 Deliveries

- `delivery_id` = `<deal_id>:d<attempt>`.
- The deliverable is an AgentDb artifact uploaded by the seller. The reference is `artifact_id`, `sha256`, `byte_length` and `media_type`. E checks that the artifact exists and matches before evaluation.
- A new delivery supersedes the previous one; verdicts for a superseded delivery have no effect.

### 9.2 Requests and verdicts

- `evaluation_request_id` = `<delivery_id>:<evaluator_id>@<evaluator_version>`.
- A request carries `terms_hash`, `delivery_id`, the artifact reference, the evaluator ID and version, the params from the acceptance spec, and `respond_by`.
- A verdict echoes `evaluation_request_id`, `terms_hash`, `delivery_id`, the artifact `sha256` and the evaluator ID and version. It is signed by the DID registered for that evaluator version, and its outcome is `pass`, `fail` or `error`.
- A **stale** verdict (another delivery, or after the decision) is acknowledged as rejected (`stale_verdict`) and changes nothing.
- A **duplicate** identical verdict is a no-op. A **conflicting** second verdict for the same request is rejected and flagged to the operator.

### 9.3 Policy

| Policy | Approve when | Reject when |
| --- | --- | --- |
| `all` | Every named evaluator passes | Any evaluator fails or returns `error` |
| `any` | One evaluator passes | Every evaluator has answered without a pass |
| `quorum k` | k evaluators pass | Enough have answered without a pass that k is unreachable |

E decides as soon as the outcome is certain. A missing verdict is re-requested once at
`respond_by`; if it is still missing, the deal goes to `DISPUTED` with reason
`evaluator_unavailable`, so infrastructure failure never moves money automatically.
Evaluators are free of charge in the demo.

## 10. Payments

### 10.1 Amounts and fees

- Money is an integer in minor units (`amount_minor`) plus `currency` (`EUR` only for now).
- The buyer pays exactly the price. The fee is taken from the seller's payout:
  `fee_minor = (price_minor × fee_bps + 5000) div 10000`, rounding half up to the cent.
  `payout_minor = price_minor − fee_minor`.
- Partial settlement is out of scope: a ruling is release or refund, never a split.

### 10.2 Funding

- `payment_request` names E's escrow IBAN, the exact amount and a unique deal reference.
- The sim bank reports every credit with its own event ID. E records it once (`bank_credits`, unique by event ID).
- A credit with the deal reference and the exact amount, while the deal is `FUNDING_REQUESTED`, funds the deal. Any other credit (wrong amount, unknown reference, duplicate, late) is returned to its sender in full through a `return_unmatched` intent.

### 10.3 Disbursement

Every outgoing transfer is a durable payment intent.

1. **Prepare.** The intent (`payout`, `fee`, `refund` or `return_unmatched`) is committed together with the deal event that requires it. At most one active `payout` or `refund` intent exists per deal (partial unique index).
2. **Submit.** E calls the bank with `Idempotency-Key: <intent_id>`; the intent becomes `submitted`.
3. **Confirm.** On the bank's answer, E marks the intent `confirmed` and writes the ledger posting, unique by `intent_id`, in one command.
4. **Reconcile.** On timeout or an unclear answer the intent is `unknown`. `tick` looks the transfer up at the bank by idempotency key, then confirms it, or re-submits under the same key. The bank de-duplicates, so a re-submission never pays twice.

The `sim-bank` app must therefore support idempotency keys, lookup by key and credit events
with stable IDs. A real partner bank will be chosen for those same three properties.

## 11. Components

Each folder under `packages/`, `modules/`, `agents/` and `apps/` is self-contained, like a
`cogit-library` package: its own manifest (`pyproject.toml` or `manifest.json`), `src/` or
`migrations/`, `tests/` and `README.md`.

### 11.1 `modules/cogit-messaging` (AgentDb module)

| Table | Columns |
| --- | --- |
| `agent_identities` | `did` (PK), `installation_id`, `org_id`, `role` (buyer, seller, evaluator, escrow), `active`, `registered_at` |
| `message_types` | `type_key` + `type_version` (PK), `json_schema`, `registered_by`, `registered_at` |
| `messages` | `message_id` (PK), `conversation_id`, `causation_id`, `type_key`, `type_version`, `sender_did`, `recipient_did`, `envelope` (verbatim, signed), `status` (`queued`, `claimed`, `processed`, `rejected`, `dead`), `attempts`, `claimed_at`, `admission_key`, `run_id`, `reason`, `created_at`, `acked_at` |

Exports: `identity.register`, `identity.resolve`, `type.register`, `message.send`,
`message.claim`, `message.ack`, `message.release`, `conversation.read`. The module knows
nothing about escrow.

### 11.2 Messaging contract and runtime extension (framework worktrees)

| Part | Behaviour |
| --- | --- |
| SDK `MessagingSeams` | `send(type_key, type_version, recipient_did, conversation_id, body, causation_id=None)`, returning the `message_id`. The inbound message is given to the agent as typed work input |
| Runtime: signing | Signs with the agent's key: a local `did:key` file, or an Affinidi-managed DID if the identity slice works |
| Runtime: delivery loop | Claim, admit, acknowledge and release as in §7 |
| Runtime: routes | `GET /messages/inbox`, `GET /conversations/{id}` for inspection; sending stays inside the runtime |

### 11.3 `modules/cogit-finance-catalog` (AgentDb module)

| Table | Columns |
| --- | --- |
| `companies` | `org_id` (PK), `legal_name`, `register_id`, `address`, `roles` (buyer, seller), `categories`, `iban`, `kyb_verified`, `kyb_verified_by`, `spending_limit_minor` |
| `offers` | `seller_org_id` + `offer_id` (PK), `title`, `description`, `category`, `price_minor`, `currency`, `delivery_time_s`, `input_schema`, `deliverable` (media type, required files), `default_acceptance`, `active` |
| `evaluators` | `evaluator_id` + `version` (PK), `org_id`, `did`, `description`, `deterministic`, `accepts`, `params_schema` |

Exports: `sellers.list` (optional category), `catalog.read`, `evaluators.list`,
`catalog.publish`, `company.upsert`, `evaluator.upsert`. Adding a company, offer or evaluator
is a data change only, and an empty catalog returns empty lists. The operator's company data
is imported through `company.upsert`.

### 11.4 `modules/cogit-finance-deals` (AgentDb module)

| Table | Columns |
| --- | --- |
| `deals` | `deal_id` (PK), `buyer_org_id`, `seller_org_id`, `offer_id`, `state`, `head_seq`, `head_hash`, `terms`, `terms_hash`, `created_at`, `updated_at` |
| `deal_events` | `deal_id` + `seq` (PK), `prev_hash`, `hash` (unique), `event_type`, `source_message_id` (unique, nullable), `actor_did`, `body` (incl. the verbatim envelope), `state_after`, `recorded_at` |
| `outbox` | `outbox_id` (PK), `deal_id`, `seq`, `envelope` (signed by E), `status` (`pending`, `sent`), `sent_at` |
| `deliveries` | `delivery_id` (PK), `deal_id`, `attempt`, `artifact_id`, `sha256`, `byte_length`, `media_type`, `delivered_at`, `status` |
| `evaluations` | `evaluation_request_id` (PK), `delivery_id`, `evaluator_id`, `evaluator_version`, `evaluator_did`, `respond_by`, `resends`, `verdict_message_id`, `outcome` |
| `payment_intents` | `intent_id` (PK), `deal_id`, `kind`, `amount_minor`, `currency`, `to_iban`, `status` (`prepared`, `submitted`, `unknown`, `confirmed`, `failed`), `bank_ref`, `created_at`, `updated_at` |
| `bank_credits` | `bank_event_id` (PK), `deal_id`, `reference`, `amount_minor`, `from_iban`, `received_at`, `disposition` (`funded`, `returned`) |
| `ledger_postings` | `posting_id` (PK), `deal_id`, `source_id` (intent or credit, unique), `account` (`held`, `seller`, `fee`, `buyer_refund`, `returned`), `amount_minor` (signed), `created_at` |

Exports: `deal.commit` (expected head, new event, outbox entries and any delivery,
evaluation, intent or credit rows, all in one transaction), `outbox.pending`,
`outbox.mark_sent`, `intent.update`, `intents.unresolved`, `deal.read`, `deal.list`,
`ledger.balances`. The module enforces the hash chain, the expected head and the uniqueness
constraints; E decides which transitions are legal.

### 11.5 `packages/cogit-finance` (E)

Created with `cogit init`, following the cogit.foundation Build skill: the generated agent
class and entrypoint stay in place, and business behaviour goes into the generated domain,
schema and operation files.

| Part | Content |
| --- | --- |
| Domain | The §5 transition table as data, guards, deal-terms builder, fee calculation, verdict policy, timers, receipts |
| Actions | `handle_message` (entry point for every inbound `finance.*` message), `tick` (timers, outbox re-send, payment reconciliation), `resolve_dispute` (operator) |
| Payment adapter | One interface; `sim` calls `apps/sim-bank`, `sepa` calls the partner bank API (later), `card` (later). Implements §10.3 |
| Evaluator dispatch | Sends `evaluation_request` messages, correlates verdicts (§9) and refuses evaluators from either party's company |
| Database packages | `cogit-messaging`, `cogit-finance-catalog`, `cogit-finance-deals` |
| Config | Reads the operator YAML from a path given by environment variable |

### 11.6 Demo apps (`apps/`)

| App | Purpose |
| --- | --- |
| `sim-bank` | Accounts by IBAN; transfers with a reference and an idempotency key; lookup by key; credit events with stable IDs. It stands in for the partner bank's API |
| `dashboard` | Read-only view of deals, events, verdicts and balances, through module queries under the read-only operator identity |

### 11.7 Identity (`identity/`)

The Affinidi DID Auth slice described in [ALICE-BOB-PLAN.md](ALICE-BOB-PLAN.md), kept separate
and optional. The demo runs on local `did:key` identities. If the slice works, the runtime
can use the gateway-verified DID as the sender identity; nothing else changes.

## 12. Message types

Registered in `cogit-messaging` by `cogit-finance`, all version `1`. Deal messages go to E,
which records them and relays or answers. Discovery uses catalog queries, not messages.

| Type | From → to |
| --- | --- |
| `finance.service_request` | buyer → E, relayed to seller |
| `finance.quote` | seller → E, relayed to buyer |
| `finance.decline` | buyer or seller → E, relayed |
| `finance.terms_proposed` | E → buyer, seller |
| `finance.accept_terms` | buyer, seller → E |
| `finance.terms_countersigned` | E → buyer, seller |
| `finance.payment_request` | E → buyer |
| `finance.funding_confirmed` | E → buyer, seller |
| `finance.delivery` | seller → E, relayed to buyer |
| `finance.evaluation_request` | E → evaluator |
| `finance.verdict` | evaluator → E |
| `finance.decision` | E → buyer, seller |
| `finance.dispute` | buyer or seller → E |
| `finance.ruling` | operator → E |
| `finance.cancel` | buyer → E |
| `finance.payout_confirmed`, `finance.refund_confirmed` | E → buyer, seller |
| `finance.receipt` | E → buyer, seller |

## 13. Demo scenario and acceptance

Ten steps: discover, catalog, request, confirm, **fund**, work, deliver, evaluate, approve,
pay out. Fund is its own step: it is when the buyer's money is locked and the seller can start.

### 13.1 Expected happy-path deal events

| Seq | Event | Actor |
| --- | --- | --- |
| 1 | `service_request` | buyer |
| 2 | `quote` | seller |
| 3 | `terms_proposed` | E |
| 4, 5 | `accept_terms` (either order) | buyer, seller |
| 6 | `terms_countersigned` | E |
| 7 | `payment_request` | E |
| 8 | `funding_received` | E (bank credit) |
| 9 | `delivery` | seller |
| 10 | `evaluation_requested` (one request per evaluator) | E |
| 11–13 | `verdict` ×3 (any order) | evaluators |
| 14 | `decision` (approve) | E |
| 15 | `payout_submitted` (payout and fee intents) | E |
| 16 | `payout_confirmed` | E |
| 17 | `receipt` | E |

Every outgoing message carries a `causation_id` that links it to the message or event that
caused it. Discovery (steps 1–2 of the scenario) happens before a deal exists; its evidence is
the buyer run's recorded `sellers.list` and `catalog.read` results.

### 13.2 Acceptance tests

- [ ] All four agents run as Cogit resident agents against one AgentDb and pass `cogit agent validate` and `cogit test`.
- [ ] The happy path produces exactly the §13.1 event sequence and reaches `SETTLED`.
- [ ] Balances: buyer −price; held +price, then 0; seller +(price − fee); fees +fee.
- [ ] Broken delivery: rejected, redelivered, then settled. A late verdict for the first delivery has no effect.
- [ ] Evaluator does not answer: one re-request, then `DISPUTED`; no money moves.
- [ ] No delivery by the deadline: refunded.
- [ ] Authorization: sending as another installation's DID, reading another DID's inbox, publishing another org's catalog and calling a deals command from a non-E installation are all refused.
- [ ] Duplicates: the same message delivered twice yields one deal event; a duplicate bank credit is returned.
- [ ] Crashes around a payout (before submit, after the bank commits but before the answer, after the answer but before the ledger posting) each end with exactly one transfer and one posting.
- [ ] A message illegal in the current state is rejected and changes nothing.
- [ ] An evaluator from the buyer's or seller's company is refused.
- [ ] With an empty catalog the board returns empty lists; adding a company, offer or evaluator takes no code change.

## 14. Operator configuration

One YAML file per deployment, validated against `config/operator.schema.json`:

```yaml
operator:
  name: Example Campus
  legal_name: Example Campus GmbH
  address: Example Street 1, 10115 Berlin
  contact: escrow@example.invalid
escrow:
  fee_bps: 100
  currency: EUR
  timers: {quote_ttl_s: 600, funding_due_s: 900, rework_window_s: 600, dispute_window_s: 3600, evaluator_respond_s: 60}
  max_delivery_attempts: 5
rail:
  kind: sim                        # sim | sepa | card
  escrow_iban: DE00EXAMPLE0000000001
  fee_iban: DE00EXAMPLE0000000002
  sim: {base_url: http://sim-bank:8080}
evaluators:
  allow: []                        # evaluator ids the operator accepts; empty = any registered
```

## 15. Prerequisites and build order

### 15.1 Prerequisites

- Docker's Linux engine running, restored as described in [WSL-HANDOVER.md](WSL-HANDOVER.md) without resetting or pruning existing containers and volumes.
- One pinned framework cohort: Template 0.1.25 selects SDK 0.5.16, Runtime 0.3.31 and AgentDb client 0.2.13. Use its vendored wheels.
- Isolated worktrees for `cogit-agent-sdk` and `cogit-runtime` (§4). The existing checkouts have unrelated local changes, which stay untouched.

### 15.2 Milestones

| # | Milestone | Done when |
| --- | --- | --- |
| M0 | Environment | Docker reachable from WSL; cohort pinned; worktrees created |
| M1 | Integration proof | One module installed into the tenant; one signed message sent, delivered, admitted and acknowledged, and still processed exactly once after the worker is killed mid-delivery |
| M2 | Finance domain and sim bank | §5 table, fees, policy and payment intents unit-tested in `cogit-finance`; `sim-bank` supports idempotency, lookup and credit events |
| M3 | Messaging integration | All three modules installed; the SDK seam and runtime delivery loop pass §6–§7 tests |
| M4 | Happy path | Four agents (built with the foundation skills, about 15 minutes each by the operator's estimate) complete §13.1 |
| M5 | Recovery and rejection | All §13.2 tests pass |
| M6 | Dashboard | The demo is visible end to end |
| M7 | Affinidi (optional) | The identity slice works and is wired in, or is recorded as skipped |

## 16. Out of scope for the first release

Real SEPA and cards, on-chain rails, messaging between separate AgentDb deployments, LLM
evaluators, a dispute UI, consumers, real KYB checks, negotiation beyond one quote, split
settlements, evaluator fees, and production key management.

## 17. Open questions

1. **Artifact access:** in one tenant, AgentDb artifacts are readable tenant-wide. Is that acceptable for the demo, and what per-installation grant should production use?
2. **Module context:** confirm in M1 that module exports can read the calling installation from AgentDb's module context, as §6.5 assumes.
3. **Read-only operator identity:** confirm in M1 how to create a principal that may call queries but no commands.
4. **Partner bank:** which licensed partner offers idempotency keys, lookup by key and stable credit event IDs for the SEPA rail.
