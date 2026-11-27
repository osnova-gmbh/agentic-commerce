# A10 worker result handoff

`canonical-input.txt` is the exact UTF-8 `text/plain` query input. The worker
maps it to a tenant-scoped request ID and commits `root-result.v1.json` through
`RunHandle.finalize_artifact`. The public JSON is only the five fields in
`root-result.v1.schema.json`; it excludes the original text and internal IDs.

`json-looking-input.txt` exercises the same `text/plain` admission with content
that is also valid JSON. The installed-worker proof requires the exact original
text to be stored and hashed; it must not be decoded as a typed request.

`worker-action-output.v1.json` is the action output from the deterministic
`persist` step with fixed test artifact IDs. Its `root_artifact_id` and
`root_sha256` identify the public JSON bytes; the concrete artifact ID varies
per run. Runtime 0.3.8 stores a separate `RunResult` artifact at settlement.
For the generated database pipeline, the root reference appears at
`RunResult.output.steps[id="persist"].output.root_artifact_id` and its digest
at the adjacent `root_sha256`. The settled `core.runs.result_artifact_id` points
to Runtime's `RunResult`, whose JSON also contains internal action output.

R05/W04 must use an explicit, authorized root selection contract: locate the
`persist` step's root reference, verify its run link and SHA-256 commitment,
read that artifact, validate the public schema, and expose those public bytes.
The current SDK/Runtime cohort has no `set_result_artifact` or equivalent
agent-facing root designation. Treating Runtime's settlement artifact as the
public root would expose the internal action output.
