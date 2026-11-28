# AgentDb commerce runtime

| Mode | Launcher | Storage and execution |
| --- | --- | --- |
| Local simulation | `python scripts/run_demo.py` | In-process agent cores, SQLite reference modules, simulated bank |
| AgentDb | `python scripts/run_agentdb.py up` | Native PostgreSQL modules, four external Cogit workers, durable run admission, simulated bank |

The AgentDb path is implemented separately from the running local simulation.
Building its packages is not proof of a healthy deployment. Native SQL execution
and restart acceptance require the live checks below. All funds are simulated.

**Current limitation:** the 1.1.0 recovery changes have source-level and native
PostgreSQL coverage, not complete four-worker crash/restart acceptance. Inbox
messages still share a drain run. The deployment helper still submits
`expectedRevision: 0` for module settings: do not rerun deployment blindly on an
already configured tenant or reset volumes to make it succeed. See [the next-agent
handover](../init.md) for the ordered completion work.

## Start

Use Python 3.11 or newer, Node 22, the Cogit CLI and a working Docker Desktop
Linux engine. The selected AgentDb source checkout needs its dependencies and
compiled packages, including `packages/deployment/dist/index.js`.

```powershell
python scripts/run_agentdb.py prepare
python scripts/run_agentdb.py up --agentdb-root C:/cogit/cogit-core/agent-db
```

`prepare` builds and hashes the native modules and worker cohorts without using
a server. `up` also installs the workers with Cogit, starts an isolated local
AgentDb stack, publishes four routes, installs their database dependencies,
binds their receipts, seeds the demo data, and starts the dashboard.
Dependency installation and initial Docker image builds may need downloads.

Open **http://127.0.0.1:8093/demo**. The simulation on port 8091 stays independent.
`/api/runtime` reports the actual worker processes; purchases are admitted through
AgentDb's `/v1/queries` API.

After a successful deployment:

```powershell
python scripts/run_agentdb.py serve
python scripts/run_agentdb.py status
```

The foreground launcher supervises its own workers and restarts one that exits.
Ctrl+C stops the launcher and its workers. Docker volumes are retained, and the
services use `unless-stopped`. The simulated bank's state belongs to the bank
process; keep that process running while restarting the AgentDb backend.

## Implementation

- `modules/*/agentdb` contains the native migrations and manifests.
  `scripts/build_agentdb_modules.py` builds them deterministically.
- The platform's closed schemas use a bounded JSON-string carrier. The adapter
  preserves the existing `ModulePort` API and signed message bodies. Native
  workers enable it with `COGIT_COMMERCE_NATIVE_MODULES=1`.
- Every exported function calls `core.require_module_context`. Domain checks
  restrict privileged writes to the configured operator/escrow identity.
  Rows include tenant IDs. Deal updates lock their head; native unique indexes
  enforce event, posting and active payment-intent uniqueness. Message claims
  use row locks with `SKIP LOCKED`.
- Root handlers accept only each agent's explicit commerce commands, retain the
  real run context, and invoke registered operations. Inbox drains validate
  signatures and use stable message acknowledgement keys.
- The scheduler saves admission keys before making HTTP calls. A restart or
  lost response reuses the original key and run.
- Native requirements are added alongside the existing template dependencies;
  both are installed so advertised reference actions retain their modules.

`scripts/agentdb_stack.mjs` operates only the stack identified in this checkout's
`.state/agentdb/stack.json`. It does not prune Docker, delete volumes, reset other
services, or change Docker Desktop settings. Local test credentials stay in the
ignored `.state` directory. Worker environments receive the worker credential,
not the platform admin token.

## Verify

```powershell
node scripts/check_agentdb_modules.mjs C:/cogit/cogit-core/agent-db
python scripts/verify_agentdb.py --restart
```

The first command uses AgentDb's own module-kit to validate manifests, hashes,
schemas and migration restrictions. It does not execute SQL.

The second requires the native launcher to be running. It admits a purchase,
checks four workers, waits for `SETTLED`, verifies signatures and the event hash
chain, checks the EUR 495 seller / EUR 5 fee ledger, downloads the delivery,
restarts the backend, and reads the identical deal and delivery back. It saves
the actual evidence under `.state/agentdb/acceptance-*.json`.

Python tests cover successful and retry deliveries through inbox actions,
native transport, and recovery after a lost admission response.
`tests/e2e/test_native_postgres.py` executes the generated SQL when
`COMMERCE_SQL_TEST_DSN` points to a disposable PostgreSQL database. Those tests
use randomly named test schemas and do not alter `core`.

## Environment blockers

If `docker version` cannot reach `dockerDesktopLinuxEngine`, start Docker Desktop
from the Windows user's session. A desktop process existing does not prove the
engine started. The old file-lock report in `WSL-HANDOVER.md` is historical;
recheck it before concluding that Zed still holds the settings file.

If installation reports offline cache misses, make the pinned dependencies
available and rerun it. Do not report workers as deployed merely because their
wheels and manifests were built successfully.
