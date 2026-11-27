-- cogit-finance-deals: hash-chained deal log, outbox, deliveries, evaluations, payment
-- intents, bank credits and ledger postings (SPEC §11.4).
-- Written in the subset SQLite and PostgreSQL share. Objects are JSON text, timestamps
-- are YYYY-MM-DDTHH:MM:SSZ text, money is integer minor units.

CREATE TABLE deal_deals (
    deal_id       TEXT PRIMARY KEY,
    buyer_org_id  TEXT NOT NULL,
    seller_org_id TEXT NOT NULL,
    offer_id      TEXT NOT NULL,
    state         TEXT NOT NULL,
    head_seq      INTEGER NOT NULL CHECK (head_seq >= 1),
    head_hash     TEXT NOT NULL,
    terms         TEXT,
    terms_hash    TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE deal_events (
    deal_id           TEXT NOT NULL REFERENCES deal_deals (deal_id),
    seq               INTEGER NOT NULL CHECK (seq >= 1),
    prev_hash         TEXT NOT NULL,
    hash              TEXT NOT NULL,
    event_type        TEXT NOT NULL,
    source_message_id TEXT,
    actor_did         TEXT NOT NULL,
    body              TEXT NOT NULL,
    state_after       TEXT NOT NULL,
    recorded_at       TEXT NOT NULL,
    PRIMARY KEY (deal_id, seq)
);
CREATE UNIQUE INDEX deal_events_hash_key ON deal_events (hash);
-- One event per inbound message; events that E originates carry no message ID.
CREATE UNIQUE INDEX deal_events_source_message_key ON deal_events (source_message_id)
    WHERE source_message_id IS NOT NULL;

-- created_at and ordinal are not in SPEC §11.4: they give outbox.pending its
-- "oldest first" order without an engine-specific sequence.
CREATE TABLE deal_outbox (
    outbox_id  TEXT PRIMARY KEY,
    deal_id    TEXT NOT NULL REFERENCES deal_deals (deal_id),
    seq        INTEGER NOT NULL,
    envelope   TEXT NOT NULL,
    status     TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'sent')),
    sent_at    TEXT,
    created_at TEXT NOT NULL,
    ordinal    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX deal_outbox_pending_idx ON deal_outbox (created_at, deal_id, seq, ordinal)
    WHERE status = 'pending';

CREATE TABLE deal_deliveries (
    delivery_id  TEXT PRIMARY KEY,
    deal_id      TEXT NOT NULL REFERENCES deal_deals (deal_id),
    attempt      INTEGER NOT NULL CHECK (attempt >= 1),
    artifact_id  TEXT NOT NULL,
    sha256       TEXT NOT NULL,
    byte_length  BIGINT NOT NULL CHECK (byte_length >= 0),
    media_type   TEXT NOT NULL,
    delivered_at TEXT NOT NULL,
    status       TEXT NOT NULL
);
CREATE INDEX deal_deliveries_deal_idx ON deal_deliveries (deal_id, attempt);

-- deal_id is not in SPEC §11.4: it ties a request to its deal without a join.
CREATE TABLE deal_evaluations (
    evaluation_request_id TEXT PRIMARY KEY,
    deal_id               TEXT NOT NULL REFERENCES deal_deals (deal_id),
    delivery_id           TEXT NOT NULL,
    evaluator_id          TEXT NOT NULL,
    evaluator_version     INTEGER NOT NULL,
    evaluator_did         TEXT NOT NULL,
    respond_by            TEXT NOT NULL,
    resends               INTEGER NOT NULL DEFAULT 0 CHECK (resends >= 0),
    verdict_message_id    TEXT,
    outcome               TEXT CHECK (outcome IS NULL OR outcome IN ('pass', 'fail', 'error'))
);
CREATE INDEX deal_evaluations_deal_idx ON deal_evaluations (deal_id, delivery_id);

CREATE TABLE deal_payment_intents (
    intent_id    TEXT PRIMARY KEY,
    deal_id      TEXT NOT NULL REFERENCES deal_deals (deal_id),
    kind         TEXT NOT NULL CHECK (kind IN ('payout', 'fee', 'refund', 'return_unmatched')),
    amount_minor BIGINT NOT NULL CHECK (amount_minor >= 0),
    currency     TEXT NOT NULL,
    to_iban      TEXT NOT NULL,
    status       TEXT NOT NULL CHECK (status IN ('prepared', 'submitted', 'unknown', 'confirmed', 'failed')),
    bank_ref     TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
-- At most one active payout or refund per deal (SPEC §10.3).
CREATE UNIQUE INDEX deal_payment_intents_one_active_key ON deal_payment_intents (deal_id)
    WHERE kind IN ('payout', 'refund') AND status IN ('prepared', 'submitted', 'unknown');
CREATE INDEX deal_payment_intents_deal_idx ON deal_payment_intents (deal_id);

CREATE TABLE deal_bank_credits (
    bank_event_id TEXT PRIMARY KEY,
    deal_id       TEXT NOT NULL REFERENCES deal_deals (deal_id),
    reference     TEXT NOT NULL,
    amount_minor  BIGINT NOT NULL CHECK (amount_minor >= 0),
    from_iban     TEXT NOT NULL,
    received_at   TEXT NOT NULL,
    disposition   TEXT NOT NULL CHECK (disposition IN ('funded', 'returned'))
);
CREATE INDEX deal_bank_credits_deal_idx ON deal_bank_credits (deal_id);

CREATE TABLE deal_ledger_postings (
    posting_id   TEXT PRIMARY KEY,
    deal_id      TEXT NOT NULL REFERENCES deal_deals (deal_id),
    source_id    TEXT NOT NULL,
    account      TEXT NOT NULL CHECK (account IN ('held', 'seller', 'fee', 'buyer_refund', 'returned')),
    amount_minor BIGINT NOT NULL,
    created_at   TEXT NOT NULL
);
-- A source (payment intent or bank credit) posts to an account once.
CREATE UNIQUE INDEX deal_ledger_postings_source_account_key ON deal_ledger_postings (source_id, account);
CREATE INDEX deal_ledger_postings_deal_idx ON deal_ledger_postings (deal_id);
