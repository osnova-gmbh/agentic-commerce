# WSL / Boris handover

Environment last checked: 2026-11-27. Planning and environment setup only; no application has been built here.

## Environment and access

- Windows workspace: `C:\ai\_experiments\agentic-commerce`
- Same folder in Ubuntu: `/mnt/c/ai/_experiments/agentic-commerce`
- WSL2 distribution: **Ubuntu 24.04**, x86_64.
- Default Linux user: **denys** (UID 1000), home `/home/denys`.
- Use `denys` for Boris. Root has a different home/profile and is not signed in.
- The new user has no configured sudo/password setup. For an authorised administrative task, explicitly use `wsl -d Ubuntu -u root`; do not run Boris as root.

From PowerShell / Windows Terminal:

```powershell
wsl -d Ubuntu
# You are now in Ubuntu; `exit` returns to Windows.
```

Reliable noninteractive commands from Windows:

```powershell
wsl -d Ubuntu -u denys --exec /home/denys/.boris/bin/boris --version
wsl -d Ubuntu -u denys --exec /home/denys/.boris/bin/boris doctor --plain --no-color
wsl -d Ubuntu -u denys --exec /home/denys/.boris/bin/boris status --json --no-input
wsl -d Ubuntu -u denys --exec /home/denys/.boris/bin/boris local status --json --no-input
wsl -d Ubuntu -u denys --exec /home/denys/.boris/bin/boris agent status --json --no-input
```

Boris is linked at `/home/denys/.local/bin/boris`; interactive/login shells have it on PATH. Prefer the absolute binary path for automation.

### Bash-tool / Windows quoting gotchas

The agent's Bash tool runs on **Windows**, not inside Ubuntu. Native-command argument quoting and MSYS path conversion can interfere with Linux paths. For scripts, use Windows Python to pass an argument array and send the shell script over stdin:

```python
import subprocess, sys
sys.stdout.reconfigure(encoding="utf-8")
r = subprocess.run(
    ["wsl.exe", "-d", "Ubuntu", "-u", "denys", "--exec", "/bin/sh", "-s"],
    input="set -eu\ncd /home/denys\n/home/denys/.boris/bin/boris --version\n",
    text=True, encoding="utf-8", errors="replace", capture_output=True, timeout=60,
)
print(r.stdout)
print(r.stderr)
r.check_returncode()
```

Linux command output is UTF-8. WSL's own status/list output may be UTF-16LE. Set Python stdout to UTF-8 before printing Boris's Unicode diagnostic marks.

## Boris: installed and signed in

- CLI **0.1.35**, build `b291fbc9`, installed under `/home/denys/.boris/bin/boris`.
- Official installer SHA-256 and Ed25519 release signatures were verified using OpenSSL 3.
- Deployment/profile: `https://trustboris.ai` / `trustboris.ai`; existing sign-in works.
- Project: an existing operator project. Resolve the current project name and ID with the authenticated CLI; account-specific identifiers are omitted from this public handover.
- Agent and LLM caller-authentication features are enabled. No local agents, tunnels or local Boris service are running.
- No model calls, purchases or agent runs were performed during this check. Query the current account balance through the authenticated CLI.
- A demonstration project-rename plan was generated but **never applied**; the project name is unchanged.
- Community-agent searches return `community_agents_off`: a deployment administrator must enable that catalogue. This is not a local installation error.

Credentials under `/home/denys/.boris/credentials/` are secrets. Do not print, paste or export them into handover/context files. Prefer the CLI for authenticated queries. Do not unnecessarily log out or repeat login.

## Runtime blockers — resolve before claiming an agent can run

1. **Docker Desktop is currently stopped.** Its restart failed because it could not atomically replace:
   `C:\Users\denys\AppData\Roaming\Docker\settings-store.json`.
   Windows Restart Manager identified **Zed** as holding the file. Ask the operator to save and close that tab, then recheck the lock before starting Docker. Do not kill their editor or close arbitrary process handles.
2. **Ubuntu Docker integration is not working.** Enabling integration via Docker's settings API returned success, but persistence failed with the file-lock error. Do not assume the setting survived. Enable integration for Ubuntu and verify `docker version` as Linux user `denys`.
3. **Linux OS keyring is not configured.** No active `org.freedesktop.secrets` service was found; GNOME Keyring is not installed. File-backed Boris login works, but the agent runner requires an OS keychain for agent secrets.
4. **User lingering is off** (`Linger=no`); long-running user services may stop after the last session ends. Configure deliberately if persistent agents are wanted.

There were **21 running containers**, all with `unless-stopped` restart policy, before the attempted Docker restart. Preserve existing containers/volumes. Do not factory-reset Docker, prune data, unregister WSL or reinstall the runtime as a shortcut. A restart was authorised in this session; coordinate any further disruptive action with the operator.

`boris doctor` can exit successfully while reporting Docker warnings. Test Docker connectivity separately.

Boris requires a **person at a terminal** to approve initial local pairing and a new `boris agent run`. Do not bypass coding-agent detection or spoof human approval.

## Identity investigation / current direction

The intended marketplace has independently owned agents: Alice belongs to an external buyer company; Bob represents the operator's seller company. Do not assume both belong in one corporate identity directory. Keycloak/Entra are **not native Trust Fabric prerequisites**.

Verified against released Agent Gateway **v1.0.10** source/docs:

- Native DID authentication: challenge -> caller-signed JWS -> DID resolution/signature verification -> surface-bound session.
- Developer-owned or gateway-managed DIDs; independent gateways can exchange signed identity presentations over DIDComm.
- DID control is not proof of a legitimate business or purchasing authority; marketplace trust/access policy is still needed.

Verified against this account's live, read-only `GET https://trustboris.ai/api/v1/init` response:

- Boris caller-authentication methods: `shared_key`, `identity_provider`.
- Boris identity modes: `payload`, `bearer`, `api_key`; no exposed `did_auth` choice.
- A `sign_proof` setting exists, but signing a derived identity is not independent caller proof-of-possession.

**No end-to-end Alice/Bob exchange has been executed.** First determine how to expose native DID Auth on the existing Boris-backed gateway. A separate managed/self-hosted gateway is only a fallback if that capability is unavailable, not an established requirement. Do not claim that installing the Boris CLI installed the full gateway appliance.

Sources:
- https://github.com/affinidi-ai/agent-gateway/blob/v1.0.10/docs/SOURCE_AUTH.md#did-auth
- https://github.com/affinidi-ai/agent-gateway/blob/v1.0.10/docs/CAPABILITIES.md#managed-or-owned
- https://github.com/affinidi-ai/agent-gateway/blob/v1.0.10/docs/CAPABILITIES.md#federation-across-organisations

## Existing evidence / recovery files

Windows: `C:\Users\denys\AppData\Local\Temp\affinidi-review\`

- `containers-immediately-before-restart.json`: the 21-container baseline.
- `docker-settings-pre-integration.json`: pre-change settings backup.
- `native-identity/hosted-boris-feature-schemas.json`: sanitised live feature schemas, no credentials.
- `native-identity/v1.0.10/`: downloaded upstream source/documentation evidence.

These are temporary evidence files outside the repository, not project dependencies; check they still exist. They are not included in the repository.
