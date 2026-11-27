# Minimal Alice/Bob implementation plan

Status: three-agent identity support is implemented. The active project uses the
operator-enabled Boris payload identity use case through its existing endpoint;
it does not require the native DID Auth gateway experiment below. See
[implementation and CLI commands](docs/AFFINIDI.md). Native DID Auth remains a
separate optional client, with live vendor verification outstanding.

## Goal

Demonstrate two independently controlled agent identities: Alice authenticates to a seller's Affinidi gateway, requests a quote from Bob, and verifies Bob's signed quote. No LLM, payment, purchase, corporate identity provider or company-verification system in this first slice.

## What we program versus configure

| Piece | Our code/configuration | Affinidi's responsibility |
|---|---|---|
| Alice buyer client | Hold Alice's key, sign an authentication challenge, call `get_quote`, verify Bob's signed response | Resolve Alice's DID and verify her proof |
| Bob seller service | Expose one MCP tool, generate a quote and sign it with Bob's key | Protect access to Bob through a closed gateway surface |
| Gateway surface | Configure native `did_auth`, audience, short session lifetime, nonempty approved-DID list, and Bob's MCP target | Issue/consume challenges, check proofs, create surface-bound sessions, enforce access |

The agents need not share an identity provider. In production each company creates and controls its own private keys. A demo may generate two test keys locally, in separate private files.

## SDK and runtime choice

Use a small Node.js/TypeScript application, not a custom identity server:

- `jose` **6.2.18** for standard Ed25519 JWS signing and verification.
- `multiformats` **14.0.8**, `bases/base58`, to encode/decode a standard Ed25519 `did:key` (multicodec prefix `0xed01`). This is an encoding operation, not new cryptography.
- `@modelcontextprotocol/sdk` **1.32.2** for the MCP seller server and buyer client; its published Node requirement is >=18.
- Node's HTTP client and test runner; pin remaining development dependencies at implementation time and commit a lockfile if/when the project is initialised.

No Affinidi SDK is required for the documented DID Auth HTTP ceremony. The gateway does DID resolution and proof verification. Affinidi's broader TDK/service clients are optional and must not be assumed to contain a ready-made TypeScript DID Auth client. DIDComm/VC integration is a later scope, if needed.

Windows has Node **22.22.3**. Ubuntu currently has **no native `node` executable**; its PATH exposes Windows npm/pnpm launchers. Before running this project in WSL, install/verify a supported native Linux Node.js and package manager rather than accidentally mixing runtimes. The current TDK repository recommends Node >=22.23.4, another reason not to install it indiscriminately into the older runtime.

## Proposed files (keep each focused and under 300 lines)

- `src/keys.ts`: generate/load separate demo key files; derive `did:key` and its verification-method ID. Ignore private state in Git and restrict directory/file permissions.
- `src/did-auth.ts`: request a challenge, sign the compact JWS and exchange it for a session; do not log proofs, keys or session tokens.
- `src/bob.ts`: MCP server exposing only `get_quote`; sign the quote using Bob's independent key.
- `src/alice.ts`: authenticate, create an MCP session with the gateway-configured authentication header, request and verify a quote.
- `gateway/bob-surface.json`: actual exported/validated native gateway surface configuration, not an invented Boris feature configuration.
- `tests/identity.test.ts`: key/DID/JWS and quote verification tests.
- `tests/gateway.test.ts`: tests against a real configured Affinidi gateway; never substitute a mock and call it vendor integration.
- `README.md`, `package.json`, lockfile, `.gitignore`: reproducible commands and safe demo-state handling.

Existing `tools/wsl/check-boris.sh` overlaps with environment diagnostics: reuse it, do not replace it or write another checker. See `WSL-HANDOVER.md` for the installation and Docker history.

## Execution order

1. **Establish the real integration endpoint first.** Find how to configure native DID Auth on the existing Boris-backed gateway. Only if unavailable, explicitly choose a managed/self-hosted Trust Fabric gateway with the operator. Do not assume another deployment is required. Current hosted Boris account schemas expose only shared-key/external-JWT caller authentication, not `did_auth`.
2. Verify the runtime. If local Docker is required, resolve the documented settings-file lock and restore the existing containers without resets/pruning. Do not change someone else's editor or runtime silently.
3. Implement test-key generation and local signature tests. Use `did:key` for this demonstration; do not imply it provides corporate verification or production key rotation.
4. Configure one closed Bob surface: native DID Auth, explicit audience, e.g. a 300-second session, Alice's DID allowed, Bob's MCP server reachable only through the trusted gateway path. An empty DID allowlist means *any* DID is accepted, so do not leave it empty.
5. Implement Alice's exact documented ceremony, relative to the gateway's actual surface routes:
   - `POST .../authenticate/challenge` with `{ "did": aliceDid }`.
   - Sign a compact EdDSA JWS with `kid` pointing to Alice's DID key and payload `{ challenge, iat, exp, aud }`.
   - `POST .../authenticate` with `{ "did": aliceDid, "challenge_response": compactJws }`.
   - Use the returned `session_id` in the configured extraction header. Do not assume it is an OAuth access token or universally uses `Authorization: Bearer`.
6. Implement `get_quote({ sku, quantity, nonce })`. Return a Bob-signed JWS binding seller DID, SKU, quantity, integer minor-unit amount, currency, request nonce and expiry. Alice pins Bob's expected DID/public identity and checks all fields, not just the signature. The signature binds this quote's contents; a generic identity presentation alone is not a substitute.
7. Run the real integration tests and document evidence. Do not claim success from source inspection or mocks alone.

## Acceptance checks / boundaries

- Alice's valid proof obtains a session and reaches `get_quote`.
- An unknown DID, wrong signing key, expired proof and reused challenge are refused.
- A session cannot be reused on another surface.
- Alice rejects an altered quote, unexpected seller DID, wrong nonce or expired quote.
- Missing credentials cannot bypass the gateway by reaching Bob directly.
- The initial gateway allowlist authorises Alice only. Do not trust a `buyerDid` or role supplied in tool arguments. Before adding multiple buyers or private account/order data, define and verify how authenticated identity reaches the application, or enforce the necessary decisions entirely in the gateway.
- Keys/session tokens never appear in logs, prompts, checked-in files or model context.
- This demonstrates key ownership and access, **not** business legitimacy, legal delegation, purchasing mandates or payment settlement. Those are separate next features.

## Verified protocol references

- https://github.com/affinidi-ai/agent-gateway/blob/v1.0.10/docs/SOURCE_AUTH.md#did-auth
- https://github.com/affinidi-ai/agent-gateway/blob/v1.0.10/src/didauth/handlers.rs
- https://github.com/affinidi-ai/agent-gateway/blob/v1.0.10/src/didauth/verify.rs
