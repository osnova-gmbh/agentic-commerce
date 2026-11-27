# Configurable typed capabilities for cloned agents

Status: source-based design, 2026-10-23. No implementation or release is claimed.
Read [TASKS.md](TASKS.md), then follow the assigned task number. The coordinator
owns contract decisions, integration, artifact selection and whole-plan validation.

## Goal and scope

Keep this repository an independent, neutral agent template. A clone selects
installed tool providers through configuration and gains filesystem operations,
shell/process control, browser operations, persistent working memory and evidence
without rewriting its agent. Preserve typed domain actions, CLI commands, resource
APIs, manifest parity, approvals, durable cases and the normal SDK/Runtime loop.

The workspace-capable profile must eventually demonstrate WorkspaceAgent's real
behavior, plus deliberate authenticated browser-session reuse. Dynamic initially
means configuration-time selection before a worker starts. It does not mean
installing Python packages or changing frozen bindings during a model turn.

This investigation changed documentation only. Proposed changes below distinguish
code, prompts, configuration and dependencies. No accounts or browser profiles were
accessed. Invoice/playground applications and existing dirty library work are out
of scope. Future shared-library changes need isolated checkouts at selected source
revisions; do not edit the reference worktrees or dirty main as an integration shortcut.

## Source snapshots and evidence

- Template: clean `main`, `05c819e`; package 0.1.12. SDK: `c743a01`, 0.5.11;
  Runtime: `c2952c7`, 0.3.22. Template pins AgentDB client 0.2.10 as well.
- Shared source: `C:/Users/denys/.codex/worktrees/general-agent-tools/cogit-library`,
  branch `codex/general-agent-tools`, `5dcd26b`; existing untracked directory.
  Seven workspace/tool distributions report 0.1.0. Package-index availability
  and current GitHub merge state were not verified; local refs are not proof.
- Browser adapter reference:
  `C:/Users/denys/.codex/worktrees/invoice-recovery-companion/cogit-library`,
  `490a2eb`, with relevant untracked source. This is design evidence, not a
  released dependency. `C:/ai/cogit-library` is substantially dirty/diverged.
- The template's vendored framework hash verification passed. Its existing
  `.venv` is stale: template 0.1.8, SDK 0.5.9, Runtime 0.3.16, AgentDB 0.2.7.
  A focused installed-package test run returned 37 passed, but is NOT evidence
  for the pinned current cohort. Use a fresh environment for implementation.

Authoritative local sources (paths below are relative to their named repository):

| Source | Exact evidence | Design consequence |
| --- | --- | --- |
| Template `docs/architecture.md:12` | "main.py is the only runtime composition root." | Agent/provider code imports SDK, not Runtime or provider model SDKs. Runtime CLI entrypoints must also work. |
| Template `src/cogit_finance/dependencies.py:27` | `registry.load_package("cogit_finance.functions")` | Existing function discovery is hardcoded; preserve it for pure reference functions. |
| Template `src/cogit_finance/agent.py:38` | `def configure(self, services: AgentServices)` | Register selected external bindings beside existing domain bindings. |
| SDK `src/cogit_agent_sdk/resident.py:128` | "Register an explicit tool binding during ... configure()" | Reuse the registry; no new agent loop or hot registration. |
| Runtime `src/cogit_runtime/app.py:232` | `lifecycle.configure(agent, services)` followed by freeze and parity | Prepare bindings before startup; acquire resources only after validation. |
| Runtime `src/cogit_runtime/lifecycle.py:98` | `agent.descriptor = self._descriptor` | Configuration in supported descriptor metadata reaches serve/work alike. |
| Runtime `src/cogit_runtime/manifest.py:64` | `Unknown manifest key(s)` rejection | Do not invent unhandled top-level manifest keys. |
| Template `scripts/manifest_sync.py:197` | "Rewrite actions/tools from live bindings while preserving other fields." | Extend the existing deterministic exporter, using the selected descriptor. |
| Template `cogit.yaml:360` | `provider: runtime`, `model: echo`, `supports_tools: false` | Keep offline smoke mode; add a genuine tool-capable model profile. |
| Shared `.../cogit_tool_core/contracts.py:13` | `ConfigDict(frozen=True, strict=True, extra="forbid")` | Retain original Pydantic input/output classes. |
| Shared `.../cogit_tool_core/sdk.py:79` | `"risk": "write"`, `"idempotency": "none"` | Add explicit per-tool exposure policy; current adapter omits approval/capability requirements. |
| Shared `.../cogit_agent_workspace/agent.py:33` | "never overrides handle_run or chooses tool calls in code" | Reuse model-directed execution through the standard loop. |
| Shared `.../cogit_agent_workspace/services.py:25` | "Own every service once; retain failed closes so cleanup can be retried." | Retain ownership/rollback, replace eager construction. |
| Shared `.../cogit_tool_browser/_session.py:56` | `chromium.launch(headless=headless)` then `new_context` | Generic browser has no persistent-profile or script-sharing contract. |
| Shared `.../cogit_agent_workspace/prompts/system.md:9` | "Never claim a test passed, file downloaded or task completed without checking actual tool output." | Carry behavioral guidance into optional prompt fragments. |

Here `.../PACKAGE/FILE` is under `packages/<distribution>/src/` in the shared
checkout. Existing proof is `docs/evidence/general-agent-tools-2026-10-21.md` in
that checkout: randomized portal/download/code repair/process/memory behavior.
It does not prove a fresh template clone, authenticated shared session, Docker
deployment, or a complete GitHub-to-deployment workflow.

## Minimal architecture

```text
clone + installed pinned capability distributions
  -> manifest metadata selects providers and typed settings
  -> pure provider preparation -> existing ToolBinding objects
  -> existing manifest export/parity -> Runtime registration freeze
  -> agent.startup opens owned resources -> standard SDK/Runtime loop
  -> agent.shutdown closes resources in reverse order
```

Dependency direction: template -> SDK + optional shared core SDK integration;
provider adapters -> their capability package + core SDK integration;
capability implementations -> core/Pydantic (and Playwright for browser).
Runtime remains the application host. The template must not depend on
`cogit-agent-workspace`, an invoice agent, or browser-product-specific adapters.

The first implementation needs no new SDK/Runtime execution mechanism. Put the
provider protocol and loader beside the optional SDK adapter in `cogit-tool-core`.
Keep that package's base import free of SDK/Runtime. Revisit SDK ownership only
if multiple independent integrations need a broader framework contract.

### Proposed provider contract (new code, not an existing API)

- `ToolProvider[SettingsT]`: API version 1, strict Pydantic `config_model`, and
  `prepare(settings, host_context) -> PreparedTools`. Entry-point group proposed:
  `cogit.tool_providers.v1`. Discover metadata, but import/load only selected IDs.
- `PreparedTools`: immutable canonical SDK bindings, trusted prompt fragments,
  async `start()` and `close()`. Preparing schemas must not launch a browser,
  open SQLite, spawn a process, read credentials or make network calls. Bindings
  call typed deferred service handles which become ready during `start()`.
  Initial providers own any needed driver loop/thread/process; resources may not
  depend on the caller retaining the event loop used for start/close.
- Preserve concrete models within each OperationContract/ToolBinding; an
  existential heterogeneous collection at the loader boundary does not replace
  operation types with dicts. Validate dynamically loaded provider objects,
  provider API version, settings, unique IDs/names and SDK schema parity.
- Each selected distribution is pinned in the install lock. No arbitrary import
  strings from tasks/web content, no auto-import of every installed plugin and
  no package installation by the executing model. A new external API supplies
  one provider wheel and typed models; a clone then changes config/dependencies.
- Extend `bind_tools` with explicit typed per-tool policy, or accept native
  ToolBindings directly. Carry risk, required capabilities, approval, idempotency,
  execution mode and timeout into both code and manifest. Do not route effectful
  tools through FunctionRegistry's read/inherent dispatch binding. Agent policy
  may tighten provider requirements; configuration cannot silently weaken them.
  Retain native prepare_arguments/key_for and keyed-idempotency requirements;
  union required capabilities, retain mandatory approval, and reject incompatible
  policy overrides rather than rebuilding a binding that loses these semantics.
- The execution provider owns one ProcessService and exposes process tools;
  the shell provider declares a dependency on that configured execution instance.
  Resolve this small explicit dependency graph before startup; reject missing
  instances/cycles. Filesystem/memory/browser need no eager execution dependency.
- Host context supplies paths, approved environment references and evidence sinks.
  OperationInvocation supplies trusted tenant/agent/run/session context. General
  services must not leak process handles, memory or cookies between scopes. First
  version may bind a workspace/profile to one tenant+agent and reject mismatched
  invocations; memory namespace remains host-derived and stable across restarts.
  Require tenant identity and use the host descriptor's agent identity, rejecting
  a conflicting invocation agent. Process ownership key is tenant+agent+session,
  falling back to execution_id when session_id is absent; reject missing both.
  Filter list/poll/input/stop as well as creation by that key. Memory deliberately
  shares tenant+agent+configured namespace; a dedicated browser deliberately shares
  tenant+agent+profile identity with exclusive serialized leases. Ephemeral browsers
  use the process scope. Scope never comes from model tool arguments.

### Configuration and lifecycle (code + configuration)

Use supported `metadata.cogit_tools` in `cogit.yaml`, validated by a strict
versioned model, with a provider list, typed provider settings, profile identity
and loop budgets. Missing block means the current reference profile. Host paths
and secrets use explicit environment references; never commit credential values.
For initial general profiles require an absolute workspace root supplied by the
host, avoiding dependence on the launcher's current directory.

`configure()` reads the injected descriptor, prepares providers and registers
their bindings beside reference actions. `manifest_sync.py` must load the same
selected descriptor into its agent, prepare without side effects, and regenerate
the canonical tools in the same manifest location. Configuration changes require
this explicit sync/validation step and a worker restart. Boot never rewrites the
manifest, adds undeclared tools or bypasses parity. Both exporter and runtime fail
closed on unsupported versions, missing packages, invalid settings or collisions.

`startup()` starts the resolved providers in dependency order. It performs its
own rollback on failure/cancellation: current Runtime calls startup before its
lifespan cleanup try/finally. Preserve the primary failure plus cleanup failures;
retain failed closes for retry. No resources open during offline introspection.
Keep the no-argument agent constructor expected by Runtime's lifecycle manager.

Custom CLI commands need an explicit exception: Runtime `cli.py:855-860` performs
configure/startup/handler/shutdown without parity/freeze, using separate asyncio.run
calls. Keep existing report commands capability-free in v1. The template's public
freeze hooks delegate to the SDK first and record each successful action/tool
freeze; startup opens external providers only after both. Without it, leave
providers prepared but inactive, and reject calls into their deferred handles.
Do not add tool-using custom commands under this contract. Test an enabled-profile
report with zero resource starts, stale inventory causing zero acquisitions, and
loop-affine resource misuse rejection. Normal serve/work startup still depends on
Runtime's full parity check, not the eligibility flag alone.

Maintain reference/offline and workspace-capable profiles. Changing profiles
must preserve domain actions/CLI/resource APIs and each intended queue pipeline.
The workspace profile chooses a Runtime-supported tool-capable model; fail early
if configured otherwise. Do not copy WorkspaceAgent's InMemoryRuntimeStore,
canonical-admission opt-out, provider hardcoding or model compatibility shim.

### Browser ownership and generated code (new shared-library code)

Provide typed `BrowserSessionSettings` with explicit ephemeral or dedicated
persistent modes. Dedicated profiles live under a host-owned automation root,
bound to a tenant/agent/profile identity. There is no default-profile discovery,
copying or attachment, and no operation on the user's normal Chrome session.

Reuse `cogit_transport_browser_session.locking.ProfileLock` and its canonical
`{profile}.lock` identity (source `locking.py:48`), with the neutral transport
distribution and filelock included in the pinned closure. Do not invent another
lock filename or widen that transport's fixed-route request interface.
One supervisor holds the OS-backed lock for the browser's lifetime, outside the
script worker: a crashed lock-owning worker could otherwise leave orphan Chromium.
Built-in tools borrow a serialized driver and never own/close the shared context.
The owner records bounded traces/download artifacts and closes context/process
before releasing the lock. Close failure must retain/quarantine ownership; never
start a second browser against a possibly live profile. Reuse neutral lock/owner
patterns and borrowed-driver abstractions from the reference, not product code.

Preferred initial script interface: `browser_run_script` submits a workspace
script to the same supervised owner process. Its documented entrypoint receives
the existing context/page on the owner's Playwright thread/event loop. This is
actual session reuse; ordinary shell-launched scripts do not inherit it. Serialize
built-in operations and scripts against the same lease. Reuse the existing browser
worker and bounded retirement code (`_worker.py:158`), extending it to verify owned
browser descendants, not just worker exit. Bind approval to immutable script bytes,
digest and typed arguments; reject changed files at execution/resumption. Logging
a digest alone is insufficient. Expose the script as privileged, effectful and
non-idempotent with explicit capability/approval policy, deadlines, output limits
and artifact/error reporting. A stuck script requires terminating the owned tree
and confirming exit before lock release; thread cancellation alone is insufficient.
Keep the script deadline plus retirement budget inside the broker timeout so
control cannot return while an unretired script continues issuing browser actions.
Generated Python is privileged local
code like shell execution, not a security sandbox. Do not expose it to untrusted
tenants or promise to constrain arbitrary Python through type hints. Built-in
borrowers must not close the context; arbitrary scripts can close it, so detect
invalidation and retire the session. Report timeout/crash effects as unknown where
completion cannot be established; do not blindly retry a potentially committed write.

Prove this owner/runner slice before claiming a complete browser solution. An
authenticated external Playwright/CDP connection can be a later transport, but
is not needed for the first supported script path. It would require endpoint
authentication, isolation, version checks and shared-session arbitration. Playwright
documents lower-fidelity CDP and a Node launchServer requirement for its protocol
connection; neither automatically shares the existing Python persistent context.
See [BrowserType](https://playwright.dev/python/docs/api/class-browsertype).
Python entry-point discovery uses the standard
[importlib.metadata API](https://docs.python.org/3/library/importlib.metadata.html#entry-points).

### Prompts, memory and evidence

**Prompt changes:** package a general work fragment for inspect -> act -> observe
failure -> repair -> verify, honest completion claims, bounded iteration and memory
recall. Load only fragments for enabled tools. Preserve the synthetic restriction
in the reference profile; the workspace profile must not say it can work only on
synthetic records. Prompt text cannot implement session persistence or authority.

**Code changes:** retain original filesystem/process/memory implementations where
possible. Reuse namespaced SQLite as working memory, separate from durable domain
state/Runtime cases. Align provider evidence with existing Runtime events/artifact
handles and correlation IDs; the local journal is supplemental evidence, not a
second execution store. Redact credentials/cookies and bound trace/output sizes.
Keep tool failures available to the model so it can repair rather than claim success.

### Distribution and completion criteria

**Dependency changes:** keep the current exact framework pins unless a concrete
API gap requires a coordinated cohort refresh. Build/version provider adapters
and all six tools as immutable wheels; vendor hashes/provenance or use verified
releases. Never make the standalone clone rely on sibling/editable workspaces.
Optional capability profiles install their own dependency closure; the minimal
profile must import/run without Playwright. The browser profile additionally
installs the matching browser binary/system dependencies in its container image.

Coordinator integration sequence: freeze shared contract BEFORE parallel code -> independently build
provider/browser/template slices against that contract -> select immutable tool
wheels -> integrate lock/provenance/profile packaging -> run whole-plan gates.
The checkpoint includes settings/bundle signatures, provider dependency references,
minimum policy rules, trusted scope, evidence event shapes and custom CLI behavior.
Use separate release steps for library artifacts and template consumption; do
not represent successful local tests as permission to publish/merge/deploy.

Completion requires:

1. Typed provider selection, invalid/missing/duplicate settings/names, unsupported
   APIs, schema/policy drift, disabled import/launch absence and late registration
   rejection. No resource side effects before preflight/parity succeeds.
2. Startup rollback, cancellation, reverse cleanup, failed-close retention, one
   shared execution service, scope isolation and exact approval denial/resumption
   behavior through the real Runtime broker.
3. Fresh clone/rename/install from pinned artifacts with sibling trees unavailable,
   installed-import verification, strict Pyright/import boundaries, manifest parity,
   existing action/CLI/resource and queue/recovery gates. Test minimal and workspace
   profiles on Windows and Linux, including an installed container browser run.
4. Local authentication fixture: login to a disposable dedicated profile, inspect
   through built-in tools and a generated Playwright script, assert one launch and
   the same live page/context marker (cookies alone are insufficient), restart and reuse
   cookies, compare with a fresh ephemeral session. Test contention, timeout/crash,
   trace/download cleanup and a sentinel proving ordinary Chrome paths untouched.
5. Real tool-capable model on randomized local tasks: navigate/download original
   bytes; write/run code; observe a genuine injected failure and repair it; verify
   independent totals/hashes; manage an interactive process; recover a memory note
   in a new process. Record actual model/provider, wheels, budget, tool events and
   independent checks. Never claim this from echo or scripted fake-model tests.

No implementation tests for the proposed design have run yet. The first safe
implementation slice is provider preparation/registration plus one filesystem
provider and an unrelated fixture API provider, proving genericity before adding
the remaining services. Browser ownership/runner is a separate mandatory slice
for the full user goal, not something prompt text can supply.

Independent plan review: pass after correcting custom-CLI lifecycle, policy
composition, trusted scope, contract sequencing, browser orphan cleanup and
approval binding to script contents. This is readiness for the contract-definition
checkpoint; it is not evidence that implementation or live proofs have passed.

## Current implementation ownership — 2026-10-23
The original conversation (computer-use invoice agent (2)) owns implementation, integration and merge. The separate template chat and all its workers stopped; reuse its unfinished work. This section supersedes earlier proposal details where they differ.
Worktrees: C:/cogit/cogit-core/.worktrees/dynamic-agent-template-20261023/{template,sdk,runtime,library,agentdb}; branch codex/dynamic-agent-capabilities-20261023. Bases respectively 05c819e, c743a01, c2952c7, 13283f4, 1da0460. Other worktrees and normal Chrome are out of scope.
AgentDB owns policy rules/evaluation/provenance. Existing governance APIs, pinned snapshots, module evaluators and Runtime transports must be reused. SDK adds inert typed contracts; Runtime enforces mandatory pre-run, pre-tool/action, post-tool, checkpoint/resume, post-run decisions independently of optional agent hooks. Agent hooks cannot grant authority. Preserve intrinsic requirements, distinguish pinned revisions from live revocation, and never treat post-effect checks as rollback. Current governance outcomes differ from the conceptual decision envelope; implement an explicit tested bridge rather than invented server fields. Required real AgentDB proof is separate from mocked contract checks.
Do not prohibit authorized workspace dependency installation or cloning. Provider discovery itself installs nothing. Browser supports explicit ephemeral/dedicated modes, headed/headless, a documented dedicated login path and one live context shared by tools and generated code. Agent may select allowed launch modes; no personal-profile discovery/copy/attachment.
Completion requires a fresh installed clone, no sibling imports, genuine model-driven unfamiliar portal traversal with no supplied selectors/workflow/script, agent-authored acceptance tests and script with observed failure/repair, independent original-file oracle, login reuse after restart and continuation of unfinished work. Include a bounded create-and-run-new-agent coding proof. Required code/config review and security remediation precede coordinated PR/CI/merge; do not claim partial proof as completion.
Provider contract currently exists in cogit_tool_core.providers: HostContext, ProviderSelection, ToolProvider(config_model, prepare, api_version, dependencies), PreparedTools(bindings,prompt_fragments,start,close,resource), ProviderBundle. Coordinate breaking changes before editing these interfaces. Source scope and tool metadata do not grant policy authority.
Coordinator owns template files, packaging/cohort integration, full evidence and merging. Internal task owners below may not commit/push/merge independently. Continue through working checks; report concrete failures, not unsupported completion.
