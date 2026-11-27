# Optional installed database example

The SDK, Runtime and AgentDb are separate repositories. Default local checks
install the exact vendored framework cohort from `pyproject.toml` and `uv.lock`;
they need no sibling sources or private build credentials. Verify the wheel
receipt before installation. See [the README](../README.md#framework-dependencies)
for explicit source-development setup and [the provisional provenance](../vendor/wheels/PROVENANCE.md)
for the current preparation limits. Hosted dependency closure and canonical
worker execution remain separate image/release acceptance gates. Runtime's
canonical worker requires an artifact cohort and a deployment receipt; the
steps below use the exact installed agent, framework wheels, and generated
database manifest.

The root `cogit.yaml` pins the AgentDb reference module and includes a
deterministic queue pipeline. The module owns business rows in the AgentDb tenant
schema. The same deployment owns execution state and worker authority.

You can prepare a narrower worker descriptor if you need only the deterministic
request action:

```powershell
uv run --no-sync python scripts/enable_database.py --output .data/cogit.database.yaml
```

Publish the exact manifest you will run. Both profiles pin
`cogit.seller-agent` 1.1.7 and its exact manifest digest. The root
profile also declares the two resolution exports. Verify the immutable
artifact digest before approving installation. The artifact digest hashes the
recursively key-sorted compact UTF-8 manifest JSON. Migration and resource
hashes commit to exact bytes.

## Setup and installation

The operator uses AgentDb's built `scripts/module-deploy.mjs` deployment CLI with
an `agentdb_migrator` database URL; no worker executes migrations. The CLI reads
one JSON request on standard input. From the Template checkout, extract the
reviewed wheel and initialize the application with deployment-provisioned values:

```powershell
$AgentDbDeploy = Join-Path $AgentDbCheckout "scripts/module-deploy.mjs"
python -m zipfile -e $ReferenceWheel .data/reference-wheel
$BundlePath = (Resolve-Path .data/reference-wheel/seller_agent/database).Path
$env:AGENTDB_DEPLOYMENT_DATABASE_URL = $DeploymentDatabaseUrl
$binding = (@{
  applicationKey = "reference-application"
  mode = "create"
  operatorPrincipalId = $OperatorPrincipalId
} | ConvertTo-Json -Compress) | node $AgentDbDeploy --operation initializeApplication |
  ConvertFrom-Json
$TenantId = $binding.tenantId
```

`create` is for the first application in a fresh deployment. In an existing
populated deployment choose the authorized tenant explicitly:

```powershell
$binding = (@{
  applicationKey = "reference-application"
  mode = "attach"
  tenantId = $TenantId
  operatorPrincipalId = $OperatorPrincipalId
} | ConvertTo-Json -Compress) | node $AgentDbDeploy --operation initializeApplication |
  ConvertFrom-Json
```

Repeating initialization recovers the durable binding after a lost response.
It does not select the first tenant.
Provision the agent definition, installation and worker pool using AgentDb's
authorized deployment workflow; use that installation UUID below. `install`
binds the selected descriptor's exact requirements to the extracted wheel bundle:

```powershell
$env:AGENTDB_DEPLOYMENT_APPROVED_ARTIFACTS = (@(
  @{ moduleKey = "cogit.seller-agent"; artifactSha256 = $ApprovedArtifactDigest }
) | ConvertTo-Json -Compress -AsArray)
$requirements = uv run --no-sync python -c `
  "import json,yaml; print(json.dumps(yaml.safe_load(open('cogit.yaml', encoding='utf-8'))['database_packages']))" |
  ConvertFrom-Json
$install = @{
  tenantId = $TenantId
  installationId = $InstallationId
  bundlePath = $BundlePath
  approvedArtifactSha256 = $ApprovedArtifactDigest
  requirements = @($requirements)
} | ConvertTo-Json -Compress -Depth 16
$install | node $AgentDbDeploy --operation plan
$install | node $AgentDbDeploy --operation apply
(@{ tenantId = $TenantId; moduleKey = "cogit.seller-agent" } |
  ConvertTo-Json -Compress) | node $AgentDbDeploy --operation inspect
```

`$ApprovedArtifactDigest` is the canonical manifest digest reviewed and approved
by the trusted deployment operator. This separate allowlist is required; a hash
declared by the agent descriptor does not grant publication authority. The
allowlist contains no secret. Remove deployment variables before starting a
worker; they are not worker credentials.

Installation creates only this tenant's reference tables and approved exports,
records the version/hash and migration attempt, and applies exact grants. Another
tenant acquires no tables or access. Package settings contain only a nonsecret
display label; they never carry tenant IDs, SQL targets or credentials. Installation
does not enable a second agent: grant that installation its declared read/write
capabilities through the authorized AgentDb workflow.

An additive approved upgrade must declare its supported base and retain old run
contracts. Inspect failed/held installation attempts before retrying. SQL failure
rolls back the transaction; committed-response recovery reuses the success ledger.
Disabling the agent preserves shared reference data. Destructive removal is a
separate operation.

## Prepare and bind the canonical worker cohort

Build from the final reviewed framework wheel pins with a frozen, noneditable
installation. Reinstall the exact built wheel into the host worker environment
before starting Runtime. A project installed from source by `uv sync` can have
build metadata outside the approved wheel inventory. The Template packager
copies the built agent wheel, selected vendored wheels, and the **exact selected
agent manifest** into a fresh
directory. It writes `executable.json` and `prepared.json`, but no deployment
receipt or route IDs:

```powershell
uv sync --frozen --no-dev --no-editable
uv build --wheel --out-dir .data/agent-wheel
$AgentWheels = @(Get-ChildItem -LiteralPath .data/agent-wheel -Filter '*.whl' -File)
if ($AgentWheels.Count -ne 1) { throw 'Expected exactly one built agent wheel' }
uv pip install --python .venv/Scripts/python.exe --reinstall --no-deps ($AgentWheels[0].FullName)
.venv/Scripts/python.exe -I -B scripts/worker_cohort.py prepare `
  --manifest cogit.yaml `
  --agent-wheel-dir .data/agent-wheel `
  --output .data/worker-cohort
.venv/Scripts/python.exe -I -B scripts/verify_installed_packages.py `
  --agent-wheel-dir .data/agent-wheel
```

Use the `executableSha256` and `manifestSha256` in
`.data/worker-cohort/prepared.json` when publishing the immutable version in
the existing AgentDb deployment workflow. These are hashes of the raw
`executable.json` and `cogit.yaml` bytes, respectively. Keep those files and
every referenced wheel file. When that workflow has returned the real tenant,
installation, definition, version, deployment, pool and agent-principal IDs,
bind them to the same bytes. Supply the two hashes **as published**; the
script rejects a mismatch and will not overwrite a receipt:

```powershell
.venv/Scripts/python.exe -I -B scripts/worker_cohort.py receipt `
  --cohort .data/worker-cohort `
  --tenant-id $TenantId --installation-id $InstallationId `
  --definition-id $DefinitionId --version-id $VersionId `
  --deployment-id $DeploymentId --pool-id $PoolId `
  --agent-principal-id $AgentPrincipalId `
  --published-executable-sha256 $PublishedExecutableSha256 `
  --published-manifest-sha256 $PublishedManifestSha256
```

The two `$Published*` values must come from the actual published version and
match the prepared hashes. Keep a separate installed environment and cohort
directory for each retained version. A source checkout or editable installation
does not satisfy Runtime's installed wheel check. Template 0.1.11 now has
local installed-worker acceptance with Runtime 0.3.18; a deployment receipt
still requires the actual publication IDs and hashes for that deployment.

The Docker image includes the same prepared, unsigned artifact set at
`/app/worker-cohort`. Extract that directory from the **exact image being
deployed**, publish its `prepared.json` hashes, and run the receipt command
against the extracted directory after publication. Mount only its completed
`receipt.json` read-only at `/app/worker-cohort/receipt.json`. Set
`COGIT_AGENTDB_COHORT_RECEIPT` to that in-container path, set
`COGIT_AGENTDB_API_VERSION=0.1.0`, and start
`sh /app/scripts/start_database_worker.sh`. The worker exposes no local HTTP
probe for this queue-only process. The image's installed packages and bundled
artifact files are root-owned, while the worker runs as the unprivileged
`agent` user. The launcher invokes the installed Runtime with Python's
isolated mode, so ambient import paths cannot replace the reviewed wheel.

Production launchers also pass Python's explicit `-B` flag. Isolated mode ignores
`PYTHONDONTWRITEBYTECODE`, so that environment setting alone cannot prevent cache
writes. The image removes generated bytecode after installation and checks that
none was recreated during final verification. This avoids repeated cache
reconstruction during worker integrity checks; source, wheel and any present
cache verification remain unchanged. These are build/launch configuration
changes, with no business prompt or Runtime verification change.

Compose enables Docker's init reaper for the worker so orphaned
tool/browser descendants can be reaped. When launching those capabilities with
plain `docker run`, use `--init` as well; this is process cleanup, not isolation
between customers.

## Start the worker

Configure a normal pool-worker token and installation UUID. It has no owner role,
table write access or migrator credentials. Runtime verifies the receipt,
installed wheel bytes, published route and pinned export snapshot before a
claim.

For the root manifest, set `COGIT_AGENTDB_APPROVAL_DECIDER_ID` to the UUID of
the active tenant member authorized with the tenant-wide `human.decide` grant.
The reduced descriptor declares no approval-gated actions and can omit this
setting.

```powershell
$env:AGENTDB_DEPLOYMENT_DATABASE_URL = $null
$env:AGENTDB_DEPLOYMENT_APPROVED_ARTIFACTS = $null
$env:COGIT_AGENTDB_URL = $AgentDbOrigin
$env:COGIT_AGENTDB_API_VERSION = "0.1.0"
$env:COGIT_AGENTDB_POOL_ID = $PoolId
$env:COGIT_AGENTDB_INSTALLATION_ID = $InstallationId
$env:COGIT_AGENTDB_WORKER_TOKEN = $PoolWorkerToken
$env:COGIT_AGENTDB_APPROVAL_DECIDER_ID = $ApprovalDeciderPrincipalId
$env:COGIT_AGENTDB_COHORT_RECEIPT = `
  (Resolve-Path .data/worker-cohort/receipt.json).Path
.venv/Scripts/python.exe -I -B -m cogit_runtime work `
  --manifest .data/worker-cohort/cogit.yaml
```

Missing/incompatible packages or grants fail readiness; startup never
silently installs SQL. Install and upgrade the package through the AgentDb
deployment operator before starting the worker.

The shipped database profile disables the model. A canonical SDK/model profile
also needs a private, stable `COGIT_AGENTDB_LOOP_INTEGRITY_KEY` for its protected
tool journal, normal provider credentials, and an admitted model-spend policy.
Provision these through the deployment's secret configuration and retain the
integrity key across worker replacement; never put it in the manifest, prompt
or public cohort receipts. Runtime's AgentDB integration guide describes this
existing requirement. The deterministic profile's success does not test it.

### Upgrade and retire an installed cohort

Database module **1.1.7** targets physical AgentDB core migration heads
**179 through 216** and permits upgrades from 1.1.6. Its SQL, exports and
contracts match 1.1.6, which is retained with its original upper bound of 215.
The exact released 1.1.4 tree is retained under
`database/historical/module-1.1.4`, with its original upper bound of 211.
The 1.1.3 bundle remains retained with its original upper bound of 205. Migration
205 registered the released API contract digest; 204 corrected the event
timestamp projection before its digest is computed. The prior 1.1.2, 1.1.1 and
1.1.0 upper bounds remain 204, 203 and 199. Those older bundles correctly reject
a fresh installation above their certified head. Candidate acceptance includes
the final framework artifacts and physical-head-216 cohort checks; the public wire schema remains 211.

`platform.maxSchema` compares the actual highest applied core migration, rather
than the public `/version` compatibility label. A framework release owner must
test the module against the selected server head and publish a new immutable
module/cohort when its certified range changes. Customers should use that tested
cohort; editing an installed manifest or raising the bound by hand is not an
upgrade procedure. The finite guard remains enabled.

Use the deployment host's authenticated `PlatformAdminApi` from AgentDB client
0.2.13. Workers and tenant clients do not have this authority. The public routes
are `POST /v1/admin/installations/{installationId}/retain` and `/retire`;
each requires an idempotency key and a `CohortTransitionRequest` containing the
exact `tenantId` and `deploymentId`. No owner SQL or worker-side migration is
needed for these transitions.

Retain the old active cohort before creating its replacement. Retention preserves
the old version, executable and manifest hashes and allows already-pinned runs
to drain; unfinished runless work blocks the transition. Use distinct scoped
worker principals/pools for old and new cohorts while both remain eligible.
Sharing one worker principal across retained and active routes can correctly
fail readiness with `ambiguous_route`.

Retire only after the retained cohort has no unfinished runs, work, processing
or actions. Busy-cohort rejection protects outstanding work; do not disable it
by hand to make readiness pass. Retrying the same accepted idempotency key
returns that transition's original receipt, even after a later transition.
It is not a query for the cohort's current status.

## Authenticated resource and durable run requests

Tenant clients use an OIDC bearer token accepted by AgentDb and mapped to an
authorized principal/tenant. Set `AGENTDB_CLIENT_TOKEN` from your supported login
or client-credential flow and `COGIT_AGENTDB_URL` to its API origin. No development
authentication bypass is needed. From the template checkout:

```powershell
.\examples\resource_api.ps1
uv run python examples/durable_run.py --installation-id $InstallationId
```

The resource script calls catalog, declared create, bounded list/get and the
revision-checked `close` action. Repeating a create with the same key/content is
idempotent; changing that identity's content is rejected. Unknown resources,
fields, filters, sorts and unauthorized caller kinds fail closed. `requests.put`
is worker-only and has no client resource alias. The example's client commands
declare no mandatory policy; AgentDb still records the client invocation context
and applies any applicable tenant/module governance.

The durable script uses AgentDb's generated `ClientApi`. It allocates an input
artifact, uploads the exact UTF-8 JSON bytes, and finalizes their SHA-256 and
length before admission. It then uses `AcceptQueryRequest` and
`AcceptQueryRequestInput` to submit:

```json
{"installationId":"<installation UUID>","input":{"sha256":"<finalized input SHA-256>","text":"{\"request_id\":\"request-db\",\"description\":\"Persist a reference record.\"}"}}
```

`POST /v1/queries` returns 202 plus an AgentDb run UUID. Queue claim decoding turns
`input.text` into the flat typed input, selects `persist-reference-request` via the
`queue` trigger, and executes deterministic `persist` then terminal `finish`.
The action calls fenced `requests.put` and `requests.get` through `RunHandle`.
It performs no model/provider call, DDL, tenant-token lookup or direct table DML.
Worker HTTP calls use the pool bearer token plus the claim's attempt token,
generation/execution identity, pinned package/export versions and contract IDs.
RunHandle supplies these; agent code never chooses an attempt or SQL function.

### Canonical text and the public result

The same worker also accepts an AgentDb query whose finalized input artifact is
`text/plain` and whose `input.text` contains one canonical UTF-8 instruction.
The bounded adapter accepts 1–2000 characters, rejects blank text and NUL,
and maps the exact text to the request description. Its request ID is `text-`
plus SHA-256 of `tenant ID UTF-8 || NUL || canonical text UTF-8`. This stable
tenant-scoped ID keeps retries on the existing `requests.put` business key.
The [invoice text fixture](../tests/fixtures/a10/canonical-input.txt) fixes an
exact newline-terminated example.

After `requests.put` and `requests.get` agree on the stored row, the action
commits a JSON artifact through `RunHandle` and reports a completed business
outcome. The [public schema](../src/seller_agent/public/root-result.v1.schema.json)
contains only `schemaVersion`, `outcome`, `requestId`, `status`, and `revision`.
The [exact root bytes](../tests/fixtures/a10/root-result.v1.json) and
[worker output fixture](../tests/fixtures/a10/worker-action-output.v1.json)
pin the contract and its `root_artifact_id`/`root_sha256` reference.

Runtime 0.3.18 stores a separate, internal `RunResult` artifact for settlement.
In the generated pipeline, that wrapper contains the root reference at
`output.steps[id="persist"].output.root_artifact_id`; its adjacent
`root_sha256` commits the public bytes. The wrapper also contains internal
action fields, so a public download must select the referenced run-linked
artifact, verify its SHA-256 and schema, and serve those public bytes. The
[fixture handoff](../tests/fixtures/a10/README.md) records this distinction.
Current Runtime also JSON-decodes JSON-looking `text/plain` claim content,
which can change the original text before Template sees it. Exact admission
for that case requires a media-type-aware Runtime input adapter. The assembled
public gateway and current AgentDb schema acceptance remain separate gates.

## Persistent write pattern

`Agent` and the reduced `DatabaseAgent` use the same pinned
module operations for persistent request writes. AgentDb stores the business
rows in the tenant schema and owns the authoritative command receipt.

The reference command key is `reference-request:` plus SHA-256 of the stable
request ID. It does not use a worker attempt or model tool-call ID. Repeating
the same command, input and immutable package/export/contract pins within the
same admitted run reuses its receipt; changed content or incompatible pins must
fail before another effect.
AgentDb rechecks current authority on replay. The domain identity constraint is
an additional SQL safeguard, not a substitute for that receipt.

Keep the three authority scopes separate:

| Scope | Owner and caller |
| --- | --- |
| Install or upgrade package SQL | Authorized deployment operator through AgentDb; never the worker |
| Read or mutate client resources | Authenticated tenant client with the declared module capability |
| Execute `requests.put` | Fenced worker using the claim's pinned exports and current grants through `RunHandle` |

For a bounded replay check, submit a unique request ID with the durable script,
wait for success, replace only the worker process using the same installed
descriptor, then run the identical command again:

```powershell
uv run python examples/durable_run.py --installation-id $InstallationId `
  --request-id replacement-check --description "One persistent reference request."
```

The script retains the same admission key, so the second invocation must return
the same run UUID and authoritative result. Verify the resource still has the
same object UUID, description and revision 1. This checks admission replay and
stored domain state; it alone does not prove that a replacement worker retried a
command whose response was lost.

Release acceptance must also interrupt a worker after `requests.put` commits
and before its response is observed, replace the worker, and resume through the
supported recovery path. Inspect AgentDb's command receipt identity and package
row: the replacement must observe the original receipt/result and exactly one
effect. Reuse this installed fixture for that recovery proof. Do not infer
workflow continuation or supported upgrades from a successful HTTP replay;
use only the recovery and upgrade profiles validated by the release cohort.

## Observe the outcome

The script waits for authoritative `GET /v1/runs/{runId}` lifecycle, then reads
`/events` and `/result`; 202 alone is not success. Timeout/nonterminal work needs
inspection, and failed/cancelled work exits unsuccessfully. After success the
resource list contains `request-db` with status `open`, revision 1, and a stable
object UUID. Inspect durable processing steps/events for `persist` and `finish`.

## Validation

Template tests cover strict input, queue pipeline selection, query/command
contracts, hash/path tampering and wheel assets. The bootstrap test genuinely
installs a renamed wheel and loads its resources outside the source checkout.
AgentDb integration tests consume the same first-party bundle in an isolated
PostgreSQL deployment for table/catalog/authentication and transactional proof.
Use fake providers; reference installation and execution need no Gmail, Chrome,
invoice package or model credential.
