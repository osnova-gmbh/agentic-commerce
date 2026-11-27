# Independent bounded-journal review — 2026-10-24

## Scope and current verdict

This follow-up reviews code changes in Runtime and AgentDB. It does not change
agent prompts or supplier workflows. The original live capability proof is
reported separately in `dynamic-tools-live-independent.md`.

The observed 64 KiB checkpoint exhaustion was caused by completed model/tool
metadata, despite the result payloads already being stored as artifacts. The
bounded v2 extension addresses that specific limitation without removing replay
evidence or increasing the canonical checkpoint limit.

The reviewed implementation has no unresolved source security finding in this
scope. The installed Runtime replacement-worker gate has now passed and its raw
artifact commitments were independently verified. Hosted CI and merge orchestration
remain the parent agent's responsibility.

## Contract reviewed

- `runtime/src/cogit_runtime/agentdb/continuation_index.py` declares
  `MAX_INDEX_BYTES = 1024 * 1024` and `MAX_INDEX_ARTIFACTS = 400`. It validates
  a typed `cogit.runtime.journal.v1` artifact containing the complete previous
  typed state. The inline `cogit.runtime.continuation.v2` root contains only
  identities, revision, its index commitment and exact compact artifact grants.
- Its reference enumeration states: "Enumerate only the existing six evidence
  positions, never arbitrary JSON." The allowlist is sorted, unique and exact;
  hydration rejects missing or extra grants and differing work, execution,
  identity or revision. Duplicate JSON keys, non-JSON constants and excessive
  structure are rejected. Artifact reads are bounded before decoding and checked
  against exact byte length and SHA-256.
- `continuation.py` publishes the index before the checkpoint. Unconfirmed
  publication permanently fences that journal instance. Small checkpoints retain
  their existing v1 encoding. v2 is enabled only by validated, authenticated
  server readiness, not caller configuration.
- `current_journal_artifacts.py` uses the existing fenced binary upload/finalize
  APIs. It does not send a large index through the older 64 KiB inline artifact
  endpoint.
- `agentdb/migrations/core/000202__runtime_journal_artifact_reads.sql` states:
  "Validate the entire list before yielding even the index". It recognizes only
  the exact index commitment and `[UUID, SHA256, byteLength]` tuples, with fixed
  JSON MIME. It preserves migration 193's pinned checkpoint, restricted artifact,
  exact commitment, execution-output provenance and ancestor-work checks. There
  is no recursive artifact grant or broad same-run access.
- The database migration ledger advances to 202 while the existing published
  `schemaSurface` compatibility identifier remains 194. Readiness advertises the
  additive continuation capability. The policy module requires schema 202 for the
  new cohort. Historical invoice packages keep their immutable maxSchema 200.

## Independent executions

1. **21 independent codec/journal adversarial checks passed.** A state with 60
   completed model slots and 100 completed tool slots produced a 91,923-byte index
   and 30,591-byte checkpoint with 260 exact artifact grants. The probes rejected
   changed hashes/lengths, changed identities/revisions, missing/extra grants,
   duplicate/deep/non-JSON input and malformed tuples. A canonical identity
   mismatch caused no index fetch. An uncertain index upload poisoned subsequent
   journal access and published no checkpoint.
2. **Two independent cold PostgreSQL tests passed**, 20.09s total, 13.30s test time.
   One exercised 11 malformed grant/index variants and verified that the entire
   list returned no grants. The other expired a real attempt, claimed a
   replacement and checked actual artifact HTTP reads: listed index/output
   allowed; unlisted same-execution output, wrong hash, wrong size and output
   outside the lineage denied; old or mismatched attempt tokens fenced.
3. **88 focused Runtime regression tests passed**, 8.40s, covering the new index
   and binary port, existing journal/claim compatibility, and cohort readiness.
   Pytest reported only a local cache-write permission warning.

4. **One retained-session upgrade probe passed**, 9.95s total. An isolated
   database advanced from schema 201 to 202 through the real migration runner.
   A retained named prepared query and the already-open API pool both observed
   the new capability; the v1 grant helper still worked. Only the unique reviewer
   database was dropped; the shared canonical proof database was untouched.
5. **Installed R15 replacement-worker proof independently reviewed.** The owner
   reran it with raw evidence preservation: 149.32s, canonical run
   `e6553753-5228-4b81-8ed5-bd7290320fd2`. Evidence is under
   `runtime/.quality/reports/r15/8ba03ace-5ef1-4b21-a786-f6967ad39f19/`.
   After 50 model calls and 50 keyed writes, the first process exited immediately
   after acknowledged checkpoint publication. Following API restart, real lease
   expiry/projection and a new claim, a distinct process needed only six model
   calls and five writes. Actual database assertions confirm 55 rows, 56 model
   intents, zero outstanding spend and successful settlement.

The reviewer recomputed both R15 raw index hashes and lengths, checked the exact
checkpoint commitments, and hydrated them through the strict typed codec to
verify identity/revision and exact grant closure:

| Stage | Index bytes | Inline bytes | SHA-256 |
| --- | ---: | ---: | --- |
| acknowledged before exit | 75,925 | 18,841 | `1f5cb1190a6fab2adfd6a98aae9d1f6fddacb9deb3e7fccabbab73f1233f3097` |
| replacement completed | 84,231 | 20,791 | `2f0b92f6f893dd14c4c54fe09a211cbbe89f370fb903f16c2888d44cece3fab4` |

The final installed cohort `r09373efe72` was independently checked: all 140
Runtime, 80 SDK, 268 client and one fixture-agent Python files equal their wheel
members. Runtime source also equals its installed wheel. Runtime wheel SHA-256:
`a6df5e900a90debe4c949092ca2bc37f4c80d1eba0d34453b5fb6cb6caa589ad`;
production source commit `c95d0be`. The fixture uses a deterministic provider to
test durability, not a live model or intelligence claim. Its earlier attempt lacked
the normal worker heartbeat and correctly expired; adding the test-consumer
heartbeat fixed the harness without bypassing fencing or changing production.

Owner-reported broader gates, separately attributed: Runtime 1,320 passed and one
skip; AgentDB v2 PostgreSQL 10/10, unchanged v1 5/5, non-PostgreSQL 620/620 and
fixture cap boundaries 16/16. The reviewed AgentDB migration commit is `ac2891b`;
the subsequent narrow fast-uri development dependency fix is `aaa45fb`. The owner
reports its full dependency audit now has zero advisory findings. Historical
invoice artifacts retain their schema-200 ceiling; this is not fresh invoice
bundle admission support on schema 202.

The initial independent PostgreSQL run failed before artifact reads because the
first migration draft incorrectly changed `schemaSurface` to 202. The owner
corrected that compatibility identifier. The fixture was stopped and a fresh
fixture passed; its migration ledger was not modified in place.

Review probes are isolated under ignored `.tmp/review-journal` and the local
review workspace. They are not added to the production test inventory. No
production source was edited by this reviewer during this follow-up.

## Release assessment and limits

The installed replay and independent negative-boundary checks close the bounded
v2 source/security acceptance gate. The hosted workflow now adds a separately
pinned schema-202 server checkout while preserving the old generated-client pin;
its source archive verification is unchanged. CI execution and merge authorization
remain separate from this local review.

The extension remains bounded: 64 KiB inline checkpoints, 1 MiB index, 400 explicit
artifact grants, and the existing 128 model/tool-slot limits. Pipeline-heavy
states may reach a bound sooner. It does not establish unlimited-length coding
sessions, exactly-once external effects, or permission to replay an interrupted
unkeyed operation.
