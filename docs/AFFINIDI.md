# Affinidi / Boris agent identity

The project uses the existing Boris **Agent Identity & Access** use case in
payload mode. No new gateway or native DID-auth challenge is required for this
mode. The configured endpoint is:

https://agent-gateway-01.agw.pool.boris-md.usw1.affinidi.io/agents/teal-orchard-5580

## Enable and check the project

From the repository root:

```powershell
python scripts/affinidi_agents.py enable
python scripts/affinidi_agents.py probe
```

`enable` writes the public [project configuration](../config/agent-identity.json).
It is idempotent and needs no remote credential. `probe` sends an MCP initialize
and tools/list using each agent's own identity. It reports connection results;
it does not claim to verify a gateway-signed identity proof.

| Agent | `applicationInfo.name` |
| --- | --- |
| Buyer | `buyer-agent` |
| Seller | `seller-agent` |
| Escrow | `cogit-finance` |

The server-side identity use case was enabled separately by the operator. The
project configuration enables clients to provide the identity that use case
expects; it does not edit the remote gateway's settings.

Each initialize, notification and tools/call includes this metadata, with the
appropriate name for its caller:

```json
{
  "params": {
    "_meta": {
      "agentIdentity": {
        "applicationInfo": {"name": "buyer-agent", "version": "0.1.0"}
      }
    }
  }
}
```

`BorisMCPClient` preserves unrelated metadata, negotiates MCP sessions, handles
JSON and SSE responses, and attaches identity to every request. The three
agent `identity.py` modules expose `boris_client()` using the project setting.
`BORIS_IDENTITY_CONFIG` can select another configuration file. Agent health
reports whether payload identity is enabled and which application name is used.
The client sends to the existing endpoint only; finance envelopes still use
independent local signing keys.

Payload identity is an asserted application identity. A gateway-signed proof of
that payload does not establish possession of the application's private key.
The implementation keeps that distinction explicit.

## Local signing and optional native DID Auth

The older [Alice/Bob plan](../ALICE-BOB-PLAN.md) also describes a separate native
DID Auth experiment. Its reusable client is available, but it is not required
by the enabled Boris payload-identity use case.

```powershell
python scripts/affinidi_agents.py init
python scripts/affinidi_agents.py status
python scripts/affinidi_agents.py verify-local
```

These commands preserve existing Ed25519 keys, create missing keys in
`.state/keys/`, and verify seller-signed quotes and escrow-signed receipts.
Use `--key-dir .state/agentdb/keys` to reuse the AgentDb launcher's identities.
Private key material and session tokens are not printed. Local cryptographic
checks are explicitly labeled as local, not vendor integration.

Native DID Auth uses separate `BUYER_AFFINIDI_*`, `SELLER_AFFINIDI_*` and
`ESCROW_AFFINIDI_*` URL/audience/session-header settings. It can be invoked with
`authenticate`, or enabled at startup with
`AFFINIDI_AUTHENTICATE_ON_STARTUP=1`. Leave that flag unset for the current Boris
payload mode. The optional [native surface templates](../config/affinidi/README.md)
are references, not deployed configuration.

## Validation

Automated checks cover three distinct caller identities, metadata on every MCP
message, JSON/SSE decoding, MCP session handling, safe errors, durable keys,
quote verification and the three resident-agent hooks. The live `probe` must
run from a network-enabled CLI session; the restricted execution shell used for
implementation could not reach the supplied endpoint.
