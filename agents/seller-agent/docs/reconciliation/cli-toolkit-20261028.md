# Queued approval and toolkit reconciliation — 2026-10-28

This is a **package/configuration and documentation change**. It reconciles
the approval/bootstrap branch `dbd7e086871e6bd5f02613ea853be8d647d2c29c` with
upstream `e6413584f630bd3263651ec1e3cf865916a7e9b7` (toolkit PR31).
Business Python, prompts, action metadata, bootstrap logic and tests remain
unchanged from the reviewed approval branch.

The merged template remains **0.1.22**; no 0.1.22 tag existed at reconciliation.
It selects Runtime **0.3.29**, SDK **0.5.15**, client **0.2.13**, tool-core
**0.1.3**, and optional shell/browser **0.1.2**. The README states:

> The optional workspace profile selects shell and browser
> 0.1.2 for UTF-8 PowerShell handling and confirmed owned-browser cleanup.

The active frozen lock, package sources and `vendor/wheels/cohort.json` agree.
All **39 historical vendor assets** other than the active cohort/provenance
documents retain their exact Git blob identities. The two new toolkit archives
retain their upstream hashes and committed producer `b654e46b0da0bb43e1524ce8ede56118c9f334a7`.
Runtime's exact producer archive remains
`f440cf12d22bf1bbb8e443972c1ca0596de619c5a19c70eadc6248f1826029bd`.
Historical provenance sections are retained separately from the current merged
selection; no old wheel or immutable database module receipt was rewritten.

## Verification

- Framework cohort verification, frozen lock check and all-extras noneditable
  installation passed. Dependency consistency passed. Installed-byte verification
  compared **630 framework files** against the selected archives.
- `scripts/check.ps1 -SkipSync -SkipLiveEval -SkipImage` passed manifest/action
  parity, Ruff lint/format (**75 files**), strict Pyright (**zero errors and
  warnings**), import boundaries, dependency checks and the complete installed
  producer suite: **260 passed, 6 platform/privilege skips**. All eight bootstrap
  formatting cases ran and passed without a generated-tree repair.
- `uv build` produced the wheel and source distribution successfully.

These local checks used Python 3.14.6. Hosted CI independently checks the pinned
Python 3.11.16 Windows/Linux profiles, live smoke evaluation and production
container closure. No existing server, customer environment or grant was changed.

The primary template checkout's two pre-existing parallel-work documents were
not copied into this worktree or edited. Their before/after hashes are identical.
