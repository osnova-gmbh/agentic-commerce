# cogit-messaging (module)

Reference implementation of the `cogit-messaging` AgentDb module of SPEC §11.1: Python over
SQLite, behind the frozen export contract in
[contracts/module-exports.md](../../contracts/module-exports.md). It is the specification
for the later AgentDb-native port (PL/pgSQL functions plus `manifest.json`).

The module binds agent DIDs to installations, keeps an immutable registry of message
types and runs a simple message queue. It knows nothing about escrow and verifies no
signatures (SPEC §6.2); the recipient's delivery loop does that.

| Part | Content |
| --- | --- |
| `migrations/000001__init.sql` | `msg_agent_identities`, `msg_message_types`, `msg_messages`, in the SQL subset SQLite and PostgreSQL share |
| `cogit_messaging_module.MessagingModule` | The eight exports over `cogit_finance_seams.SqliteModule` |
| `cogit_messaging_module.check_dialect` | Refuses schemas outside the SPEC §6.1 dialect |

| Export | Kind | Caller | Behaviour |
| --- | --- | --- | --- |
| `identity.register` | command | operator | Upsert of a DID's installation, org and role |
| `identity.resolve` | query | any | By `did`, or the oldest active identity with a `role` (and `org_id`) |
| `type.register` | command | E | `created`, `unchanged` for the same canonical JSON, else `type_conflict`; `unsupported_schema` outside the dialect |
| `message.send` | command | any installation | Checks the envelope shape, the sender binding, the recipient, the type and the body; stores the envelope verbatim; `duplicate` for a known `message_id` |
| `message.claim` | command | any installation | The caller's due messages, oldest first; also claims older than `redeliver_after_s` |
| `message.ack` | command | recipient | `processed` or `rejected` with `reason` and `run_id`; repeating it is harmless |
| `message.release` | command | recipient | Back to `queued`, due after `delay_s` |
| `conversation.read` | query | any (demo) | One conversation in insertion order |

Settings: `escrow_installation_id` (`cogit-finance`), `redeliver_after_s` (30),
`max_delivery_attempts` (5).

Beyond the SPEC columns, `msg_messages` has `available_at` (when a queued message may be
claimed) and `seq` (insertion order, because timestamps have whole seconds). A message that
used up `max_delivery_attempts` becomes `dead` with reason `max_delivery_attempts` at its
next claim or release. Malformed arguments fail with `invalid_argument`.

```python
from cogit_finance_seams import LocalModuleHost
from cogit_messaging_module import MessagingModule

host = LocalModuleHost()
host.install(MessagingModule(), {"redeliver_after_s": 30})
host.port("operator", "operator").module_command(
    "cogit-messaging", "identity.register",
    {"did": "did:key:z…", "installation_id": "buyer-agent", "org_id": "buyer-co", "role": "buyer"},
    idempotency_key="identity:buyer-agent",
)
```

## Tests

From the repository root, after `scripts/dev-install.sh`:

```sh
scripts/test.sh modules/cogit-messaging
```
