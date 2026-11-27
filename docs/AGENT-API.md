# Agent API and MCP

The commerce API supplies contract discovery, per-service input schemas, and state-dependent actions. The MCP adapter uses that same API and does not create another checkout engine or bank ledger.

## Discover the API

Start with GET /api or /.well-known/agent.json. Follow returned links rather than guessing mutation URLs.

| Resource | Purpose |
| --- | --- |
| /openapi.json | Operation, request, response, and error schemas |
| /docs, /redoc | Human-readable API reference |
| /agent-skill.md | Agent operating instructions |
| /api/catalog | Public companies |
| /api/provider-offers | Public offerings and published pricing |
| /api/demo/services | Purchasable services, exact IDs, input schemas, and preparation actions |
| /api/demo/orders/{deal_id} | Checkout state and available actions |
| /api/demo/boris?deal_id={deal_id} | Per-deal request evidence |

Action descriptors include method, URL, input and response schemas, required headers, idempotency, side effects, preconditions, and confirmation requirements. Existing allowed_actions labels remain for compatibility. Read-only deployments advertise only registered capabilities.

Public provider offer IDs can differ from checkout IDs. Select exact identifiers from /api/demo/services. Keep published billing terms separate from the chosen simulated amount.

## Connect through MCP

Use the repository's development setup for a fresh checkout (`scripts/dev-install.sh`). If the demo is already running, leave it running and install only the MCP dependency in the Python environment used by the client:

```powershell
python -m pip install "mcp>=1.26,<2"
```

To start the checkout API when it is not already running:

```powershell
python scripts/run_demo.py --port 8091
```

Run a separate stdio MCP process from a client:

```json
{
  "mcpServers": {
    "agentic-commerce": {
      "command": "python",
      "args": [
        "C:/ai/_experiments/agentic-commerce/scripts/run_mcp.py",
        "--api-url", "http://127.0.0.1:8091"
      ]
    }
  }
}
```

Replace the script path with this checkout's actual location. For HTTP:

```powershell
python scripts/run_mcp.py --api-url http://127.0.0.1:8091 --transport streamable-http --port 8094
```

Use the endpoint printed by the launcher. The adapter uses the official Python MCP SDK 1.26 and its MCP 2025-11-25 compatibility; it does not claim support for the newer 2026 revision. Read commerce://skill and discover the tool schemas before calling them. The HTTP sidecar can supply a current contract for an older running checkout API.

## Operate a checkout

1. Discover companies, public offers, and purchasable services.
2. Prepare the exact selected service with its required inputs and retain the idempotency key.
3. Poll that deal until processing stops, then inspect quoted terms and actions.
4. Fund only when authorized for the service and current total. MCP funding requires confirm, expected_price_minor, expected_currency, and idempotency_key.
5. Run requested work simulation; inspect the delivery and every evaluator result.
6. Release only when advertised and authorized for the approved delivery. Supply the current amount and currency and a distinct release key.
7. Poll until SETTLED and report the actual state and evidence.

HTTP 202 or processing acknowledges a request, not completed funding or settlement. After an uncertain response, read status and reuse the original logical action's key.

## Scope

This local demo uses simulated money and generated artifacts. It does not buy the public provider's actual product. Budget replenishment is separate from payment confirmation; do not invoke administrative funding or reset endpoints to force a purchase.

Boris evidence distinguishes real remote exchanges from offline and injected test transports. Payload identity is not a cryptographic DID proof. Report correlation IDs and timestamps without exposing credentials.

The portable skill is in .agents/skills/use-agentic-commerce/. Repository content alone does not mean a personal skill has been installed in a user's account.

## Validation

The automated tests exercise REST discovery and a complete isolated checkout through the official MCP client. Check their results before claiming verification. Published source or configuration alone does not prove that a live server was restarted or a transaction completed.
