# Independent live capability proof review — 2026-10-24

## Verdict

The observed agent independently navigated two unfamiliar authenticated local
portal layouts, recovered from real failures, wrote and ran its own code and
acceptance checks, and saved PDFs whose bytes match the host-only originals, including the final
three binary fixture PDFs.
A fresh worker reused both the dedicated login and the prior worker's saved
unfinished-work memory. These bounded fixture claims are independently supported.

This is evidence of an agent adapting tools to a new interface. It is not proof of
general supplier coverage, arbitrary PDF parsing, production invoice booking,
GitHub deployment or production child-agent admission. A later recorded run also
proved model-authored child-agent creation, packaging and local Runtime invocation,
as detailed below. The root agent owns final packaging, CI and merge gates.
No ordinary Chrome session was accessed.

## Evidence and method

The reviewer read canonical AgentDB records for the following completed runs,
then fetched each original initial state, SDK-loop snapshot and result artifact
through the owned fixture's read-only artifact endpoint. The first nine artifacts matched
their canonical byte length and SHA-256 commitments. Conclusions below use recorded
assistant tool calls, their results, process exit codes and actual output files;
the agent's final narrative alone was not used as evidence. Snapshot MACs were not
independently verified or their private integrity key read.

| Canonical run | Model calls | Policy evaluations | Lifecycle |
| --- | ---: | ---: | --- |
| `460805c1-3ac8-46b4-8e8a-ecdf34f65f8b` | 29 | 87 | succeeded |
| `bcb55e41-e860-437e-adf7-705439ee796f` | 21 | 63 | succeeded |
| `148fbad1-f0d6-444f-b378-d989b453e213` | 36 | 108 | succeeded |
| `8fe0f8b1-5d60-443c-a00b-2d24a4efe362` | 26 | 96 | succeeded |
| `10ec1ce5-19b4-4e44-9180-42120bd5ecdb` | 10 | 36 | succeeded |

Private evidence remains under the local proof workspace, including
`independent-review-phase12.json`, `independent-container-restart.json`,
`independent-review-phase3.json`, the copied workspaces and `review-private/`.
The two additional successful runs and two failed coding attempts were also
preserved before fixture shutdown: ten further initial/snapshot/result artifacts
matched their canonical SHA-256 and length commitments. The independent final
checks are recorded in `independent-final-live-review.json` and
`independent-preserved-final-histories.json`. No private login URL, token, browser
profile or raw trace is included in this report.

## First layout and worker restart

Run one received a portal origin and a business request to collect May, June and
July invoices, complete only May initially, and save the rest for another session.
The request explicitly said: "Create reusable browser automation and your own
acceptance checks as appropriate"; it supplied no invoice IDs, route sequence,
acceptance code or expected hashes. The recorded model discovered the actual
navigation and invoices from DOM observations.

The portal returned a 32-byte incomplete May PDF. The agent's first diagnostic
command failed with exit 127 because optional CLI utilities were absent; it
replaced that command with Python. Its own PDF check then exited 1 with
`FAIL: invalid PDF structure`. It downloaded again, validated the 645-byte original,
promoted it using `write_bytes`, and observed successful process exits. It also
recovered from a hidden link/navigation timeout by inspecting and opening the DOM
details element. The incomplete file remains separate from the verified artifact.

Run two read exactly the text previously written by `memory_put`, at revision 1,
under `supplier_portal_invoice_session_2026`; it completed the remaining documents
and wrote revision 2. Equality was checked against the actual recorded arguments
and tool result, including the unfinished invoice identifiers/routes and May hash.

The model-authored `temp_download.py` is exactly the bytes recorded in its
`filesystem_write` call: SHA-256
`17c4d16be2e64424d886c689e584b48947108ada46b86d01ead876afe40ab1b3`.
It was invoked successfully twice through `browser_run_script`, using the owned
authenticated context (`response = page.request.get(href)`). The downloaded response
bytes and final files were independently compared to the private originals.

Docker inspection was limited to identity, image, lifecycle and mounts:

- Worker 5, ID `87f1c507c261231f085781731a8a899c530520b1100c926c7654bfe0a7785573`,
  stopped at `2026-10-24T12:10:38.943361123Z`, after its successful run.
- Worker 6, ID `df98f4986300c1e1a140e9f708733eb0524b68ecd3c18cba8159cd534435059f`,
  started at `2026-10-24T12:10:39.63727161Z`, using the same named `/automation`
  profile and `/workspace` volumes, with the cohort mounted read-only.

Both containers later show exit 143 from deliberate stopping. This is a clean
new-process continuation after a successful session, not forced-crash recovery
of an unfinished canonical run. Portal events contain exactly one login across
these two sessions; both runs close their owned browser context successfully.
Separate Playwright trace archives are present for the two sessions.

The first layout's original-file SHA-256 matches are:

| Invoice | SHA-256 |
| --- | --- |
| `DOC-810017` | `79e6ce8194451d48e23fcb3d37741d71cc6747ecb0270a3e2640ad9d525fd01c` |
| `DOC-923039` | `fcc0474786d84ac846ede098a5367450c76f6af457f1d735c6b900571cfd07a3` |
| `DOC-645748` | `ea1229adf7a03191f9c008300932e7a145d184ca2d24d9b1193e6c2162edfb2a` |

**Narrow limitation:** run two returned the two small PDF responses as base64 to
the model, then reproduced their literal ASCII text with `filesystem_write`.
The output bytes are exact for these fixtures, but this is fragile for arbitrary
binary or large PDFs. This behavior is not a general binary-download guarantee.

## Second layout and saved automation

The third run used a different portal layout and freshly randomized invoice IDs,
amounts and routes. The initial state contains none of the oracle's invoice IDs,
hashes or private login URL. All three resulting files independently match that
portal's private expected SHA-256 values:

| Invoice | SHA-256 |
| --- | --- |
| `DOC-857910` | `6c66361255b2570265d4e48308c0ba47a37dcd922394e17fd4e7a702c0e151fe` |
| `DOC-924892` | `4949b141d6cf6d1c3431f4f85a271d5c3ba0ce26317c273b0ef4701b07e6f8b2` |
| `DOC-258550` | `cb383a79db1c1b6d7697cb570cde413d016b9ea7f228829085d70f8ba48cf043` |

The model wrote three versions of `cedar_collect_paid_invoices.py`. Recorded
`browser_run_script` results show a Playwright operation failure, then an explicit
`AssertionError: invalid PDF bytes for DOC-258550`, then success. The model
changed DOM extraction after the first failure and changed the authenticated
fetch method before retrying the incomplete response. The portal log independently
records one partial document response. The final script receives response bytes
inside the browser tool and writes them internally with `with open(path, "wb")`
and `fh.write(data)`, avoiding the first layout's transcription through model text.

The final collector's bytes exactly match the final model write and invocation:
`9f96ec05073ab101c6e1b5eb9225e43156cfe2856e381cee5462c31a220c4d68`.
The saved `test_cedar_paid_invoices.py` similarly matches the model write:
`d7b0ebb78fee282293e4618e8dc13d41b4199a3565c73dd7068abe176280cd3d`.
It checks the file set, PDF header, EOF marker, embedded invoice ID, period and
amount; its real process exits 0 on the collected artifacts.

The later `failed-check-before-repair.log` was deliberately generated by running
the acceptance script against a wrong directory **after the initial acceptance
already passed**. It is a negative control, not evidence of the genuine earlier
repair. The real collector failures and repaired invocations establish that claim.

## Model-authored child agent and final F restart

The model created `invoice_inventory_agent` through recorded shell heredocs in
run `9e286a36-d7ce-4edc-be25-279083066564`. That run exhausted its model budget.
The next attempt, `cf8c00bc-0469-4c00-aa3d-9880eaec3928`, repaired the generated
manifest's JSON-schema references with a recorded `filesystem_edit`, built a
wheel and exercised the Runtime, then stopped at the old continuation byte cap.
These are failures, not completed runs. The later successful run reconciled the
retained work and reran its acceptance in a fresh worker.

The reviewer reconstructed the heredoc writes and the exact hash-guarded edit
without executing those commands. The final agent source, package initializer,
tests, `pyproject.toml` and manifest match those model-authored bytes. The source
declares `class InvoiceInventoryAgent(CogitAgent)` and binds
`inventory_invoices` with `risk="read", idempotency="inherent"`; it uses strict
typed Pydantic input/output models. Its main source SHA-256 is
`4e3ee8576ba17c4453f69f313e246925c6f57f8297567d1e73cc68262cb6011a`.

The saved wheel SHA-256 is
`d4cc1d72bc476b3f6d6105edfa1836979082c296fc2c9ba842bdd026df990755`.
Its two Python members match the reconstructed model-authored source. Recorded
output in successful run `8fe0f8b1…` confirms all three generated unit tests passed.
The model handled absent `pip` by extracting the wheel into its owned temporary
directory, then repaired its incorrect assumption that `action_bindings` was an
iterable rather than a method. It discovered the actual Runtime action route and
started the extracted wheel through standard `python -m cogit_runtime serve`.
The HTTP POST to `/actions/inventory_invoices` returned 200, five file records and
one duplicate group. The reviewer independently recomputed every returned byte
length and SHA-256 from the copied files; the duplicate group is exact.

This demonstrates local child-agent code generation, tests, wheel packaging and
Runtime execution. The successful final invocation used wheel extraction and
`COGIT_DEV_MODE=1`, not production AgentDB publication of the child. It does not
prove GitHub deployment or a hardened file-access boundary for that prototype.
The generated action accepts a local directory and follows ordinary filesystem
semantics; it was tested against owned fixture data.

Run `10ec1ce5…` then read prior working memory and discovered the saved portal
collector/tests without receiving a portal URL or workflow in its initial prompt.
It invoked the exact previously model-authored collector via
`browser_run_script`, ran the saved acceptance test with exit 0, and closed its
browser context. It made no `filesystem_write` calls. The three resulting PDFs
still match the second-layout original hashes listed above.

Independent restricted Docker inspection confirmed worker 10 stopped at
`2026-10-24T12:34:18.22370579Z`; worker 11 started at
`2026-10-24T12:34:18.937452488Z`. Their IDs are respectively
`9d605d54221a4fee1cf2395db57204d761a01adea4f9b5d6fcc7ab12a0102c49`
and `acda34eed7606766e5196768fc23e34aa4d386eabcd0102830db596269594cc5`.
Both use the F image and the same named profile/workspace volumes as the original
second-layout worker 7, with the cohort mounted read-only. The portal event log
contains exactly one login across these sessions. Container environment values
were neither requested nor inspected.

These historical F PDFs are small ASCII fixtures. The later binary-PDF fixture
change and new G acceptance are separate; their success is not implied by F.

## Code, prompts and limits

The framework supplies general browser, filesystem, process/shell and persistent
memory tools. The recorded model created the task scripts and tests at execution
time. The task prompt asked for discovery, checking and continuation; it did not
contain a supplier workflow. The observed adaptation therefore came from model
tool use and newly generated code, not a prewritten portal script.

The saved collector and test remain scoped to the discovered May–July invoice
IDs and amounts in `TARGETS` / `EXPECTED`. They are useful automation for this
task, not a recurring general invoice processor. A later request needs the agent
to rediscover new documents or revise that generated task configuration. The
acceptance parser assumes these simple uncompressed fixture PDFs; it is not a
general PDF parser. Neither fixture tests MFA/CAPTCHA, a real supplier's anti-bot
rules, arbitrary browser migrations or actual booking/deduplication in Lexware.

This report independently approves the stated local discovery, script generation,
failure handling, original-byte verification and clean-worker login/memory reuse
claims, plus the bounded child-agent creation and local Runtime invocation above.
It does not independently attest all fresh-clone packaging checks, production
deployment, and it does not authorize merging by itself. The later G proof is
independently verified below.

## Final G binary-PDF and login-restart addendum

The final fresh-clone run `e1c897fa-479b-4c2b-b499-691722bd86b3` succeeded with
25 model calls, 75 policy evaluations and zero denials. Its new-process continuation
`7315dda8-63bf-46e3-aede-22e1a96790e2` succeeded with ten calls, 34 evaluations and
zero denials. The six canonical initial/snapshot/result artifacts were fetched
before fixture shutdown and independently checked against exact recorded hashes
and byte lengths. Private evidence is in `independent-preserved-g-histories.json`
and `independent-g-proof.json`.

The first run's initial input contains neither private login URL, invoice IDs nor
expected hashes. Recorded `filesystem_write` and hash-guarded `filesystem_edit`
calls reconstruct the saved collector byte for byte. Its first real invocation
failed with `RuntimeError: Invalid PDF bytes for DOC-765845: 32 bytes`. The model
added `for attempt in range(1, 4)` and retried. The successful collector uses
Playwright `page.expect_download()` and `download.save_as(str(destination))`,
preserving the actual downloaded binary bytes without model transcription.

Final collector SHA-256:
`691f56e47018208c69782a8d3da29a4462cee5abd44bf8f084d48c3678b17e1d`.
Model-authored test SHA-256:
`45b2ff23e04b68ee57bf2620e4045ea955905867ab9eba15d9794b84e3f9eae5`.
The real test process exits 0. The separate deliberately wrong-amount check is a
negative control, not evidence of the genuine earlier download failure.

All three files are 651 bytes, include non-ASCII binary bytes that cannot survive
UTF-8 replacement decoding, and independently match the host-only originals:

| Invoice | SHA-256 |
| --- | --- |
| `DOC-272962` | `4e3a5af22e755812ccb985bd0cc4e9e6488c3683df71092352c7b50c8da620d7` |
| `DOC-823273` | `d2c0bcd37454d18e7c2f129e26eeda453f6bb2c80e18a95490630fb5f1caf353` |
| `DOC-765845` | `f5aef92e936850494831685b936fd7759b877563c034652ebb104e05c83b3fc7` |

The restart prompt supplied no URL or code. It read the saved memory key
`cedar-invoice-collection-2026`, discovered the saved files, invoked the exact
collector hash, passed the exact saved test with exit 0 and closed its browser.
There were no file-write/edit calls; all three resulting binary files again match
the originals. The portal event log contains exactly one login across both runs.

Restricted Docker inspection verified distinct workers 12/13, IDs
`eb36370fd546dc7d77491be3eb5e863f5a548a107067db1fc006a033f5abee24`
and `d3ecfef0a0ecf89aeb59e69b3bfe3638e6135025490d371d1cfa282d382b14fd`.
Worker 12 stopped at `2026-10-24T13:03:09.989006438Z`; worker 13 started at
`2026-10-24T13:03:10.442426709Z`. Both used the G image, dedicated fresh
`20261024-v2` profile/workspace volumes and a read-only cohort mount. No ordinary
Chrome session or container environment was read.

This closes the earlier ASCII-only transfer gap for these bounded fixtures.
The generated acceptance checks validate manifest identities/amounts and saved
byte consistency using a PDF signature/size heuristic. They do not parse the PDF
to establish those business fields or validate arbitrary PDFs. The independent
comparison to private original hashes supplies the stronger content evidence here.
The collector still targets the requested three periods; production multi-supplier
booking remains outside this proof.
