# Agentic Commerce

Exploration and implementation planning for independently owned buyer and seller agents using Affinidi identity infrastructure.

## Current status

This repository contains research, an implementation plan and machine-specific WSL setup notes. The Alice/Bob application has **not** been implemented, and no end-to-end native DID authentication exchange has been executed.

The first proposed demonstration is intentionally small: Alice authenticates with her own DID, requests a quote from Bob through an Affinidi gateway, and verifies Bob's signed response. No LLM calls, purchases or payments are included in that first slice.

## Documents

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
