# A02 Template image and stack proof

This report covers only the Template-owned image, dependency closure, Compose
stack, and standalone queue worker. The final check ran on 2026-10-08 in an
isolated Docker Compose project `a02fix805e` against a fresh PostgreSQL 16
volume on the committed default Compose network.

## Exact image and installed cohort

The fresh image was built from Template 0.1.5 as
`evaluator-agent:a02-0.1.5-fixed`, image digest
`sha256:54f45118a9bcc0fa6bb82069f8e1792b5032bd053b9e15bfcdef4cbd947a6b28`.
The final runtime stage ran as user `agent` and imported `psycopg 3.3.4` from
its installed Python 3.11.16 environment. Its installed framework versions were
Runtime 0.3.8, SDK 0.5.3, and AgentDb client 0.2.5. The image build verified
all 429 installed framework files against these vendored wheels:

| Wheel | SHA-256 |
| --- | --- |
| `cogit_runtime-0.3.8-py3-none-any.whl` | `931bbb9b18ee3cab47a272f1e3be3e614531d8907bc0dfab468797d4ef00ae67` |
| `cogit_agent_sdk-0.5.3-py3-none-any.whl` | `242d52f3285d3e66ba90aff5eb00fbf71d2cd2de3951be2b45e4e65189f4e829` |
| `agentdb_client-0.2.5-py3-none-any.whl` | `1fa62eabd215fa1555381769d49c1bf523ca91fabc2c1fe993150060f3078fb5` |

The Runtime wheel matches the reviewed A02.RUNTIME handoff exactly. The SDK
and client wheels were rebuilt locally from their reviewed source revisions;
their local archive hashes differ from the Runtime handoff's earlier validation
copies. [Wheel provenance](../../../vendor/wheels/PROVENANCE.md) records this
distinction. The Template database module digest in the installed image stayed
`d4cb30dd44889dd06ca0cf6e119cf1aaa8105e4610e56262f6ea8e0b3e897fd2`.
The locally built Template 0.1.5 wheel had SHA-256
`6bec615af21bee97da1f376bfa8f56c5021a64f00e466980e1033819d4ac191e`.

## Real stack and worker results

The stack started with the fresh image and a unique Compose project. PostgreSQL
became healthy, `migrate` exited successfully, server became healthy, and the
worker stayed running with its HTTP healthcheck disabled. PostgreSQL had 14
`cogit_rt_*` tables at Alembic revision `0007_outbox_run_identity`; a second
`migrate` reported the same head and preserved the tables.

Docker published container bridge port 8081 only on host
`127.0.0.1:18082`. Runtime itself logged a listener on container
`127.0.0.1:8080`. Host `GET /health` and `POST /actions/lookup_record` both
returned HTTP 200. The health payload named Runtime 0.3.8 and SDK 0.5.3;
the model and optional platform mirror were degraded as expected in local Echo
mode, while the runtime, manifest, store, agent, and recovery components were
healthy.

A real `POST /dev/enqueue` with `queue_name=default`,
`item_type=plain_request`, and source `A02-FIX-1` produced a case and was
claimed by the queue worker. PostgreSQL recorded the item as `processed` with
`retry_count=0`, its run as `completed` with outcome `completed`, and `GET
/cases/{caseId}` returned `status=succeeded`. The worker was then force
recreated; its container ID changed from `58b9e5b95822841c8ba6d25a41ebb6a6241585d8f045833f8276c5b40be18b21`
to `e5c632d8e9301c211e0e84c5fedb457d0b96548f705363fa412fb5cbec01b40c`.
A second real item, `A02-FIX-2`, also reached `processed` with zero retries
and a `completed` run; the first item stayed processed. This proves a real
standalone worker request completes before and after worker replacement.

The rebased Template source gate passed with 95 tests and four existing skips,
and the local smoke evaluation passed 4/4. Ruff,
formatting, Pyright, import boundaries, dependency checks, and the frozen
noneditable installed-package verification passed on this cohort.
The final bridge fix also passed a socket-level half-close regression: a client
that sent request EOF still received the backend's full HTTP response.

## Separate pipeline limit

An earlier same-cohort diagnostic used the manifest's `case_request` item. It
selected the `resolve-case` pipeline and was accepted by `/dev/enqueue`, but
its `validate` step failed four attempts.
The queue item ended `failed` with three retries; persisted step errors read
`PIPELINE_STEP_FAILED: Operation failed (IntegrityError)`. Runtime's standalone
pipeline branch constructs a deterministic child execution ID for the action
without first creating a corresponding `cogit_rt_runs` row, so persisting the
action step violates that table's foreign key. Changing the Template pipeline
to skip deterministic validation would change its declared behavior, so this
report does not count that request as successful. Runtime owns the repair.

The selected client 0.2.5 understands AgentDb schema 179, not the separate D03
schema 180 fixture. This standalone image proof does not claim schema-180
module worker compatibility or the A04 replacement-worker result.
