---
name: bootstrap-cogit-agent
description: Use to create or develop a Cogit resident agent with the official Cogit CLI, keeping its generated structure and changing the required business behavior.
---

# Build a Cogit agent

Turn the accepted brief into working code and prompts with evidence for its
acceptance checks. This skill guides the agent host through the workflow.
Read the [command guide](references/commands.md) for exact examples and use
the installed CLI's `--help` to confirm current options. Apply the CLI-only
section throughout when the user requires Cogit CLI commands.

## Establish the project

1. Reuse the user's brief and existing project. Settle any business ambiguity
   that blocks implementation. For a handoff, give the brief, target checkout,
   expected result, normal request inputs, required durable effects, and the
   checks that prove them. Keep evaluation expectations with the evaluator.
2. Read the project guidance, manifest, lock, tests, and existing progress.
   Check free disk space before setting up a new environment. Run
   `cogit --version` and `cogit init --help`. Use `cogit init <project>` for
   scaffolding, frozen installation, and project skills. In Core use its
   pinned template, honoring any authorized trusted template override.
   `cogit agent create` only scaffolds. Recover partial setup in place.
3. Read the generated `cogit.yaml`, `main.py`, and chosen source package.
   Compare the generated entrypoint with `.cogit/template.json` when present.
   Keep the generated or existing agent class, entrypoint, and Runtime and
   AgentDb wiring. Change the business behavior in the existing domain, schema,
   operation, or prompt locations and extend the current bindings as needed.
   Keep action requirements and approval gates within the accepted scope.

## Implement and verify

Make the next bounded change that advances an acceptance check. Use
`cogit agent edit` for supported metadata or system prompt edits. Update
relevant tests, reviewing the actual diff and keeping the configured agent
class and entrypoint. Check code before contract sync. Use the configured
entrypoint for contract sync and omit `--entrypoint`. Use `--manifest` and
`--artifact` together when synchronizing an existing separate fixture profile.

```text
cogit check --project <project>
cogit agent contract sync --project <project>
cogit install --project <project>
cogit agent validate --project <project>
cogit test --project <project>
```

Reinstall after code, prompt, or manifest changes to update the noneditable
agent wheel. A focused test path verifies only the selected tests. For
readiness, use `cogit doctor --json --project <project>` for provenance and
`--verify` with the bound, authorized deployment for installed preflight.

Manifest requirements declare the capabilities needed for execution. For actual
permissions, grants, database modules, and running work, use the companion
`cogit-run` skill. If it is bundled in the installed CLI, open it with
`cogit skills show cogit-run`.

## Verify live behavior when required

Use the real provider and installed project through the requested execution
boundary. For each required case, confirm the provider call and compare the
observed response or effect with the acceptance criteria.

- For AgentDb acceptance, use [Run](../cogit-run/SKILL.md) to prepare the
  installed cohort, submit ordinary input, start the worker and retrieve the
  saved result. Use [Evaluate](../evaluate-cogit-agent/SKILL.md) to check the
  result bytes and the actual business effect against the brief.
- For Runtime HTTP acceptance, use the authorized endpoint and its intended
  request or evaluation suite. Inspect the actual responses against the HTTP
  contract.

Report installed validation and offline smoke tests apart from live evidence.

Preserve explicit model and reasoning choices and the production profile.
When the live test has no model selection, use GPT-6 Luna (`gpt-6-luna`) with
max reasoning via a compatible request path. The [model evaluation
guide](references/model-evaluation.md) covers transport compatibility, private
expectations, and how to verify actual provider behavior. Report a concrete
compatibility gap when the required model and tools cannot run on the selected
cohort.

## When the user requires Cogit CLI commands only

Use the [command guide](references/commands.md) through
`cogit skills show bootstrap-cogit-agent --reference commands.md`. Inspect and
author bounded project text with `cogit agent files`; reread the current hash
before updating it. Use `cogit check` to resolve formatting, lint, and
type-check failures before syncing the configured contract and reinstalling.
Use the supported AgentDb module commands for authorized persistent schemas.
Use `cogit task submit` and `cogit task inspect` for the standard query path.
Approval decisions and domain-specific readback use their owning interfaces.
Report checks as unrun when the command restriction prevents them.

## Continue and hand off

Record evidence, the next accepted increment, and blockers in the existing
progress file or `.cogit/build-progress.md`. Use host messages or supported
file commands for a CLI-only checkpoint. Keep credentials and private records
out of checkpoints. Continue accepted work through its verification and stop
on completion, a user limit, or a blocker that requires an external change.
Inspect the actual error and state before retrying. Report verified outcomes
and any unrun checks. Distinguish code, prompt, and configuration changes and
quote the relevant source.
