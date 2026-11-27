# Final template security validation — 2026-10-24

Verdict: no unresolved confirmed must-fix in this bounded final template code/configuration and Python supply-chain review. This is not a proof of model intelligence, a general OS sandbox, or an OS-package/Chromium CVE scan. Root owns the live portal, authenticated restart, policy and durable-continuation acceptance.

## Exact artifacts and automated evidence

- Template public lock export: 60 dependency entries, pip-audit reports zero known vulnerabilities. All 10 selected vendored framework/provider wheels match pyproject paths and the cohort receipt.
- Image F: manifest-list digest `0f807c1a3f150c60a0097a626d1dde286896bf8a5ea022acea0db5bb235abf52`; root reports config ID `e79c0de4d3559d5c26d1611d733a4104877b655cd0339b2859a82a77464892a9`.
- Separate image container used `--rm --network none --read-only --entrypoint /app/.venv/bin/python` for metadata only, with no mounts or supplied environment; the active worker was untouched.
- Image inventory: 52 distributions, comprising 41 public packages and 11 private packages. Actual versions include filelock 4.2.1, SDK 0.5.12 and Runtime 0.3.23. pip-audit of all 41 exact public installed versions reports zero known vulnerabilities. Private packages are verified by artifact commitments, source review and tests, not by assuming absence from a public vulnerability database means safety.
- Gitleaks redacted source-mirror scan: 145 tracked/nonignored text files, approximately 968 KB, no secrets detected. The mirror deliberately excludes ignored profiles, private runtime fixtures and binary wheels; no real credentials were copied.
- Installed isolated-import template setup/configuration/cohort boundary regressions: 61 passed in 8.00s, one upstream Starlette/AnyIO deprecation warning. Includes invalid inputs without manifest changes, literal/provider error redaction, policy pin/authority conflicts, archive bounds and exact provider cohort selection.
- Bandit scanned 2,259 source lines and reported four existing findings, classified below. It is not claimed clean.

## Existing scanner findings and practical scope

1. B104, scanner Medium, `scripts/localhost_bridge.py:14`: `BRIDGE_HOST = "0.0.0.0"`. Compose exposes this only with `127.0.0.1:${COGIT_LOCAL_API_PORT:-8080}:8081` (`compose.yaml:56`), forwarding to Runtime loopback. It is an intentional local development bridge, not part of the production workspace image entrypoint. Same Docker-network peers can reach the development listener; do not use this local development composition as a hostile multi-tenant boundary. Future hardening: isolate the development network/bridge if untrusted peer containers are permitted. No current external-host exposure or new feature exploit was demonstrated.
2. B310, scanner Medium, `scripts/wait_for_http.py:20`: operator CLI URL passes to urllib. Its only repository callers (`scripts/check.ps1:46`, `scripts/check.sh:56`) supply the fixed localhost health URL; it does not return the response body or expose a network service. Future defense-in-depth: restrict schemes to HTTP(S) if accepting untrusted caller input. This is an operator helper, not a model tool/API endpoint; no current remote exploit demonstrated.
3. B101, scanner Low, `src/buyer_agent/database_example.py:73`: assertion narrows optional typed values after `require_one_input_shape` validates them (`:56–63`). The validation, not the assertion, rejects missing request fields. Explicit raises would be a readability/defense-in-depth alternative; no authorization bypass demonstrated with optimized Python.
4. B101, scanner Low, `src/buyer_agent/operations.py:149`: internal configured-operation assertion. Without assertions an absent operation still raises on the immediately following access; this is not a permission decision. Explicit initialization checking may improve diagnostics.

## Process state, authority and code/prompt boundary

- Code: capabilities are instance-owned on `Agent`; setup assigns `agent.descriptor` to the new instance. No new process-wide environment, working-directory, registry or class-descriptor mutation was found. Host environment names are bounded/validated and only explicit referenced values enter HostContext. CLI helper sys.path additions point to their own resolved source/scripts directories; they are build/operator helpers, not per-invocation arbitrary path mutations.
- Code: bounded YAML uses safe_load; manifests validate before atomic replacement. `src/buyer_agent_setup/policy.py` states `no policy content lives here`. Runtime/AgentDB enforce policy and admitted artifacts separately from provider selection.
- Code/configuration: entry points are trusted installed Python code and can have import side effects; they are not a sandbox. `cogit_tool_core/providers.py` explicitly says `Entry points are trusted installed code; discovery never installs dependencies.` Actual selected distribution/target origin is separately constrained by the canonical Runtime cohort. Shell and generated scripts retain worker OS authority; separate credentials/containers remain required between hostile trust domains.
- Prompt: `src/buyer_agent/prompts/workspace.md` says `Write automation and task-specific acceptance checks` and `Do not try to change your own grants.` These statements guide model behavior; they implement no security boundary and no supplier workflow.

## Commands

- `uv export --locked --all-extras --no-emit-project --no-emit-local --format requirements-txt --output-file <evidence>/template-public-requirements.txt`
- `python -m pip_audit --requirement <hashed-lock-export> --disable-pip --format json ...`
- `python scripts/verify_framework_wheels.py`
- `bandit -r src scripts bootstrap.py -f json ...`
- `gitleaks dir <source-only-mirror> --redact --no-banner --report-format json ...`
- `python -m pip_audit --requirement <linux-public-requirements> --disable-pip --no-deps --format json ...`
- `.venv/Scripts/python.exe -I -m pytest -p no:cacheprovider -o pythonpath=tests --import-mode=importlib tests/test_capability_configuration.py tests/test_capability_setup.py tests/test_cohort_providers.py tests/test_worker_cohort.py -q`

Initial image audit invocation omitted --no-deps for the unhashed installed-version inventory and the tool rejected the invocation before audit; rerun included --no-deps and checked the complete installed public set. Neither invocation mutated the image. GitHub status reads and Docker metadata operations needed ordinary sandbox escalation; no approval was rejected.

## Independent post-v2 security addendum

This addendum reviews code/configuration changes; no prompt-based security rule
was added. The independent reviewer found no remaining confirmed must-fix in the
bounded Runtime continuation, AgentDB 202 grant/readiness or template pin changes.
Detailed tests and exact evidence are in `dynamic-tools-journal-independent.md`.

- Runtime source `c95d0be`, wheel
  `a6df5e900a90debe4c949092ca2bc37f4c80d1eba0d34453b5fb6cb6caa589ad`:
  140 installed Python files independently equal the wheel and current source.
  Strict 64 KiB checkpoint/1 MiB index/400 exact-grant bounds remain. The code
  says `Read one authorized exact artifact, then verify all duplicated commitments`;
  identity/revision and full reference-closure checks reject tampering.
- AgentDB 202 preserves pinned-checkpoint ancestry/provenance and fixed digest,
  length and MIME checks. The SQL says `Validate the entire list before yielding
  even the index`. Independent malformed-grant/lineage probes passed 2/2 and a
  retained prepared connection/API-pool upgrade probe passed 1/1. No wildcard
  artifact access, recursive authorization or shadow policy store was introduced.
- The final installed R15 test performs a hard exit after acknowledged publication,
  API restart and authoritative replacement claim. Independent verification of the
  raw index/checkpoint files closes the artifact/replay gate: 50+6 provider calls,
  50+5 keyed writes, 55 actual rows, 56 model intents and zero outstanding spend.
  This is deterministic durability evidence, separate from live model capability.
- The template policy artifact pin is
  `141e0989cbf89d08052db9c578cf4e083d41f63754e7ec91000069bc8b72ab80`,
  requiring schema 202. The template's vendored Runtime is the exact reviewed
  wheel. Documentation accurately keeps the unchanged bounds and older-server v1
  behavior. Historical invoice bundles retain their schema-200 ceiling.
- The binary PDF fixture now includes `b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"`;
  four independently executed fixture tests passed. This strengthens acceptance
  evidence and introduces no production download behavior. Final G live discovery
  and restart evidence is independently described in the live review report.
- Separately attributed owner audit: AgentDB `aaa45fb` changes only the fast-uri
  development dependency override/lock from 3.1.8 to 3.1.9; the reviewer verified
  no other resolution changed. The owner reports 37 focused tests and a full
  dependency audit with zero advisory findings. The unchanged public Python
  dependency audit above was not repeated or silently relabeled as a new run.

Source/security and local installed acceptance are approved within these stated
limits. Hosted CI and final merge decisions remain independent release gates.
Neither shell authority nor trusted entry-point import is presented as a sandbox;
central policy decisions are not replaced by model instructions.


## Final image G advisory audit

This records code/artifact validation, not a prompt change.

- Image: `cogit-dynamic-template-proof:20261023-g`.
- Manifest list: `a0dedeb299da12d2fdbb28539e7408aa3eec591488c1b892590d078d75fde1d8` (also independently returned by Docker image inspect).
- Linux config identity supplied by the root's exact artifact check: `749118921a7bba3a4a7df6e72b202ffa7773c2386bd0b59ccb0991f367b6ec10`.
- Inventory obtained from a separate `docker run --rm --network none --read-only` container; no running worker was modified.
- 52 installed distributions: 41 public and 11 private project packages. Names and versions exactly match prior image F (no added or removed dependencies).
- Fresh `pip-audit 2.10.1` lookup of all 41 installed public Python dependencies: **zero known vulnerabilities**. Actual JSON and requirements are adjacent to this report.
- Runtime candidate changed to the reviewed bounded-index implementation, wheel SHA-256 `a6df5e900a90debe4c949092ca2bc37f4c80d1eba0d34453b5fb6cb6caa589ad`; SDK wheel remains `e795edffb06d44b00e26a2632746b8dc51ea200a4a71660c1e16a4cd23a13b51`.
- Independent source review and actual installed replacement/replay proof cover the new Runtime protocol: exact compact grants, immutable identities, verified bounded binary index, live worker authority and preserved model/tool accounting. The schema-202 server is pinned separately from the frozen older generated client.
- Prior source audit classifications remain applicable: the development bridge binds inside its container while host publication is loopback; the HTTP wait helper takes an operator-supplied URL; two existing internal assertions are not authority checks. No new must-fix finding arose in the Runtime/CI additions.

Scope: installed Python advisory scan plus reviewed Runtime source/protocol and prior template source audit. This is not an operating-system/Chromium CVE inventory or a guarantee for arbitrary installed third-party providers. Model-driven portal success is separate root-owned evidence.
