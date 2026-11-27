# Cogit Finance — landing-page concept

A responsive, browser-ready sketch based on [`SPEC.md`](../../SPEC.md). It presents Cogit Finance as an **escrow tool for agent-to-agent commerce**, not a bank or a personal-finance assistant.

## Open the preview

From this directory, with Node.js 22 or newer:

```sh
npm start
```

Open **http://127.0.0.1:4173**. No dependency installation is needed to run the preview. The local server binds only to loopback and exposes an explicit list of public files, including the specification.

Alternatively, open `index.html` directly in a modern browser. All fonts, icons, and assets are local; there are no analytics, external runtime requests, or backend services.

## What's interactive

- Two sample paths: approved delivery → settlement; missed delivery deadline → full refund.
- Play/pause walkthrough: advances one stage every six seconds, stops at the outcome, and can be replayed. Playback is opt-in and pauses when the page is hidden or you use a manual control.
- Clickable lifecycle stages and next-step controls; pausing and playing resumes from the current stage.
- A receipt dialog and downloadable **unsigned, illustrative** JSON with integer-cent amounts.
- Responsive mobile navigation and expandable FAQ answers.

The fixed example is €1,250.00 with a 1% seller-side operator fee (€12.50). Escrow remains held until the simulated bank confirmation. A refund returns the full price and charges no fee.

This is a visual prototype, **not** an implementation of the finance agent, bank, cryptographic verification, evaluators, or AgentDb. Jumping between stages explores illustrations; it does not execute protocol transitions. The workspace controls are for the landing-page demonstration, not proposed write permissions for the read-only operator dashboard.

## Design direction

Warm off-white, forest green, pale sage, Manrope typography, technical micro-labels, and a product-first escrow illustration. An original layout informed by [Instalanding's Kestrel AI Finance example](https://instalanding.ai/prompt/kestrel-ai-finance-landing-page); no template code is copied. No invented customer logos, adoption metrics, regulatory approvals, or live-service claims.

Manrope is bundled under the SIL Open Font License; see `assets/OFL-Manrope.txt`.

## Verify

```sh
npm ci
npx playwright install chromium
npm run check
npm test
```

The browser suite runs desktop and mobile checks for six-second playback, pause/resume/replay and timer cleanup, both deal outcomes, receipt arithmetic and downloads, keyboard behavior, navigation, FAQ, accessibility, local assets, and overflow from 320px to 1440px. Screenshots and failure traces go to the ignored repository `.local/landing-test-results/` folder. Screenshots require human visual review; automated accessibility checks are not a full accessibility audit.

## Files

- `index.html` — content and inline SVG illustration
- `styles.css`, `hero.css`, `workspace.css`, `responsive.css` — visual design
- `demo.js` — explicitly fictional interaction states
- `server.mjs` — dependency-free local preview server
- `tests/` — Playwright and axe checks
