# Repository change summary

> Historical snapshot from an earlier review on 27 November 2026. The local escrow agents, catalog checkout, simulated bank and dashboard were implemented after this review. See README.md for the current runnable state.

Reviewed on 27 November 2026, using the local Git history and working tree.

The repository has progressed from an Alice/Bob identity demonstration plan to a detailed
Cogit Finance escrow specification, an interactive landing-page prototype, a parallel
implementation plan, and an animated explainer in progress. The transactional backend is
still planned; the landing page does not execute real escrow transactions.

## Committed changes

Current branch: `docs/spec-review-fixes`. Current commit: `70964da`.
The branch is one commit ahead of the locally recorded `main` at `db4a043`.

| Commit | Change |
| --- | --- |
| `9536331` | Initialized the repository with the README, Alice/Bob implementation plan, WSL/Boris handover, a diagnostics script, and Git configuration. |
| `0bd48a6` | Added the 486-line [escrow product specification](SPEC.md). |
| `db4a043` | Merged the escrow specification into `main` through pull request #1. |
| `70964da` | Refined evaluator failure handling, event idempotency, ledger uniqueness, and the corresponding acceptance criteria. |

### Escrow product specification

[SPEC.md](SPEC.md) defines:

- Separate buyer, seller, evaluator, and escrow roles. An operator such as Delta runs the
  escrow service; buyer and seller remain separate parties.
- A deal lifecycle covering quotes, acceptance, funding, delivery, evaluation, settlement,
  refunds, disputes, and timeouts.
- Signed messages using independent agent DIDs, an immutable message-type registry,
  authorization rules, replay checks, and delivery recovery.
- Three planned AgentDb modules for messaging, the company/offer/evaluator catalog, and
  deals. Deal storage includes an event hash chain, an outbox, payment intents, and ledger
  postings.
- Integer-cent accounting, seller-side fees, idempotent bank transfers, and reconciliation
  after uncertain payment responses.
- A simulated bank, a read-only operator dashboard, a 17-event successful deal, acceptance
  criteria, and implementation milestones. Affinidi integration is a separate optional
  milestone.

### Latest specification fixes

The changes in `70964da` affect only `SPEC.md`: 13 insertions and 11 deletions.

- Only evaluator `pass` and `fail` outcomes count toward the decision policy.
- An evaluator error or missed deadline triggers one re-request. A second failure moves
  the deal to `DISPUTED` with reason `evaluator_unavailable`.
- Evaluator infrastructure failures neither move money automatically nor consume a
  seller delivery attempt.
- Timer-driven and bank-driven commits receive idempotency keys derived from the deal
  head and the timer name or bank event ID.
- Ledger uniqueness applies to the combination of `source_id` and `account`, allowing
  separate account postings for the same source while preventing duplicate postings.
- The evaluator-failure acceptance criterion now covers errors as well as missing replies.

## Uncommitted changes

Before this summary was added, the working tree contained one modified tracked file and
30 untracked files. Nothing was staged.

| Path | Status and contents |
| --- | --- |
| [README.md](README.md) | Seven added lines introduce the visual product concept, its launch command, and a link to the escrow specification. |
| [PARALLEL-PLAN.md](PARALLEL-PLAN.md) | New implementation plan: six required work lanes plus an optional framework-port lane, exclusive file ownership, frozen interfaces, integration gates, fixtures, and explicit demo scope cuts. |
| [apps/landing/](apps/landing/) | 18 new files implementing the Cogit Finance landing-page concept, local assets, preview server, configuration, and tests. |
| [films/alice-bob-delta/](films/alice-bob-delta/) | 11 new files containing an explainer brief, character drawings, animation source, a bundled canvas engine, font, and licenses. Work is in progress. |

### Landing-page implementation

The landing page uses plain HTML, CSS, and JavaScript, with a dependency-free Node preview
server. It includes:

- A responsive product page explaining the buyer, seller, evaluator, and operator roles.
- A fictional EUR 1,250 market-research purchase between Northstar Studio and Fieldwork
  Labs, with a 1% operator fee.
- Successful-settlement and missed-deadline/refund scenarios, selectable lifecycle stages,
  and six-second play/pause/replay controls.
- A receipt dialog and downloadable illustrative JSON. Settlement allocates EUR 1,237.50
  to the seller and EUR 12.50 to the operator; a refund returns EUR 1,250 with no fee.
- Local fonts and graphics, mobile navigation, FAQs, keyboard interactions, and reduced
  motion styling.
- Type checking and browser tests for accounting, playback, downloads, accessibility,
  responsive layouts, navigation, and asset loading.

This is a working visual prototype. Its balances, evaluations, and receipts are generated
in the browser rather than connected to agents, AgentDb, or a bank.

### Explainer status

The film brief describes a 26-second story: Alice buys a research report from Bob, Delta
holds the payment, independent checks approve the report, and Bob receives payment.

The film sources were being edited during this review. The latest inspected `film.js`
defines a four-second `payment-contact-proof` scene. A browser smoke check raised:
`Morph needs corresponding points; use drawing substitution for topology changes`.
The complete storyboard and final export have not been verified.

## What remains to be implemented

This checkout does not yet contain the planned buyer, seller, evaluator, or escrow-agent
implementations; the three AgentDb modules; the simulated bank; or the live operator
dashboard. The parallel plan specifies those deliverables but does not implement them.
The existing identity documents also record that no end-to-end native DID authentication
exchange has been completed.

## Verification performed

- Inspected local branches, commit history, committed diffs, pending files, and source.
- `npm run check` in `apps/landing`: passed.
- `npm test -- --workers=2` in `apps/landing`: all 36 browser tests passed across desktop
  and mobile projects.
- `node --check` passed for the 11 repository JavaScript/module files inspected.
- Film browser smoke check: failed with the animation error recorded above.

This review adds only `CHANGE-SUMMARY.md`; it does not modify implementation files or
create a commit.
