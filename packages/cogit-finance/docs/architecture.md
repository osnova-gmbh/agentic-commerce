# Architecture

The repository owns one resident agent's identity and domain behavior. Generic
execution infrastructure belongs to `cogit-agent-sdk` and `cogit-runtime`.

## Boundaries

- `src/cogit_finance/` may import the SDK and domain libraries, but not the
  runtime, FastAPI, SQLAlchemy, Uvicorn, or model-provider SDKs.
- `domain.py`, `schemas.py`, and `dependencies.py` are transport-free.
- `agent.py` adapts typed domain operations to SDK `@action` handlers.
- `main.py` composes Runtime execution. The separate `cogit_finance_setup`
  package composes offline host configuration; it validates the Runtime manifest
  without starting resources. Neither is imported by `cogit_finance` domain code.
- `evals/` is data-only and exercises a running endpoint through the runtime
  eval runner.

Import-linter and an AST regression test enforce these boundaries.

## Execution paths

AgentDb admits work, assigns a worker lease and fences the active execution.
Runtime checks the manifest's typed bindings and invokes the selected pipeline.
The default queue pipeline performs a deterministic request write and readback,
then publishes a result artifact through AgentDb. Optional model profiles can
expose read-safe actions as tools.

The resolution command remains approval-gated in the action contract and
requires `records.write` and an exact request key. It uses the fenced AgentDb
module command. The module commits the resolution and its request-key binding
in one transaction. A replay with another payload fails. The corresponding
query requires `records.read` and reads the committed result by case ID in the
same AgentDb tenant and installation.

## State ownership

AgentDb owns admission, leases, execution state, artifacts and domain tables.
Runtime supplies the fenced run handle. The `database/` bundle defines typed
reference request and resolution exports and their tenant schema migrations.
An operator installs the module and publishes the worker cohort. Workers
execute only exports authorized by their claim and grants.

See [database-example.md](database-example.md) for the installation and worker
proof. Its reduced descriptor is optional. The default cohort uses the root
`cogit.yaml` and the same published AgentDb module.

## Optional dynamic capabilities

`cogit_finance.capabilities` resolves typed provider selections from descriptor
metadata. `cogit-tool-core` discovers only selected installed entry points and
prepares ordinary SDK ToolBindings. Startup/shutdown own each provider resource;
there is no second agent loop. Tool implementations remain independent library
distributions. The workspace prompt supplies general work habits, while
AgentDB and Runtime supply enforceable execution authority.

The separate setup package exports exactly the selected typed inventory and
declares the central policy module dependency. Deployment preparation commits
the selected provider wheels alongside the agent/framework artifacts. See
[dynamic-tools.md](dynamic-tools.md) for configuration, authentication ownership,
recording and acceptance requirements.
