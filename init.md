# Next-agent handover

Updated 2026-11-28. **`SPEC.md` is authoritative; full compliance is not yet proven.**
The requested publication packages the completed SPEC recovery work and this
handover. It does not declare the native deployment production-ready.

## Read first

1. [SPEC.md](SPEC.md), especially lifecycle, messaging/admission and acceptance.
2. [docs/SPEC-REMEDIATION.md](docs/SPEC-REMEDIATION.md): implementation decisions,
   historical evidence and the isolated publication checks.
3. [docs/AGENTDB-RUNTIME.md](docs/AGENTDB-RUNTIME.md): native launch/deployment.
4. [README.md](README.md) and [apps/dashboard/README.md](apps/dashboard/README.md):
   distinguish the local simulation from the native worker runtime.

Use Spec → Plan → Build → Evaluate → Test → Commit. Preserve existing work;
never reset databases, prune Docker, broadly stage files or weaken tests.

## What is implemented

- Escrow expiry, decline/cancellation, delivery/rework deadlines, refunds,
  disputes and signed operator release/refund rulings.
- One correlated evaluator retry; another error/timeout disputes the deal
  without disbursement. Old verdicts cannot satisfy the retry.
- Durable full returns of unmatched, incorrect, duplicate-transfer and late
  credits; replaying the same bank event does nothing.
- Ambiguous bank submissions are looked up before resubmitting the original
  intent ID. Transfer confirmation and ledger postings are atomic.
- Exact participant-DID authorization for deal/ledger/conversation reads;
  separate dashboard reader and scheduler credentials; failed scheduler slots
  are durably archived and released.
- Message freshness (24-hour age, 2-minute future allowance), separate from
  archival signature verification. Quorum 1–16 uses new v2 quote/terms schemas.
- Native module 1.1.0 append-only recovery migrations, synchronized actions and
  requirements, and mandatory PostgreSQL acceptance in GitHub Actions.

Keep these decisions: unknown credits do not invent deals; refunds use the
actual funding account; `operator.ruling_did` must be configured or rulings fail
closed; v1 contracts and published 1.0.0 migration bytes remain immutable.
`resolve_dispute` takes a signed `finance.ruling` envelope, not a UI command
that bypasses authentication.

## Next work, in order

1. **Per-message native admission.**
   `packages/cogit-finance-seams/src/cogit_finance_seams/inbox.py` still processes
   a batch inside one admitted drain run. Implement stable `msg:<message_id>`
   admission, persist its real run ID, and cover replay, acknowledgment,
   claim expiry and crash recovery. A nested step is not independent admission.
2. **Safe existing-tenant upgrades.**
   `scripts/agentdb_stack.mjs` still writes module settings with
   `expectedRevision: 0`. Read/reconcile actual settings revisions and principal
   bindings; test 1.0.0 → 1.1.0 against retained data. Never reset volumes to
   bypass revision checks. Confirm reader `viewer` and scheduler `member`
   behavior through the real API, including denial cases.
3. **Live four-worker acceptance.**
   Run all four installed Cogit workers against AgentDb's fenced API. Kill and
   restart at claim, admission, outbox, bank-submit, bank-confirm and ledger-write
   boundaries. Prove exactly-once monetary effects and continued processing.
   `scripts/verify_agentdb.py --restart` is a starting point, not the full matrix.
4. **Rebuild and verify the deployed artifacts.**
   This publication rebuilt seams 0.2.1 and messaging shim 0.2.2, refreshed all
   four vendored hashes/locks, and prepared worker cohorts. They were **not
   installed or live-validated** here. Bump shared versions before rebuilding
   changed source; verify the installed receipts, not just local wheels.

The lack of a dispute UI does not defer disputes, rulings, refunds or timers.
Do not confuse direct SQL tests/injected failures with fenced-worker recovery.

## Reproduce publication checks

The isolated publication tree passed **507 Python tests**, **18 Node tests**,
scoped Pyright, escrow Ruff, eleven wheel builds and all three module-kit bundle
checks. The Python suite includes native PostgreSQL, finance action/manifest and
source-to-vendored-wheel parity checks. No live deployment was started.

Linux / GitHub Actions setup:

```bash
bash scripts/dev-install.sh
uv pip install --python .venv/bin/python pytest-asyncio psycopg2-binary ruff pyright
# Point only at a disposable PostgreSQL 17 instance, never a production DB.
COMMERCE_SQL_TEST_DSN='postgresql://postgres:test-only@127.0.0.1:15439/postgres' \
  .venv/bin/python scripts/check_commerce.py --require-native
node --test apps/dashboard/tests/checkout-selection.test.mjs
.venv/bin/pyright --project pyright-commerce.json --pythonpath .venv/bin/python
.venv/bin/ruff check packages/cogit-finance/src/cogit_finance/escrow
.venv/bin/ruff format --check packages/cogit-finance/src/cogit_finance/escrow
node scripts/check_agentdb_modules.mjs /path/to/agent-db
```

On the original Windows host, the known test interpreter is
`C:/ai/_experiments/agentic-commerce/.local/publication-test-venv/Scripts/python.exe`.
AgentDb source is `C:/cogit/cogit-core/agent-db`. Module-kit needs its compiled
packages. The publication tests used a dedicated temporary PostgreSQL container
on loopback port 15439; recreate it if absent. Existing services were untouched.
New native stacks default to API port 18180; do not assume port 18080 is free.

## Git and local-state precautions

- Repository: `osnova-gmbh/agentic-commerce`; default branch: `main`.
  Publication branch: `fix/spec-recovery-handover`. Resolve its actual merge and
  CI state rather than assuming this document is a deployment receipt:
  `gh pr list --state all --head fix/spec-recovery-handover`, then
  `gh pr view <number> --json state,mergeCommit,statusCheckRollup`.
- Original commits `f88e8dc` and `6f92c8a` are preserved in the publication
  history, integrated with published baseline `568dfbd`.
- The primary checkout `C:/ai/_experiments/agentic-commerce` remains on local
  `docs/spec-review-fixes` at `6f92c8a959986f3d4c133f441ce6cb6ee8ce10b1`, with
  extensive pre-existing modified/untracked work. It is **not** the clean
  publication tree. API discovery/Boris, demo-funding, landing/film and skill
  edits were not swept into this PR. Some related work also exists on remote
  `docs/spec-review-fixes` / `feat/discoverable-commerce-api`; compare before
  integrating anything. Never force-push the divergent old branch.
- Task checkout: `C:/ai/_experiments/agentic-commerce/.local/spec-publication`.
  It is retained for the synchronized `main` after successful merge, rather than
  switching the dirty primary checkout. Before merge it holds the publication
  branch. Inspect `git worktree list --porcelain` for its current branch/HEAD.
  Its ignored `.state/agentdb/builds/` contains prepared cohort plans, not proof
  of deployment. Retain this checkout while primary work remains unresolved.
- Local evidence stays under the primary `.local/`: `spec-publication-*.log`,
  `spec-publication-wheels/`, `publish-baseline.patch`,
  `publish-baseline-status.txt`, plus the earlier `spec-fixes-baseline.patch`
  and `spec-fixes-before/`. Do not commit `.local/`, `.state/`, credentials or
  private identity material. A root `init.md` copy may be left in the primary
  checkout so its next agent sees this warning.

After publication, the fixed local recovery reference is
`recovery/worktrees/spec-recovery-handover-20261128`. Verify it with
`git rev-parse <reference>`; recreate the committed snapshot with
`git worktree add --detach <new-path> <reference>`. It does not back up ignored
state or the primary checkout's uncommitted work.
