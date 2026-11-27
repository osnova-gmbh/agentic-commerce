# Three-agent Affinidi gateway templates

These templates describe three closed MCP access points for the buyer, seller,
and escrow agent. They are based on the Affinidi Agent Gateway **v1.0.10**
configuration structs. They are templates, not exports of a configured or tested
gateway. No gateway configuration has been applied.

| Target surface | Route | DIDs allowed to call it |
| --- | --- | --- |
| Buyer | `/buyer` | Escrow |
| Seller | `/seller` | Buyer and escrow |
| Escrow | `/escrow` | Buyer and seller |

The evaluator remains outside this identity slice. The seller's existing quote
and the escrow protocol's signed envelopes still need their application-level
checks; a successful gateway session does not replace them.

Before importing, replace every `<...>` placeholder with the actual gateway
origin, public agent DID, and private MCP endpoint. Each target must be reachable
only through the trusted gateway path, or separately reject direct callers. The
gateway does not make a publicly reachable target private by itself. Use the
gateway's management interface to validate and save the resulting surface; do
not treat the placeholder files as ready-to-apply configuration.

`listen_address` is loopback-only here. The operator must supply the deployment's
actual listener and TLS arrangement when the callers are on other hosts.

The important native configuration is:

```json
{
  "caller_authentication": {
    "methods": [{
      "type": "did_auth",
      "extraction": {"source": "http_header", "field": "X-Agent-Session"},
      "allowed_dids": ["<explicit-caller-public-DID>"],
      "challenge_ttl_seconds": 300,
      "session_ttl_seconds": 300,
      "audience": "<gateway-origin>/seller",
      "allowed_algorithms": ["EdDSA"]
    }],
    "on_failure": "reject"
  },
  "public": false
}
```

An empty `allowed_dids` list accepts any DID with a valid proof, so these
templates deliberately require explicit callers. A session is bound to the
surface that minted it; use a separate authentication ceremony for each target.

For a surface at `<gateway-origin>/seller`, the native ceremony is:

1. `POST /seller/authenticate/challenge` with `{"did":"<caller-DID>"}`.
   The response is `{"challenge":"...","expires_in":300}` (the lifetime can
   differ with gateway configuration).
2. Sign a compact EdDSA JWS with `kid` set to the caller's DID verification
   method, and payload containing `challenge`, integer `iat`, integer `exp`,
   and the configured `aud`.
3. `POST /seller/authenticate` with `{"did":"<caller-DID>",
   "challenge_response":"<compact-JWS>"}`.
   The response contains `session_id`, `expires_at`, and `expires_in`.
4. Send the **raw** `session_id` in `X-Agent-Session` to the seller surface.
   Native DID Auth's HTTP-header extractor does not remove a `Bearer ` prefix.

The caller must use the actual surface's extraction header and audience. No
private keys, proofs, or session tokens belong in these files or in logs.

The repository's existing Boris investigation found only `shared_key` and
`identity_provider` in its hosted caller-authentication schema. This does not
establish a native DID Auth endpoint. The existing endpoint and an operator-
validated surface configuration are still needed for a real gateway test.

Verified upstream source:

- [Surface, access point and caller-authentication structs](https://github.com/affinidi-ai/agent-gateway/blob/v1.0.10/src/config/agent_surface.rs)
- [DID Auth settings and credential extraction](https://github.com/affinidi-ai/agent-gateway/blob/v1.0.10/src/source_auth/models.rs)
- [Challenge and authentication request/response fields](https://github.com/affinidi-ai/agent-gateway/blob/v1.0.10/src/didauth/handlers.rs)
- [Proof verification](https://github.com/affinidi-ai/agent-gateway/blob/v1.0.10/src/didauth/verify.rs)
- [Raw HTTP-header session extraction](https://github.com/affinidi-ai/agent-gateway/blob/v1.0.10/src/source_auth/middleware.rs)
