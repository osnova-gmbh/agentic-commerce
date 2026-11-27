# Reusable agent-lab fixes in the template

These are **code and YAML configuration changes**, with no agent prompt change.
The source work is isolated from the original template and invoice installations.

## One authored agent definition

The default `cogit.yaml` now declares
`metadata.entrypoint: cogit_finance.agent:Agent`. Bootstrap renames
that value with the package/class. The optional database profile is generated
from this native YAML and selects its database class in the same field.

Docker, Compose, worker launch and check commands obtain their class from YAML.
`scripts/cohort_entrypoint.py` uses Runtime's actual manifest loader. Its contract
is: "an explicit legacy selector must agree when both exist". Preparation also
checks, without importing wheel code, that the selected module declares the
concrete class. Prepared-artifact verification repeats the YAML/class agreement.
The selected source may be a normal `.py` module or a package `__init__.py`.
The concrete top-level class convention excludes re-export aliases in this
template's build guard; it is not a restriction on Runtime's Python loader.
The generated executable/receipt JSON is an integrity and installation record;
there is no authored `agent.json` contract.

The canonical integration fixture now retains and retires its unused placeholder
through authenticated AgentDB lifecycle endpoints, with exact tuple/status
checks. Only its read-only seeded-ID lookup uses owner access. This is isolated
test setup with synthetic platform credentials; customer deployment hosts use
their actual platform authorization. The fixture verifies all five mandatory
wheel commitments, including `cogit-tool-core`, rather than assuming the older
four-wheel closure or treating optional provider pins as installed requirements.

## Database compatibility discovered by real deployment

The first real canonical installation exposed another existing template defect:
module 1.1.0 capped physical core migrations at 199, while the selected isolated
AgentDB server reports head 203. Module installation correctly rejected it.
This is separate from the public schema compatibility label.

The new immutable module **1.1.1** certifies the finite range **179..203** and
declares upgrade from 1.1.0. Its SQL, resources, exports and contracts are unchanged.
The new canonical artifact is
`d4f0551fea2ccd14c882e3d7d0b0a404becb8082f51ff38db5cd52a69d55a5c3`.
Every original 1.1.0 declared asset and its original canonical digest
`61f796ccbb759899a088527bd94c68936f96d51bd372b04506afde4fadb23461` remains
under `database/historical/module-1.1.0`; the D08 historical fixture selects that
bundle explicitly. Bootstrap and packaging validate both retained versions.
Future framework release owners must certify a compatible immutable module,
rather than asking customers to patch the bound or bypassing the installer.

## Permission preservation

`cogit_finance_setup.manifest.write_manifest` now says: "Replace validated YAML
without changing an existing POSIX access mode." Previously, replacing a readable
manifest with `NamedTemporaryFile` changed its mode to 0600. The fix keeps the
existing mode and leaves a new file's secure temporary-file default in place.
Failed promotion retains the old manifest and removes only its owned staging file.

The lab's protected Windows staging-directory ACL defect does **not** occur in
the template's direct cohort mkdir/copy path. A direct Windows/Python 3.11 probe
found both NamedTemporaryFile and ordinary file creation unprotected and inherited
(security descriptor control 33796). No blanket ACL fixer is copied upstream;
Windows inheritance is covered without claiming that probe fixes a bug.

## Existing behavior retained

The image already uses a clean uv virtual environment, noneditable installed
wheels, nonroot UID 10001 and a writable owned `.data` directory. The workspace
image separately owns `/workspace`, `/automation` and `/run/cogit`. Startup hooks
and unexpected installed payloads remain rejected by Runtime. The template does
not need the lab's setuptools removal, owner SQL, alternate descriptor format,
hardcoded reconciliation tools or domain-specific acceptance checker.

## Final validation (2026-10-26)

The final installed template passed **195 tests**, with **5 platform-dependent
skips**. This includes a clean copied bootstrap, renamed wheel installation and
a real custom command launched from outside the checkout with only its renamed
`cogit.yaml`. Ruff passed, all 68 Python files were formatted, strict Pyright
reported zero errors, and import/dependency/lock checks passed. The immutable
module patch separately passed 40 focused tests with four platform skips.
Independent review compared all seven retained 1.1.0 files to original Git blobs
and loaded the new approved artifact with AgentDB's actual module-kit.

The real authenticated lifecycle fixture retained and retired its unused old
cohort through public endpoints, then published the replacement. Readback showed
old installation/deployment disabled and new installation/deployment active.
The isolated server's physical migration head was **203**.

### Real queued database-agent work

Both cases used the normal installed canonical worker with a YAML-selected class,
module 1.1.1 and the final framework wheels. The task was to persist the supplied
plain-text request and publish the typed reference receipt; it did not review or
book an invoice. Each worker reported `claimed=1 completed=1 failed=0 parked=0`.
A separate TypeScript oracle checked the original stored text, tenant-scoped ID,
one write receipt, revision 1, artifact link, and exact bytes read through the API.

| Input | Run ID | Public root SHA-256 |
| --- | --- | --- |
| canonical text | `601e4799-8125-4f20-b95f-3a304ee30330` | `9a3ecf8a487c66be2d919ab6f9851e65e503bf6f879138e555937c6112062341` |
| JSON-looking literal text | `c8ca2606-07db-4b81-9146-7d8a4f6bf16f` | `5280eda8da9e1226ec5d10470b52eeaf3ffa436ddf3b4e2d0cd5587e2a1b0e23` |

The second input remained literal text rather than becoming trusted request
fields. Both public receipts have `outcome=completed`, `status=open`,
`revision=1` and `schemaVersion=reference-request-result.v1`. Runtime's internal
settlement artifact was checked separately from this public root.

One initial parallel probe hit the test driver's 90-second worker deadline.
The same case passed when rerun alone with the original deadline and assertions;
the failed log remains local history. This does not establish a root cause or
performance improvement, and no production timeout was increased.

### Container and artifact checks

The final image is
`sha256:be8f4b5d06b1ff0036653cffcdae885f9ac2484ce011071acf51afc7bca3cfa7`.
Offline, read-only execution as UID 10001 verified native normal/database YAML
entrypoints, exact framework commitments, retained 1.1.0, active module 1.1.1,
only the permitted uv startup hook, and preserved POSIX mode 0640. All **574**
installed agent/framework payload files matched the reviewed host wheels.
The Windows all-extras environment compared **651** payload files.

The Windows-built agent archive is
`4ee27c099cf10fbed2e687f9ad05adcbd83c95f96fa852c7edf942b4b649904e`;
the image's Linux-built archive is
`2abd42c8a32c8ad83f32409901408141694fd9245ff6fdfa1029b0e1624d3eae`.
Their archive hashes differ; the installed immutable payload comparison passed.
Each prepared cohort binds its own exact archive and manifest bytes.

The image's default command also started successfully and completed one actual
standalone SQLite queue request: one completed business execution, two child
invocations, one pipeline checkpoint, and all three steps completed. Its model
was the explicitly configured local echo. This container check is distinct from
the canonical AgentDB checks, which used installed host workers.

All owned proof containers, project networks/volumes and canonical Python workers
were absent at final cleanup. Local images and ignored evidence remain available
for inspection. No production rollout, memory/CPU improvement or package-index
publication is claimed.
