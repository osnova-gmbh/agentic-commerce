# Connection and recovery

## Connect a client

Start the checkout application separately. The MCP adapter connects to it and does not create a second ledger.

```powershell
python scripts/run_demo.py --port 8091
python scripts/run_mcp.py --api-url http://127.0.0.1:8091
```

The second command runs stdio. Configure a client with command python and args ["C:/ai/_experiments/agentic-commerce/scripts/run_mcp.py", "--api-url", "http://127.0.0.1:8091"], substituting the actual path. Never put Boris credentials in MCP client configuration.

For an HTTP adapter:

```powershell
python scripts/run_mcp.py --api-url http://127.0.0.1:8091 --transport streamable-http --port 8094
```

Use the printed MCP URL. Read commerce://skill or /agent-skill.md for guidance. The HTTP adapter also serves discovery for the target API; it can describe an older running checkout server without creating another commerce engine.

## Follow REST actions

Start with GET /api. Follow the OpenAPI and resource links. The services response supplies per-service input schemas. Each actions entry gives its name, method, href, input_schema, response_schema, required_headers, idempotency, side_effects, preconditions, and requires_confirmation.

Keep URLs on the configured service origin. Do not send a confirm body field to REST unless its advertised schema includes it. Confirmation parameters belong to the MCP adapter; REST uses its own advertised request schemas.

## Recover safely

| Observation | Next step |
| --- | --- |
| Mutation timed out | Read the same deal, then retry with the original key if needed |
| processing or running: true | Poll the same deal; do not start another action |
| Invalid inputs or changed price | Re-read schema and terms; obtain any missing authorization |
| Network or Boris failure | Retain the deal ID and keys; report the failure and retry after connectivity recovers |
| No advertised next action | Inspect state and error; do not guess a write endpoint |
| Missing or archived checkout | Read history if available; do not claim it remains actionable |
| Failed checks | Report the verdicts and follow only advertised recovery actions |

Report request IDs, timestamps, operation names, and results for the selected deal. Do not disclose keys. A simulated bank booking proves a simulation, not a real transfer.
