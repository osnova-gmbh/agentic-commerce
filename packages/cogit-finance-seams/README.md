# cogit-finance-seams

Ports between the escrow demo code and its hosts, plus in-process stand-ins.

| Module | Content |
| --- | --- |
| `protocols` | `ModulePort` (mirror of the SDK's `DatabaseSeams`), `ArtifactPort`, `WorkPort`, `BankPort`, `ModuleError`, `Caller` |
| `local` | `LocalModuleHost` and `SqliteModule` (module reference implementations over in-memory SQLite), `LocalArtifacts`, `LocalRuntime` |
| `sim_bank_client` | `SimBankClient`, a `BankPort` over `apps/sim-bank` |
| `cogit_host` | `HandleModules` and `HandleArtifacts` (ports over a Cogit run handle), `LocalRunHandle`, `invoke_action`, `agent_invoker`. Needs `cogit-agent-sdk` |

The stand-ins let the whole deal flow run and be tested without Docker. On a
deployment, AgentDb and the Cogit runtime take their place; agent code does not change,
because it only sees the ports.
