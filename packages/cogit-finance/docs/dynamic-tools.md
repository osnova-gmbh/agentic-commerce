# Dynamic tools and authenticated workspaces

The template stays a separate agent repository. Its resident class composes
installed providers through the neutral `cogit-tool-core` contract. It does not
import `WorkspaceAgent`, copy its tool implementations, or contain a supplier
workflow. The optional workspace profile supplies general tools and a general
problem-solving prompt.

## What changes where

- **Code:** typed provider discovery, SDK bindings, resource lifecycle, manifest
  export, owned browser contexts, and installed artifact verification.
- **Configuration:** selected providers, their typed settings, model identity,
  work budgets, and host environment references.
- **Prompts:** inspect before acting; write checks; use observed failures to
  repair work; record progress; verify results. These instructions do not grant
  permissions or implement a navigation workflow.
- **AgentDB:** authoritative policy definitions, bindings, versions and
  evaluation receipts. Runtime enforces the lifecycle contract. The template
  declares an exact dependency on the central policy export, not policy content.

## Start from a clone

Run `bootstrap.py` as described in the README. Install the checked-in artifacts
with `uv sync --frozen --no-editable --extra workspace`. A normal installation
without the workspace extra does not require Playwright or the OpenAI client.
For a local browser, install its binary with
`uv run --no-sync python -m playwright install chromium`.

Supply a host-owned absolute workspace, a separate automation directory, and
the actual tenant identity in `COGIT_WORKSPACE_ROOT`, `COGIT_BROWSER_ROOT`, and
`COGIT_TENANT_ID`. These are configuration inputs; they do not create grants.
Keep model credentials in the host environment. They are not automatically
forwarded to shell subprocesses.

Copy `cogit.yaml` to `cogit.workspace.yaml`, then prepare it:

```text
uv run --no-sync cogit-agent-setup --manifest cogit.workspace.yaml --providers profiles/workspace-providers.json --profile workspace --model YOUR_MODEL --context-window INPUT_BOUND --max-output-tokens OUTPUT_BOUND
uv run --no-sync cogit-agent-setup --manifest cogit.workspace.yaml --check
```

Supply positive numeric token bounds reviewed for the deployment; the template
does not guess model capacity. AgentDB uses these bounds for conservative model
spending reservations, and setup rejects missing bounds before provider preparation.

The setup command validates the actual Runtime schema and exports the selected
tools' input/output schemas. It starts no browser, subprocess, model connection
or database migration. `--list-providers` lists installed entry-point IDs.
Installing a new provider and selecting it in configuration does not require
editing the agent class. Its distribution must expose `cogit.tool_providers.v1`
with strict settings and ordinary typed SDK bindings.

The generated manifest declares the pinned `cogit.runtime-policy` export.
The selected policy module requires AgentDB schema 202. Runtime negotiates
continuation.v2 through authenticated module readiness; an agent manifest cannot
enable it. Small journals keep the existing v1 format. Larger replay indexes use
a hash-verified artifact with a compact exact grant list in the unchanged 64 KiB
checkpoint. The external index is bounded to 1 MiB and 400 artifact grants; model
and tool slot bounds still apply. Older servers without this capability retain
v1 behavior and its explicit size limit.
An operator must install that module in AgentDB, configure the authoritative
policies/grants and publish the agent deployment. A missing or unavailable
authority prevents execution; a handwritten manifest cannot bypass that check
by omitting the policy marker. The default deterministic reference workflow runs
without these optional providers.

The default central policy requests approval for destructive tools. Arbitrary
shell/process commands and generated browser scripts have no replay-safe
idempotency contract, so Runtime rejects an approval requirement for them with
`unsupported_approval_for_unkeyed` before dispatch. A human approval cannot
currently resume such a script. To enable these capabilities, an operator must
deliberately allow them for the specific isolated installation, or expose a
replay-safe operation instead. This is an explicit current limitation; the agent
cannot change the policy itself.

Prepare the worker cohort using `scripts/worker_cohort.py prepare` in the
installed environment. It includes selected provider entry-point owners and
their supplied local dependency wheels. For independent provider distributions,
pass their exact artifacts with repeatable `--additional-wheel` arguments.
`metadata.entrypoint` in `cogit.yaml` selects the cloned agent class. Publication binds those exact
bytes to the route receipt; Runtime checks the receipt and installed bytes
before loading selected providers. The normal `cogit_runtime work` command
executes the agent; there is no template-specific agent loop.

## Browser session ownership

The example profile uses a dedicated persistent session. Its identity is the
host tenant, agent ID and `profile_id`, so a later worker can reuse the login.
The automation directory is outside the coding workspace. The browser package
does not enumerate, copy or attach the user's ordinary Chrome session.

`headless` selects headed or headless launch. `channel` can be unset for bundled
Chromium, or explicitly `chrome`/`msedge` when that browser is installed. Use
the same dedicated identity and channel when performing the initial sign-in
and when restarting. A headed login does not guarantee that a supplier accepts
headless access; test the real portal. Profile encryption and storage are not
portable between Windows and Linux.

The model can use DOM observation/navigation directly or write a Python file
with `run(page, context, arguments)` and call `browser_run_script` with its exact
SHA256. Both use the same owned authenticated context. A separately launched
Playwright process does not inherit the session. Python scripts and shell
commands have OS authority and are classified as destructive capabilities for
central policy; workspace path checks are not an OS sandbox.

After a timeout or crash, effects may be unknown. The worker must reconcile
them before retrying. A profile is released only after owned process retirement
is confirmed. In a Linux container use `--init` or Compose `init: true` so
descendants are reaped. Browser traces are local artifacts and may contain page
content and authentication data; treat them like the profile itself.

## Standalone container

`Dockerfile.workspace` installs the exact locked workspace profile, Chromium,
its system dependencies, Python, Git and uv. It runs as a non-root user. Build
it with `docker build -f Dockerfile.workspace -t my-agent:workspace .`.
Mount the published cohort read-only at `/run/cogit`, persist separate
`/workspace` and `/automation` volumes, inject the host's worker/model
environment, and run with `--init`. The image uses the standard Runtime worker.
The default Dockerfile remains the smaller reference-agent image.

## Acceptance evidence

`tests/capability_proof` supplies authenticated local portals with different
layouts, randomized routes and a private original-document oracle. The model
receives only the origin and business objective. The first PDF response is
deliberately incomplete. Acceptance must show model-authored checks detecting
the defect, repair, independent byte verification, a fresh worker using the
same login, and continuation from the AgentDb checkpoint.

Unit tests of this fixture prove only fixture correctness. A real-model run,
the complete policy/worker path, a fresh installed clone and container evidence
are separate release gates. Do not infer those results from mocked tests or
from the existence of this harness.


## Queue role boundaries

The existing AgentDB route, claim, lease, fenced-attempt and continuation path can
host separate planner, supervisor and assessor workers. This feature does not
implement those roles or their policies. A planner needs planning data but no
scheduling, launch or execution-check grants. A supervisor needs authorized
scheduling and launch operations. Only the assessor should receive the durable
decision-write capability for done/proceed/no-op and one-or-many agent targets.

Enforce those distinctions with separate AgentDB identities, central policies,
operator-assigned grants and isolated worker credentials. Dynamic tool selection
describes capability inventory; it cannot grant authority. Arbitrary shell and
Python have the worker's OS access, so workers with different authority must not
share an OS identity or credential mount. Prompt-only role descriptions are not
enforcement. Existing queue durability does not imply exactly-once external
effects: an uncertain unkeyed effect still requires reconciliation.


The native OpenAI adapter currently uses Chat Completions. Select a model that
supports function tools on that API. An explicit `--thinking-level LEVEL` writes
`model.defaults.thinking_level`; the SDK forwards it as `reasoning_effort` only
for native OpenAI. Omission preserves provider defaults. Supported levels depend
on the model; this option does not make a Responses-only model compatible.
The isolated acceptance candidate uses `gpt-5.6-terra --thinking-level none`
because its API rejected tool requests without that explicit setting.
