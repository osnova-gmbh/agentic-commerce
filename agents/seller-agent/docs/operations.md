# Operations

Build and install the frozen dependencies and validate the authored manifest
before publishing the worker. Install the exact approved agent wheel in the
worker environment after building it. Use `scripts/worker_cohort.py prepare --manifest
cogit.yaml` with the built wheel and the intended output directory. Install
the module and bind the cohort to the AgentDb installation and worker pool.
Follow the [deployment example](database-example.md) for exact steps.

Start the installed worker with `cogit work --project . --environment`.
Set the AgentDb endpoint, API version, installation ID, pool ID, scoped worker
token, and published receipt path through environment configuration. Keep the
token out of the manifest and command arguments.

The default manifest declares an approval-gated action. Set
`COGIT_AGENTDB_APPROVAL_DECIDER_ID` to an active tenant member's principal UUID
with the tenant-wide `human.decide` grant. The deployment operator provisions
this separate approval authority in AgentDb.

The Docker image prepares the same root manifest at `/app/worker-cohort`.
Publish that cohort before starting Compose. Set the host path of its receipt
in `COGIT_AGENTDB_COHORT_RECEIPT`; Compose mounts it read-only and connects to
the existing AgentDb service. The optional reduced database descriptor uses
`/app/database-worker-cohort` and a receipt for that exact cohort.

Admit a request using the authorized member client in
`examples/durable_run.py`. Check the resulting lifecycle, events and result
artifact through AgentDb. Replace the worker using the same published cohort
and receipt. AgentDb retains its leases, attempts, checkpoints and command
receipts and supplies the continuation to the replacement.

The credential-free `scripts/check.sh` and `scripts/check.ps1` gates verify the
installed closure, manifest and action parity, typing, lint, and tests.
The integration fixture uses a disposable AgentDb deployment.
