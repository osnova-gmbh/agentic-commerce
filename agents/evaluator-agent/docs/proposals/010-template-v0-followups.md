# Proposal 010 — Template v0 Follow-ups

_Status: gap-closure PR open against feat/gap-closure-008. Depends on
Proposal 008 (implemented, PR #1 merged)._

## 1. Status summary

P008 implemented the reference-agent template and merged as PR #1. This
document records the gap closure performed in the follow-up PR and the
residual dependency gaps that remain in owning repositories. Each gap is
traced to the task that closed it or to the upstream package that still
owns the open item.

## 2. Gap inventory

| Gap | Owning area | Status after this work | Evidence |
|-----|-------------|------------------------|----------|
| Smoke-only evals | template | Closed (Task 1) | `evals/task.json` added; `cogit.yaml` lists `[smoke, task]` |
| No negative-approval test | template | Closed (Task 2) | `test_gated_write_denial_does_not_apply` added |
| No bootstrap test | template | Closed (Task 3) | `tests/test_bootstrap.py` added |
| PowerShell-only tooling | template | Closed (Tasks 4 + 6) | `scripts/check.sh` added; README bash examples added |
| Split import boundary | template | Closed (Task 5) | `.importlinter` widened to whole `evaluator_agent` package + `anthropic`/`openai`; `cogit_agent_sdk.providers` enforced by AST test (import-linter cannot express external subpackage paths) |
| `system_prompt()` not wired into `DefaultLoopHooks.convert_to_model` | cogit-agent-sdk | Open | P006 D7; runtime implements it internally but SDK defaults do not |
| Action->tool bridge / CompositeLoopHooks / manifest parity not public SDK API | cogit-agent-sdk | Open | P006 D4/D5/D6; runtime implements internally; SDK defaults do not compose them |

## 3. What this PR closes

1. **Task 1 — Task-fulfilment eval suite.** Added `evals/task.json` with four
   items (validate-valid-request, validate-invalid-request, lookup-known-record,
   pipeline-resolves-case) and `tests/test_eval_task.py`. Updated `cogit.yaml`
   `eval_suites` to `[smoke, task]`.
2. **Task 2 — Denial-path approval test.** Added
   `test_gated_write_denial_does_not_apply` to
   `tests/test_runtime_integration.py`, asserting that a denied approval never
   mutates `applied_resolutions`.
3. **Task 3 — Bootstrap test.** Added `tests/test_bootstrap.py` that copies the
   repo to `tmp_path`, runs `bootstrap.py`, and verifies the renamed package
   passes `validate_action_parity`.
4. **Task 4 — Bash local gate.** Added `scripts/check.sh` mirroring
   `scripts/check.ps1` for bash/darwin/linux environments.
5. **Task 5 — Unified import boundary.** Widened `.importlinter`
   `source_modules` to the whole `evaluator_agent` package and added
   `anthropic` and `openai` to `forbidden_modules`. `cogit_agent_sdk.providers`
   cannot be expressed as an import-linter forbidden module — the tool raises a
   hard error for subpackage paths of external packages
   (`ValueError: subpackages of external packages are not valid`). The
   `cogit_agent_sdk.providers` boundary is enforced by the existing AST test in
   `tests/test_contract.py`, which is the authoritative check for this path.
6. **Task 6 — Bash README examples.** Added bash code blocks alongside every
   PowerShell example in `README.md`.

## 4. Ordered follow-ups

(a) **Quality eval (L2)** once a non-echo model path is exercisable offline.
    The current eval suite runs against the echo provider; a model-backed
    variant would exercise prompt construction and tool-call parsing.

(b) **Worker crash mid-pipeline recovery test.** Verify that a worker that
    dies between pipeline steps resumes correctly on the next lease claim
    without replaying completed checkpoints.

(c) **CI container job** running `docker compose up` plus a four-command smoke
    sequence (migrate, serve, enqueue, eval) rather than only validating
    `compose.yaml` syntax.

(d) **Retry / multi-tenant isolation tests.** Confirm that queue retries do
    not leak state across tenants and that concurrent workers on different
    tenant IDs never observe each other's items.

## 5. Stop conditions (inherited from Proposal 009)

- Template must not need an undocumented runtime method.
- Runtime must not accept a manifest field it does not execute.
- Model and HTTP action paths must use the same handler.
