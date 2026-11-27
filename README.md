# Agentic Commerce

Exploration and implementation planning for independently owned buyer and seller agents using Affinidi identity infrastructure.

## Current status

This repository contains a runnable local escrow demo alongside research, implementation plans and machine-specific WSL setup notes. The demo runs the buyer, seller, evaluator and escrow cores with signed messages, SQLite reference modules and a simulated bank. No end-to-end native Affinidi DID authentication exchange has been executed.

## Run a transaction demo

Agent identity is configured for the buyer, seller and escrow through the existing
Boris MCP endpoint. Run `python scripts/affinidi_agents.py enable` to apply the
public project settings and `python scripts/affinidi_agents.py probe` to check
the connection. See [identity setup](docs/AFFINIDI.md) for the per-agent payload
and the separate optional DID Auth experiment.

From the repository root:

```powershell
python scripts/run_demo.py --port 8091
```

Open **http://127.0.0.1:8091/demo** and select a service from the catalog.
Review its terms, **Fund escrow**, **Simulate work & delivery**, and then
**Release payment to seller** after the delivery checks pass. The price and
deliverable come from the selected offer. A failed delivery keeps the funds held
and requires a corrected delivery before release. Each purchase produces downloadable
files and a signed event log. These are simulated funds; the local runtime and reference
modules do not require a deployed AgentDb worker. See [dashboard setup and details](apps/dashboard/README.md).

The separate planned identity demonstration has Alice authenticate with her own DID,
request a quote from Bob through an Affinidi gateway, and verify Bob's signed response.

## Visual product concept

[`apps/landing/`](apps/landing/) contains a responsive **Cogit Finance** landing-page sketch based on [`SPEC.md`](SPEC.md), with an interactive sample escrow deal. It is a front-end concept only; it does not implement the agents, bank, or payment protocol.

Run `node apps/landing/server.mjs` and open **http://127.0.0.1:4173**, or open [`apps/landing/index.html`](apps/landing/index.html) directly. See the [preview README](apps/landing/README.md) for checks and design notes.

## Protocol video

The replacement [commerce-flow film](films/commerce-flow/README.md) shows the
catalog queries, signed requests and quotes, terms, funding confirmation,
artifact delivery, evaluator verdicts, payouts and receipts as an animated
sequence diagram. Run `node films/commerce-flow/server.mjs` and open
http://127.0.0.1:4175/ to watch the 62-second export.

## Visual product concept

[`apps/landing/`](apps/landing/) contains a responsive **Cogit Finance** landing-page sketch based on [`SPEC.md`](SPEC.md), with an interactive sample escrow deal. It is a front-end concept only; it does not implement the agents, bank, or payment protocol.

Run `node apps/landing/server.mjs` and open **http://127.0.0.1:4173**, or open [`apps/landing/index.html`](apps/landing/index.html) directly. See the [preview README](apps/landing/README.md) for checks and design notes.

## Cartoon explainer

[`films/alice-bob-delta/`](films/alice-bob-delta/) contains the editable 26-second cartoon: Alice buys a research report from Bob while Delta holds the payment. Open `alice-bob-delta.html` for the source animation; see [`FILM.md`](films/alice-bob-delta/FILM.md) for the storyboard, Vidder rendering commands, licenses, and verification notes. Generated MP4s, audio, and review frames stay in the ignored `out/` directory.

## Documents

For native AgentDb execution, see [the runtime guide](docs/AGENTDB-RUNTIME.md).
`python scripts/run_agentdb.py up --agentdb-root C:/cogit/cogit-core/agent-db`
prepares and installs four workers, deploys the native modules to an isolated
local stack, and serves a transaction workspace on port 8093. It requires a
working Docker engine and the pinned dependencies. Use
`python scripts/verify_agentdb.py --restart` for live settlement and persistence
acceptance; building the packages alone is not a successful deployment.

- [Cogit Finance specification](SPEC.md): authoritative escrow product behavior and implementation plan.
- [Alice/Bob implementation plan](ALICE-BOB-PLAN.md): responsibilities, protocol, proposed files and acceptance checks.
- [WSL/Boris handover](WSL-HANDOVER.md): local commands, installed software, blockers and verification evidence. Paths and account state are specific to the original development machine; recheck them before use.

## Local WSL diagnostics

On the configured Windows development machine, run from PowerShell:

```powershell
wsl -d Ubuntu -u denys --exec /bin/sh /mnt/c/ai/_experiments/agentic-commerce/tools/wsl/check-boris.sh
```

This queries the existing installation and writes `tools/wsl/boris-check.out.txt`. The generated report is ignored by Git because it can contain account metadata. Do not publish credentials or private identity keys.

## Integration boundary

Released Affinidi Trust Fabric Agent Gateway supports native DID authentication. The hosted Boris account inspected during this investigation does not expose `did_auth` in its caller-authentication feature schema. First determine whether the existing Boris-backed gateway can expose that capability; a separate gateway deployment is only a fallback, not an established requirement.
