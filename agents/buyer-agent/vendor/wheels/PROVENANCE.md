# Vendored framework wheel provenance

## AgentDB-only cohort (0.1.24)

Runtime 0.3.31 was built from the exact merge commit of Runtime PR 52 with
the producer's pinned build constraints. The selected SDK, AgentDB client and
supported tool providers retain their existing producer archives. Earlier
Runtime and optional memory archives remain available from repository history.

| Wheel | Producer commit | SHA-256 |
| --- | --- | --- |
| `cogit_runtime-0.3.31-py3-none-any.whl` | `55bce909fdafdf8d796f12bf4434c91c961227a9` | `5d81546f43a910a78860ff5c6bdb244ca00c338c3ebb5ccc1827034b8bd3fb7b` |

The Runtime wheel contains 155 normalized payload files with digest
`fe92c6e9864e0aa1fbf97755cc2ed5d040b5dbba074e8c34dc5b6eb21468774b`.

## Local Responses cohort (0.1.23)

The selected SDK and Runtime wheels are built from the exact producer
commits using the pinned Hatchling backend. This cohort supports local
text-only Responses profiles and retains the reference echo profile.

| Wheel | Producer commit | SHA-256 |
| --- | --- | --- |
| `cogit_agent_sdk-0.5.16-py3-none-any.whl` | `7dc11fd500427a1d27fd477e4fac2322c5cff6b5` | `16f2c46e3b4648bdd6d784fdbec5cc8ce79a62d50b80eaa2c962bc0185c1a3b6` |
| `cogit_runtime-0.3.30-py3-none-any.whl` | `9f5c1f3bd1e8476c0da47c919d1c677a9fd32bfb` | `fe2ee689019cc319ca24414408b7be104b22173913de62603e09befe408bec91` |

## Template 0.1.22 reconciled approval and toolkit cohort

This reconciles the queued approval/bootstrap branch `dbd7e086871e6bd5f02613ea853be8d647d2c29c`
with upstream toolkit PR31 at `e6413584f630bd3263651ec1e3cf865916a7e9b7`.
The active selection is SDK 0.5.15, Runtime 0.3.29, AgentDB client 0.2.13,
tool-core 0.1.3, and optional shell/browser 0.1.2. Source version, manifest and
frozen lock remain 0.1.22; no 0.1.22 release tag existed at reconciliation.

The historical branch sections below record their original selected cohorts.
The current `cohort.json` and lock combine Runtime 0.3.29's exact producer wheel
with the reviewed shell/browser archives from library PR84. Both old and newly
selected archives retain their original bytes and committed producer receipts.
No historical wheel or immutable module receipt was rewritten.

Protected durable resolution writes, capability/approval gates and the clean
bootstrap regressions are retained. These are package/configuration/documentation
changes; business prompts and domain code are unchanged by this reconciliation.

## Earlier 0.1.22 branch: bootstrap formatting

This template-only patch makes renamed code and tests pass the unchanged Ruff
format/lint gate for supported package names up to 48 characters. Python display
names remain safely encoded as string data; the prompt-resource test reads the
expected name from the selected manifest, avoiding quote/length-dependent code.
Stable multiline imports and short path constants change layout, not business
logic. A generated-tree regression checks short/default/maximum package names
and quoted long display names without running a formatting repair.

All selected framework archives, producer receipts and historical assets remain
the exact 0.1.21 cohort below. Runtime remains 0.3.29. Business prompts and local
resolution behavior are unchanged; no publication or deployment is claimed.

## Template 0.1.21 local queued approval integration

This local template selects the normal Runtime 0.3.29 release identity for the
reviewed queued approval fix. Code binds each local continuation to its original
saved context, action, payload, key and approved decision before case/report
creation. Decisions and consumption cannot be reset by delayed concurrent writes.
The canonical AgentDB worker still derives current authority through its separate
server-backed path; local saved claims are not refreshed canonical grants.

| Newly selected wheel | Committed producer source revision | SHA-256 |
| --- | --- | --- |
| `cogit_runtime-0.3.29-py3-none-any.whl` | `df14818e6051aa76073ddc6d7b751da2ccf842e1` | `f440cf12d22bf1bbb8e443972c1ca0596de619c5a19c70eadc6248f1826029bd` |

The wheel was built from the exact committed producer source archive. SDK 0.5.15,
client 0.2.13, tool-core 0.1.3 and optional provider archives retain the exact
selected bytes and producer receipts below. Runtime 0.3.28 and every older
framework wheel and historical database module remain preserved unchanged.

The template's existing `apply_resolution` now requires `records.write`, a
request key and approval. Its agent-owned local SQLite ledger commits the effect
and exact-key binding atomically; the `records.read`-protected
`lookup_resolution` reads that effect after restart. Schema initialization needs
no manual setup. These are template code, contract, dependency, test and
documentation changes; business prompts are unchanged. `cohort.json` and the
frozen lock bind the actual selected archive. No publication, live canonical
acceptance or deployment is claimed by this local integration.

## Template 0.1.21 Windows toolkit fixes

The optional workspace profile selects the two reusable fixes merged in
[library PR84](https://github.com/osnova-gmbh/cogit-library/pull/84), exact producer
`b654e46b0da0bb43e1524ce8ede56118c9f334a7`. Shell 0.1.2 preserves top-level
PowerShell headers/exit behavior while setting Console and pipeline UTF-8.
Browser 0.1.2 retains exact owned process objects before graceful shutdown,
confirms termination before profile release and guarantees forced Job cleanup.

These are selected package artifacts and configuration/documentation changes.
No template business code or prompt changes. SDK 0.5.15, Runtime 0.3.28, client
0.2.13, core 0.1.3 and all other selected provider wheels remain unchanged.
Every historical wheel and immutable module remains byte-identical. No
package-index publication, active deployment or customer rollout is claimed.

The wheels were built with the six existing exact build-tool versions in
`vendor/build-toolchain.json`; packaged payloads and RECORDs were checked against
the committed producer source. `cohort.json` pins the actual resulting archives.

| Newly selected wheel | Committed producer source revision | SHA-256 |
| --- | --- | --- |
| `cogit_tool_shell-0.1.2-py3-none-any.whl` | `b654e46b0da0bb43e1524ce8ede56118c9f334a7` | `a71cca62c9042eab74dd17b2f367ff2d89ebbde7af0558530d3cfe8657c844a4` |
| `cogit_tool_browser-0.1.2-py3-none-any.whl` | `b654e46b0da0bb43e1524ce8ede56118c9f334a7` | `92b5bf62c193d56437d586ff3de183cff0d60e0bc5117e0e2865f239fea9c4d1` |

## Template 0.1.20 review corrections

Code changes make bootstrap display names safe in Python and YAML and validate
all text before changing a clone. Package configuration selects Runtime 0.3.28,
which wires protected-action preflight into the canonical worker factory.
Production prompts and classifier criteria are unchanged. No business policy is
published or activated, and no deployment or package-index publication is claimed.

| Newly selected wheel | Committed producer source revision | SHA-256 |
| --- | --- | --- |
| `cogit_runtime-0.3.28-py3-none-any.whl` | `5773d3dfefe0de8a080e675a04a7b4714ed80e86` | `ea6adb9075788be2ac86486bd4a80c266bf6fcb7bbce891b4a3c6be3441058a5` |

The exact SDK 0.5.15, client 0.2.13 and tool-core 0.1.3 archives below remain
selected. The released Runtime 0.3.27 archive remains retained with its original
bytes and provenance. Reference module 1.1.5 certifies physical schema 179–213,
with canonical manifest SHA-256 `4a317b715605a66a95ebfd11aebaa9b58155b8dba79ed349b179ff89db9f1fa4`.
The complete released 1.1.4 tree remains retained at
`database/historical/module-1.1.4`, original bound 211 and digest
`701bb78e4cfd2f0f1ba340afd8149c7eb62bb67c53970814fa019e3de6f42408`. Module SQL, exports and resources are unchanged.
The universal-policy module and public wire schema remain at the exact 211
commitments recorded below. `cohort.json` records the current selection.

## Template 0.1.19 universal-policy candidate

This candidate configures SDK 0.5.15, Runtime 0.3.27, AgentDB client 0.2.13 and
tool-core 0.1.3. The selected filenames, actual archive hashes and committed
producer receipts are recorded below and in `cohort.json`; the lock is generated
from those actual local archives. No package-index publication or deployment is
claimed. SDK 0.5.15 remains byte-identical to its reviewed archive.

| Selected wheel | Committed producer source revision | SHA-256 |
| --- | --- | --- |
| `agentdb_client-0.2.13-py3-none-any.whl` | `2f37f53bf262fa8e6f1f74d14a10b016b6ac8dbf` | `a85a1257374f4be432d7bffcfc51625fa87ee59e23ca7793ba35a423c601603e` |
| `cogit_agent_sdk-0.5.15-py3-none-any.whl` | `c91a938ae9884344ff08e859ae1c0f3ca024b88f` | `2cd3428442af32d3d345ec9c6f5361ee1c87bddb1b0519ec829438fa99ea43d9` |
| `cogit_runtime-0.3.27-py3-none-any.whl` | `3cd4053209141ad784a7f32fcdd08cecb4987e3d` | `821ce6394a436df8c3204f0d2fe9aed28590006df09196029419f3ab70480e9a` |
| `cogit_tool_core-0.1.3-py3-none-any.whl` | `2f52218d84d7f58afe1a87241b1bdccb30cc895e` | `2c4eae7441256515b55cb383626681823732038110c1ccd1e88fc2f493656c2e` |

The client's embedded generator input remains
`eb1a29e1d825046fa7dba8a282e45b386adc35ff`, with OpenAPI digest
`9b22d950ec81cd7c46b5eed70c1d23ac4a405d031b8a4084fed1bc0d913b1d6b`.
That generated-byte commitment is distinct from its final producer receipt.

Reference module 1.1.4 declares the finite schema range 179 through 211, with
canonical manifest SHA-256
`701bb78e4cfd2f0f1ba340afd8149c7eb62bb67c53970814fa019e3de6f42408`.
Its SQL, resources, exports and migration identities are unchanged. The complete
released upstream 1.1.3 tree is retained byte for byte under
`database/historical/module-1.1.3`; its original schema ceiling is 205 and its
canonical manifest digest is
`3bbcfcdee737d0875cc5f8f7986e39d6b1e39b1c7ce858e5a276f199749decf6`.
The actual universal-policy 1.0.0 schema-211 artifact digest is
`490032710ff6c013b334ad6e38f89dc76b2529390a070934c844fae09f1dcc14`.
Its independently pinned descriptor-resource canonical fingerprint is
`a0d0339c8df28e8e3e9e86dc986a6a915b6bf22e941ab769c504d5b9ad04d8b8`.

Upstream Docker, explicit bytecode suppression, init-reaper and diagnostic
changes are retained. These are code/build and package configuration changes;
business prompts and classifier criteria remain unchanged, with no live policy
activation. The earlier unpublished 0.1.18 universal-policy candidate is preserved
in Git commit `248bf3d0fbcec891db8b0148eb1829c608a56361` and the task recovery
evidence; it does not replace the released 0.1.18 wheel bytes documented below.

## Template 0.1.18 safe diagnostics and bytecode-free workers

This release selects the reviewed direct-tool diagnostic fix and typed AgentDB
internal-error client. Runtime advances only its exact client pin; SDK 0.5.14
and Runtime behavior remain unchanged. These are code/build configuration,
dependency metadata, tests and documentation changes. Business prompts, database
SQL/export contracts and every historical wheel/module archive remain unchanged.
Module 1.1.3 certifies the same SQL through physical AgentDB head 205, whose
forward migration registers the new API contract digest. Exact module 1.1.2 is
retained with its original upper bound and canonical commitment.

| Selected wheel | Reviewed source revision | SHA-256 |
| --- | --- | --- |
| `cogit_tool_core-0.1.2-py3-none-any.whl` | `2ad9f88e4a11459c58bf6aa99e94a1c62c7318d6` | `ba304a00447dd44076276f3304124e1e6395949cb0f472f8c3b168ff2ed7dacb` |
| `agentdb_client-0.2.12-py3-none-any.whl` | `5a1e91e4233b9ae70b264861f888a8c114a441e9` | `fd88dcf4f09c251296814dcd0676a231268b0398e2e6c8b97b3c36ae14028765` |
| `cogit_runtime-0.3.26-py3-none-any.whl` | `046dbdf60edff0e472eb58929f98d3519a89e930` | `71fafde78cf9b5b22d99c334c5883ef944411f70a0e64d00bd32e0c799ed4775` |

The client candidate records generation base `82f4993` and its exact OpenAPI
digest; the reviewed source above binds the resulting generated package. The
producer versions remain hatchling 1.32.3 and setuptools 84.2.1. No unrelated
public dependency version advances in this template's lock.

Isolated Python ignores `PYTHONDONTWRITEBYTECODE`. Build and production commands
therefore pass explicit `-B`; the builder removes generated `.pyc` files and
requires no recreated caches after installed verification. This avoids repeated
bytecode reconstruction during integrity checks without disabling any source,
wheel, inventory or present-cache verification. The measured improvement is
component CPU cost, not a general task throughput or memory claim.
Compose's server/worker services also use Docker's init reaper for orphaned tool
descendants; no custom supervisor or Runtime concurrency change is introduced.

## Template 0.1.17 manifest-selected validation

This patch makes template setup, manifest parity and generated action-contract
validation/export use the class selected by `cogit.yaml` metadata.entrypoint,
including the shipped database profile. Validation continues to reject stale
contracts; the existing export command regenerates them from the selected class.
Only template code, tests, release metadata and documentation change. Prompts,
database module 1.1.2, historical bundles and every framework/provider wheel
remain unchanged from Template 0.1.16 below.

## Template 0.1.16 timestamp and bootstrap compatibility

This patch fixes bootstrap's retained-bundle digest substitutions and selects
immutable database module 1.1.2 for physical AgentDB heads 179 through 204.
AgentDB's additive migration 204 formats timeline timestamps before computing
their projection digest. The new module preserves the prior SQL and export
contracts; only its version, upgrade base and certified upper bound change.
The exact previous 1.1.1 bundle is retained alongside 1.0.0 and 1.1.0.

Module 1.1.2 canonical manifest SHA-256:
`a6790747cbc73f36b9c2d7c9e5003412ac9f3bc7b20443fc53cb944fb58da499`.
Retained 1.1.1 canonical manifest SHA-256:
`3d58744d7e47380b349d34cf8821a4dc3ae77d5486d8e6a91d2b313c437dae50`.

These are bootstrap code, package configuration, assets and tests; business
prompts and domain behavior are unchanged. All selected framework/provider
wheel bytes and build-producer pins remain those of Template 0.1.15 below.
Release acceptance includes a freshly bootstrapped installed agent and typed
AgentDB event/result reads; source commits and execution receipts are recorded
in the timestamp/bootstrap fix handoff.

## Template 0.1.15 boundary fixes

This candidate selects the reviewed SDK terminal-diagnostic and Runtime native
loop-default repairs. These are framework code/configuration changes; template
business code and prompts are unchanged. Client 0.2.11, capability wheels, build
producer pins and immutable database module 1.1.1 remain selected unchanged.
Older wheel bytes and their historical receipts remain preserved.

| Selected wheel | Reviewed source revision | SHA-256 |
| --- | --- | --- |
| `cogit_agent_sdk-0.5.14-py3-none-any.whl` | `ef5185ad79befd8739b1b7ec69c93460a847d220` | `8b7f0d4b35cee5930783a5ce1a1f30b91d94f7e8eb9b19377151cc86f8516047` |
| `cogit_runtime-0.3.25-py3-none-any.whl` | `4863282d433464ba31ae840f29906d95a726058e` | `7f2662c761d4b047b51bdb81ed74c18c601ca8f4de028cac7f3a3a9009698104` |

`cohort.json`, `pyproject.toml` and the frozen lock bind these actual archives.
Their RECORDs and packaged sources were checked against the reviewed inputs.
This records selected vendored artifacts, not a package-index publication,
complete environment hash or production deployment. Installed/cohort/image
acceptance remains part of the release gates.

## Template 0.1.14 agent-lab upstream cohort

This candidate selects the reusable input-validation, native manifest and
AgentDB lifecycle/error fixes. The exact source commits and archive hashes below
replace the selected dependency pins; older wheel files remain historical.
Source commits are reviewed and committed; upstream PR merge status is recorded
separately. No package-index publication or production deployment is claimed.

| Selected wheel | Reviewed source revision | SHA-256 |
| --- | --- | --- |
| `agentdb_client-0.2.11-py3-none-any.whl` | `f5bfd452fceb1d3b7467c5a99de0a5515eb291ce`, provenance tip `eac9025224a07c373fe3f1fdc4f104a92c873e2e` | `e1195f11dd222706b965c29be9053ab96f0703c7680c14e59fe8ca9033239868` |
| `cogit_agent_sdk-0.5.13-py3-none-any.whl` | `02803004ef85c9958d3322743f6cc7f76f3dfeec` | `78df815be282707eeed7667072d17826d8e2f5ecc9cc84212dc22ebb52c92583` |
| `cogit_runtime-0.3.24-py3-none-any.whl` | `0941f38279e228a115f9588a2708c6fd2d75c362` | `059f139c40a9ef3d708f60fbbbde989ae3bd5cfc8c81d589fc28cba948e77373` |

The client includes the reviewed generator correction for schema-valued
`additionalProperties`. Earlier unpublished 0.2.11 and 0.3.24 candidates were used
for intermediate probes; their receipts remain local history, not the selected
cohort. `cohort.json`, project metadata and `uv.lock` select only the final hashes.

SDK PR32 merged as `37eb173cd65dd9a3d34a95831b05aed0d3d9db48` and AgentDB
PR310 as `fc1c8aaa27b0499106afd84eacb6ed08adebc4e1`. Runtime PR45 merged as
`98b24fc27c7991fbcf96d5e5c2f9a88bfeefef56`; integration head
`2f9dc86d7db764bbc0b6970b85b7000a0051c507` passed its installed-wheel suite
and both hosted packaged recovery/replay gates. These provenance notes do not
change source pins or archive hashes. The framework dependencies are on main.

The mandatory template executable closure also includes the unchanged
`cogit-tool-core` 0.1.1 wheel plus the built agent wheel. Optional provider pins in
the receipt are selected only when the authored profile requires them. See the
[upstream repair report](../../docs/reports/agent-lab-upstream.md) for validation
scope and the native YAML launch path.

## Template 0.1.12 accepted main cohort

This cohort selects locally built AgentDB client 0.2.10, SDK 0.5.11,
and Runtime 0.3.22 wheels. The AgentDB client source commit was included in
[AgentDB PR 304](https://github.com/osnova-gmbh/agent-db/pull/304), merged as
`661cb6b4850df2a0e9e669adfe41c0394c1f0afd`. The Runtime source commit
was included in [Runtime PR 43](https://github.com/osnova-gmbh/cogit-runtime/pull/43),
merged as `c2952c7c8e90ebb767996b631fbded3669d9cfc6`. The SDK source
revision is on main at `c743a016072584d27d353713bebaeb072fd44ec9`.
The source branches remain preserved. No image or production deployment is
claimed here.

| Selected wheel | Source revision at wheel build | SHA-256 |
| --- | --- | --- |
| `agentdb_client-0.2.10-py3-none-any.whl` | `35d3df0b039cbf9bda695c05cfd7a6135a8981d7` | `3ad5e7a242b7d90d32a99724ed527108ef8a05a445e4075bfe1f50203ee45b20` |
| `cogit_agent_sdk-0.5.11-py3-none-any.whl` | `c743a016072584d27d353713bebaeb072fd44ec9` | `0470069a75e804c1677a52893f55fa9d1fccc0b5a5e3fe4bb102ba3dc9a98777` |
| `cogit_runtime-0.3.22-py3-none-any.whl` | `2a88a4ec441180d9f27c67256055ce4af732bcfb` | `92b5db1352faf4ca8c7f2cc58a64380451fc0002640c1301e2ec23e9d1c51f4a` |

This cohort preserves all older wheel files and their historical receipts.
The selected wheels were installed from the frozen lock and tested with the
Template 0.1.12 source before acceptance.

## Template 0.1.11 selected local wheel and image

The 0.1.11 source and manifest set worker concurrency to one. The active
`pyproject.toml`, `uv.lock` and `cohort.json` select AgentDb client **0.2.9**,
SDK **0.5.9**, and Runtime **0.3.18**. The selected portable wheel bytes are:

| Selected wheel | Source revision at wheel build | SHA-256 |
| --- | --- | --- |
| `agentdb_client-0.2.9-py3-none-any.whl` | `798b84f4aeada221a5accc81924f00f8801f81ec`, merged in AgentDb PR 298 as `39124a746ce3f68fece201036539e630df5bad3e` | `b70a5b72d97ef13103bc0c9b144f2cd032995a56ac07cc44b231f2628400a425` |
| `cogit_agent_sdk-0.5.9-py3-none-any.whl` | `f9b1c394defddbf3538d9c69f54588a298a9a2c3`, merged in SDK PR 28 as `40a84e7e980651a822662e37755588e36e95032e` | `479b76d58700b2204f627a2d222b21153269faaf46785c6b8774aa8410067bcc` |
| `cogit_runtime-0.3.18-py3-none-any.whl` | `60f0e5ea409e08d515b636d53336d13b1a923d5c`, merged in Runtime PR 38 as `812ee9b1b15a77a7cc73a8c72c50f7e90c3ca23f` | `75e3cf2b0bfa59fe0b4f18401431b5dfc55224004f13329386f77bb1a00e51f7` |

The selected immutable Template image is
`sha256:361279af7feeadd5b3ec99295a1c77702daf2fa5813fd51599ef79ffacec83a7`.
Its exact image-extracted, noneditably installed Template wheel is
`reference_cogit_agent-0.1.11-py3-none-any.whl`, SHA-256
`639ced22bcd81ec28ceda1ba785b06d3fed28a0d9e0e266ffc4147f19e2a3191`.
The unsigned image cohort's `executable.json`, `cogit.yaml` and `prepared.json`
have SHA-256 `ffed27dd36bdd7fde71be26cbed734b651aad81b53f8e883501ddbd830a911cf`,
`8b50e5ba7ed5721f16f2071799258cd897442b3b10c0f47abe4117a176ae94a1`
and `80e5f58e70d232c8cd64611bfa90215ac5ced99964b47d515b70f7f6baeadc52`.
All 525 installed selected-package files matched these four wheel archives;
the image has no unexpected files in their installed package trees. The same
wheel passed A02 image 4/4, A04 host 1/1, A10 host 2/2, A10 image 2/2 and D08
schema-194 1/1 local acceptance. Exact run IDs, outputs and fixture setup are
in [the current handoff](../../docs/reports/framework-release-hardening/HANDOFF.md).
No package-index publication or production deployment is claimed.

The superseded Runtime 0.3.17 wheel remains preserved with SHA-256
`d1f28379d3726930a5c9ae6e8c5454ccd614cf1c4281ee0b4c2ee2d1704fdd06`.
Template 0.1.9 was a diagnostic wheel only; its
dependency metadata selected older framework wheels and is excluded from this
cohort. An ignored local `reference_cogit_agent-0.1.10-py3-none-any.whl`
already exists with SHA-256
`f9fd9b8fb7d8c09afcfc90e17857db21aa646b8f11a682a58bdd0176bb8f344f`.
Its build provenance is unclear; preserve those bytes but exclude the wheel
from release selection. Template 0.1.11 uses a fresh artifact identity.

The selected 0.3.18 framework cohort passed `uv lock --check --offline`, frozen
noneditable installation and `uv pip check` for 55 installed packages on Python
3.11.16. The final source gate passed 115 tests with four platform skips,
Ruff, formatting, Pyright, import boundaries, dependency analysis, manifest
validation and the 4/4 live smoke evaluation after the image/TLS fixture
adjustments.

## Selected Template 0.1.8 cohort

Template 0.1.8 selects AgentDb client 0.2.7, SDK 0.5.9 and Runtime 0.3.16
for AgentDb schema 191. The exact portable hashes are enforced by
`cohort.json`, the frozen lock and installed-package verification. These are
vendored builds; no package-index publication is claimed.

| Selected wheel | Source revision | SHA-256 |
| --- | --- | --- |
| `agentdb_client-0.2.7-py3-none-any.whl` | `34e868a877176ee43f2d46e3b6722af4d49c788a`, `clients/python-canonical` | `d263fe34554700bfc5d23b94884ea6bc111535ddc9bb2cf23bfaa556fe960708` |
| `cogit_agent_sdk-0.5.9-py3-none-any.whl` | `f9b1c394defddbf3538d9c69f54588a298a9a2c3`, merged in SDK PR 28 | `479b76d58700b2204f627a2d222b21153269faaf46785c6b8774aa8410067bcc` |
| `cogit_runtime-0.3.16-py3-none-any.whl` | `8f7093404a7ea655d5af243f8043ba1937332331`, Runtime PR 37 | `2d55f053b5144487d924b56d690ffca21bfe71808948282741d5dfc911a1415f` |

The final local Template wheel `reference_cogit_agent-0.1.8-py3-none-any.whl`
has SHA-256 `48e68d8edf4f727bd7374f64b869ccb157ad7e803cc49060c8d9635f0252a0ac`.
Template 0.1.7 was used only for diagnostic builds while the producer cohort
was being repaired; those candidates remain ignored local evidence and are
not selected release artifacts. Rejected Runtime candidates 0.3.13–0.3.15
are likewise excluded from the vendored selection. Existing historical
committed wheels below retain their original bytes.

The active module 1.1.0 digest remains
`618f39aa1587ad5b5ac6132386c4bef829fadb5b90051855d16716f1c0b7f548`.
Its historical module, SQL migrations and resource contracts are unchanged.
See [the current handoff](../../docs/reports/framework-release-hardening/HANDOFF.md)
for the final installed-worker, container and schema-191 receipts.

## Historical cohorts through Template 0.1.6

The remainder records earlier receipts and their limitations at the time.
Its selected-wheel labels refer to the historical cohort, not Template 0.1.8.

The 0.3.8/0.5.3/0.2.5 framework cohort selected by Template 0.1.5 is retained
by Template 0.1.6. It has no G01 release approval or AgentDb schema-180 worker
compatibility claim.
These are vendored builds; no public package-index publication is claimed.

| Wheel | Source revision | SHA-256 |
| --- | --- | --- |
| `agentdb_client-0.2.4-py3-none-any.whl` | `6dccd513142eba59f6d95b8e1d3acacbbf426a56`, `clients/python-canonical` | `5b54b31949f3af4105035293a6e0304fc8023a21b2839fa62ef28ad444bf027c` |
| `cogit_agent_sdk-0.5.2-py3-none-any.whl` | `70ac3cc06be1881d39a69e27cd1b75862b4adf6b` | `f2f1883650ee598025a61aac140dde5ae76bf919da481faa70a9b9880a8ef834` |
| `cogit_runtime-0.3.6-py3-none-any.whl` | reviewed candidate `c849d6c0ce061d110a0f6ede7494defda9418d58` | `e50eb4a128f9557fb01bbb41cbfebb3c1250c8b1701cfd6191f3a0722554cc44` |
| **Selected** `agentdb_client-0.2.5-py3-none-any.whl` | `65a1948e0bbe613a527b7287dcc2e41e049fa091`, `clients/python-canonical` | `1fa62eabd215fa1555381769d49c1bf523ca91fabc2c1fe993150060f3078fb5` |
| **Selected** `cogit_agent_sdk-0.5.3-py3-none-any.whl` | `7ba4e3baeae574023424b0498cd537c8de8f206c` | `242d52f3285d3e66ba90aff5eb00fbf71d2cd2de3951be2b45e4e65189f4e829` |
| **Selected** `cogit_runtime-0.3.8-py3-none-any.whl` | A02.RUNTIME [PR 29](https://github.com/osnova-gmbh/cogit-runtime/pull/29), merged `84161cea77cfc09b4f4bf1d7fc09b5bbfbb67e14` | `931bbb9b18ee3cab47a272f1e3be3e614531d8907bc0dfab468797d4ef00ae67` |

The historical 0.2.4 client bytes came unchanged from Library's reviewed
wheelhouse. Runtime 0.3.6 requires exactly that client. The selected Runtime
0.3.8 wheel is the exact A02.RUNTIME producer handoff and requires SDK 0.5.3 and
client 0.2.5. The selected SDK and client wheels were rebuilt from the exact
reviewed source commits shown above. Their archive hashes differ from the
earlier Runtime validation copies (`2f40a5aa...` and `7a3fc285...`), so those
older wheel identities are not claimed here. Independent archive comparison
found the rebuilt client's 246 member payloads identical to an earlier producer
copy; the SDK rebuild contains the reviewed coordination source. `cohort.json`
records the portable selected hashes used by the local verification command;
it contains no machine paths or credentials.

Template's changed dependency metadata and typed consumer used candidate 0.1.2.
The A01 hosted/default-image closure and pinned build toolchain used Template
0.1.3 and database module 1.0.0. Prior 0.1.1 and candidate 0.1.2 wheel bytes
remain preserved. Core's existing optional-database evidence already binds a
renamed Template 0.1.1 wheel
(`57ce6117a8d23ca748e1d2d12f94e086ad64dcfea9dd7e4a3fcfed866ec0763d`).
No changed candidate replaces those historical bytes.

Template 0.1.4 now contains active database module 1.1.0 with canonical manifest
digest `618f39aa1587ad5b5ac6132386c4bef829fadb5b90051855d16716f1c0b7f548`.
It retains module 1.0.0 under `historical/module-1.0.0` with its original
manifest digest
`15714d0a37fbea9938514f3ab61f445b6a4cfe1ab4db1ad3f8b5fbd4002c4bd9`
and unchanged original migration bytes. The locally built Template 0.1.4 evidence
wheel has SHA-256
`2bb42197ba7a15cb272ef54b96618add36946a1bbe43824d1017471a2c2e416c`.
At the time of this historical 0.1.4 evidence, its declared Runtime/client
cohort failed schema-180 worker preflight; image/request and
replacement-worker acceptance had not yet passed. Later Template PR 14 proved
the standalone `plain_request` image and worker recreation with the selected
0.1.5 cohort;
PR 15 separately proved a replacement-worker database receipt on schema 179
using the 0.1.4 wheel with newer framework wheels installed explicitly.
The same tracked recovery fixture also passed post-merge with the selected
installed 0.1.5 wheel and `uv pip check`-clean framework cohort, removing that
historical `--no-deps` caveat for schema-179 behavior.
Neither proof establishes a supported schema-180 worker cohort, and Runtime's
standalone `case_request` pipeline still fails on child-run persistence.

Template 0.1.5 selects the new standalone cohort without replacing the 0.1.4
package evidence or its database module bytes. The generated 0.2.5 client
accepts AgentDb schema 179, while the current D03 fixture is schema 180; a
schema-180 `DatabaseAgent` worker cannot pass version preflight with
this cohort. Refresh this receipt, metadata and lock together for any future
compatible cohort. Never replace released wheel bytes under an existing
version, and retain historical files when selecting newer wheels.

Template 0.1.6 adds the A10 canonical-text input adapter and public root-result
schema to the existing `DatabaseAgent`. The local evidence wheel
`reference_cogit_agent-0.1.6-py3-none-any.whl` has SHA-256
`6af8801491c1528d19c55d77ed661043f7bad700a3e0efb1d11415d099a9432c`.
It uses the same selected Runtime 0.3.8, SDK 0.5.3 and AgentDb client 0.2.5
wheel hashes above. Its active database module 1.1.0 manifest digest remains
`618f39aa1587ad5b5ac6132386c4bef829fadb5b90051855d16716f1c0b7f548`;
the historical module remains unchanged. The 0.1.6 wheel was rebuilt after
rebasing onto merged A02/A04 main and retained the same archive SHA-256.
The [A10 proof](../../docs/reports/framework-release-hardening/A10-ADAPTER.md)
records the installed-wheel AgentDb schema-179 admission, exact public artifact
bytes and the separate Runtime settlement wrapper. This receipt does not claim
schema-180 compatibility, gateway root selection or release approval.
