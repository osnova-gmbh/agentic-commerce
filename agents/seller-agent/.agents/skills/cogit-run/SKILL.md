---
name: cogit-run
description: Use to set up, run, or diagnose a Cogit agent with the CLI, including AgentDb execution, database modules, permissions, grants, and approvals.
---

# Run a Cogit agent

Read the project guidance, manifest, and current deployment settings. Reuse
the selected target and authorization. The [operations
guide](references/operations.md) lists command examples, AgentDb configuration,
and the supported authority and result checks. Confirm options with the
installed CLI's `--help`. Apply the CLI-only section throughout when the user
requires Cogit CLI commands.

## Start and verify execution

1. Install or refresh the frozen project wheel with
   `cogit install --project <project>`. Validate the installed manifest and
   bindings with `cogit agent validate --project <project>`.
2. Use the authorized AgentDb target, installation and pool, scoped worker
   credential, and verified Runtime cohort receipt. Set runtime
   configuration through the environment, keep development mode off, and
   leave `DATABASE_URL` unset. Resolve applicable failures from
   `cogit doctor --project <project>`.
3. Start `cogit work --project <project>` to claim AgentDb work. Use
   `cogit run --project <project>` for Runtime HTTP health and inspection.
   These commands run in the foreground. Retain the host's process control.
4. For a standard query, submit through `cogit task submit` using the scoped
   client credential and save the admission record. Use `cogit task inspect`
   to capture the run, events and verified result for the returned run ID.
   Check the actual provider call and business effect before reporting a pass.

## Repeatable local acceptance

Prepare and bind a new executable generation when code, prompts or the
manifest change. Publish the hashes in `prepared.json` with the authorized
AgentDb deployment workflow. For a disposable local trial, use
`agent-db/docs/local-e2e.md` in the selected Core checkout.

```text
cogit cohort prepare --project PROJECT --output COHORT
cogit cohort bind --project PROJECT --cohort COHORT --publication ROUTE_JSON
cogit doctor --json --verify --project PROJECT
cogit task submit --project PROJECT --installation-id INSTALLATION_ID --request-id REQUEST_ID --input REQUEST_FILE --output ADMISSION_JSON
cogit work --project PROJECT --once
cogit task inspect --project PROJECT --run-id RUN_ID --wait 60 --output RUN_JSON
```

Keep each admission and inspection record. After an uncertain response reuse
the original request ID and input, or inspect the known run ID. Use a new
request ID for a deliberate new case run. To verify persistence, restart the
local services, inspect the same run into a separate file and re-read any
domain record through the project's owning contract.

For an approval-gated write, verify it parked before any effect. Record the
authorized decision for the exact approval through AgentDb and confirm the
continuation retains its original input and current authority. Before retrying
failed work, inspect the run, attempts, leases, approval, and observed domain
state. `work --once` can report zero claims, so confirm an execution occurred.
On a shared queue it can also process another pending request. For a batch,
keep the worker running while inspecting each submitted run ID.

## Manage database modules and permissions

- With `cogit db module`, plan or inspect the selected request before an
  authorized `initializeApplication` or `apply`. Confirm the exact tenant,
  application, module, and operation. Pass `--yes` when the existing
  authorization covers the mutation. Inspect state before retrying an
  uncertain result.
- Use `cogit permissions show/require/unrequire/approval` for action and
  approval declarations. They express requirements in the manifest and
  supported source bindings. Reinstall and validate after changes.
- Use `cogit permissions grants list/grant/revoke` for canonical AgentDb
  authority. Identify the exact principal and effect scope. `--installation`
  resolves the grantee's principal, while `--settings-installation` selects
  the settings effect target. Preserve object qualifiers and use the exact
  observed version, idempotency key, and previously authorized operation for
  mutations. Verify the persisted grant and the actual authorized or denied
  effect wherever the owning interface supports it.

The operations guide covers allowed object and settings capabilities and
verification with the ordinary mapped member. Keep separate worker, admin,
and member credentials in the environment. Preserve scope and identity after
a denial. Registration uses the agent's advertised endpoint with a separately
configured platform API target.

## When the user requires Cogit CLI commands only

Read the examples with `cogit skills show cogit-run --reference operations.md`.
Inspect and edit supported source through `cogit agent files`. Use the current
hash for guarded edits, check affected source, sync the existing entrypoint,
reinstall, and validate. Keep checkpoints in host messages or supported docs
files. Use the CLI for standard query admission and result retrieval.
Approval decisions and arbitrary domain readback use their owning interfaces.
Mark dependent checks unrun when only the CLI is allowed.

Report the actual effect, failure or missing capability for each requested
check. Distinguish health and installed validation from the completed business
result, and identify code, prompt, and configuration changes with relevant
source quotations.
