# Operations guide

Use installed command `--help` for current arguments and options.

| Outcome | Command |
| --- | --- |
| Read bundled operations instructions | `cogit skills show cogit-run` |
| Read this guide through the CLI | `cogit skills show cogit-run --reference operations.md` |
| Inspect readiness | `cogit doctor --project PATH` |
| Inspect manifest | `cogit agent show --project PATH` |
| Inspect project source text and hash | `cogit agent files show src/my_agent/agent.py --project PATH` |
| Create supported schema/request/test text | `cogit agent files write src/my_agent/database/schema.sql --content 'SQL_TEXT' --create --project PATH` |
| Make a short guarded literal edit | `cogit agent files replace cogit.yaml --find 'OLD_LITERAL' --replacement 'NEW_LITERAL' --expected-sha256 CURRENT_SHA256 --project PATH` |
| Check authored source and product tests | `cogit check --project PATH --path src/my_agent/custom.py --path tests/custom_agent.py` |
| Sync authored bindings using the configured entrypoint | `cogit agent contract sync --project PATH` |
| Reinstall frozen dependencies and project wheel | `cogit install --project PATH` |
| Validate manifest/action agreement | `cogit agent validate --project PATH` |
| Plan an AgentDb module | `cogit db module plan --agentdb-root PATH --request JSONFILE` |
| Inspect an AgentDb module | `cogit db module inspect --agentdb-root PATH --request JSONFILE` |
| Execute admitted AgentDb work | `cogit work --project PATH` |
| List bundled skills | `cogit skills list` |
| Install to a chosen skill directory | `cogit skills install --target PATH` |

Skill installation preserves existing folders unless `--force` is requested.
The default target is `.agents/skills` under the current working directory;
it is not inferred from another command's `--project`. Supply `--target` when
operating from a different directory or when the host uses another layout.
Copied files do not prove host activation.

For an explicit Cogit-CLI-only request, load instructions through `skills show`.
Use supported file commands, not direct file tools or ad hoc shell, Python,
HTTP or generic execution workarounds. `--content` is literal text in one
argument; replace placeholders with actual content and real newlines as needed.
Use `--create` for new files or the exact shown `--expected-sha256` for updates.
Prefer `files replace` for a small edit to a large generated file: find must
match exactly once, the literal pair is bounded to 16 KiB combined, and the
existing file stays within the 256 KiB file limit. Use short literal or literal
here-string arguments, without redirection, and reread the hash after every
edit. Normal whole-file `write --content` remains available.
Authoring requested Python source is supported; launching an ad hoc interpreter
or hiding a bypass in tests is not. Use host-message checkpoints if file writing
is unavailable; report remaining unsupported operations as concrete gaps.

Run `cogit check` for installed Ruff formatting/lint and Pyright on authored
source/tests, using the selected project's Python for Pyright import resolution.
Missing imports are failures to resolve, not diagnostics to suppress. Its
repeatable `--path` accepts supported `src`/`tests` paths;
without paths it checks both trees. `--fix` can edit source, so finish fixes,
sync changed bindings, and then install the wheel, validate and test.
Contract sync imports user-trusted source with the installed SDK. For a business
schema, author the AgentDb module migration and its typed contracts. Run the
authorized module deployment workflow, and verify exact records through the
owning AgentDb contract after a worker restart.

## AgentDb tooling

```text
cogit db module initializeApplication --agentdb-root PATH --request JSONFILE --yes
cogit db module plan --agentdb-root PATH --request JSONFILE
cogit db module apply --agentdb-root PATH --request JSONFILE --yes
cogit db module inspect --agentdb-root PATH --request JSONFILE
```

Use a real AgentDb checkout and its request schema. Keep deployment credentials
in the environment and out of request files, command arguments and output.

An application binding request names `applicationKey`, `mode`, and
`operatorPrincipalId`. Use `mode: attach` with the exact existing `tenantId`.
Use `mode: create` only for authorized tenant creation. Both operate in the
existing physical database selected by the deployment connection. There is no
Cogit CLI name search for databases or tenants. Obtain the exact target from the
operator before sending a mutating request.

## Permission declarations

Inspect `cogit permissions show --help`, `require --help`, `unrequire --help`,
and `approval --help` for positional arguments. The supported commands update
manifest declarations and one unique literal Python `bind_action` found across
bounded project `src`, including custom agent classes. Derived tool inspection
covers all scanned modules and keeps mirrored requirements consistent.
Dynamic, aliased or duplicate bindings are refused with guidance;
an existing action contract is synchronized in the same recoverable edit.
When a dynamic binding needs source changes, author them through safe file
commands in CLI-only mode or an editor when unrestricted, then run contract
sync. Reinstall after edits because the agent wheel is
noneditable. These declaration commands do not issue canonical grants; use the
separate grant administration commands below.

## Canonical capability grants

The backend owns capability authority. Configure `COGIT_AGENTDB_ADMIN_TOKEN`
outside command arguments and files; use `COGIT_AGENTDB_URL` or the explicit
endpoint. Never copy a worker token into the administrative setting or print
the environment to discover credentials. Replace the uppercase placeholders
with the exact authorized IDs, scope, endpoint and observed grant version.

```text
cogit permissions grants list --tenant TENANT_UUID --endpoint HTTPS_AGENTDB_URL
cogit permissions grants grant records.read --tenant TENANT_UUID --principal PRINCIPAL_UUID --idempotency-key grant-read-001 --yes --endpoint HTTPS_AGENTDB_URL
cogit permissions grants grant records.read --tenant TENANT_UUID --installation INSTALLATION_UUID --module MODULE_KEY --idempotency-key grant-module-read-001 --yes --endpoint HTTPS_AGENTDB_URL
cogit permissions grants grant object.read --tenant TENANT_UUID --principal PRINCIPAL_UUID --object OBJECT_UUID --purpose case-review --max-classification confidential --valid-from 2026-11-01T09:00:00Z --valid-until 2026-11-01T10:00:00Z --idempotency-key grant-object-read-001 --yes --endpoint HTTPS_AGENTDB_URL
cogit permissions grants grant agent.settings.read --tenant TENANT_UUID --installation GRANTEE_INSTALLATION_UUID --settings-installation SETTINGS_INSTALLATION_UUID --idempotency-key grant-settings-read-001 --yes --endpoint HTTPS_AGENTDB_URL
cogit permissions grants revoke GRANT_UUID --tenant TENANT_UUID --expected-version 1 --idempotency-key revoke-read-001 --yes --endpoint HTTPS_AGENTDB_URL
```

Use exactly one of `--principal` or `--installation`. Grants attach to the
principal. Installation selection resolves its actual active agent principal;
inspect that principal in the response rather than assuming an installation-only
ACL. If active installations share the same principal, the installation-targeted
request is denied. Use explicit `--principal` only when the user authorized
authority shared by that principal's installations. No effect-scope flag means
core `{}`; `--module` carries the exact module key. `--module`, `--object`, and
`--settings-installation` are mutually exclusive. Do not drop or replace the
requested scope or substitute another principal to make an access check succeed.
`list` is tenant-scoped
and bounded; use its `--limit` and `--after` options when inspecting more pages.

Object scope is `{objectId: ...}` and is restricted to `object.read` and
`object.events.read` for existing tenant-owned artifacts, context items, or
context manifests. It does not grant run/execution/case/task access. Optional
`--purpose` is a lowercase token matching `^[a-z][a-z0-9._:-]{0,127}$`;
`--max-classification` is `public`, `internal`, `confidential`, or `restricted`.
Optional RFC3339 `--valid-from`/`--valid-until` normalize to UTC milliseconds
with `Z`; when both exist, the start must precede the end. Omitted qualifiers
remain omitted. These qualifiers are object-only; do not add defaults or unknown
keys, mix shapes, or use arbitrary JSON.

Settings scope is `{installationId: ...}` and is restricted to
`agent.settings.read` and `agent.settings.write`. Its `--settings-installation`
is the tenant-owned effect target, distinct from the grantee selector
`--installation`. Use each observed ID for its actual purpose. Object/settings
grants never enter invocation `effectiveCapabilities` and cannot stand in for
`action.execute`, module attachment, or separate run/execution access.

Verify the actual supported owning object/settings effect before and after
revoke or expiry, including denial for a sibling object/installation and an
out-of-scope purpose/classification/time window where applicable. Keep these
checks separate from invocation claims. When the selected CLI lacks an owning
effect command, report that exact check as unrun and name the missing public
surface. In CLI-only mode, use the supported Cogit commands for other checks.

`grant` and `revoke` mutate canonical state and require `--yes` plus an
idempotency key. Existing user authorization for the exact operation and target
is sufficient; do not add another confirmation gate. List before changing
state, preserve unrelated entries, and read back the returned grant ID, subject,
capability, scope and version. Revoke using the observed current version rather
than assuming every grant is version 1. The literal `1` above is a syntax example.

Read back revocation, and when the target's execution or access-check surface is
available, verify fresh authority resolution allows the intended grant before
revocation and denies it afterward. If only backend grant state was checked,
report that narrower evidence. After an uncertain mutation, inspect state before
retrying the same payload/key; a version conflict requires rereading the grant.
Backend authorization denials are failures to report, not invitations to broaden
scope, edit declarations, or change credentials. HTTPS is required remotely;
loopback HTTP is permitted for an authorized disposable local backend.

## Canonical object and settings effects

Use the selected ordinary mapped member's `COGIT_AGENTDB_TOKEN` through host
environment configuration for these effects. Grant administration continues to
use `COGIT_AGENTDB_ADMIN_TOKEN`; neither value belongs in arguments, fixtures,
reports, or displayed environment dumps. A denial must not cause identity
switching, administrator/worker fallback, or scope widening.

```text
cogit settings get --tenant TENANT_UUID --installation SETTINGS_INSTALLATION_UUID --key SETTINGS_KEY --endpoint HTTPS_AGENTDB_URL
cogit settings put --tenant TENANT_UUID --installation SETTINGS_INSTALLATION_UUID --key SETTINGS_KEY --schema INSTALLED_SCHEMA_KEY --expected-version 0 --values-json '{"enabled":true}' --idempotency-key settings-write-001 --yes --endpoint HTTPS_AGENTDB_URL
cogit objects timeline OBJECT_UUID --purpose audit --limit 100 --endpoint HTTPS_AGENTDB_URL
```

Replace example IDs, key, schema, purpose, values and version with the actual
authorized target contract and observed state. `settings put` needs `--yes`, an
idempotency key and the expected version; `0` means creation, not a concurrency
bypass. The backend's settings module and validator must already be installed.
The CLI checks the returned tenant, installation, key, schema and exact values.
Object timeline has no `--tenant` option: the mapped member identity chooses
the tenant, and the EventPage receipt does not independently attest a tenant ID.
Preserve the exact object and requested purpose; use its numeric returned cursor
with `--after` for further pages. A timeline read proves only that owning event
path, not arbitrary object content, run access, or worker mutation.

Observe actual allowed effects, sibling denial and fresh denial after revocation
or expiry. Report any unavailable target, mapped identity or installed settings
contract as an unrun dependency. These supported commands keep a CLI-only pilot
within public contracts. Run admission uses the authenticated AgentDb client.

## Launch and verify AgentDb work

Configure `COGIT_AGENTDB_URL`, `COGIT_AGENTDB_API_VERSION`,
`COGIT_AGENTDB_POOL_ID`, `COGIT_AGENTDB_INSTALLATION_ID`,
`COGIT_AGENTDB_WORKER_TOKEN`, and `COGIT_AGENTDB_COHORT_RECEIPT` for an
authorized installation and approved Runtime cohort. Use the installation and
pool IDs recorded in the receipt. Set `COGIT_DEV_MODE=0` and leave
`DATABASE_URL` unset. Use distinct credentials for worker claims, tenant client
operations, grant administration, and module deployment.

```text
cogit agent validate --project PATH
cogit agent validate --project PATH --environment
cogit doctor --json --verify --project PATH
cogit work --project PATH
```

Ordinary validation checks the project manifest against installed bindings
without opening storage. `--environment`, `run`, and `work` select the deployed
manifest named in the cohort receipt. Runtime verifies the cohort before
importing the agent and checks AgentDb readiness when launching. Doctor's
`--verify` invokes the installed Runtime preflight for that deployment.

Set `AGENTDB_CLIENT_TOKEN` for the `task submit` and `task inspect` commands.
Use one stable request ID per input and installation and keep the structured
admission and result files. The CLI verifies saved artifact length and hash.
See `agent-db/docs/local-e2e.md` for disposable provisioning and the install
runbook for a managed route.
`cogit work --project PATH --once` polls once, and returns nonzero when the
worker reports failed jobs. A poll reporting zero claims is not execution
evidence.

Verify the observed run status, attempts and actual domain result. For
approval-gated work, verify the request parked before its effect, use the
AgentDb approval interface for the observed request, and verify the authorized
continuation retains the original input. Before retrying failed work, inspect
the run, attempts, leases and affected domain state. For persistence, restart
the worker, then read back the exact saved record through the owning module.
In CLI-only mode, mark approval decisions or domain-specific readback as
unrun where the necessary command is absent.

## Runtime endpoints and registration

```text
cogit run --project PATH
cogit eval --project PATH --suite NAME --endpoint RUNTIME_URL
cogit register --project PATH --endpoint HTTPS_AGENT_URL
```

Run/work remain foreground processes. The Runtime HTTP server provides health
and inspection. Use an incoming `COGIT_AGENT_API_KEY` for protected endpoints.
HTTP suites for those endpoints are distinct from AgentDb admission and result
checks. Protected Runtime evals attach the incoming key only to the chosen
origin. Remote authenticated endpoints require HTTPS. Keep credentials in
environment configuration and out of suite files.

The registration `--endpoint` advertises the agent URL. Select the separate
platform API via its configured environment or `--api-url`. Platform
registration and AgentDb cohort publication/installation are separate
operations. Verify the target and existing authorization before mutating it.
