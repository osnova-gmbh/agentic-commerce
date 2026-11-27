# A04 installed worker recovery proof

This is an opt-in PostgreSQL integration proof for the existing reference worker.
It uses a read-only AgentDb D01 checkout at
`65a1948e0bbe613a527b7287dcc2e41e049fa091` (schema
`000179__module_resource_projection`), the installed Template wheel, and two
real `cogit-runtime work --once` processes. It makes no sibling source change.

## Final 0.1.11 rerun inputs

Use the once-built final 0.1.11 wheel and unsigned cohort prepared by
[the canonical worker instructions](../../database-example.md#prepare-and-bind-the-canonical-worker-cohort).
Set `$ReleaseProof` to their common proof directory; its `wheel` subdirectory
must contain that one wheel, and `cohort` must contain the matching
`prepared.json`. Do not rebuild the wheel for this proof. From the Template root:

```powershell
$ReleaseProof = 'C:\path\to\final-0111-proof'
$env:COGIT_A04_AGENTDB_CHECKOUT = 'C:\path\to\merged-schema-194-agentdb'
$env:COGIT_A04_BUNDLE_PATH = (Resolve-Path '.venv/Lib/site-packages/seller_agent/database').Path
$env:COGIT_A04_BUNDLE_DIGEST = '60f030fbffecfb72d4f9d3daf43bd5faf5c4fdc1b447830ad77d85f14c23bc14'
$env:COGIT_A04_RUNTIME_CLI = (Resolve-Path '.venv/Scripts/cogit-runtime.exe').Path
$env:COGIT_A04_COHORT_DIR = (Resolve-Path (Join-Path $ReleaseProof 'cohort')).Path
$env:COGIT_A04_EVIDENCE_PATH = Join-Path $ReleaseProof 'a04.json'
.venv/Scripts/python.exe -I scripts/verify_installed_packages.py `
  --agent-wheel-dir (Join-Path $ReleaseProof 'wheel')
node "$env:COGIT_A04_AGENTDB_CHECKOUT/node_modules/vitest/vitest.mjs" run `
  --config tests/agentdb/vitest.config.mjs --reporter=verbose
```

The fixture derives the installed Python interpreter from `COGIT_A04_RUNTIME_CLI`
and launches Runtime with `python -I -m cogit_runtime work --once`. The prior
schema-179 instructions and receipts below remain historical.

## Observed result

The [reproducible fixture](../../../tests/agentdb/worker_recovery.test.ts) passed
on 2026-10-08: **1 test passed**. The first worker committed `requests.put` in
PostgreSQL; the proxy discarded its HTTP response after the upstream returned
200. Runtime raised `AgentDbReconciliationRequiredError`. The fixture expired
that attempt through AgentDb's test helper, projected the failed job, and
reconciled the queue. A replacement worker then reported
`claimed=1 completed=1 failed=0 parked=0` and the run succeeded.

The fixture asserted **two** observed PUT requests, one
`core.module_worker_receipts` row with the same request key, digest and result,
one package row at revision 1, attempt generation 1 `expired`, attempt
generation 2 `succeeded`, and run lifecycle `succeeded`. The receipt table is
the fenced-worker authority; `core.module_command_invocations` stores
tenant-client commands. The lease helper shortens test time but the installation,
HTTP calls, queue claims, SQL write, receipts and worker processes are real.

The passing run used these exact bytes:

| Artifact | SHA-256 | Source |
| --- | --- | --- |
| Template `reference_cogit_agent-0.1.4-py3-none-any.whl` | `2bb42197ba7a15cb272ef54b96618add36946a1bbe43824d1017471a2c2e416c` | A04 PR 10 wheel |
| Active module 1.1.0 canonical manifest | `60f030fbffecfb72d4f9d3daf43bd5faf5c4fdc1b447830ad77d85f14c23bc14` | Extracted from that wheel |
| Runtime `cogit_runtime-0.3.8-py3-none-any.whl` | `931bbb9b18ee3cab47a272f1e3be3e614531d8907bc0dfab468797d4ef00ae67` | Reviewed A02.RUNTIME producer |
| SDK `cogit_agent_sdk-0.5.3-py3-none-any.whl` | `242d52f3285d3e66ba90aff5eb00fbf71d2cd2de3951be2b45e4e65189f4e829` | Rebuilt from reviewed source `7ba4e3baeae574023424b0498cd537c8de8f206c` |
| AgentDb client `agentdb_client-0.2.5-py3-none-any.whl` | `1fa62eabd215fa1555381769d49c1bf523ca91fabc2c1fe993150060f3078fb5` | Rebuilt from reviewed source `65a1948e0bbe613a527b7287dcc2e41e049fa091` |

The SDK and client rebuilt bytes are distinct from the wheels used in Runtime's
producer validation. Template package 0.1.4 still declares the older
0.3.6/0.5.2/0.2.4 cohort. This run installed the newer framework wheels normally,
then installed Template 0.1.4 with `--no-deps`; it proves the worker behavior,
not a clean locked installation. A02's subsequently merged
[Template PR 14](https://github.com/osnova-gmbh/cogit-agent-template/pull/14)
pins package 0.1.5 to the newer wheel cohort and separately proves the
standalone `plain_request` image, default stack, and worker recreation. A
post-merge rerun of this tracked A04 fixture with the installed 0.1.5 wheel
and `uv pip check`-clean selected framework cohort passed on schema 179; it
was a separate installed-wheel proof, not a Docker image rerun.

## Historical reproduction: Template 0.1.4

Provide a read-only AgentDb D01 checkout at the commit above with its Node
dependencies installed, Docker with PostgreSQL available, Python 3.11 and
`uv`. Supply the four wheel files with the hashes in the table above. From a
fresh Template checkout, create an ignored proof environment and check the
wheel bytes before installing them:

```powershell
$TemplateWheel = 'C:\path\to\reference_cogit_agent-0.1.4-py3-none-any.whl'
$RuntimeWheel = 'C:\path\to\cogit_runtime-0.3.8-py3-none-any.whl'
$SdkWheel = 'C:\path\to\cogit_agent_sdk-0.5.3-py3-none-any.whl'
$ClientWheel = 'C:\path\to\agentdb_client-0.2.5-py3-none-any.whl'
$Expected = @{
  $TemplateWheel = '2bb42197ba7a15cb272ef54b96618add36946a1bbe43824d1017471a2c2e416c'
  $RuntimeWheel = '931bbb9b18ee3cab47a272f1e3be3e614531d8907bc0dfab468797d4ef00ae67'
  $SdkWheel = '242d52f3285d3e66ba90aff5eb00fbf71d2cd2de3951be2b45e4e65189f4e829'
  $ClientWheel = '1fa62eabd215fa1555381769d49c1bf523ca91fabc2c1fe993150060f3078fb5'
}
foreach ($Wheel in $Expected.Keys) {
  if ((Get-FileHash -LiteralPath $Wheel -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Expected[$Wheel]) {
    throw "Wheel hash mismatch: $Wheel"
  }
}
$Proof = Join-Path (Get-Location) '.quality\a04-proof'
New-Item -ItemType Directory -Path $Proof -Force | Out-Null
uv venv --python 3.11 (Join-Path $Proof 'venv')
$Python = Join-Path $Proof 'venv\Scripts\python.exe'
uv pip install --python $Python $RuntimeWheel $SdkWheel $ClientWheel
uv pip install --python $Python --no-deps $TemplateWheel
& $Python -m zipfile -e $TemplateWheel (Join-Path $Proof 'extracted')
& $Python scripts/enable_database.py
```

Template 0.1.4 needs `--no-deps` because its metadata pins the older cohort;
that is a stated limit of this historical proof. The fixture checks that the
installed `seller_agent` is in `site-packages`, matches the extracted
bundle digest, and that the generated descriptor contains the same pin before
starting Docker. Set the D01 checkout path and run its Vitest binary:

```powershell
$env:COGIT_A04_AGENTDB_CHECKOUT = 'C:\path\to\agentdb-d01-checkout'
$env:COGIT_A04_BUNDLE_PATH = Join-Path $Proof 'extracted\seller_agent\database'
$env:COGIT_A04_BUNDLE_DIGEST = '60f030fbffecfb72d4f9d3daf43bd5faf5c4fdc1b447830ad77d85f14c23bc14'
$env:COGIT_A04_RUNTIME_CLI = Join-Path $Proof 'venv\Scripts\cogit-runtime.exe'
$env:COGIT_A04_MANIFEST = (Resolve-Path 'cogit.database.yaml').Path
$env:COGIT_A04_EVIDENCE_PATH = Join-Path $Proof 'receipt.json' # optional
& "$env:COGIT_A04_AGENTDB_CHECKOUT\node_modules\.bin\vitest.cmd" run --config 'tests/agentdb/vitest.config.mjs' --reporter=verbose
```

`AGENTDB_TEST_COMPOSE_OVERRIDE_FILE` may point to an isolated network override
when Docker's default address pool is exhausted. The
[Vitest configuration](../../../tests/agentdb/vitest.config.mjs) maps imports to
the supplied read-only checkout; no machine path is checked in. The fixture
creates a unique Docker project and cleans it up after the run.

## Cohort limit

AgentDb D03 schema `000180__module_command_exact_replay` publishes an audited
client 0.2.6 wheel (SHA-256
`949a38b7ccec22c4b133c85ac0743e5b24bf41c93c7b73724488ce495e649ce0`).
An isolated diagnostic also passed the same behavioral fixture against D03
after overlaying that client, but Runtime 0.3.8 requires client 0.2.5 and
client 0.2.5's `/version` model accepts only schema 179. The D03 overlay fails
the package metadata check, so it is not a supported release cohort. This
report claims the compatible D01 schema-179 result only. A02's standalone
`plain_request` and D08's evolution fixture subsequently passed in separate
Template PRs. A10's installed canonical worker separately finalized and read
back a public root on D01 schema 179; its consumer root selection remains
external. Runtime's standalone `case_request` pipeline still fails on child
run persistence, and a supported schema-180 worker cohort and assembled
invoice acceptance remain separate work.

## Post-merge locked-cohort replication

On 2026-10-08, the same tracked `tests/agentdb/worker_recovery.test.ts` fixture
passed **1/1** in a fresh 106-second run on D01 schema 179 using installed
Template 0.1.5 wheel SHA-256
`6bec615af21bee97da1f376bfa8f56c5021a64f00e466980e1033819d4ac191e`,
Runtime 0.3.8, SDK 0.5.3 and AgentDb client 0.2.5. `uv pip check` passed with
that selected cohort. The first worker exited 1 on reconciliation after its
PUT committed and its HTTP response was lost. A replacement exited 0 with
`claimed=1 completed=1`. The test again observed two PUT calls, one package
row at revision 1, the same authoritative receipt/result, attempts
`expired` and `succeeded`, and a succeeded run. The isolated proof project was
`a04wdd9f6cf2`, run `a892e4cc-55c4-4551-ba7a-960bbbd2f6c8`; local
evidence was saved under ignored `.quality/a04-proof/locked-0.1.5.json`.
This removes the historical `--no-deps` caveat for schema-179 behavior. It
does not make client 0.2.5 compatible with schema 180.
