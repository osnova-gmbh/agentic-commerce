# Template framework release handoff

## Selected local Template 0.1.11 cohort

Template 0.1.11 uses one canonical worker and selects AgentDb client 0.2.9,
SDK 0.5.9 and Runtime 0.3.18. Runtime PR 38 merged as
`812ee9b1b15a77a7cc73a8c72c50f7e90c3ca23f`; AgentDb schema-194 fixture
PR 300 merged as `7a22a2216c6d48e5825b2667124569a313f790ac`.
[PROVENANCE.md](../../../vendor/wheels/PROVENANCE.md) records all three exact
framework wheel bytes and their producer revisions. This is a local artifact
selection; package-index publication and production deployment are not claimed.

The selected immutable image is
`sha256:361279af7feeadd5b3ec99295a1c77702daf2fa5813fd51599ef79ffacec83a7`.
Its `/app/worker-cohort` contains the unsigned
`reference_cogit_agent-0.1.11-py3-none-any.whl`, SHA-256
`639ced22bcd81ec28ceda1ba785b06d3fed28a0d9e0e266ffc4147f19e2a3191`.
The extracted `executable.json`, `cogit.yaml` and `prepared.json` hashes are,
respectively, `ffed27dd36bdd7fde71be26cbed734b651aad81b53f8e883501ddbd830a911cf`,
`8b50e5ba7ed5721f16f2071799258cd897442b3b10c0f47abe4117a176ae94a1`
and `80e5f58e70d232c8cd64611bfa90215ac5ced99964b47d515b70f7f6baeadc52`.
The exact extracted wheel was installed noneditably; `uv pip check` passed and
all 525 installed files of the four selected packages matched their wheel
members. The image had no unexpected installed files under those packages.
The image rebuild replaced a source-installed Template distribution that had
left `uv_build.json` in its dist-info directory. That earlier image was
rejected; no final claim uses it. Runtime's strict inventory check was retained.
Its host A04/A10 receipts remain valid for the selected image because the
extracted Template wheel SHA-256 and all three framework wheel hashes are
identical between the two builds; the image-only A10 suite was rerun on the
selected image.

| Final local check | Selected evidence |
| --- | --- |
| A02 default image | Project `tmpl0111b50518f5`: default CMD healthy, Alembic `0007_outbox_run_identity`, `plain_request` and `case_request` succeeded before and after worker recreation (4/4). Four queue rows processed with zero retries; ten completed run rows and six nonfailed execution steps. |
| A04 lost response | Installed-wheel run `d5755d52-a15f-4a41-ae67-17218b5eee03` passed 1/1: two PUT attempts, one receipt and one module row at revision 1; first attempt expired and the replacement succeeded. |
| A10 installed host worker | Passed 2/2 with exact wheel SHA above. Canonical run `f67ce168-27c2-4959-a956-013c1e9ceb01` produced public root SHA-256 `1110554836f8d4be34ed934c3623a55ded38818796aa6a6f4327c0c72fcc8acf`; JSON-looking `text/plain` run `381c3fe9-1167-47c3-82cb-551e839d1772` produced `091caba2404b8113cc8e21073edb5c9729d3bede0219f02cfceedda1444daa23`. Each stored the exact input, emitted exact public bytes, and had one row and receipt. |
| A10 immutable image worker | Passed 2/2 from the selected image with isolated `python -I -m cogit_runtime work`. Canonical run `347d6dfe-bd2e-431b-8bee-c67b9b347ad9` public root SHA-256 `d41f3fca9ce1cb488cfcae99bbd247a8ec7e624dc4fb0556bee26ff8a12a71a7`; JSON-looking run `1037f155-5083-4588-8555-2babc468240c` public root `817be2d7edfed7034a2af639f3152c1e0e5a6659a5c6e590890f12fb183646d6`. Both preserved exact input/public bytes, one row and one receipt. |
| D08 module evolution | Passed 1/1 against AgentDb schema 194, exercising both tenant paths: retained old read alias, distinct successor identities, rejected old writes and wrong-tenant access, and explicit retirement. Active module digest remained `61f796ccbb759899a088527bd94c68936f96d51bd372b04506afde4fadb23461`; generated v2/v3 fixture digests were `2a3a4a6c2a7259b522d020b4dd17e3617d4ecf69472a12029e59ec5e0f65cee4` and `211392dcc7c38ff2b3c89d7b7c2bd8f74d4ca3059eaaa0dc8a3b69be51e3f8a8`. |

The final Template source gate passed on Python 3.11.16: 115 tests, four
platform skips, Ruff, formatting, Pyright, import boundaries, dependency
analysis, manifest/action validation and the 4/4 live smoke evaluation.
The image and AgentDb fixture suites above ran serially, and their task-owned
Docker resources were removed after each run.

The A10 image fixture creates a short-lived HTTPS proxy bound to host
`127.0.0.1`, forwarding complete HTTP requests to the fixture's loopback
AgentDb API. The worker connects through `host.docker.internal` only over TLS;
its read-only CA mount is verified by urllib3 and HTTPX before publication.
The private server key remains on the host. To reproduce the TLS setup on
Windows, generate a fresh CA and DNS-SAN server certificate with
`tests/agentdb/New-A10-Test-Cert.ps1 -OutputDirectory .quality/a10-tls`.
Set `COGIT_A10_IMAGE_TLS_CA_PATH`, `COGIT_A10_IMAGE_TLS_CERT_PATH` and
`COGIT_A10_IMAGE_TLS_KEY_PATH` to that directory's `ca.pem`,
`server-cert.pem` and `server-key.pem` respectively. Set `COGIT_A10_IMAGE` to
the immutable image ID above, `COGIT_A10_AGENTDB_CHECKOUT` to the schema-194
checkout, `COGIT_A10_RUNTIME_CLI` to the noneditable installed Runtime CLI,
`COGIT_A10_COHORT_DIR` to the image-extracted cohort,
`COGIT_A10_WHEEL_PATH`/`COGIT_A10_WHEEL_SHA256` to its Template wheel/path hash,
and `COGIT_A10_BUNDLE_PATH`/`COGIT_A10_BUNDLE_DIGEST` to the installed module
bundle and active digest above. Run `node <AgentDb checkout>/node_modules/vitest/vitest.mjs run --config tests/agentdb/a10.vitest.config.mjs` from this checkout. The fixture creates and removes unique task-owned Docker projects. It never disables Runtime's HTTPS guard.

The image includes a prepared, unsigned artifact set. `scripts/worker_cohort.py`
binds a deployment receipt only after real route IDs and published hashes are
supplied. The live fixtures use their own route IDs and receipts; this handoff
does not claim that the selected image has been published or deployed.

## Historical reconciliation: Template 0.1.8

Template 0.1.8 selects the compatible AgentDb schema-191 cohort:
client **0.2.7**, SDK **0.5.9**, Runtime **0.3.16**. Exact producer commits and
wheel hashes are in [PROVENANCE.md](../../../vendor/wheels/PROVENANCE.md) and
[cohort.json](../../../vendor/wheels/cohort.json). The final Template wheel is
`reference_cogit_agent-0.1.8-py3-none-any.whl`, SHA-256
`48e68d8edf4f727bd7374f64b869ccb157ad7e803cc49060c8d9635f0252a0ac`.
Earlier 0.1.7 diagnostic builds are excluded from this release receipt.

The generated database descriptor now declares only the operation it executes,
with no tools or model and an explicit disabled model profile. Its actual
registered action inventory matches that descriptor. The ordinary local
reference agent retains its direct actions/tools and accurately declares that
Echo does not support model tool dispatch. Module 1.1.0, historical module
1.0.0, SQL bytes, business keys and public-result schema remain unchanged.

Final local validation uses frozen, noneditable packages, the real installed
CLI with no source path or inbound HTTP key, and distinct disposable test
stacks. Canonical tests use AgentDb commit
`34e868a877176ee43f2d46e3b6722af4d49c788a`, schema
`000191__runtime_audit_events`.

| Check | Final evidence |
| --- | --- |
| Source and installed closure | 108 tests passed, four existing platform skips; Ruff, formatting, Pyright, import boundaries, dependencies, manifest/action parity and frozen installation passed. 464 installed framework files matched their exact selected wheels; `uv pip check` passed. |
| A02 image and worker recreation | Passed in isolated project `tmplfinala56bcd0827`: both `plain_request` and `case_request` completed before and after worker recreation, all four queue jobs processed with zero retries and all ten parent/child/checkpoint records completed. Alembic head `0007_outbox_run_identity`; separate smoke evaluation passed 4/4. Image `cogit-finance:final-0.1.8`, image ID `sha256:c6d7ae3d69e62f2625bf8020e7dae59002e70af1fb5372d70d31e1768f5c6a1e`. |
| A04 lost response | Passed 1/1. Run `491c6551-fa4c-45a3-b5a9-f25db9c06ece`: first worker exited on reconciliation after the committed response was dropped; replacement completed. Two PUT requests produced one receipt and one module row at revision 1. Attempts expired/succeeded; the run succeeded. |
| A10 ordinary text | Passed. Run `64a0dc66-3cea-4a43-9fbd-dbfc0fc84314`; authenticated public root `2b1b4c87-7cf6-4033-9dd7-4d61f0d32927`, SHA-256 `841c819f259b22ac2492e90198e428c15f862cf6e4abfed8decd485a44ad22c5`. Stored input and public output bytes matched exactly, with one receipt and one row. |
| A10 JSON-looking `text/plain` | Passed. Run `f1963255-0f8f-4da8-b70b-6ef7a3b3b6b5`; authenticated public root `0a2d174f-013e-43eb-9c7a-2643019aa1a5`, SHA-256 `93679c8846b4546ed331113fcfbe52773d68abf0ae5cefaeaed4b9f3e623b44c`. The JSON-looking input remained literal text, with one receipt and one row. |
| D08 module evolution | Existing fixture rerun passed 2/2 against schema 191. Old object `804ad042-a00e-4042-92d9-dfe2a0fa8997` retained its read alias; successor object `5ab28579-1126-4e53-abcf-69e29c8d64a5` had a distinct identity/type. Old writes, wrong-tenant reads and retired routes returned 404; successor remained accessible. See the [fixture receipt](../../../tests/fixtures/d08/README.md). |
| Dependency security | 51 public dependencies audited with no known vulnerabilities. The four private packages were reviewed through their producer source, exact hashes and installed-byte parity. |

The earlier schema mismatch, standalone child-run persistence failure and
JSON-looking text decoding failure are closed for this selected cohort.
Canonical execution also passes the producer's explicit worker-role startup,
zero-spend claim and bounded checkpoint accounting fixes. No model credential
or inbound HTTP credential was added to make the canonical worker pass.

Invoice application synchronization and assembled invoice acceptance remain
owned by the separate Library task. A10 still finalizes a public root separately
from Runtime's internal settlement wrapper; the application must select the
public result using its agreed contract. Template does not claim package-index
publication, whole-application release approval or production deployment.

## Historical receipts through Template 0.1.6

The sections below preserve earlier Git/artifact receipts and their limitations
at the time. Their "current", "selected" and remaining-limit references describe
that historical cohort; the 0.1.8 receipt above supersedes them.

Updated 2026-10-08 for the existing invoice processor integration. This report
covers only `osnova-gmbh/cogit-agent-template`. Template supplies the reusable
reference worker and package; it does not contain the invoice processor's domain
source. No sibling repository or production deployment was changed for this
handoff.

## Status and exact Git receipts

| Card | Status and repository result |
| --- | --- |
| A01 | Complete. [PR 9](https://github.com/osnova-gmbh/cogit-agent-template/pull/9) merged as `7067a35d4ab716315cc136414c139e881d41b98a`; three checks passed. Frozen, noneditable standalone installation and vendored framework wheel provenance remain the baseline. |
| A02 | Complete for the standalone `plain_request` worker stack. [PR 11](https://github.com/osnova-gmbh/cogit-agent-template/pull/11), reviewed head `ab92cec458da40bd800cca42744880a349ab81ec`, merged as `05921245e7d21bfc483ef000c82b745fc82d8831`, fixed worker health reporting. [PR 14](https://github.com/osnova-gmbh/cogit-agent-template/pull/14), reviewed head `cfbf8da2ddc8d0c1500a9a2aef780012966e9754`, merged as `76274ff26d1ad89898e1296812d1f1cf62bb6871`, supplied the locked 0.1.5 image and a real successful request before and after worker recreation. Its Ubuntu contract, Windows contract and container checks passed. The separate `case_request` pipeline limit is below. |
| A04 | Complete for the schema-179 installed-module replacement-worker proof. [PR 10](https://github.com/osnova-gmbh/cogit-agent-template/pull/10), reviewed head `d6fd3b78ded63b2704fb0146e75f2472f924ad9f`, merged as `f8e5f2e88f354d0a7b39c5f687014084b4419507`, supplied immutable module 1.1.0. [PR 15](https://github.com/osnova-gmbh/cogit-agent-template/pull/15), reviewed head `b4d6e48d6d4dc7f6a6882d06b5ee713d85a3b676`, merged as `48fe0ac7a7b9445caea72053a84eba2f7edae842`, proved one committed effect across a lost response and worker replacement. Its Ubuntu contract, Windows contract and container checks passed. The original PR proof used historical Template 0.1.4 with newer framework wheels installed explicitly; a post-merge run passed with the clean locked Template 0.1.5 cohort. |
| D08.TEMPLATE | Complete. [PR 13](https://github.com/osnova-gmbh/cogit-agent-template/pull/13), reviewed head `a14d6db4ccd58f417f8252fe817fe685f9b2cb52`, merged as `ddbcd0267afa40b0f2ce0076d43b4a68f0d232b7`. Its Ubuntu contract, Windows contract and container checks passed. The fixture proves a retained read alias, distinct successor type and explicit retirement against live AgentDb schema 181. |
| A10 | Complete for Template's installed schema-179 canonical-input and public-root proof. [PR 16](https://github.com/osnova-gmbh/cogit-agent-template/pull/16), reviewed head `ed801fa6083c99f4c1e4f989ac65d430324308c7`, merged as `1087d878240c6622ba807e8bceca3cc41fc0d206`; Ubuntu contract, Windows contract and container checks passed. The 0.1.6 adapter accepts canonical text, writes and reads the module row, and finalizes a public root artifact. The consumer's public root selection and download gateway remain separate work. |

## Exact Template producer artifacts

| Artifact | Identity |
| --- | --- |
| Current Template package | `cogit-finance==0.1.6`; noneditable A10 evidence wheel `reference_cogit_agent-0.1.6-py3-none-any.whl`, SHA-256 `6af8801491c1528d19c55d77ed661043f7bad700a3e0efb1d11415d099a9432c`. This is local build evidence, not public package-index publication. |
| A02/A04 0.1.5 package | Noneditable A02 image and post-merge A04 recovery wheel, SHA-256 `6bec615af21bee97da1f376bfa8f56c5021a64f00e466980e1033819d4ac191e`. |
| A02 image | `cogit-finance:a02-0.1.5-fixed`, image digest `sha256:54f45118a9bcc0fa6bb82069f8e1792b5032bd053b9e15bfcdef4cbd947a6b28`. |
| Selected Runtime wheel | `cogit_runtime-0.3.8-py3-none-any.whl`, SHA-256 `931bbb9b18ee3cab47a272f1e3be3e614531d8907bc0dfab468797d4ef00ae67`; exact reviewed A02.RUNTIME producer wheel. |
| Selected SDK wheel | `cogit_agent_sdk-0.5.3-py3-none-any.whl`, SHA-256 `242d52f3285d3e66ba90aff5eb00fbf71d2cd2de3951be2b45e4e65189f4e829`; locally rebuilt from reviewed source `7ba4e3baeae574023424b0498cd537c8de8f206c`. |
| Selected AgentDb client wheel | `agentdb_client-0.2.5-py3-none-any.whl`, SHA-256 `1fa62eabd215fa1555381769d49c1bf523ca91fabc2c1fe993150060f3078fb5`; locally rebuilt from reviewed source `65a1948e0bbe613a527b7287dcc2e41e049fa091`. |
| A04 worker-proof packages | Historical Template 0.1.4 evidence wheel, SHA-256 `2bb42197ba7a15cb272ef54b96618add36946a1bbe43824d1017471a2c2e416c`, installed with `--no-deps` in the original PR proof. A post-merge rerun used the 0.1.5 wheel SHA-256 `6bec615af21bee97da1f376bfa8f56c5021a64f00e466980e1033819d4ac191e` in a dependency-clean installed cohort. |
| Current database module | `cogit.cogit-finance` version `1.1.0`, canonical manifest digest `61f796ccbb759899a088527bd94c68936f96d51bd372b04506afde4fadb23461`, minimum AgentDb schema 179 |
| Retained historical module | Version `1.0.0`, canonical manifest digest `9a2e000b015a71acbed53d19fb33885f1f534f3c41a31ccc5259cf44ab25df4e` |
| D08 successor fixtures | Generated 2.0.0 retained-alias manifest digest `2a3a4a6c2a7259b522d020b4dd17e3617d4ecf69472a12029e59ec5e0f65cee4`; generated 3.0.0 retired-alias digest `211392dcc7c38ff2b3c89d7b7c2bd8f74d4ca3059eaaa0dc8a3b69be51e3f8a8`. These are test fixtures, not the active module. |
| A10 public fixtures | Canonical UTF-8 input SHA-256 `b5499c65746606fe606ef5fd6275c7c5910110efe2f7432841b24d72e06b4e6e`; root JSON fixture SHA-256 `de93b59e89b5ed72ef99791c1de1320a6bf0ccb50553262dbb677bb8c2378844`; worker-action output fixture SHA-256 `c94ec1fa3b3183ae52feed13057ec8bddc044fb057c500cf249a9efc92616861`; public schema SHA-256 `9e51f5d12e49cb2bd185dc960cd2be3cf1bfe9676eee02715c8d4d1a820be499`. These hash committed Git bytes; the live root has its own digest below. |
| Original SQL migrations | `000001` SHA-256 `8f29fb9257338f7900e15c6add9b834d46579265565ceb8576ffb45ad037d632`; `000002` SHA-256 `e21386240e510af0b13d791a6dc9d3bc0843ea4f3ba0f37e62f49a603f816817`. Their bytes remain unchanged. |
| New SQL migration | `000003__reference_list_v2.sql` SHA-256 `efdfe3872da07f45826c202684d8753d4fe2381768db0c6fd8d8b2b4913f49a4` |
| New list contract | `requests.list` export version `1.1.0`, contract ID `cogit.cogit-finance.requests.list.v2`, SQL function `cogit_finance_list_v2`; accepts an empty first-page `after`, returns full rows for AgentDb facade projection, bounds pages to 100, and rejects unsupported filter/sort values. `requests.get` and `requests.put` retain their v1 contract IDs. |

The current bundle is [the package database manifest](../../../src/cogit_finance/database/manifest.json), loaded and hash-checked by [database_bundle.py](../../../src/cogit_finance/database_bundle.py). The historical bundle is under `src/cogit_finance/database/historical/module-1.0.0/`. The explicit descriptor generator is [enable_database.py](../../../scripts/enable_database.py). The installed worker write uses `request_id` as its stable business key in [database_example.py](../../../src/cogit_finance/database_example.py); it does not use a run, attempt, or provider ID. [The database example](../../database-example.md) describes the actual AgentDb deployment CLI and keeps deployment, tenant-client and fenced-worker authority distinct. The default synthetic `RecordService` deduplication remains process-local.

The selected framework wheel cohort is recorded in [PROVENANCE.md](../../../vendor/wheels/PROVENANCE.md) and [cohort.json](../../../vendor/wheels/cohort.json); Template 0.1.6 retains the same 0.3.8/0.5.3/0.2.5 closure as 0.1.5. The Runtime wheel matches the reviewed producer bytes. The selected SDK and client archive hashes differ from Runtime's earlier validation copies; the source revisions and exact local hashes above identify the bytes used for A02, A04 and A10. The earlier A01 client 0.2.4, SDK 0.5.2 and Runtime 0.3.6 wheel bytes remain preserved in provenance. The selected client 0.2.5 accepts AgentDb schema 179, not the separate schema-180 D03 fixture.

## Validation

- **A02 image and stack:** [The A02 proof](A02_IMAGE_PROOF.md) reports 95 Template
  tests passed and four existing skips, local smoke evaluation 4/4, and passing
  Ruff, formatting, Pyright, import-boundary, dependency and frozen
  noneditable-package checks. The final bridge also passed a socket-level HTTP
  half-close regression. The image imported `psycopg 3.3.4` and verified 429
  installed framework files against the selected wheels. In a fresh isolated
  PostgreSQL Compose stack, migration created 14 Runtime tables at Alembic
  `0007_outbox_run_identity`; a second migration preserved the head and tables.
  The server and worker became healthy. The bridge published only host
  `127.0.0.1:18082`, and host health and action lookup returned HTTP 200. A real
  `plain_request` was processed with zero retries and a completed run; after
  force-recreating the worker, a second real request did the same while the
  first stayed processed.
- **A04 durable write:** [The A04 proof](A04-RECOVERY.md) passed one opt-in live
  PostgreSQL test using a read-only AgentDb D01 checkout at
  `65a1948e0bbe613a527b7287dcc2e41e049fa091`, schema
  `000179__module_resource_projection`. The first real worker's `requests.put`
  committed, but a proxy dropped the HTTP 200 response. The attempt expired;
  a replacement worker claimed and completed the projected job. There were
  two observed PUT requests, one `core.module_worker_receipts` row with the
  same request key/digest/result, and one package row at revision 1. Attempt
  generations 1 and 2 were `expired` and `succeeded`; the run succeeded.
  Template 0.1.4's old dependency metadata required `--no-deps` for the
  original PR proof. On 2026-10-08, the same tracked fixture passed 1/1 in
  106 seconds with the installed Template 0.1.5 wheel and selected Runtime
  0.3.8, SDK 0.5.3 and client 0.2.5 wheels. `uv pip check` was clean. It
  again observed two PUTs, one package row at revision 1, the same receipt
  and result, a first worker exiting on reconciliation, a replacement worker
  reporting `claimed=1 completed=1`, expired/succeeded attempts, and a
  succeeded run. This closes the historical `--no-deps` caveat for the
  schema-179 recovery behavior; it is a separate installed-wheel proof, not
  a Docker image rerun.
- **D08 module evolution:** [The D08 fixture](../../../tests/fixtures/d08/README.md)
  passed six Python fixture tests and a live AgentDb schema-181 PostgreSQL
  upgrade against commit `dadf1cd`. It installed 1.1.0 and created an old
  object, installed 2.0.0, read the same old object through the retained
  read-only route, and rejected old create. A new resource accepted the same
  natural key as a different object ID and type; both resources read/listed
  their own rows, wrong-tenant reads returned 404, and 3.0.0 retired the old
  route while preserving the new one. Original module resources and old
  object identity remained unchanged.
- **A10 canonical input and public root:** [The installed worker proof](A10-ADAPTER.md)
  passed 1/1 against real AgentDb D01 schema 179 with a noneditable 0.1.6
  wheel, installed Runtime CLI and no source path. The tracked
  [canonical input](../../../tests/fixtures/a10/canonical-input.txt) was
  admitted as exact UTF-8 `text/plain` bytes. One module worker receipt and
  one package row were present; the worker reported
  `claimed=1 completed=1 failed=0 parked=0`, and run
  `773b7c56-0e29-4c6d-8f1c-c25190a91c43` succeeded. An authenticated
  artifact read returned the exact public JSON bytes and SHA-256
  `21dee8933c917490c3859eb805bdd9799c50a3069ab1c676cf1a3f772cba7355`.
  That root artifact was linked to the same run as evidence. Runtime's settled
  `RunResult` artifact was separate and included internal action output; its
  `persist` step carried the public root ID and digest. The source gate passed
  108 Python tests with four platform-specific skips, plus Ruff, Pyright,
  import, dependency, contract, offline lock and installed-package checks.

The earlier 1.1.0 AgentDb resource proof also passed on a fresh schema-180
PostgreSQL fixture: authenticated create/get, empty cursor, 101 creates, 100+1
pagination, projection, rejected filter/sort/page-size, changed-description
conflict and second-tenant denial. This was a **module deployment and
tenant-client proof**, not a schema-180 Runtime worker proof. Its original row
stayed at revision 1 and the other tenant had no reference objects.

## Remaining integration limits

- Runtime 0.3.8's selected AgentDb client 0.2.5 accepts schema 179. The
  separate current D03 AgentDb fixture is schema 180. An isolated D03
  diagnostic passed with client 0.2.6 overlaid, but that violates Runtime
  0.3.8's client 0.2.5 dependency. A supported schema-180 worker cohort and
  its locked, installed-image proof remain externally owned work.
- Runtime's standalone `case_request` pipeline still fails at its `validate`
  action: it persists a deterministic child execution step without first
  creating the corresponding `cogit_rt_runs` row, causing a foreign-key
  `IntegrityError`. The A02 success uses the declared `plain_request` route.
  Runtime owns the child-run persistence repair.
- The current Runtime 0.3.8 claim decoder JSON-parses JSON-looking
  `text/plain` content. Preserving exact raw bytes for that input class
  requires a Runtime producer fix. A10's tenant-scoped stable request ID uses
  unkeyed SHA-256 of tenant ID, NUL and input text; with a known tenant ID,
  low-entropy instruction membership can be guessed. It is not a secrecy
  mechanism.
- R05/W04 must explicitly select the run-linked public A10 root, verify its
  SHA-256 and schema, and authorize its download. Runtime's
  `core.runs.result_artifact_id` points to an internal `RunResult` wrapper,
  not to the public root. The present SDK/Runtime cohort has no agent-facing
  root selector. The consumer gateway and assembled invoice acceptance remain
  external work.
- No G01 release approval, public package-index publication, assembled invoice
  processor integration or production deployment is claimed here. Consumer
  release approval requires its own exact wheel/module pin and acceptance.

Generate `cogit.database.yaml` using the selected Template package, and approve
its pinned module digest independently in AgentDb deployment tooling. The
active 1.1.0 module is unchanged by A02 and D08; D08's versioned successor
bundles are fixtures. The installed worker uses `request_id` as the stable
business key for database writes. The default synthetic `RecordService`
deduplication remains process-local.
