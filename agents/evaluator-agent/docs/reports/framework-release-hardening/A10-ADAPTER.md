# A10 installed canonical worker proof

The Template 0.1.6 adapter reuses `DatabaseAgent` and the existing
`persist-reference-request` pipeline. It maps one bounded canonical UTF-8 text
instruction to a stable tenant-scoped request ID and the stored description,
then uses the approved `requests.put`/`requests.get` module exports. After
readback, it finalizes a public JSON artifact through `RunHandle` and declares
the business outcome `completed`. The local test fixture is the invoice text
in [`canonical-input.txt`](../../../tests/fixtures/a10/canonical-input.txt).

## Final 0.1.11 rerun inputs

Use the once-built final 0.1.11 wheel and unsigned cohort prepared by
[the canonical worker instructions](../../database-example.md#prepare-and-bind-the-canonical-worker-cohort).
Set `$ReleaseProof` to their common proof directory. The wheel SHA-256 below
is calculated from the selected bytes; no new hash is assumed. From the
Template root:

```powershell
$ReleaseProof = 'C:\path\to\final-0111-proof'
$BuiltWheel = (Resolve-Path (Join-Path $ReleaseProof 'wheel/reference_cogit_agent-0.1.11-py3-none-any.whl')).Path
$AgentWheel = (Resolve-Path (Join-Path $ReleaseProof 'cohort/wheels/reference_cogit_agent-0.1.11-py3-none-any.whl')).Path
$AgentHash = (Get-FileHash -LiteralPath $AgentWheel -Algorithm SHA256).Hash.ToLowerInvariant()
if ((Get-FileHash -LiteralPath $BuiltWheel -Algorithm SHA256).Hash.ToLowerInvariant() -ne $AgentHash) {
  throw 'Prepared cohort wheel differs from the once-built final wheel'
}
$env:COGIT_A10_AGENTDB_CHECKOUT = 'C:\cogit\cogit-core\.worktrees\framework-reconciliation\agentdb-runtime-cohort-acceptance'
if ((git -C $env:COGIT_A10_AGENTDB_CHECKOUT rev-parse HEAD).Trim() -ne `
  '7a22a2216c6d48e5825b2667124569a313f790ac') {
  throw 'A10 must use the exact merged AgentDb schema-194 checkout'
}
$env:COGIT_A10_BUNDLE_PATH = (Resolve-Path '.venv/Lib/site-packages/evaluator_agent/database').Path
$env:COGIT_A10_BUNDLE_DIGEST = 'd4cb30dd44889dd06ca0cf6e119cf1aaa8105e4610e56262f6ea8e0b3e897fd2'
$env:COGIT_A10_RUNTIME_CLI = (Resolve-Path '.venv/Scripts/cogit-runtime.exe').Path
$env:COGIT_A10_COHORT_DIR = (Resolve-Path (Join-Path $ReleaseProof 'cohort')).Path
$env:COGIT_A10_WHEEL_PATH = $AgentWheel
$env:COGIT_A10_WHEEL_SHA256 = $AgentHash
$env:COGIT_A10_EVIDENCE_PATH = Join-Path $ReleaseProof 'a10.json'
.venv/Scripts/python.exe -I scripts/verify_installed_packages.py `
  --agent-wheel-dir (Join-Path $ReleaseProof 'wheel')
node "$env:COGIT_A10_AGENTDB_CHECKOUT/node_modules/vitest/vitest.mjs" run `
  --config tests/agentdb/a10.vitest.config.mjs --reporter=verbose
```

The fixture derives the installed Python interpreter from `COGIT_A10_RUNTIME_CLI`
and launches Runtime with `python -I -m cogit_runtime work --once`. It records
separate plain-text and JSON-looking-text receipts. The schema-179 instructions
and receipts below remain historical.

## Opt-in final image worker proof

After building the one final 0.1.11 image, extract its unsigned worker cohort
once and use it as the A10 cohort source. The fixture compares the extracted
descriptor, manifest, and all four wheel hashes with the bytes inside the
selected image, and checks framework wheels against the committed release pins,
before publication. From the Template root, with `$ReleaseProof`
and the other A10 inputs above already set:

```powershell
$ImageTag = 'cogit-reference-agent:final-0111'
$env:COGIT_A10_IMAGE = (docker image inspect --format '{{.Id}}' $ImageTag).Trim()
if ($LASTEXITCODE -ne 0 -or !$env:COGIT_A10_IMAGE) { throw 'Final A10 image is missing' }
$ImageCohort = Join-Path $ReleaseProof 'image-cohort'
if (Test-Path $ImageCohort) { throw 'Choose a fresh image-cohort extraction path' }
$Extract = 'a10-extract-' + [guid]::NewGuid().ToString('N')
$ExtractId = $null
try {
  $Created = docker create --name $Extract $env:COGIT_A10_IMAGE
  if ($LASTEXITCODE -ne 0 -or !$Created) { throw 'Image container creation failed' }
  $ExtractId = ($Created | Select-Object -Last 1).Trim()
  docker cp "${ExtractId}:/app/worker-cohort" $ImageCohort
  if ($LASTEXITCODE -ne 0) { throw 'Image cohort extraction failed' }
} finally {
  if ($ExtractId) {
    docker rm -f $ExtractId | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Could not remove extraction container $ExtractId" }
  }
}
$env:COGIT_A10_COHORT_DIR = (Resolve-Path $ImageCohort).Path
$env:COGIT_A10_WHEEL_PATH = (Resolve-Path (Join-Path $ImageCohort `
  'wheels/reference_cogit_agent-0.1.11-py3-none-any.whl')).Path
$env:COGIT_A10_WHEEL_SHA256 = (
  Get-FileHash $env:COGIT_A10_WHEEL_PATH -Algorithm SHA256
).Hash.ToLowerInvariant()
if ($env:COGIT_A10_WHEEL_SHA256 -ne (Get-FileHash $BuiltWheel -Algorithm SHA256).Hash.ToLowerInvariant()) {
  throw 'Image worker wheel differs from the once-built final wheel'
}
node "$env:COGIT_A10_AGENTDB_CHECKOUT/node_modules/vitest/vitest.mjs" run `
  --config tests/agentdb/a10.vitest.config.mjs --reporter=verbose
```

The default uses the A10 task-owned AgentDb Docker network and reaches the
fixture API through `host.docker.internal` on its dynamically assigned port.
The opt-in `COGIT_A10_IMAGE_NETWORK=host` uses Docker Desktop host networking
when enabled; `COGIT_A10_IMAGE_AGENTDB_HOST` changes only the hostname and
preserves the assigned port. A container connection probe runs before the
cohort is published or work is admitted, with a diagnostic if the host API is
unreachable. The fixture mounts only the task's published receipt into the
image, runs `/app/scripts/start_database_worker.sh`, verifies PID 1 executed
`python -I -m cogit_runtime work` with the HTTP health probe disabled, and then
checks the same single durable
module receipt, package row, run result, and exact public root bytes as the
installed host-worker path. It removes only its task-owned worker container
and AgentDb project. Unset `COGIT_A10_IMAGE` to rerun the installed host worker.

## Installed cohort and observed result

The [opt-in integration test](../../../tests/agentdb/canonical_root.test.ts)
passed on 2026-10-08 against a real AgentDb D01 PostgreSQL fixture at
`65a1948e0bbe613a527b7287dcc2e41e049fa091` (schema 179). It used a
noneditable installed Template 0.1.6 distribution, installed Runtime CLI,
`PYTHONPATH=''`, and `COGIT_DEV_MODE=0`. The test checked the wheel SHA-256,
site-packages import, installed adapter/schema/module files against the wheel,
and the active module manifest digest before starting the worker.

| Artifact | SHA-256 |
| --- | --- |
| Template `reference_cogit_agent-0.1.6-py3-none-any.whl` | `6af8801491c1528d19c55d77ed661043f7bad700a3e0efb1d11415d099a9432c` |
| Active database module 1.1.0 canonical manifest | `d4cb30dd44889dd06ca0cf6e119cf1aaa8105e4610e56262f6ea8e0b3e897fd2` |
| Runtime 0.3.8 wheel | `931bbb9b18ee3cab47a272f1e3be3e614531d8907bc0dfab468797d4ef00ae67` |
| SDK 0.5.3 wheel | `242d52f3285d3e66ba90aff5eb00fbf71d2cd2de3951be2b45e4e65189f4e829` |
| AgentDb client 0.2.5 wheel | `1fa62eabd215fa1555381769d49c1bf523ca91fabc2c1fe993150060f3078fb5` |

The input artifact was finalized as `text/plain` with the exact bytes
`Review invoice INV-2026-0042 from Example GmbH.\n`, then admitted through
`POST /v1/queries` with its SHA-256 and installation ID. The real worker
reported `claimed=1 completed=1 failed=0 parked=0`. Run
`773b7c56-0e29-4c6d-8f1c-c25190a91c43` succeeded in isolated Docker
project `a10wec40f3dd`. One `core.module_worker_receipts` row for
`requests.put` and one package row existed. That row had object ID
`c0ce6290-1f39-45a7-9554-a83759f01a69`, request ID
`text-27902e90f46d3e6a445387bbba0eda624c48c1beeb7e316494abac1b2fecc209`,
the exact input description, status `open`, and revision 1.

AgentDb linked the worker-finalized public artifact
`2ec3c75f-4588-4f30-a2a0-8fc603edaf2f` to this run as `evidence`. An
authenticated `GET /v1/artifacts/{id}/bytes` returned these exact UTF-8 bytes,
including one trailing LF, with SHA-256
`21dee8933c917490c3859eb805bdd9799c50a3069ab1c676cf1a3f772cba7355`:

```json
{"outcome":"completed","requestId":"text-27902e90f46d3e6a445387bbba0eda624c48c1beeb7e316494abac1b2fecc209","revision":1,"schemaVersion":"reference-request-result.v1","status":"open"}
```

The exact body validates against the [public schema](../../../src/evaluator_agent/public/root-result.v1.schema.json).
Runtime settled a **different** `RunResult` artifact,
`2884915a-5d48-4a7b-bbe7-2e3c6594c604`. Its JSON has the public root ID and
SHA-256 at `output.steps[id="persist"].output.root_artifact_id` and adjacent
`root_sha256`. The fixture downloaded that wrapper and asserted both fields.
The wrapper also contains internal action data, so it is not a public result.
The test removed only its own Docker stack and volume afterward.

## Historical reproduction: Template 0.1.6

Use a read-only AgentDb D01 checkout at the commit above with its Node
dependencies installed, Docker/PostgreSQL available, Python 3.11, and `uv`.
From a fresh Template checkout on this change:

```powershell
python scripts/verify_framework_wheels.py
uv sync --frozen --all-extras --no-editable --python 3.11
uv lock --check --offline --python .venv\Scripts\python.exe
uv run --no-sync python -I scripts/verify_installed_packages.py
uv run --no-sync python scripts/enable_database.py
uv build --wheel --python .venv\Scripts\python.exe --out-dir .quality\a10-proof\dist

$env:COGIT_A10_AGENTDB_CHECKOUT = 'C:\path\to\agentdb-d01-checkout'
$env:COGIT_A10_BUNDLE_PATH = (Resolve-Path '.venv\Lib\site-packages\evaluator_agent\database').Path
$env:COGIT_A10_BUNDLE_DIGEST = 'd4cb30dd44889dd06ca0cf6e119cf1aaa8105e4610e56262f6ea8e0b3e897fd2'
$env:COGIT_A10_RUNTIME_CLI = (Resolve-Path '.venv\Scripts\cogit-runtime.exe').Path
$env:COGIT_A10_MANIFEST = (Resolve-Path 'cogit.database.yaml').Path
$env:COGIT_A10_WHEEL_PATH = (Resolve-Path '.quality\a10-proof\dist\reference_cogit_agent-0.1.6-py3-none-any.whl').Path
$env:COGIT_A10_WHEEL_SHA256 = '6af8801491c1528d19c55d77ed661043f7bad700a3e0efb1d11415d099a9432c'
$env:COGIT_A10_EVIDENCE_PATH = (Join-Path (Get-Location) '.quality\a10-proof\receipt.json')
& "$env:COGIT_A10_AGENTDB_CHECKOUT\node_modules\.bin\vitest.cmd" run `
  --config tests/agentdb/a10.vitest.config.mjs --reporter=verbose
```

The output path is optional. `AGENTDB_TEST_COMPOSE_OVERRIDE_FILE` can point
to an override assigning an unused subnet if Docker's default address pools
are exhausted. This run used `10.248.227.0/24`. The fixture creates a unique
Compose project and tears it down in `finally`. It requires no model key or
external invoice package. The SHA-256 assertion identifies the exact evidence
wheel used above; a rebuild with different source bytes, line endings or build
tools is a new candidate and must not be substituted for this receipt.

## Packaging and acceptance boundary

Template `pyproject.toml` and `uv.lock` both select package 0.1.6 and the
same reviewed 0.3.8/0.5.3/0.2.5 cohort. The evidence wheel rebuilt after the
A02/A04 main rebase with the identical archive SHA-256 above. The generated
`cogit.database.yaml` still pins module 1.1.0 digest and the `requests.put`
and `requests.get` v1 contract IDs. Its `version` and `template_version`
remain 0.1.3, inherited from the base `cogit.yaml` descriptor; those describe
the example agent template, while 0.1.6 is the Python distribution version.
The Python suite covers the generated contract, historical module bytes,
bootstrap rename and installed renamed wheel.

On this branch, `scripts/check.ps1 -SkipSync -SkipLiveEval -SkipImage` passed:
Ruff lint/format, strict Pyright, import contracts, dependency check, manifest
and action contract validation, and **108 passed / 4 skipped** Python tests.
`uv lock --check --offline`, `uv pip check`, and the isolated installed-package
verifier passed separately; the verifier compared 429 vendored framework
members and reported the module digest above. The four skipped bootstrap
cases are platform-specific Linux symlink controls on this Windows run.

The selected AgentDb client 0.2.5 supports schema 179 in this proof; this
receipt does not establish schema-180 compatibility. A04 separately proved
replacement-worker recovery with one durable module effect. This A10 run
proves canonical admission, write/read, root commitment, and readback on one
built worker; it does not claim a second A10 replacement-worker run.

The current Runtime 0.3.8 claim decoder JSON-parses JSON-looking `text/plain`
content, so that input class needs a media-type-aware producer fix to preserve
exact bytes. The tenant-scoped request ID is an unkeyed SHA-256 of tenant ID,
NUL and canonical text. It is stable for repeated work, but if a viewer knows
the tenant ID it permits membership guesses for low-entropy instructions; it
is not a confidentiality mechanism. A keyed or opaque ID would need an agreed
cross-retry identity contract.

R05/W04 must make the public selection explicit: authorize this run-linked
artifact, verify its SHA-256 and public schema, and reject foreign or nested
artifact IDs. The current SDK/Runtime has no agent-facing root selector, and
`core.runs.result_artifact_id` points to Runtime's internal wrapper. This
Template proof does not claim the public download gateway or assembled Phase 1
acceptance is complete.
