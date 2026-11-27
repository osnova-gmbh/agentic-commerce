-- cogit-messaging: agent identities, message type registry and message queue (SPEC §11.1).
-- Written in the subset SQLite and PostgreSQL share. JSON is stored as TEXT, booleans as
-- INTEGER 0/1 and timestamps as 'YYYY-MM-DDTHH:MM:SSZ' TEXT, which sorts chronologically.

CREATE TABLE msg_agent_identities (
    did             TEXT PRIMARY KEY,
    installation_id TEXT NOT NULL,
    org_id          TEXT NOT NULL,
    role            TEXT NOT NULL CHECK (role IN ('buyer', 'seller', 'evaluator', 'escrow')),
    active          INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    registered_at   TEXT NOT NULL
);

CREATE INDEX msg_agent_identities_installation_idx ON msg_agent_identities (installation_id);

-- Immutable per (type_key, type_version); json_schema holds canonical JSON text.
CREATE TABLE msg_message_types (
    type_key      TEXT NOT NULL,
    type_version  INTEGER NOT NULL CHECK (type_version >= 1),
    json_schema   TEXT NOT NULL,
    registered_by TEXT NOT NULL,
    registered_at TEXT NOT NULL,
    PRIMARY KEY (type_key, type_version)
);

-- seq is the insertion order (timestamps have whole seconds only). available_at is when a
-- queued message may be claimed; message.release moves it into the future.
CREATE TABLE msg_messages (
    message_id      TEXT PRIMARY KEY,
    seq             INTEGER NOT NULL,
    conversation_id TEXT NOT NULL,
    causation_id    TEXT,
    type_key        TEXT NOT NULL,
    type_version    INTEGER NOT NULL,
    sender_did      TEXT NOT NULL,
    recipient_did   TEXT NOT NULL,
    envelope        TEXT NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('queued', 'claimed', 'processed', 'rejected', 'dead')),
    attempts        INTEGER NOT NULL DEFAULT 0,
    available_at    TEXT NOT NULL,
    claimed_at      TEXT,
    admission_key   TEXT,
    run_id          TEXT,
    reason          TEXT,
    created_at      TEXT NOT NULL,
    acked_at        TEXT,
    FOREIGN KEY (type_key, type_version) REFERENCES msg_message_types (type_key, type_version)
);

CREATE UNIQUE INDEX msg_messages_seq_idx ON msg_messages (seq);

CREATE INDEX msg_messages_conversation_idx ON msg_messages (conversation_id, seq);

CREATE INDEX msg_messages_inbox_idx ON msg_messages (recipient_did, seq) WHERE status IN ('queued', 'claimed');
