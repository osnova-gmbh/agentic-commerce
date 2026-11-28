-- Unknown references have no deal. Keep their credits, intents and postings
-- durable without manufacturing a commerce deal or assigning fake participants.
CREATE TABLE new_payment_intents (
    intent_id TEXT PRIMARY KEY,
    deal_id TEXT REFERENCES deal_deals(deal_id),
    kind TEXT NOT NULL CHECK (kind IN ('payout','fee','refund','return_unmatched')),
    amount_minor BIGINT NOT NULL CHECK (amount_minor >= 0),
    currency TEXT NOT NULL, to_iban TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('prepared','submitted','unknown','confirmed','failed')),
    bank_ref TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    CHECK (deal_id IS NOT NULL OR kind = 'return_unmatched')
);
INSERT INTO new_payment_intents SELECT * FROM deal_payment_intents;
DROP TABLE deal_payment_intents;
ALTER TABLE new_payment_intents RENAME TO deal_payment_intents;
CREATE UNIQUE INDEX deal_payment_intents_one_active_key ON deal_payment_intents(deal_id)
    WHERE kind IN ('payout','refund') AND status IN ('prepared','submitted','unknown');
CREATE INDEX deal_payment_intents_deal_idx ON deal_payment_intents(deal_id);

CREATE TABLE new_bank_credits (
    bank_event_id TEXT PRIMARY KEY,
    deal_id TEXT REFERENCES deal_deals(deal_id), reference TEXT NOT NULL,
    amount_minor BIGINT NOT NULL CHECK (amount_minor >= 0),
    from_iban TEXT NOT NULL, received_at TEXT NOT NULL,
    disposition TEXT NOT NULL CHECK (disposition IN ('funded','returned')),
    CHECK (deal_id IS NOT NULL OR disposition = 'returned')
);
INSERT INTO new_bank_credits SELECT * FROM deal_bank_credits;
DROP TABLE deal_bank_credits;
ALTER TABLE new_bank_credits RENAME TO deal_bank_credits;
CREATE INDEX deal_bank_credits_deal_idx ON deal_bank_credits(deal_id);

CREATE TABLE new_ledger_postings (
    posting_id TEXT PRIMARY KEY, deal_id TEXT REFERENCES deal_deals(deal_id),
    source_id TEXT NOT NULL,
    account TEXT NOT NULL CHECK (account IN ('held','seller','fee','buyer_refund','returned')),
    amount_minor BIGINT NOT NULL, created_at TEXT NOT NULL
);
INSERT INTO new_ledger_postings SELECT * FROM deal_ledger_postings;
DROP TABLE deal_ledger_postings;
ALTER TABLE new_ledger_postings RENAME TO deal_ledger_postings;
CREATE UNIQUE INDEX deal_ledger_postings_source_account_key ON deal_ledger_postings(source_id, account);
CREATE INDEX deal_ledger_postings_deal_idx ON deal_ledger_postings(deal_id);
