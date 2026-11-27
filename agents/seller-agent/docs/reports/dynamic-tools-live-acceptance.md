# Live dynamic-template acceptance — 2026-10-24

## Scope and evidence boundary

These are real `gpt-5.6-terra` model calls through the installed SDK, standard
Runtime queue worker, canonical AgentDB admission/policies and installed tools.
The explicit native OpenAI setting is `thinking_level: none` (Chat Completions).
The host supplies only an objective, portal origin, dedicated first login,
credentials and bounded authority. No selectors, supplier workflow or browser
script were supplied. The host-only fixture original hashes and login token are
not mounted into the worker. No ordinary Chrome profile or production invoice
processor was used. Synthetic portal evidence does not prove every real supplier.

**Bounded capability acceptance completed**, including the child-agent coding
proof and the final binary-original/login-reuse runs below. Coordinated pull
requests record final hosted CI and merge status. Earlier candidates and failures
are retained; their results are not relabeled as final-artifact results.

## Completed autonomous tasks

| Task | Canonical run | Observed result |
| --- | --- | --- |
| Discover unfamiliar authenticated portal; May only | `460805c1-3ac8-46b4-8e8a-ecdf34f65f8b` | Succeeded; 29 model calls; 87 policy evaluations, zero denials |
| New worker; recover unfinished work; June/July | `bcb55e41-e860-437e-adf7-705439ee796f` | Succeeded; 21 model calls; 63 policy evaluations, zero denials |

The first task observed absent `file` and `xxd` commands, switched to Python,
detected the deliberately incomplete 32-byte PDF (`FAIL: invalid PDF structure`),
retried, and passed its own invoice ID/period/paid/header/EOF checks. It saved
working memory under `supplier_portal_invoice_session_2026`.

Worker 5 was stopped before worker 6 started. Worker 6 received only the request
to continue saved work, with no portal URL or invoice identifiers repeated. The
portal recorded exactly one initial login across both tasks. It wrote and ran
`temp_download.py` using `run(page, context, arguments)` and authenticated
`page.request.get`, through the owned browser runner. Its inline Python checks
printed `ALL_ACCEPTANCE_CHECKS_PASSED`. These first tasks did not save a standalone
acceptance-test file; the second-layout task explicitly requires that artifact.

Independent host hashing of the saved PDFs, without trusting the model's hashes,
matched all three private originals (645 bytes each):

| Invoice | Original SHA256 |
| --- | --- |
| DOC-810017, May | `79e6ce8194451d48e23fcb3d37741d71cc6747ecb0270a3e2640ad9d525fd01c` |
| DOC-923039, June | `fcc0474786d84ac846ede098a5367450c76f6af457f1d735c6b900571cfd07a3` |
| DOC-645748, July | `ea1229adf7a03191f9c008300932e7a145d184ca2d24d9b1193e6c2162edfb2a` |

The incomplete May file remains as failure evidence, outside the verified result.
These tasks prove navigation/download/verification, not production booking or
exactly-once financial effects. June/July continuation also made a repeated July
download; file-content verification must not be confused with transaction deduplication.

## Artifact provenance

First successful clone E came from immutable local Git snapshot
`4fe8ff20ec16730c302a8e2207b065b773d545a7`, was genuinely cloned and renamed,
and installed without editable/sibling imports. Image configuration digest:
`sha256:2e6043ae191bb3d090cb81cc63cb54a81f87ae9937d723169c87246db8530df9`.
The image build compared 633 installed package files. Approved executable closure:
`91c4742825259556aef25c0755d1c3cde029a5ef018cafadea591e950b767d39`;
manifest: `bca4d0fe50d74c1d185a12c4bab24a1a99130b97b4914e35d9b8990161546a41`.
This candidate preceded the filelock security update; it is not the release image.
Final clone F is snapshot `435bb2e9ea1c144e70f49d404857ebcf1f2a6833` and uses
the reviewed patched browser/transport wheels and locked filelock 4.2.1.
`vendor/wheels/cohort.json` records exact component commits and artifact hashes.

## Failed attempts and repairs

1. AgentDB selected an unrelated policy version instead of the admitted pin.
   Forward migration 201 fixes selection; real PostgreSQL multi-version, tenant
   isolation and retained historical-invoice tests pass. Immutable invoice bundles
   capped at schema 200 still cannot be newly installed on schema 201; they were
   not modified to conceal that compatibility boundary.
2. Canonical model admission rejected missing token bounds. Template setup now
   validates explicit primary and fallback bounds before provider preparation.
3. The model API rejected tools without an explicit reasoning setting. The SDK
   now forwards the existing typed `defaults.thinking_level` only for native
   OpenAI. A direct 32-token transport diagnostic proved only connectivity, not
   agent capability. The successful runs used `none` explicitly.
4. The initial test portal process ended across a turn boundary. The host started
   a new fixture and seeded only its synthetic login; this was not a browser fix.
5. Docker address pools were exhausted. The isolated fixture uses the existing
   default bridge and a task-owned loopback API bridge; no other network or
   container was removed. Production URL validation was not weakened.
6. CI found stale SDK/wheel pins and a missing browser transport in the clean
   installation closure. Pins/closure were corrected. Unpinned setuptools changed
   a generated client artifact; a build constraint reproduces its existing receipt.
7. Security checks found affected certifi/filelock versions. The candidate locks
   and browser requirements were updated and retested; no advisory was suppressed.

Failed manually admitted fixture runs can remain `running` because that held
fixture does not run the production queue supervisor. A separate actual pg-boss
timeout/maintenance test proves interrupted execution, expired attempt, dead work
and failed run convergence. This limitation is recorded rather than calling those
abandoned fixture runs settled. Model prices in this fixture are synthetic
accounting rates and must not be presented as actual vendor charges.

## Code versus prompts and configuration

Code implements provider discovery/typed validation, lifecycle ownership, shared
browser context, cleanup and mandatory central policy enforcement. The generic
prompt says “Write automation and task-specific acceptance checks”; it contains
no portal routes or selectors. Model identity, bounds, reasoning setting, provider
selection and headless/persistent mode are configuration. Agent-authored files
are output evidence, not prewritten package workflows.

Private evidence is retained under the task's `.data` and `.tmp` directories:
canonical run/result exports, process logs, working-memory snapshot, browser
traces, original-file verification and immutable clone/image receipts. Browser
traces may contain authentication state and are deliberately not committed.


## Final patched image: second unfamiliar layout

Run `148fbad1-f0d6-444f-b378-d989b453e213` succeeded: 36 model calls,
108 central policy evaluations, no denials. Container image configuration digest
is `sha256:e79c0de4d3559d5c26d1611d733a4104877b655cd0339b2859a82a77464892a9`;
manifest-list digest is
`sha256:0f807c1a3f150c60a0097a626d1dde286896bf8a5ea022acea0db5bb235abf52`.
Read-only installed inventory contains 52 distributions; the 41 public Python
dependencies have no known advisory findings. This does not claim an OS-CVE scan.

The model wrote `cedar_collect_paid_invoices.py` and
`test_cedar_paid_invoices.py`, executed both, and repaired genuine DOM and
incomplete-document failures. The collector now fetches a byte array, decodes
base64 inside its own script and writes with `wb`, preserving binary bytes rather
than transcribing PDF content through model output. All three saved originals
match the private oracle; the host also reran the saved tests successfully.

| Invoice | Original SHA256 |
| --- | --- |
| DOC-857910, May | `6c66361255b2570265d4e48308c0ba47a37dcd922394e17fd4e7a702c0e151fe` |
| DOC-924892, June | `4949b141d6cf6d1c3431f4f85a271d5c3ba0ce26317c273b0ef4701b07e6f8b2` |
| DOC-258550, July | `cb383a79db1c1b6d7697cb570cde413d016b9ea7f228829085d70f8ba48cf043` |

The agent also deliberately ran a wrong-directory negative check after initial
acceptance passed. That log is a negative control, not the earlier real failure.
Its generated expected IDs and periods are scoped to the observed task; this
proves autonomous adaptation, not a universal recurring-invoice workflow.

## Coding proof budget stop

Run `9e286a36-d7ce-4edc-be25-279083066564` produced a separate agent package,
typed action, manifest, package definition and tests, then stopped at model
reservation admission after 36 calls. The conservative one-million-token input
reservation plus accrued synthetic accounting spend exceeded the remaining
per-run cap. Enforcement was not weakened. The host preserved its files and
submitted a new bounded continuation objective; no child-agent code was supplied
or repaired by the host. Its unfinished run is not counted as acceptance success.


## Completed bounded coding proof and checkpoint repair

The next coding run, `cf8c00bc-0469-4c00-aa3d-9880eaec3928`, built the child
wheel, passed its three tests and invoked its action, but stopped before completing
the task. Its v1 continuation metadata reached 65,227 bytes after 43 model slots
and 53 tool slots; the next publication exceeded the existing 65,536-byte limit.
Tool/model response bodies were already artifacts. The accumulated replay index,
not a PDF body or prompt, caused this second real infrastructure stop.

Fresh-worker run `8fe0f8b1-5d60-443c-a00b-2d24a4efe362` then completed the
bounded task successfully with 26 model calls. It inspected and retained its own
existing code, reran all three tests, checked the wheel and invoked the typed action
through standard Cogit Runtime HTTP: `POST /actions/inventory_invoices` returned
200. The result enumerated five PDFs and correctly grouped the duplicate May file.
The observed acceptance tests cover read-only preservation, duplicate detection
and invalid input. The host supplied objectives and restarted workers; it did not
write or repair the child agent's implementation.

The generated wheel is `invoice_inventory_agent-0.1.0-py3-none-any.whl`, SHA256
`d4cc1d72bc476b3f6d6105edfa1836979082c296fc2c9ba842bdd026df990755`.
Its source uses typed Pydantic input/output, SDK `@operation` and `bind_action`.
The generated operation declares a read risk and inherent idempotency. This is a
local child-agent prototype, not a production path-security audit or deployment.
The fresh container lacked `python -m pip`; the model extracted its exact wheel
using Python's standard ZIP library for isolated execution. Therefore the evidence
proves built-wheel execution through Runtime, not a pip installation of that child
wheel. The parent worker itself used the installed, verified release cohort.

These two stopped runs remain recorded as failures. A separate bounded success
does not erase either limitation. The checkpoint issue triggered a deliberate
Runtime/AgentDB continuation.v2 code change, with exact artifact grants and
authenticated server capability negotiation; its separate acceptance evidence is
recorded in the journal review. The inline checkpoint bound stays unchanged.

## Patched-image login reuse

Run `10ec1ce5-19b4-4e44-9180-42120bd5ecdb` started in another worker process
using the final patched F image and the same dedicated fixture profile. Without
receiving a new portal URL or workflow code, the model found its saved collector
and acceptance tests, reran both successfully, and retrieved the three exact
originals again. The private portal recorded exactly one login across initial
collection and restart. This extends restart evidence to the patched image.

The earlier fixture PDFs were ASCII-only. Their exact hashes establish byte
preservation for those originals, but cannot alone detect text-transcription
strategies. The strengthened fixture now includes a standard binary PDF comment;
its own test verifies that decoding and re-encoding as UTF-8 changes the original.
The final candidate is tested separately against these binary originals.


## Final continuation-v2 candidate: binary originals

A new immutable source snapshot `7026602dd9be84d3cce72e5f7e1d227c0dd41c98`
was genuinely cloned, renamed with the supported bootstrap, installed noneditable,
and built into image G. It includes Runtime source `c95d0be4020803cb419ad17b1f2b26b7680c817a`,
wheel SHA256 `a6df5e900a90debe4c949092ca2bc37f4c80d1eba0d34453b5fb6cb6caa589ad`,
and the schema-202 policy module. Image configuration SHA256 is
`749118921a7bba3a4a7df6e72b202ffa7773c2386bd0b59ccb0991f367b6ec10`;
manifest-list SHA256 is
`a0dedeb299da12d2fdbb28539e7408aa3eec591488c1b892590d078d75fde1d8`.
An independent read-only, network-disabled container check compared **635 installed
archive members** against their exact framework and agent wheels successfully.
The parent used Python 3.11.16, SDK 0.5.12 and Runtime 0.3.23 in the image.

The model started with empty workspace/profile volumes and a new local portal
layout, randomized routes and binary PDF originals. The host seeded only the
synthetic login. It supplied the portal origin and business objective, without
selectors, invoice IDs, workflow code, oracle hashes or fixture source.

Run `e1c897fa-479b-4c2b-b499-691722bd86b3` succeeded with **25 model calls,
75 policy evaluations and zero denials**. The model wrote
`cedar_invoice_collector.py` and `test_cedar_invoice_collection.py`. Its first
collector failed on a genuine 32-byte incomplete PDF. It preserved failure
evidence, added bounded download retries, ran the repaired script through the
owned browser context and ran its saved checks successfully. Its Playwright code
uses `page.expect_download()` and `download.save_as(...)`; PDF bytes do not pass
through the model as text. The host reran the saved acceptance script successfully.

The generated tests check observed invoice identity/period/amount metadata,
file presence, signature/size and agreement with the generated manifest's hashes.
They are task-specific checks, not a general PDF parser or independent oracle.
The independent host comparison below supplies the separate byte-integrity proof:
all three 651-byte originals, including non-UTF-8 binary bytes, match exactly.

| Binary original | SHA256 |
| --- | --- |
| `2026-05_DOC-272962.pdf` | `4e3a5af22e755812ccb985bd0cc4e9e6488c3683df71092352c7b50c8da620d7` |
| `2026-06_DOC-823273.pdf` | `d2c0bcd37454d18e7c2f129e26eeda453f6bb2c80e18a95490630fb5f1caf353` |
| `2026-07_DOC-765845.pdf` | `f5aef92e936850494831685b936fd7759b877563c034652ebb104e05c83b3fc7` |


The host then stopped worker12 and launched worker13 with the same dedicated
profile/workspace volumes. Run `7315dda8-63bf-46e3-aede-22e1a96790e2` received
only a request to find and rerun the saved work, without repeating the portal URL
or any workflow code. It succeeded with **10 model calls,34 policy evaluations
and zero denials**. All three binary originals matched again; the portal logged
exactly **one login** across both workers. Both task-owned workers are stopped.
The final runs' canonical histories and results are retained privately.

The synthetic model-spend cap for this isolated fixture was explicitly raised
from20 to50 to avoid the earlier conservative-reservation stop during testing.
It remains centrally enforced and bounded; these are synthetic accounting rates,
not a statement of actual vendor charges. No production policy was changed.

The long-journal crash/replay proof is a separate deterministic installed Runtime
test, not an extra live-model claim. It uses an84,231-byte final index while the
inline checkpoint remains20,791bytes, survives worker and API replacement, and
finishes with55 committed keyed writes without replaying the first50. See the
independent journal review for exact receipts, denial tests and remaining bounds.

This completes the bounded fresh-clone/browser/coding acceptance. It does not
establish universal supplier support, production booking, autonomous external
deployment, or exactly-once execution of arbitrary unkeyed scripts.
