# Spec: cogit-agent-template

_Status: this document retains the v0 design baseline from 2026-07-11.
The current template runs against AgentDb. `README.md` and `docs/` describe
the shipped operation._

_The default descriptor pins the reference-domain AgentDb module and selects
a deterministic queue pipeline. `scripts/enable_database.py` can generate a
reduced descriptor for that pipeline. The agent distribution owns its domain
SQL, contracts and catalog. AgentDb applies the approved module migrations in
the tenant schema, owns the durable state and admits work. Runtime executes the
published worker cohort and invokes fenced module exports.
See [database-example.md](docs/database-example.md) for the shipped setup,
authenticated generated-client admission, packaging and recovery contract._

The local implementation depends on SDK/runtime commits that are ahead of their
remote `main` branches. Publish those dependency commits and refresh `uv.lock`
before tagging the template.

Related: [definitions.md](./definitions.md) ·
[01-spec-cogit-agent-sdk.md](./01-spec-cogit-agent-sdk.md) ·
[02-spec-cogit-runtime.md](./02-spec-cogit-runtime.md) ·
[04-spec-cogit-library.md](./04-spec-cogit-library.md) ·
[05-spec-cogit-org-sdk.md](./05-spec-cogit-org-sdk.md) · background in
[brainstorm/](./brainstorm/).

---

## 1. Purpose and position

`cogit-agent-template` is the repository that gets **cloned to create every
resident business agent**. The clone *is* the agent: the agent lives inside
this repository — its code, prompts, config, evals, docs, and local run setup
— while exposing the standardized runtime API to the outside world.

There is exactly **one** template. No level-2/level-3 variants, no
resident-agent flags. Every generated agent is a resident agent with the full
surface (query, runs, actions, queue/email handling, introspection, evals,
improvement) because the surface comes from `cogit-runtime` and
`cogit-agent-sdk`, not from the template. Simple agents simply implement fewer
hooks.

The template is deliberately **thin**. Its job is to be the smallest correct
skeleton around the runtime:

> The template contains the agent's *identity and domain*: one `CogitAgent`
> implementation/facade, its actions/tools, pipelines, loop hooks, prompts,
> manifest, evals, migrations, and docs. Everything generic is imported:
> the model abstraction and one agentic loop from `cogit-agent-sdk`; server,
> workers, auth, sessions, persistence, and deployment from `cogit-runtime`.

If a file in a generated agent repo would be identical in every other agent
repo, it belongs in the runtime (code) or is generated (CI/docker), and its
presence in the template must be justified as configuration, not logic.

### 1.2 Relationship to the runtime: interface, not fork

The agent interfaces with the runtime in exactly three places:

1. **SDK agent facade/contract** — `class Agent(CogitAgent)` (or the
   language-equivalent SDK agent implementation) declares tools, pipelines,
   model/loop configuration, and hooks.
2. **Factory** — `CogitRuntimeApp.from_manifest("cogit.yaml",
   agent_class=Agent).build()` in a five-line `main.py`.
3. **Manifest** — `cogit.yaml` declares what the runtime should mount,
   consume, store, and enforce, and what the SDK loop should use as default
   model/tool/pipeline policy.

Nothing else. A generated repo importing `fastapi`, `uvicorn`, `httpx`, or a
provider SDK in `src/` is malformed (runtime spec §18).

### 1.3 Who instantiates it

- **Humans**: `git clone` + rename (v0), later `cogit capability init`.
- **Cogit SaaS / Foundation**: the software factory creates a repo from the
  template when a customer's agent needs its own residency. The Foundation's
  build/rework API is out of scope here; the template just has to be
  factory-legible (§9).
- **Supervisor agents** never instantiate templates; they *talk to* the
  resulting agents over the runtime API and remain DB-resident ADK agents in
  Cogit SaaS.

---

## 2. Modeled after BCBI

BCBI (`C:\ai\_experiments\bcbi`) is the closest existing thing to a resident
agent done right: FastAPI app with lifespan-wired dependencies, an internal
Anthropic tool-use loop with cost/iteration budgets, a typed query interface,
a registry of domain functions, local knowledge + cache persistence, and a
black-box eval harness with ground-truth capture. The template is the
generalization of that repo with the generic parts extracted into the
runtime. The mapping is explicit, so BCBI itself can be re-hosted onto the
template with minimal movement (runtime acceptance test 1):

| BCBI today | Template equivalent | What changed |
| --- | --- | --- |
| `src/main.py` (FastAPI app, lifespan, `/query`, `/health`, CLI) | `src/{agent}/main.py` — 5 lines calling `CogitRuntimeApp` | server/endpoints/CLI come from runtime |
| `src/app.py` (`AppState`, `create_app_dependencies`) | `src/{agent}/dependencies.py` — domain deps only (connectors, caches) wired in `Agent.configure()` | generic deps (client, stores, sessions) provided by runtime |
| `src/agent/core.py` (`BCBIAgent.process_query` loop, budgets, token tallies) | `src/{agent}/agent.py` — `Agent(CogitAgent)` configuring SDK loop + `system_prompt()` | the LLM/tool loop moves to `cogit-agent-sdk`; runtime hosts it; budgets come from manifest/request |
| `src/agent/tools.py` (`TOOL_DEFINITIONS`, `dispatch_tool`, `data_ref` registry, entity contracts) | `src/{agent}/actions/*.py` — `@action(..., as_tool=True)` typed handlers | declaration + tool scheduling are SDK; runtime policy hooks enforce; only handlers remain |
| `src/agent/prompts.py` (`build_system_prompt` from entity/function contracts) | `src/{agent}/prompts/` + `Agent.system_prompt(ctx)` | same pattern, now a hook |
| `src/analytics/registry.py` + `functions/` | `src/{agent}/domain/` — domain function registry stays agent-side (it *is* domain) | unchanged in spirit; may be seeded from a library function pack |
| `src/components/specs.py` | `src/{agent}/schemas/` — typed domain outputs | component specs are domain content (SDK keeps `components` as passthrough) |
| `src/integrations/business_central/` | `src/{agent}/integrations/` | domain integrations stay agent-side |
| `src/knowledge/` (Chroma store + populate/ingest) | manifest `persistence.stores: vector_index` + `src/{agent}/knowledge/` ingestion code | store handle from runtime; ingestion logic stays |
| `config.yaml` + `.env` (`BCBI__` prefix) | `cogit.yaml` + `.env` | one manifest format for all agents |
| `evals/` (runner, capture, comparator, ground truth, HTML report) | `evals/` — same layout, rebuilt on the SDK evaluator contract and black-box agent facade | harness machinery from SDK/runtime; eval items/ground truth stay |
| `bcbi` CLI (`serve`, `ingest`, `ask`) | `cogit-runtime serve/work/eval` + agent-defined extra commands | generic commands from runtime |
| degraded-mode boot | runtime `/health` component reporting | free |

OPERA contributes the second archetype the template must support without
modification: the **domain product** whose heavy work is a deterministic
pipeline (12-phase discovery, YAML-declared function registry, per-run audit
trail) and whose agentic layer sits on top. Such an agent implements
`handle_run` by invoking its pipeline modules and exposes pipeline phases as
actions; the audit trail comes free from the runtime's execution log. The
optimizer/simulation surfaces (`opera optimize/simulate` specs) map onto the
improvement plane rather than requiring anything extra in the template.

---

## 3. Repository layout

```text
cogit-agent-template/                     # cloned → my-agent
  README.md                               # run story (§7) — kept accurate, always
  cogit.yaml                              # THE manifest (§6)
  pyproject.toml                          # deps: cogit-agent-sdk, cogit-runtime
                                          # (pinned majors), domain deps only
  .env.example                            # every env var with placeholder + comment
  Dockerfile                              # runtime image recipe (§7.2)
  docker-compose.yml                      # agent + postgres (+ optional chroma) (§7.1)
  .github/workflows/
    ci.yml                                # lint + typecheck + tests + eval smoke +
                                          # image build (§10)
  .cogit/                                 # agent-legibility layer (§9)
    start-agent.md                        # how an AI agent works on THIS repo
    context.md                            # domain context, decisions, state
    commands/                             # repo-local command playbooks
  src/{{agent_package}}/
    __init__.py
    main.py                               # 5 lines (§4)
    agent.py                              # Agent(CogitAgent) (§5)
    dependencies.py                       # domain dependency factory
    actions/
      __init__.py
      example_lookup.py                   # read action, exposed as tool (deletable)
      example_write.py                    # approval-gated write action (deletable)
    prompts/
      system.md                           # base system prompt (template vars ok)
      fragments/                          # composable prompt parts
    domain/                               # domain functions/registries (BCBI
      __init__.py                         # analytics-registry slot; often empty
    schemas/                              # agent's own Pydantic domain models
      __init__.py
    integrations/                         # domain system clients (BC, ERP, ...)
      __init__.py
    knowledge/                            # local knowledge ingestion (optional)
      __init__.py
  src/cogit_finance/database/           # optional approved AgentDb resources
    manifest.json                         # immutable package/export references
    migrations/                           # ordered domain SQL applied by AgentDb
    contracts/                            # typed operation/settings contracts
    catalog/                              # registered resources and actions
  evals/                                  # §8 — the agent's own judgment layer
    config.yaml
    ground_truth/
      smoke.jsonl                         # 3 example cases, deletable
    evaluators/
      __init__.py
      structural.py                       # process/trace evaluator (reference impl)
      extraction.py                       # field-comparison evaluator (reference)
      llm_judge.py                        # LLM-judge evaluator (reference)
    README.md
  tests/
    conftest.py                           # FakeCogitClient + agent fixtures
    test_agent_boot.py                    # manifest loads, app builds, /health ok
    test_example_actions.py
  docs/
    architecture.md                       # this agent's domain design (stub)
```

Explicitly **absent** (and must stay absent): auth middleware, session code,
hand-written LLM/tool turn loops, queue worker, provider adapter code,
execution-log writers, generic eval machinery, base classes. All imported.

---

## 4. `main.py` — the whole wiring

```python
from cogit_runtime import CogitRuntimeApp
from {{agent_package}}.agent import Agent

app = CogitRuntimeApp.from_manifest("cogit.yaml", agent_class=Agent).build()
```

That is the entire file. `build()` gives the agent: `/health`, `/manifest`,
`/query`, `/runs`, `/runs/{id}`, `/runs/{id}/events`, `/actions/*`,
`/sessions/*`, `/introspection/*`, `/evals/*` — all typed by the SDK, all
authenticated, all logged (runtime spec §5).

## 5. `agent.py` — what a developer (or the factory) actually writes

```python
class Agent(CogitAgent):
    async def configure(self, deps):  # boot: connect domain systems
        self.bc = await deps.build_bc_connector()  # from dependencies.py
        await self.knowledge_bootstrap()  # optional: populate vector store

    def system_prompt(self, ctx):  # BCBI pattern: prompt assembled
        return render(
            "prompts/system.md",  # from machine-readable contracts
            entities=self.bc.entity_contracts(),
            functions=self.domain_registry.contracts(),
            today=ctx_now(ctx),
        )

    def loop_hooks(self, ctx):  # product/domain policy, not a loop
        return LoopHookSet(
            transform_messages=self.trim_domain_context,
            after_tool_call=self.redact_domain_payloads,
        )

    @action(
        id="lookup_order",
        risk="read",
        as_tool=True,
        description="Fetch an order with lines by number",
    )
    async def lookup_order(self, req: LookupOrderIn, ctx, run) -> LookupOrderOut:
        with run.step("TOOL", "lookup_order"):
            return await self.bc.get_order(req.order_no, tenant=ctx.tenant_id)

    @action(id="create_credit_note", risk="financial", approval_required=True)
    async def create_credit_note(
        self, req: CreditNoteIn, ctx, run
    ) -> CreditNoteOut: ...  # blocks on approval via run handle
```

Email-type queue items arrive as ordinary runs (the runtime translates them,
runtime spec §11); an agent that must handle email deterministically binds a
pipeline to the `email` item type in its manifest (definitions.md §9) instead
of implementing a special hook.

Hooks not implemented simply use SDK defaults. The manifest/OpenAPI reflect
only declared capabilities. `handle_query` and `handle_run` default to the SDK
loop over the agent's tools/pipelines — hosted by the runtime in production.
A BI-style agent like BCBI often writes **no** handler code at all beyond
actions, pipeline declarations, optional loop hooks, and the system prompt.

### 5.1 `dependencies.py` — domain dependency factory (rough draft)

```python
class AgentDependencies:
    """Domain-only construction. Generic dependencies (stores, client,
    model, reporter) come from the runtime — never built here."""

    def __init__(self, settings: AgentSettings): ...  # typed env/domain config

    async def build_bc_connector(self) -> BusinessCentralConnector: ...
    async def build_domain_registry(self) -> DomainFunctionRegistry: ...

    # caches, ERP clients, local vector store, ... — whatever the domain needs
```

Compatibility: this is BCBI's `create_app_dependencies()` composition-root
pattern with the generic half removed — BCBI builds its Anthropic client,
Chroma store, and BC connector in one place; here the model client and stores
are the runtime's job and only domain connectors remain. The `domain/`
registry slot mirrors BCBI's analytics function registry and OPERA's
`stat_functions.yaml` (declared functions with applicability contracts, so
prompts can be assembled from machine-readable capability lists).

---

## 6. `cogit.yaml` — the manifest (full v0 schema)

Typed by the agent SDK's manifest loader (`cogit.yaml` → `AgentDescriptor`,
SDK spec §5.1); validated on boot, in CI, and at registration. Everything
the SDK loop should know, and everything the runtime mounts, consumes, stores,
or enforces, is declared here — the factory writes this file from the build
spec, humans review it.

```yaml
name: my-agent
version: 0.1.0
description: One-paragraph statement of the agent's job.
sdk_version: ">=0.1,<1"
runtime_version: ">=0.1,<1"

model:
  provider: anthropic
  adapter: sdk-anthropic       # SDK ModelClient adapter; runtime may inject prod wiring
  id: claude-sonnet-4-20250514
  temperature: 0.2
  max_tokens: 8192
  budget:                      # SDK loop enforces turn/tool/model budgets;
                               # runtime enforces lifecycle wall-clock bounds
    max_iterations: 25
    max_cost_usd: 10.0
    max_duration_seconds: 900
  # fallbacks: [ ... ]         # optional ModelClient failover policy

capabilities:
  query: true                  # mount POST /query
  runs: true                   # mount POST /runs (sync+async)
  queue: true                  # start the queue worker
  email: true                  # consume email-type queue items (translated to runs)

pipelines:                     # deterministic intra-agent flow (definitions.md §9)
  - name: email-intake
    applies_to: [email]
    steps:
      - {id: extract,  kind: deterministic, invoke: extract_document}
      - {id: validate, kind: deterministic, invoke: validate_fields}
      - {id: resolve,  kind: agentic, instruction: "Resolve and respond."}

loop:                          # SDK loop policy; product/domain hooks by name
  terminal_tools: []           # e.g. submit_verdict for evaluator-style agents
  budget_warnings: {half: true, critical_turns_remaining: 2}
  hooks:
    transform_messages: default
    after_tool_call: redact_and_truncate

queues:
  - queue: email-intake
    item_types: [email]
  - queue: my-agent-tasks
    item_types: [followup_due, document_received]

mailboxes: [main-inbox]        # platform mail-connection names (secrets stay
                               # platform-side; intake is the email connector)

tools:                         # SDK tool exposure + runtime policy hooks (§10.4)
  allow_by_trigger:
    email: [lookup_order, search_knowledge]
    queue: "*"
    improvement: []            # improvement runs get no domain tools

database_packages: []          # optional SDK references; generated example pins
                               # module/version/digest/export/contract identities.
                               # No schema-per-agent or worker database credentials.

evals:
  suites:
    - {name: smoke,      kind: structural, gate: {min_pass_rate: 1.0}}   # CI gate
    - {name: extraction, kind: extraction, gate: {min_pass_rate: 0.95}}
  immutable_for_improvement: true    # enforced by runtime sandbox + CI (§8.3)

schedules:                     # desired platform schedules; applied at registration
  - {name: daily-digest, interval_seconds: 86400, prompt: "Produce the daily digest."}

contracts: []                  # published data contracts (brainstorm/05), when needed

runtime:                       # RuntimeConfig overrides (worker concurrency,
  worker: {concurrency: 4}     # session window, trace persistence, rate limits)
  trace: {persist_messages: false}
```

---

## 7. The run story

Prepare the exact root `cogit.yaml` and agent wheel with
`scripts/worker_cohort.py prepare`. An authorized AgentDb operator initializes
the application, installs the pinned database module, publishes the cohort
and returns the identifiers needed to create the bound receipt.

The worker uses the published receipt and the deployment's scoped worker
token. Start it with `cogit work --project . --environment`, or build the
worker image and start Compose after publishing that image's prepared
cohort. Submit runs through the AgentDb admission API. The default queue
pipeline commits and reads a business row, then publishes its result through
the canonical run handle. See [the deployment example](docs/database-example.md).

## 8. Evals in the template

Evals are the agent's **hyper-local, user-editable judgment layer** — they
live here, not in the runtime and not in the platform, because every agent's
definition of correct is different (concept-paper requirement).

- `evals/ground_truth/*.jsonl` — eval items (repo-owned fixtures; the SDK
  deliberately does not type the fixture format, only the resulting
  `EvalRecord` — definitions.md §19). Editable by the customer/operator;
  reviewed like code. Rough draft of one item (one JSON object per line):

```text
# evals/ground_truth/smoke.jsonl
{"id": "smoke-001",
 "input": {"query": "revenue by region last quarter"},
 "expected": {"entities": ["sales_orders"],
              "functions": ["aggregate_by"],
              "components": ["bar_chart"]},
 "weights": {"entities": 0.4, "functions": 0.3, "components": 0.3},
 "category": "analytics", "difficulty": "easy"}
```

  Compatibility: this is BCBI's ground-truth JSONL format kept nearly as-is —
  weighted per-check expectations, category/difficulty tags for breakdowns —
  so BCBI's existing suites port with a field-rename pass, not a rewrite.
- `evals/evaluators/*.py` — implementations of the SDK evaluator contract
  (SDK spec §10.3). Three reference
  implementations ship with the template, matching the three families:
  - `structural.py` — process-based: asserts which tools/entities/actions the
    trace used (BCBI's `observed_signature` weighted checks).
  - `extraction.py` — field-by-field comparison against expected structured
    output (invoice-processor regime: ~100 docs/day, 0–5 errors tolerated,
    per-field weights).
  - `llm_judge.py` — rubric-scored judgment for RAG/free-text answers
    (customer-support regime).

  Skeleton of a reference evaluator (rough draft):

```python
class StructuralEvaluator(CogitEvaluator):
    suite = "smoke"

    def load_items(self) -> list[EvalItem]:  # EvalItem = repo-local shape
        return read_jsonl("evals/ground_truth/smoke.jsonl")

    async def evaluate_item(self, item, agent: BlackBoxAgent) -> EvalItemResult:
        result = await agent.query(item.input["query"], include_trace=True)
        observed = signature_from_trace(result.trace)  # tools/entities used
        checks = [
            score_check(k, observed, item.expected, item.weights) for k in item.expected
        ]
        return EvalItemResult(
            item_id=item.id,
            passed=all(c.passed for c in checks),
            score=weighted(checks),
            checks=checks,
        )
```

  `BlackBoxAgent` is the SDK's HTTP facade — the evaluator physically cannot
  import agent internals (runtime §13.1). `EvalItemResult`/`CheckResult` are
  the SDK types from definitions.md §19; only the fixture shape is repo-local.
- Ground-truth capture: `cogit-runtime eval --capture --suite X` replays eval-item
  inputs against the live agent and writes candidate expectations for human
  review (BCBI's capture workflow, standardized).
- **Independence**: evaluators see the agent only through the SDK black-box
  agent facade (HTTP).
  The eval runner is a separate process (runtime §13.1). Results go to the
  platform via `client.evals.report`, so supervisors and the improvement
  plane read the same history the developer sees.
- **Immutability for improvement**: `evals/` is read-only inside improvement
  sandboxes and CI rejects `evals/` diffs on `autoresearch/*` branches
  (runtime §14). The agent may propose eval changes only as
  `needs_human` proposals. Custom evals are why the meta-evaluator exists
  (runtime §13.3) — that seat is the runtime's, not the template's.

## 9. `.cogit/` — agent legibility

The repo must be workable by AI agents (factory builds, improvement runs,
operator assistants), which is a documentation contract, proven in OPERA:

- `start-agent.md` — entry point: what this agent does, how to run/test/eval
  it, what is immutable, current sprint state.
- `context.md` — domain context and decisions log, updated by whoever (human
  or agent) changes the repo.
- `commands/` — playbooks (assess, implement, validate, session-end) so
  factory/improvement agents behave consistently across all agent repos.

The template ships these pre-filled with the generic skeleton; the factory
fills in domain specifics at generation time.

## 10. CI and code discipline

`ci.yml` stages: `ruff check` + `ruff format --check` + `pyright` (strict) →
`pytest` (FakeCogitClient, no network) → import contracts + deptry →
**boot smoke** (compose up, the four §7.1 curls) → **eval smoke**
(`cogit-runtime eval --suite smoke`, gate `min_pass_rate: 1.0`) → image
build. Eval gates from the manifest are CI-enforced: an agent whose smoke
evals fail does not ship. The template repo itself runs this same CI against
the example agent on every template PR (the "template smoke test").

### 10.1 Typing and lint discipline (shipped, not optional)

The template ships the SDK/runtime toolchain (SDK spec §12.1) preconfigured
in `pyproject.toml`, and the generated repo inherits it on day one — the
factory and improvement agents that work on this repo need compiler-grade
feedback, and in Python that feedback only exists if the gates ship with the
scaffold:

- **Pyright strict over `src/` and `evals/`**, zero errors on the unmodified
  template. Suppressions only as `# pyright: ignore[ruleCode]` with a
  justification; bare `# type: ignore` fails lint.
- **Ruff** with the strict shared profile (bugbear, comprehensions, asyncio
  rules, import sorting, complexity caps) plus `ruff format`. One config,
  same as SDK and runtime — an improvement agent moving between repos meets
  identical rules everywhere.
- **Typed domain code is not exempt.** Action inputs/outputs are typed models
  (`LookupOrderIn/Out` in §5 — never raw dicts); domain enums are
  `Literal`/`Enum` with `assert_never` handling; connector edges parse
  external payloads into `schemas/` models immediately (the BCBI pattern:
  its typed request/response models are why re-hosting it is mechanical).
- **Import Linter ships in the template** enforcing the agent-repo rules
  mechanically: `src/` must not import `fastapi`, `httpx`, `requests`,
  provider SDKs, or `cogit_runtime` internals (only its public composition
  API) — the §13 grep-clean acceptance as a permanent local gate, not a
  one-time check.
- **`make check` (or `uv run check`)** runs the identical gate set locally.
  `.cogit/start-agent.md` instructs every agent to run it before ending a
  session — the improvement plane's mutate-and-measure loop treats a failing
  gate exactly like a failing eval.
- The eval layer is held to the same standard: evaluators are typed against
  the SDK contract, and fixtures are validated (JSONL rows parsed into the
  repo's eval-item model at load, so a malformed ground-truth line fails the
  suite loudly, not silently skips).

## 11. Template evolution and versioning

- Template repo is versioned by tags; a generated repo records its origin in
  `.cogit/template-version`.
- Generated repos do **not** rebase on the template. Generic improvements
  reach them through `cogit-agent-sdk`/`cogit-runtime` version bumps (which is why
  the template must stay thin — thin template ⇒ upgrades are pip bumps, fat
  template ⇒ unmergeable forks).
- v0 instantiation is clone-and-rename with a `bootstrap.py` that renames
  `{{agent_package}}`, rewrites `cogit.yaml`, and re-inits git. Copier-based
  templating is a later upgrade if variable count grows.

## 12. Learnings applied

- **BCBI**: the whole shape (§2) — dependency factory, budgeted loop, typed
  query, contracts-in-prompt, black-box evals, degraded boot. The template is
  BCBI with the generic 70% moved into the runtime.
- **OPERA**: `.cogit/` legibility layer; deterministic-pipeline agents as
  first-class (domain modules + actions, audit for free); improvement-plane
  compatibility (immutable evals/weights, mutate-and-measure on branches);
  YAML-declared domain registries (as library function packs feeding
  `domain/`).
- **ai_org**: what happens without a template — 1,641-line base class
  accreting NFON case IDs, Lexoffice prompt rewrites, and tool alias maps;
  session state as JSON files next to code; agents defined by config rows
  with no tests, no evals, no docs. Every rule in §1.2/§3 exists to make that
  structurally impossible.
- **Invoice processor**: financial writes behind `approval_required`;
  extraction evals with per-field weights; domain tools (Lexoffice, NFON,
  sheets matching) belong in *this* repo layout, ending their squat in shared
  ai_org code.
- **Order processor / customer support**: config-only agents **stay on
  reusable service backends** (SDK spec §10.5) — the template is for agents that
  earn a repository; knowledge-heavy support-style agents use the
  `vector_index` store + `search_knowledge`-style read actions.

## 13. v0 scope and acceptance criteria

In scope v0: everything above except Copier templating, contract publishing
(manifest field exists, empty), and improvement-loop execution (surfaces
present via runtime; orchestration later).

Acceptance:

1. Fresh clone → `cp .env.example .env` (one provider key) → `docker compose
   up` → all four §7.1 smoke calls succeed. Time budget: under 10 minutes on
   a clean machine.
2. `uv run pytest` and `cogit-runtime eval --suite smoke` pass offline (no
   platform, no domain systems) on the unmodified template.
3. BCBI re-hosted on the template reproduces its `/query` behavior with only
   `agent.py`, `actions/`, `domain/`, `integrations/`, `prompts/`, `evals/`
   populated (runtime acceptance 1 witnessed from the template side).
4. Registration against a dev Cogit SaaS creates the `AgentRecord`, applies a
   declared schedule, and a scheduled `POST /runs` lands in the admin
   Execution Logs UI.
5. Grep-clean: no `fastapi`/`httpx`/provider imports under `src/`; no domain
   words in anything imported from `cogit_runtime` — enforced by the shipped
   import-linter contract, not just grep.
6. Static gates (§10.1) pass on the unmodified template: pyright strict at
   zero errors, ruff clean, import contracts and deptry green via one local
   `make check` identical to CI.

## 14. Open questions

1. **Bootstrap ergonomics** — `bootstrap.py` rename script vs Copier from
   day one. Recommendation: script v0, Copier when the factory needs
   parameterized generation.
2. **Local platform emulator** — is the runtime's platform-less mode enough
   for development, or do we ship a `cogit-dev-platform` compose service
   (tiny FastAPI faking the platform API)? Recommendation: platform-less mode
   first; emulator only if template tests keep needing more platform surface.
3. **Frontend slot** — BCBI ships a React frontend; does the template carry
   an optional `frontend/` for direct-UI agents, or is UI always
   platform-side (screens/components via `QueryResult.components`)?
   Recommendation: no frontend in the template; revisit with the dynamic
   interfaces workstream.
4. **Example agent domain** — the template's built-in example should be small
   but real. Candidate: a tiny "knowledge + lookup" agent over a bundled
   AgentDb test deployment, so one read action, one gated write action, and
   all three evaluator kinds are demonstrated end-to-end.
