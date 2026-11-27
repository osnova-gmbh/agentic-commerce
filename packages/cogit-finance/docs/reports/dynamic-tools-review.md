# Independent dynamic-tools review — 2026-10-24

## Decision and scope

Source review of the SDK, Runtime, AgentDB policy module, template and neutral
providers is approved with no unresolved source must-fix findings in the reviewed
scope. Final installed neutral artifacts also pass independent validation.
**Release approval remains pending** the final live disposable-AgentDB evidence,
real-model fresh-clone/container portal proof and final release checks. Unit tests
and the scripted capability integration proof do not establish that a model can
solve an unfamiliar portal. Browser validation is separate owner-run evidence.

This review used the review-feature, review-work and audit-security skills. The
independent policy reviewer made no implementation edits or commits. In addition
to Runtime `tests/test_policy_independent_review.py`, the reviewer maintained 18 explicitly
authorized AgentDB test/fixture files for schema 201 and synchronized the
generated `docs/release-manifest.json` with the actual migration list. These are
test and generated-document changes, not changes to the working invoice package.

## Independently executed evidence

- Runtime boundary/durability suite: **117 passed in 29.09s**. Files: runtime policy,
  central approval, pipeline resume, real HTTP policy errors, independent negative
  probes, resource cleanup, custom-command lifecycle, cohort/boundary and canonical
  pipeline tests. Environment: `.venv-policy`, Python 3.11, paired AgentDB OpenAPI
  path explicitly set. Initial 13 failures were a wrong default sibling fixture
  path (`agent-db` versus this worktree's `agentdb`); all cleared with the supported
  `COGIT_AGENTDB_OPENAPI_PATH` setting.
- Five new independent probes verify that entry-point metadata cannot authorize
  unapproved target/parent code, discovery executes no provider code, pre-run
  denial prevents the handler, and post-run denial prevents success publication
  while releasing execution resources. Ruff passes for this new test file.
- Installed template setup/configuration/bootstrap/cohort subset: **57 passed,
  4 Linux symlink controls skipped on Windows**, one upstream Starlette deprecation
  warning. Invoked with `python -I -m pytest -o pythonpath=tests --import-mode=importlib`.
- After the archive-bound fix: **15 cohort/provider tests passed** independently.
- SDK and Runtime lockfiles, plus the validation environment, independently
  confirmed `certifi==2026.10.19`.

## Findings and disposition

1. **High, dependency — fixed.** SDK/Runtime locks still contained certifi
   2026.6.17 after the template was patched. Those locks now use 2026.10.19.
   [Reviewed advisory GHSA-6q48-6c7w-9gw2](https://github.com/advisories/GHSA-6q48-6c7w-9gw2)
   identifies affected versions below 2026.10.19. No live TLS interception was
   attempted; the evidence is the affected installed/locked version.
2. **Medium, resource exhaustion — fixed.** `scripts/worker_cohort.py` read ZIP
   METADATA/WHEEL members without uncompressed size bounds. A safe 1,556-byte
   compressed wheel with 1,048,627-byte metadata was accepted. The same probe now
   raises `Wheel metadata exceeds the artifact size limit` before decompression;
   duplicate members are also rejected.
3. Earlier central-approval slot, cached-pipeline policy and HTTP-error downgrade
   findings are fixed in current source and exercised by the passing regressions.
   Unsupported approval for unkeyed effects stops explicitly before dispatch;
   replay-safe approvals retain exact durable invocation commitments.

## Code, configuration and prompts

- **Code:** Runtime enforces central decisions, exact provider origins and
  resource cleanup. SDK carries inert contracts. `src/cogit_finance_setup/policy.py`
  states: "no policy content lives here." AgentDB's module SQL states:
  "Core owns policy versions, admitted pins, evaluation history and grants."
- **Configuration:** installed provider selections, typed settings, host-owned
  paths, model identity and budgets select capabilities without granting authority.
- **Prompt:** `src/cogit_finance/prompts/workspace.md` says: "Write automation and
  task-specific acceptance checks" and "Do not try to change your own grants."
  This is behavioral guidance; no supplier navigation workflow is implemented there.

## Durability and role limits

Planner, supervisor and assessor workers are compatible with existing AgentDB
routes, fenced claims, heartbeats, checkpoints and approval successors. This
feature does **not** implement those roles or their policies. Planner must lack
scheduling, launch and execution-check grants; supervisor receives authorized
execution operations; assessor alone receives durable decision-write authority.
Separate worker credentials and OS isolation are required where arbitrary shell
or Python exists. Prompt-only tool hiding is not authorization.

Existing continuation does not promise exactly-once external effects: lease expiry
before confirmed park does not automatically expose the latest checkpoint; keyed
effects reconcile through canonical receipts and uncertain unkeyed effects stop.
No demonstrated gap requires adding Temporal or DBOS for these three logical roles.

The default central policy requires approval for destructive tools, while arbitrary
scripts have no replay-safe contract. Runtime therefore rejects that approval path
before dispatch. The operator must explicitly authorize such capabilities for the
isolated installation or supply an operation with a valid replay contract.

## Remaining release gates

1. Validate the final disposable-AgentDB policy, revocation, audit, cleanup and
   approval boundaries against the installed release cohort.
2. Demonstrate fresh-clone real-model discovery, self-authored failing checks, repair,
   private-original verification, authenticated worker restart and durable continuation.
3. Audit final image dependencies and run final CI/review checks before merge.

Neutral source/installed gates are complete. Browser owner reports its final
installed gates complete; this reviewer did not rerun the browser suite.

## Final neutral-provider review

Both findings below are **fixed in code and independently verified**. No prompt
change substitutes for either fix:

- **High, coordination boundary — fixed.** Both scoped and legacy core adapters
  previously converted SDK `CoordinationFailure` into ordinary `OperationError`.
  Original safe probe observed `is_coordination_failure=False`. Each catch now
  calls `raise_coordination_failure(exc)` before domain error conversion. The same
  probe now preserves `CoordinationFailure`; all six adapter regressions pass,
  including the actual Runtime `AgentDbAuthorityError` and exact exception identity.
  No completion or domain-failure event is emitted for the authority failure.
- **Medium, execution ownership — fixed.** An execution-only child previously
  remained running after scope cleanup. The original probe now observes `exited`.
  `ExecutionResources.release_scope` is registered and its contract says:
  "Retire ended execution-owned work; explicit session owners survive."
  Tests confirm another execution/session stays alive, failed stops retain their
  handle for retry, and unused-scope cleanup starts no service. Disposable probe
  children were always closed in `finally`.

Final independently executed installed suite: **82 passed, 1 Windows symlink
privilege skip in 27.05s**. All tests from core, execution, filesystem, memory and
shell ran under Python 3.11.16 with `-I`, importlib test mode, fresh site-packages,
SDK 0.5.12 and Runtime 0.3.23. Before adding SDK/Runtime, all five neutral packages
imported with neither SDK nor Playwright installed.

An independently rerun installed third-party entry-point proof dynamically loaded
an unrelated package and exercised **17 SDK bindings**: real loopback HTTP returned
42, filesystem wrote code, a process ran it with exit 0, a shell printed 43, and
SQLite memory retained a checkpoint. Disabled entry points were not imported;
all imports came from the fresh environment and Playwright remained absent.
This is a scripted capability integration proof, not an LLM intelligence or live
central-policy proof. Its disposable artifacts are in library
`.tmp/independent-neutral-final/{verification,wheel-verification}.json`.

Byte verification confirmed **47 installed neutral archive members**, including
**33 source files** matching current source. SDK's 83 and Runtime's 144 installed
archive members also match their wheels. Installer-generated RECORD is excluded.
`uv pip check` reports all 47 installed packages compatible. Fresh dependency
resolution used certifi 2026.10.23; feature locks remain at patched 2026.10.19.

| Earlier neutral-provider gate artifact | SHA-256 |
| --- | --- |
| core 0.1.1 | `e26c9abe59769f0f8f8a5b557b7db438aff85b93f31945c1d54450793dec39a5` |
| execution 0.1.1 | `4ac293043345a362226467dcccc70a34ab6a51c360707585237728aef93fec2c` |
| filesystem 0.1.1 | `3ef283b96e29ab4294b18d5c5b38924b505149935f65d161251fca8b71f964bd` |
| memory 0.1.1 | `1de826bc1d776d98e06d9fbfa2d37b512cf31db42933eda3b854a2d9b1f34b17` |
| shell 0.1.1 | `00cc480e232d97820addf1168447dd1224226eef046bfc2121704de76eb04aa7` |
| SDK 0.5.12 (superseded candidate) | `bd55ff544107ec8cda54de3b3b7ea9e266827ebd193d5f74d05ce716c41e6de1` |
| Runtime 0.3.23 | `7af8a675121ded2ed9dbb6b25b65ed8b4022a546a4e9ef82a628bb5528d563cb` |

Library `uv.lock` diff was inspected after the owner's offline refresh: only six
tool package versions/extras and browser transport/filelock/Playwright declarations
changed. No external resolved version or invoice-processor pin changed at that earlier
gate. The subsequent filelock correction and superseding SDK artifact are recorded
below; invoice-processor pins remain unchanged.

## Browser owner evidence (not independently rerun)

Library `packages/cogit-tool-browser/docs/validation-20261023.md` records original
Windows 74 pass/1 headed skip and Linux 75 pass, plus final **Linux installed
browser/core 81 pass including headed Xvfb** with SDK 0.5.12 / Runtime 0.3.23 after the
core fix; Windows installed core 38 pass. The owner also reports default minimal
image validation with 556 byte-verified files, smoke 4/4 and task 4/4. Former busy-host
timing failures and fixture repair are documented there. Core's previous 853db...
artifact is superseded by the e26c9a... artifact independently verified above.

These ownership and policy contracts are not an OS sandbox. Shell, generated code,
and browser scripts deliberately run with the worker's OS authority. Separate
credentials and container boundaries remain necessary for different policy roles.


## Final canonical-policy regression review

The first real installed worker attempt failed **before any model or tool work**.
AgentDB's old `core.module_policy_coverage` selected an arbitrary matching policy
version before reading the admitted pin. With v1 and v2 published, it could select
v1 while the run admitted v2, then report `required_policy_coverage_missing`.
The earlier single-version tests did not expose this defect. This was a code bug,
not a prompt or model failure, and the original attempt produced no external effects.

**Fixed in AgentDB code:**
`migrations/core/000201__module_policy_pinned_version.sql` states:
"Resolve the exact admitted binding/version before reading policy content."
Fenced-worker lookup now resolves one canonical admitted module/policy pin before
reading its immutable policy and binding revisions. Zero or multiple matching pins
cannot authorize execution. The live binding must belong to the same tenant,
installation, module and policy; the evaluator identity/version must also match.
Tenant-client resolution is an explicit separate branch using the current binding.
There is no fallback to the latest or an unpinned version. Runtime policy's own
evaluator separately checks live binding deactivation, retaining immediate revocation
while an admitted run otherwise keeps its immutable historical policy content.

**Configuration:** the policy module requires `minSchema: 201`. Its recomputed
artifact SHA-256 is
`dc931da450a04e86211b9a207f9a304574b151e7a725227e8732a4943aaca420`,
matching the template's declared pin. SDK 0.5.12 and Runtime 0.3.23 wheel bytes
were unchanged by this policy fix. The SDK candidate was subsequently superseded
by the reasoning-option fix below; Runtime bytes remain unchanged. No prompt
change implements this policy fix.

Independent actual PostgreSQL validation used an isolated copy of the unchanged
runtime-policy test with only fixture label, port and import locations adjusted to
avoid the live fixture. **3/3 passed in 15.53s**: two active PostgreSQL tests and the
optional held-worker case, which is a no-op when its environment flag is absent.
The version regression proves old v1 approval, newly admitted v2 allow, later v3
denial for a new run while v2 still allows, then live revocation denying the old v2
run. It also checks returned policy-version references. SDK checkpoint serialization
was independently validated against the actual module input schema in **10/10**
phase/scope combinations; the HTTP payload shape was not the cause of the failure.

The fixture publishes and binds policy versions with explicitly privileged owner
SQL. The legacy public `policy.publish` / `policy.bind` interface does not accept
these modern module policies. This evidence therefore proves operator/deployment
setup plus fenced-worker evaluation, not a new public policy-management API.

### Compatibility and test-maintenance evidence

The reviewer changed current-head test-only module ceilings and expected migration
lists from 200 to 201. Historical immutable artifact ceilings remain unchanged.
The historical fixture helper now also permits an explicitly requested isolated
schema-200 database; its isolation checks remain intact. `pnpm build`, ESLint for
the initial 16 changed test files, Prettier and `git diff --check` pass.

- Actual module-installation tenant suite: **16/16 passed in 21.30s**.
- Current-head module semantic, governance security/settings, retained invoice
  package and cross-repository invoice queue suites pass. The initial expanded
  run reported 44 passed, one stale generated-manifest assertion failure and 19
  tests skipped after two Docker fixture setup failures. No assertion was weakened.
- Module command replay, settled-action evidence, historical reconciliation and
  queue installation all pass on retry. This retry reported 29 passed plus the two
  release-manifest failures that had already sampled the old JSON. After the
  authorized JSON synchronization, the security contract passes **9/9** and the
  full bootstrap gate passes **1/1 in 57.47s**.
- Docker fixture setup initially exhausted the host's default network address pool.
  The documented Compose override used the existing bridge for disposable test
  containers. No host Docker networks were deleted; the active live fixture and
  ordinary browser sessions were not touched.
- The exact immutable invoice release cohort passes **4/4 in 20.36s** at its stated
  schema-200 ceiling, including the actual library invoice 1.1.1 / evaluation 1.2.1
  artifacts and upgrade from the exact preceding invoice 1.1.0 artifact. Separate
  retained-installation tests forward-migrate saved invoice data and governance
  settings to schema 201 successfully.

**Compatibility limitation:** the untouched invoice 1.1.1 and evaluation 1.2.1
manifests still declare `maxSchema: 200`. Fresh installation of those exact
artifacts on schema 201 is correctly rejected. Supporting a fresh installation
there requires a separate compatible artifact release. This review does not claim
fresh-install support or modify the existing working invoice processor.

Reviewer-owned AgentDB test files: `action-artifact-stack.helpers.ts`,
`foundation-bootstrap.stack.test.ts`, `governance-postgres.helpers.ts`,
`governance-security.postgres.test.ts`, `governance-settings.postgres.test.ts`,
`invoice-current-release.cross-repo.test.ts`, `invoice-package.postgres.test.ts`,
`invoice-queue-bundle.helpers.ts`, `module-installation.postgres.test.ts`,
`module-replay-fixture.helpers.ts`, `module-semantic-contract.postgres.test.ts`,
`query-wait-stack.helpers.ts`, `queue-install.postgres.test.ts`,
`reconciliation-boundary.postgres.test.ts`, `security-boundaries.contract.test.ts`,
`settled-action-evidence.postgres.test.ts`, `ci-suite-wiring.meta.test.ts` and
`postgres-baseline.unit.test.ts`, all under `tests/workspace/`.

### Final template setup review

**Code and CLI configuration, not prompts:**
`src/cogit_finance_setup/manifest.py` checks positive bounded model token limits
before provider preparation. The setup CLI explicitly requires both
`--context-window` and `--max-output-tokens` when selecting `--model`; supplying
bounds without a model also fails. The source states:
"Model selection requires --context-window and --max-output-tokens for canonical
spending reservations" and "Replace only after the entire inventory validates."
Independent setup/configuration regression run: **37/37 passed in 4.64s**,
including missing/zero/negative/oversized bounds, no provider preparation on invalid
bounds and unchanged manifest bytes after invalid CLI input. This validates the
source change; final clone/container model acceptance remains a distinct gate.

There is no unresolved source must-fix in this review's scope after these fixes.
The final real-model, final-cohort, authenticated-restart and durable-continuation
proof is owned by the root agent and must be reported separately, without inferring
it from the passing PostgreSQL or capability tests here.


## Final SDK and setup CLI review

This follow-up review was performed by the browser/installed-validation owner.
It distinguishes source inspection and independently run checks from results
reported by the SDK owner or policy reviewer.

**SDK code:** `src/cogit_agent_sdk/providers/openai.py:170` maps an explicitly set
native OpenAI `defaults.thinking_level` to
`kwargs["reasoning_effort"] = defaults.thinking_level` in the shared request
builder. Both generation and streaming use this builder. Omission preserves the
existing behavior; OpenRouter-compatible requests are unchanged. No retry or
authority behavior changes. The adapter still uses Chat Completions; this change
does not add Responses support, and permitted reasoning values remain model
dependent. The mapping was checked against the
[official Chat Completions request contract](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create).

**Template code and configuration:** `src/cogit_finance_setup/cli.py:38`
requires `--model` for bounds or `--thinking-level`, and writes the explicit
thinking choice into `model.defaults.thinking_level`. It does not select a
reasoning level implicitly. `src/cogit_finance_setup/manifest.py:45` rejects
legacy string fallbacks with
"Canonical model fallbacks require structured token bounds". Every prepared,
non-runtime model descriptor, including structured fallbacks, must have positive
integer context/output bounds at most one billion before provider preparation.
The CLI writes the manifest only after the whole inventory validates. These are
code/configuration changes; no prompt implements either safeguard.

The first real setup attempt failed before a model call because an explicit model
lacked the bounds required for Runtime spending reservation. Primary-model,
fallback, legacy-fallback and invalid CLI cases now have regressions. The earlier
37-test setup result predates the additional fallback and reasoning-option tests;
the final full installed suite below includes them.

Independent affected SDK provider suite: **80/80 passed in 13.48s**, evidence
`sdk/.quality/sdk-thinking-review.xml`. The SDK owner additionally reports
**612 passing tests** and all static gates. The policy reviewer separately reports
**44 passed, 4 optional OpenAI-transport skips**, including all 18 new reasoning
cases. These counts describe different runs and are not additive.

SDK source commit is `f81646fc30ab3649de9779eb4818606dc42269a0`.
Its final e795 artifact below supersedes the historical bd55 candidate in the
neutral-provider table. Runtime source/CI commit is
`1485c68ef4f29cb8717fab9e362932b029b26515`, with unchanged Runtime wheel bytes.
The Runtime CI follow-up was independently reviewed: immutable SDK pin, normalized
payload digest and archive digest agree; receipt verification was not relaxed.

## Filelock security correction and compatibility

The final review found that filelock 3.32.7 was a runtime dependency of the
workspace/browser extra, not merely a development dependency. The default minimal
installation excludes that extra. The upstream advisories
[GHSA-69hj-f68j-2879](https://github.com/tox-dev/filelock/security/advisories/GHSA-69hj-f68j-2879)
and
[GHSA-8mx5-7m5m-r77g](https://github.com/tox-dev/filelock/security/advisories/GHSA-8mx5-7m5m-r77g)
identify the affected range and patched 4.2.1 release. No exploit was run against a
user profile; evidence was the resolved version and upstream advisories.

**Dependency metadata/configuration:** browser requirements, the transport's
Playwright extra, and the library development bound now state
`filelock>=4.2.1,<5`; library and template locks select exactly 4.2.1.
The two rebuilt wheels retain their unpublished candidate versions. Their 36
Python source files are unchanged. No prompt or browser lifecycle code changed.
The library correction is committed as
`9e2a686ddbb472b5c4ac8f286b8622b5fadd91a1`.

Owner-run installed validation with 4.2.1 passed **377 Windows tests, 1 headed
platform skip in 78.03s**, and **373 Linux tests in 44.81s**, including headed Xvfb
browser lifecycle tests. The Windows run includes the unchanged five downstream
workspace-agent tests with SDK 0.5.11 and Runtime 0.3.22. Locks, timeout retirement,
scope cleanup and browser ownership remain covered. These targeted runs covered
transport unit/contract suites, but excluded its top-level metadata-test file;
that omission was exposed by full CI as documented next. The first Linux collection
attempt mounted tests without the package metadata; the corrected read-only
package mount resolved collection without changing assertions. Evidence is under
`library/.tmp/filelock-security/`, including `windows.xml`, `linux.xml` and the
retained `linux-mount-error.xml`.

Subsequent full library CI exposed one stale metadata-test expectation:
`tests/test_browser_session_import.py` still expected the old filelock range.
The CI owner corrected that one literal to the approved range and reports
**6/6 tests passed**, plus clean Ruff and diff checks. Independent source review
approved the exact expectation update. No production artifact bytes changed.
The original Ubuntu CI result was 3,017 passed, 36 skipped, 8 deselected and that
single failure; final CI status remains a release check.

## Final patched template installed gate

The final candidate was installed with `uv sync --all-extras --frozen --no-editable`
after `uv lock --check`. The installed interpreter confirmed filelock 4.2.1.
The complete template suite ran in isolated import mode against installed code:

- **177 passed, 4 Linux-only ordinary-symlink controls skipped on Windows in
  46.84s**; one upstream Starlette deprecation warning.
- Ruff check passed; Ruff format checked **65 files** without changes.
- Strict Pyright: **0 errors, 0 warnings**.
- Importlinter: **1 contract kept**, 28 files and 60 dependencies analyzed.
- Deptry: **20 files checked**, no dependency violations.
- Manifest parity: **3 actions, 4 tools, 1 pipeline**.
- Framework wheel verification passed; **590 installed framework archive members**
  byte-matched the declared noneditable artifacts.
- `uv pip check`: **71 packages compatible**; `git diff --check` passed.
- Installed dependency advisory audit: **60 public dependencies, zero known
  vulnerabilities**. Eleven private packages could not be looked up on PyPI;
  they remain subject to source and artifact review, not an advisory-clean claim.

Evidence under `template/.data/minimal-validation/`:
`template-final-patched-suite.xml`, `final-patched-installed-verification.json`
and `final-patched-dependency-audit.json`. An initial audit invocation used options
not supported with path mode and stopped before scanning; the supported path-mode
rerun completed successfully.

The final candidate hashes in `vendor/wheels/cohort.json` are:

| Final candidate artifact | SHA-256 |
| --- | --- |
| SDK 0.5.12 | `e795edffb06d44b00e26a2632746b8dc51ea200a4a71660c1e16a4cd23a13b51` |
| Runtime 0.3.23 | `7af8a675121ded2ed9dbb6b25b65ed8b4022a546a4e9ef82a628bb5528d563cb` |
| browser 0.1.1 | `c48519ca18e460433f1a1afea076b888cbbbaf9962f9067c435b020925aac5be` |
| browser transport 0.1.0 | `9ce9373b07bf8b45a4008ff9cdf9b3fbee502daf5451e24c67370f1315773f70` |

Core, execution, filesystem, memory and shell hashes remain those in the earlier
neutral-provider table. The 590-file final check covers this entire cohort.

## Final AgentDB maintenance closure

The independent policy reviewer confirms **18 maintained AgentDB test/fixture
files**, not 18 production changes. The last two are
`tests/workspace/ci-suite-wiring.meta.test.ts` and
`tests/workspace/postgres-baseline.unit.test.ts`. They update suite/migration
counts and explicitly assert that the new policy suite remains included in normal
and cold PostgreSQL coverage. The final AgentDB commit
`1848071e3fb1feb83516640ae64cbfaa52b765c9`,
[PR 309](https://github.com/osnova-gmbh/agent-db/pull/309), contains 31 intended files
overall; the 18-file number is the reviewer's maintenance subset.

Reviewer-reported final gates: unit **418/418**, contract **197/197**, architecture
**5/5**; build, PostgreSQL pilot typing, lint and static checks passed. Formatting
passed with private `.tmp/artifacts` excluded. These results are attributed to
that reviewer, not independently rerun by the browser-validation owner.

No unresolved source must-fix was found in this final review. **Release and live
behavior acceptance remain pending** the root-owned
[dynamic-tools-live-acceptance.md](dynamic-tools-live-acceptance.md) and final CI.
This report does not infer unfamiliar-portal reasoning, login reuse or durable
continuation from unit tests or scripted capability probes.


## Continuation-v2 final candidate

This addendum supersedes the earlier Runtime wheel and pending live-acceptance
status, while retaining earlier findings and test history. The final Runtime0.3.23
wheel is `a6df5e900a90debe4c949092ca2bc37f4c80d1eba0d34453b5fb6cb6caa589ad`,
from reviewed production source `c95d0be4020803cb419ad17b1f2b26b7680c817a`.
The policy module pin is `141e0989cbf89d08052db9c578cf4e083d41f63754e7ec91000069bc8b72ab80`
and requires AgentDB schema202. SDK and provider wheel bytes remain unchanged.

Root reran the complete installed template gate after this update:177passed,
4platform skips; strict typing, formatting, import/dependency boundaries,
manifest/action-contract parity and wheel verification passed. Windows verification
compared592 framework members; the fresh Linux agent image compared635 members,
including the cloned agent wheel, from read-only mounts with networking disabled.

The independent journal review verifies source/security boundaries, adversarial
codec and real PostgreSQL negatives, retained connections across201→202, and an
installed worker/API crash-replacement proof. Final hosted regression wiring keeps
the existing generated client pinned while separately loading the exact202 server
source. No checks were weakened to pass the new protocol.

The final real-model binary-original collection and fresh-worker login reuse
both passed; the generated child SDK agent also passed tests and Runtime invocation.
See `dynamic-tools-live-acceptance.md`, `dynamic-tools-live-independent.md` and
`dynamic-tools-journal-independent.md` for exact evidence and scope. The user browser
and working invoice processor were not touched by this feature's work.
