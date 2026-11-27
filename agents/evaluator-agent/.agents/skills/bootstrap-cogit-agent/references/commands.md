# Development command guide

Use installed subcommand `--help` as the option authority.

| Outcome | Command |
| --- | --- |
| Read bundled development instructions | `cogit skills show bootstrap-cogit-agent` |
| Read this guide through the CLI | `cogit skills show bootstrap-cogit-agent --reference commands.md` |
| Prepare project and skills | `cogit init DIRECTORY [--template SOURCE]` |
| Scaffold only | `cogit agent create ID [--directory PATH] [--name NAME] [--template SOURCE]` |
| Read metadata | `cogit agent show --project PATH` |
| List supported project text | `cogit agent files list --project PATH` |
| Read text and its exact current hash | `cogit agent files show src/my_agent/agent.py --project PATH` |
| Create supported project text | `cogit agent files write src/my_agent/custom.py --content 'SOURCE_TEXT' --create --project PATH` |
| Update text after reading its current hash | `cogit agent files write src/my_agent/agent.py --content 'SOURCE_TEXT' --expected-sha256 CURRENT_SHA256 --project PATH` |
| Replace one exact literal in an existing file | `cogit agent files replace cogit.yaml --find 'OLD_LITERAL' --replacement 'NEW_LITERAL' --expected-sha256 CURRENT_SHA256 --project PATH` |
| Copy bounded text inside the project | `cogit agent files copy cogit.yaml tests/fixtures/reference/cogit.yaml --create --project PATH` |
| Check authored formatting, lint and types | `cogit check --project PATH --path src/my_agent/custom.py --path tests/custom_agent.py` |
| Apply permitted formatting/lint fixes, then check types | `cogit check --project PATH --path src/my_agent/custom.py --path tests/custom_agent.py --fix` |
| Sync authored bindings using the configured entrypoint | `cogit agent contract sync --project PATH` |
| Sync an isolated existing profile pair | `cogit agent contract sync --manifest tests/fixtures/reference/cogit.yaml --artifact tests/fixtures/reference/action-contract.v1.json --project PATH` |
| Edit metadata | `cogit agent edit --project PATH --name NAME --description TEXT --version VERSION` |
| Replace system prompt | `cogit agent edit --project PATH --system-prompt FILE` |
| Install frozen dependencies and updated project wheel | `cogit install --project PATH` |
| Validate manifest/action parity | `cogit agent validate --project PATH` |
| Report provenance and readiness | `cogit doctor --json --project PATH` |
| Verify the deployed cohort | `cogit doctor --json --verify --project PATH` |
| Run project tests | `cogit test --project PATH` |
| Run selected product tests | `cogit test --project PATH --path tests/custom_agent.py` |
| Plan an AgentDb module | `cogit db module plan --agentdb-root PATH --request JSONFILE` |
| Inspect an AgentDb module | `cogit db module inspect --agentdb-root PATH --request JSONFILE` |
| Run a Runtime HTTP suite | `cogit eval --project PATH --endpoint URL` |
| Serve Runtime health and inspection | `cogit run --project PATH` |
| Execute admitted AgentDb work | `cogit work --project PATH` |
| Register with the configured platform | `cogit register --project PATH --endpoint HTTPS_AGENT_URL` |

Prepare a project with `cogit init my-agent`, then use `cogit agent validate
--project my-agent` and `cogit test --project my-agent`. Reinstall after source or
prompt changes because the project runs from a noneditable wheel. For live
work, use the verified AgentDb installation and its worker configuration.

`agent edit --version VERSION` is a synchronized release edit: it updates the
static package version, matching manifest marker and frozen UV root together.
It refuses ambiguous or inconsistent release metadata. After a permission edit,
validate the manifest and action contract as well as the installed bindings.

Run/work are foreground processes. Retain a host-supported way to stop them.
They inherit AgentDb configuration and require a verified cohort receipt,
development mode off, and an unset `DATABASE_URL`. Confirm the selected target
before starting the worker or registering. Ordinary validation checks installed
contracts without opening storage. Use `--environment` on validation or test to
preflight the configured cohort.
The registration `--endpoint` is the agent's advertised URL. The platform API
target comes from its configured environment or the runtime's `--api-url` option;
do not substitute one URL for the other.

`SOURCE` is a local trusted template directory or trusted HTTPS repository.
Never echo secrets into commands, checkpoint files, fixtures, or reports.
The template/SDK/runtime define agent behavior. Do not invent deployment,
identity, or AgentDb REST APIs.

## CLI-only authoring sequence

`SOURCE_TEXT` means the actual source, SQL, prompt or test text supplied as one
literal argument, including real newlines when needed; it is not a file name or
an instruction to run an interpreter. `CURRENT_SHA256` must be the exact hash
from the preceding file show response. Never invent a hash or replace a stale
file without rereading. Supported files are bounded project text; dependencies,
secrets and arbitrary host paths are outside this authoring surface.

Use `files replace` for short edits in a large generated file instead of sending
its entire contents through an OS command line. The find/replacement pair is
limited to 16 KiB combined, find text must occur exactly once, and the existing
file remains subject to the 256 KiB file limit. Pass short literal strings or
literal here-string arguments for multiline fragments; do not use redirection
or shell/Python helpers. Reread the current content and SHA-256 after every edit.
`files write --content` remains available for normal whole-file authoring.

By default, Ruff checks source and tests; Pyright uses the project's declared
configuration scope with its selected Python. Explicit `check --path` arguments
select Pyright inputs too. Check new product tests explicitly when the project
configuration excludes inherited test scaffolding; do not suppress missing
imports or remove assertions to make that broader scope pass.

Implement the accepted business behavior, schema and product tests through
these commands inside the existing agent. Run `cogit check --project PATH` before syncing contracts, installing
the updated wheel, validating, and testing. Check runs the project's installed
Ruff formatter/linter and Pyright through fixed commands. Pyright uses the
selected project's Python; missing-import errors remain failures rather than
being ignored. Selected paths must
be under `src` or `tests`, with the whole source/test tree checked by default.
`--fix` edits source under the project lock: complete fixes before contract sync
and installation so the noneditable wheel is refreshed from the final source.
Contract sync imports trusted source using the installed public SDK. Sync
the project with its configured entrypoint and preserve the existing agent
class and Runtime wiring.

For durable business data, author the AgentDb module's migration and typed
contracts. Use the authorized AgentDb module plan/apply/inspect flow and the
module's supported read and write contract. Start the configured worker with
`cogit work --project PATH` and submit work through the AgentDb client.
`cogit run` serves Runtime endpoints for health and inspection.

Read the companion guide through
`cogit skills show cogit-run --reference operations.md` for the environment,
AgentDb module deployment and capability grants. Use the authorized
principal/installation and exact module scope, with credentials in the
environment. Verify backend readback and fresh authority resolution.
For effect-specific grants, `--installation` selects the grantee principal;
`--settings-installation` selects the settings effect target. Object scope uses
`--object` only with `object.read`/`object.events.read`; settings scope uses only
`agent.settings.read`/`agent.settings.write`. Preserve exact optional object
qualifiers; do not drop scope after a denial. Neither shape enters invocation
`effectiveCapabilities` or supplies run/execution access. Read the operations
guide for the capability/shape whitelist and supported effect verification.
Run positive and negative checks on the actual custom agent, and verify exact
persisted domain records after restarting the worker. Inspect the admitted
run, attempts, leases and affected data before retrying failures. `work --once`
returns nonzero when the worker poll reports failed work. A focused test path
establishes only that subset. Use `task submit` and `task inspect`
for standard queries. Mark unavailable approval or domain-specific readback
unrun where Cogit-only commands are required.

Honor the explicit command restriction: do not use direct file tools or ad hoc
shell, Python, HTTP or generic execution workarounds. Ordinary development may
edit source directly. Use host-message checkpoints, or a supported docs file
through the same safe write commands; report any remaining CLI gap concretely.
