# Agentic Commerce

Exploration and implementation planning for independently owned buyer and seller agents using Affinidi identity infrastructure.

## Current status

This repository contains a runnable local escrow demo alongside research, implementation plans and machine-specific WSL setup notes. The demo runs the buyer, seller, evaluator and escrow cores with signed messages, SQLite reference modules and a simulated bank. No end-to-end native Affinidi DID authentication exchange has been executed.

## Run a transaction demo

Install the dependencies from the repository root with Python 3.11+ and `uv`
(Bash, including Git Bash on Windows):

```bash
bash scripts/dev-install.sh
bash scripts/test.sh
```

Start the demo in PowerShell:

```powershell
.\.venv\Scripts\python.exe scripts/run_demo.py --port 8091
```

On Linux/macOS, use `.venv/bin/python scripts/run_demo.py --port 8091`.

Open **http://127.0.0.1:8091/demo**, choose a scenario and click **Start €500 purchase**.
The successful run pays EUR 495 to the seller and EUR 5 to the operator. The retry
scenario rejects a delivery missing `summary.json`, holds the funds, and pays only
after the corrected delivery passes. Each purchase produces a downloadable report
and a signed event log. These are simulated funds; the local runtime and reference
modules do not require a deployed AgentDb worker. See [dashboard setup and details](apps/dashboard/README.md).

The separate planned identity demonstration has Alice authenticate with her own DID,
request a quote from Bob through an Affinidi gateway, and verify Bob's signed response.

## Visual product concept

[`apps/landing/`](apps/landing/) contains a responsive **Cogit Finance** landing-page sketch based on [`SPEC.md`](SPEC.md), with an interactive sample escrow deal. It is a front-end concept only; it does not implement the agents, bank, or payment protocol.

Run `node apps/landing/server.mjs` and open **http://127.0.0.1:4173**, or open [`apps/landing/index.html`](apps/landing/index.html) directly. See the [preview README](apps/landing/README.md) for checks and design notes.

## Cartoon explainer

[`films/alice-bob-delta/`](films/alice-bob-delta/) contains the editable 26-second cartoon: Alice buys a research report from Bob while Delta holds the payment. Open `alice-bob-delta.html` for the source animation; see [`FILM.md`](films/alice-bob-delta/FILM.md) for the storyboard, Vidder rendering commands, licenses, and verification notes. Generated MP4s, audio, and review frames stay in the ignored `out/` directory.

## Documents

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
