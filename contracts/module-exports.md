# Module exports (demo v0)

Frozen contract for the three modules. Export names come from SPEC §11; arguments and
results are JSON objects with the fields below. Kind is `query` (read only) or `command`
(runs in one transaction, needs an idempotency key). Errors are raised as
`ModuleError(code)` in the reference implementation; the codes are part of the contract.

Contract ID of an export: `<module>.<export>.v1`, e.g. `cogit-messaging.message.send.v1`.
Timestamps are `YYYY-MM-DDTHH:MM:SSZ`. Money is integer minor units. `?` marks an optional
argument.

Caller: every export receives the calling installation and its principal
(`installation`, `operator`, `operator_ro`). "E" is the installation named by the module
setting `escrow_installation_id` (`cogit-finance`).

## cogit-messaging

Settings: `escrow_installation_id`, `redeliver_after_s` (30), `max_delivery_attempts` (5).

| Export | Kind | Caller | Arguments → result | Errors |
| --- | --- | --- | --- | --- |
| `identity.register` | command | operator | `did`, `installation_id`, `org_id`, `role` (`buyer`, `seller`, `evaluator`, `escrow`) → `{did}`. Upsert | `forbidden` |
| `identity.resolve` | query | any | `did`, or `role` with optional `org_id` → `{identity}`: the active row or null (the oldest match for a role) | |
| `type.register` | command | E | `type_key`, `type_version`, `json_schema` → `{status}`: `created` or `unchanged` | `forbidden`, `type_conflict` (same key and version, different bytes), `unsupported_schema` (keyword outside the SPEC §6.1 dialect) |
| `message.send` | command | any installation | `envelope` → `{message_id, status}`: `queued` or `duplicate` | `invalid_envelope`, `not_your_did` (sender DID is not bound to the caller), `unknown_recipient`, `unknown_type`, `invalid_body` |
| `message.claim` | command | any installation | `limit?` (10) → `{messages: [{message_id, envelope, attempts}]}` | |
| `message.ack` | command | recipient's installation | `message_id`, `outcome` (`processed`, `rejected`), `reason?`, `run_id?` → `{}`. Repeating it is harmless | `unknown_message`, `not_your_message` |
| `message.release` | command | recipient's installation | `message_id`, `delay_s?` (0) → `{}` | `unknown_message`, `not_your_message` |
| `conversation.read` | query | any (demo) | `conversation_id` → `{messages: [{message_id, type_key, type_version, sender_did, recipient_did, causation_id, status, reason, attempts, run_id, created_at, acked_at, envelope}]}` in insertion order | |

- Identity row: `did`, `installation_id`, `org_id`, `role`, `active`, `registered_at`.
- `message.send` stores the envelope verbatim, checks no signature (SPEC §6.2) and is
  idempotent on `message_id`: the same ID returns `duplicate` and changes nothing.
- `message.claim` returns messages whose recipient DID is bound to the caller and that are
  `queued` and due, or `claimed` longer than `redeliver_after_s` ago. It sets `claimed`,
  `claimed_at` and `attempts + 1`. Oldest first.
- `message.release` returns a claimed message to `queued`, due after `delay_s`.
- Message status: `queued`, `claimed`, `processed`, `rejected`, `dead`.

## cogit-finance-catalog

| Export | Kind | Caller | Arguments → result | Errors |
| --- | --- | --- | --- | --- |
| `company.upsert` | command | operator | `company` → `{org_id}` | `forbidden` |
| `company.read` | query | any | `org_id` → `{company}`: the row or null. Demo addition; E needs it for its guards | |
| `companies.list` | query | any | `role?` (`buyer` or `seller`) → `{companies: [company]}`, sorted by `org_id` | `invalid_argument` |
| `evaluator.upsert` | command | operator | `evaluator` → `{evaluator_id, version}` | `forbidden` |
| `catalog.publish` | command | any installation (demo) | `seller_org_id`, `offers` → `{count}`. Replaces that seller's offers | `unknown_seller` (no company with role `seller`) |
| `sellers.list` | query | any | `category?` → `{sellers: [company]}`: companies with role `seller` (and that category), sorted by `org_id` | |
| `catalog.read` | query | any | `seller_org_id` → `{offers: [offer]}`, sorted by `offer_id` | |
| `evaluators.list` | query | any | none → `{evaluators: [evaluator]}`, sorted by `evaluator_id`, `version` | |

- Company: `org_id`, `legal_name`, `register_id`, `address`, `roles` (list), `categories`
  (list), `iban`, `kyb_verified` (bool), `kyb_verified_by`, `spending_limit_minor`,
  `profile` (optional object, defaults to `{}`; public company descriptions).
- Offer: `seller_org_id`, `offer_id`, `title`, `description`, `category`, `price_minor`,
  `currency`, `delivery_time_s`, `input_schema`, `deliverable` (`media_type`,
  `required_files`), `default_acceptance` (`evaluators`, `policy`, `max_attempts`), `active`.
- Evaluator: `evaluator_id`, `version`, `org_id`, `did`, `description`, `deterministic`
  (bool), `accepts` (media types), `params_schema`.
- An empty catalog returns empty lists.

## cogit-finance-deals

All commands are E's only (`forbidden` otherwise). Queries are open in the demo.

| Export | Kind | Arguments → result | Errors |
| --- | --- | --- | --- |
| `deal.commit` | command | see below → `{seq, hash, duplicate}` | `head_mismatch`, `bad_event`, `intent_conflict`, `duplicate_credit` |
| `outbox.pending` | query | `limit?` (50) → `{entries: [{outbox_id, deal_id, seq, envelope}]}`, oldest first | |
| `outbox.mark_sent` | command | `outbox_id` → `{}`. Repeating it is harmless | |
| `intent.update` | command | `intent_id`, `status`, `bank_ref?`, `postings?` → `{}`. Postings are written in the same transaction; an existing `source_id` + `account` is skipped | `unknown_intent` |
| `deal.read` | query | `deal_id` → `{deal, events, deliveries, evaluations, intents, credits}`; `deal` is null and the lists are empty for an unknown deal | |
| `deal.list` | query | none → `{deals: [{deal_id, state, buyer_org_id, seller_org_id, offer_id, head_seq, price_minor, currency, created_at, updated_at}]}`, newest first. `price_minor` and `currency` come from the terms and are null before them | |
| `ledger.balances` | query | `deal_id?` → `{held, seller, fee, buyer_refund, returned}`: sums of the postings, 0 when none | |

`deal.commit` arguments:

```json
{
  "deal_id": "…", "expected_seq": 0, "expected_hash": "000…0",
  "event": {"seq": 1, "prev_hash": "000…0", "hash": "…", "event_type": "service_request",
            "source_message_id": "… or null", "actor_did": "did:key:…", "body": {}, "state_after": "REQUESTED"},
  "deal": {"buyer_org_id": "…", "seller_org_id": "…", "offer_id": "…", "terms": null, "terms_hash": null},
  "outbox": [{"outbox_id": "…", "envelope": {}}],
  "deliveries": [{"delivery_id": "…", "attempt": 1, "artifact_id": "…", "sha256": "…", "byte_length": 1, "media_type": "…", "delivered_at": "…", "status": "delivered"}],
  "evaluations": [{"evaluation_request_id": "…", "delivery_id": "…", "evaluator_id": "…", "evaluator_version": 1, "evaluator_did": "…", "respond_by": "…", "resends": 0, "verdict_message_id": null, "outcome": null}],
  "intents": [{"intent_id": "…", "kind": "payout", "amount_minor": 1, "currency": "EUR", "to_iban": "…", "status": "prepared"}],
  "credits": [{"bank_event_id": "…", "reference": "…", "amount_minor": 1, "from_iban": "…", "received_at": "…", "disposition": "funded"}],
  "postings": [{"posting_id": "…", "source_id": "…", "account": "held", "amount_minor": 1}]
}
```

Only `deal_id`, `expected_seq`, `expected_hash` and `event` are required. Rules, in order:

1. If `event.source_message_id` is already recorded, return that event's `seq` and `hash`
   with `duplicate: true` and write nothing.
2. The deal head must equal `expected_seq` and `expected_hash`. A new deal has head 0 and
   64 zeros and needs `deal` with `buyer_org_id`, `seller_org_id`, `offer_id`. Otherwise
   `head_mismatch`.
3. `event.seq` = `expected_seq + 1` and `event.prev_hash` = `expected_hash`, else
   `bad_event`. E computes `event.hash` (`cogit_messaging_shim.event_hash`); the module
   stores it and keeps it unique.
4. Write the event, set the deal's `state` to `state_after`, move the head, apply `deal`
   fields that are present (`terms`, `terms_hash`), insert the outbox entries (status
   `pending`), upsert `deliveries` and `evaluations` by their ID, insert `intents`,
   `credits` and `postings`. All in one transaction.
5. A second active (`prepared`, `submitted`, `unknown`) `payout` or `refund` intent for a
   deal fails with `intent_conflict`. A known `bank_event_id` fails with `duplicate_credit`.

- Deal row: `deal_id`, `buyer_org_id`, `seller_org_id`, `offer_id`, `state`, `head_seq`,
  `head_hash`, `terms`, `terms_hash`, `created_at`, `updated_at`.
- Event row: `deal_id`, `seq`, `prev_hash`, `hash`, `event_type`, `source_message_id`,
  `actor_did`, `body`, `state_after`, `recorded_at`.
- Intent row: the inserted fields plus `deal_id`, `bank_ref`, `created_at`, `updated_at`.
  Kinds: `payout`, `fee`, `refund`, `return_unmatched`. Status: `prepared`, `submitted`,
  `unknown`, `confirmed`, `failed`.
- Posting accounts: `held`, `seller`, `fee`, `buyer_refund`, `returned`. Amounts are signed.
  Bank credit → `held` +price. Payout intent → `held` −payout and `seller` +payout. Fee
  intent → `held` −fee and `fee` +fee.
