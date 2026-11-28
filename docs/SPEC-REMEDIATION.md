# SPEC remediation — local execution evidence

This pass started from local `8cfe112` on `docs/spec-review-fixes`, not the
assessment's GitHub `568dfbd`. The checkout already contained extensive modified
and untracked work. It was preserved; no service or database was reset.

## Implemented

- Expiry, buyer cancellation, decline, delivery/rework deadlines, rejection
  refunds, disputes and signed operator release/refund rulings. A refund returns
  to the funding account, not a subsequently edited company IBAN.
- One evaluator re-request for error/timeout, followed by `DISPUTED` with
  `evaluator_unavailable`. Retries correlate through their outgoing message ID;
  old responses cannot consume the retry. Evaluation failure never disburses.
- Every credit is recorded once. Wrong amounts, unknown references, second
  transfers and late credits prepare full `return_unmatched` intents. Re-reading
  the **same bank event** is a no-op, not another incoming transfer.
- `submitted`/`unknown` transfers are looked up before resubmission under their
  original intent ID. Confirmation and ledger postings remain atomic.
- Quorum policies (`quorum 1` … `quorum 16`). Existing v1 message schemas stay
  unchanged; `finance.quote` and `finance.terms_proposed` v2 add quorum.
- Participant-scoped deal, ledger and conversation reads in reference/native
  modules; separate deployment `viewer` credentials for dashboard queries and
  `member` credentials for scheduler admission. No administrator token is passed
  to the dashboard client by `scripts/run_agentdb.py`.
- Failed scheduler slots are archived durably and released so subsequent inbox
  drains/ticks continue. Signature admission now enforces the 24-hour/2-minute
  freshness boundaries while archival signature verification remains possible.
- Native module version **1.1.0** appends `000100__spec_recovery.sql`; the local
  pre-change 1.0.0 migration bytes are retained rather than overwritten.

Operator rulings require `operator.ruling_did` in the operator YAML. Without it,
all rulings fail closed. `resolve_dispute` takes a signed `finance.ruling`
envelope with `outcome: release|refund` and a nonempty `reason`. It is not a UI.

For credits without a known deal, `credit.return` atomically writes the bank
credit, intent and held posting with a null deal ID. Known-deal returns use
`deal.commit` and a `credit_returned` event without changing lifecycle state.
`credit.read` and `intents.unresolved` are escrow-only exports.

## Verification

On Windows, using the available pinned-cohort test environment:

```text
COMMERCE_SQL_TEST_DSN=postgresql://postgres@127.0.0.1:15439/postgres
python scripts/check_commerce.py --require-native
pyright --project pyright-commerce.json --pythonpath <cohort-python>
ruff check packages/cogit-finance/src/cogit_finance/escrow
ruff format --check packages/cogit-finance/src/cogit_finance/escrow
node scripts/check_agentdb_modules.mjs
```

- 500 acceptance tests passed, including tests executing the actual native
  dispatchers in a disposable PostgreSQL 17 container.
- 29 additional finance contract, typed-action and manifest tests passed.
- Scoped Pyright: zero errors. Escrow Ruff lint/format checks passed.
- Wheels built for finance, deals, messaging module, messaging shim, seams and
  dashboard. AgentDb module-kit accepted all three native bundles.
- Native tests cover the exact 17-event happy path, broken delivery/stale verdict,
  refunds, unavailable evaluators, unknown credits, participant authorization and
  payout failures before submission, after bank commit, and before ledger write.
- `.github/workflows/commerce.yml` adds these source-level checks and mandatory
  PostgreSQL tests. The workflow has not been executed on GitHub.

## Still required — not full SPEC compliance

1. Native `drain_inbox` still processes a batch in one admitted run. Replace this
   with per-message admission under `msg:<message_id>` and durable run-ID binding,
   including the retry/acknowledgement lifecycle. Freshness checks alone do not
   complete §7 or M1.
2. Run the four installed Cogit workers against AgentDb's actual fenced dispatch
   API, kill/restart workers at each claim/admission/outbox/payment boundary, and
   prove persistence. PostgreSQL dispatcher tests and in-process agent actions do
   **not** establish this. No new four-worker deployment was started in this pass.
3. Validate a live deployment upgrade, including module-settings revisions,
   principal bindings and rebuilt cohort receipts. The existing deployment
   helper still assumes first-time settings (`expectedRevision: 0`); do not use it
   blindly on an already configured tenant. Do not reset volumes to bypass this.

The domain/reference fixes are committed separately. Native runtime, deployment,
authorization integration and CI edits that overlap or depend on pre-existing
uncommitted work remain in the working tree for integration; they are not a
published release. No push, PR or merge was performed.
