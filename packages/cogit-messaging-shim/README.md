# cogit-messaging-shim

In-repo stand-in for the messaging seam of SPEC §11.2. It has the same `send()` signature
and the same claim, admit, acknowledge loop as the planned SDK contract and runtime
extension, so agents switch to the framework version by changing one import.

| Module | Content |
| --- | --- |
| `canonical` | Canonical JSON, `terms_hash`, deal event hash |
| `keys` | Local `did:key` (Ed25519) identities; seed files under `.state/keys/` |
| `envelope` | Build, sign and verify the SPEC §6.1 envelope |
| `seams` | `MessagingSeams` protocol, `ShimMessaging`, `send_envelope` |
| `loop` | `DeliveryLoop`: the delivery loop of SPEC §7 (steps 1, 2 and 5) |
| `testing` | `RecordingMessaging` test double; `LocalBus`, the module, keys and loops in one process |

## Delivery loop

```python
loop = DeliveryLoop(installation_id, modules, work)   # ModulePort, WorkPort
handled = loop.run_once()
```

One pass claims the installation's due messages (`message.claim`) and settles each:

1. A bad signature is acknowledged `rejected` with reason `bad_signature` and never admitted.
2. The message is admitted as `handle_message` with input `{"envelope": …}` and the
   idempotency key `msg:<message_id>`. A message claimed again after a crash therefore
   gets the run that already exists.
3. A succeeded run whose output has `status == "rejected"` is acknowledged `rejected`
   with its `reason`; any other succeeded run is acknowledged `processed`. Both record
   the `run_id`.
4. A failed run, or a host that could not take the work, releases the message for a retry
   after `release_delay_s`.

Not in the demo: the 24 h replay window, a command-line entry point, HTTP routes.

## LocalBus

`cogit_messaging_shim.testing.LocalBus` needs the `cogit-messaging-module` package
(`modules/cogit-messaging`), which it imports only when it is constructed.

```python
bus = LocalBus()                                  # .host, .runtime, .artifacts
buyer = bus.add_agent("buyer-agent", "buyer-co", "buyer")       # AgentKey; identity.register
escrow = bus.add_agent("cogit-finance", "operator-co", "escrow")
bus.register_finance_types("contracts")           # every contracts/messages/finance.*.v1.json
bus.runtime.register("cogit-finance", escrow_agent)             # object with handle_message(envelope)
bus.messaging("buyer-agent").send("finance.accept_terms", 1, escrow.did, deal_id, body)
bus.pump()                                        # every loop, until a round handles nothing
```

`pump` skips installations that have no agent in `bus.runtime`; their messages stay queued.

## Tests

From the repository root, after `scripts/dev-install.sh`:

```sh
scripts/test.sh packages/cogit-messaging-shim
```

`tests/contract/` holds the black-box tests of `send()` and the loop. They use only the
`env` fixture of `tests/contract/conftest.py`; a port into the SDK and runtime
re-implements that fixture and must pass the test files unchanged.
