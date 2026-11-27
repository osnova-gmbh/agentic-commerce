-- cogit-finance-catalog: companies, offers and evaluators (SPEC §11.3).
-- Written in the subset SQLite and PostgreSQL share. Lists and objects are JSON text,
-- booleans are 0 or 1, money is integer minor units.

CREATE TABLE cat_companies (
    org_id               TEXT PRIMARY KEY,
    legal_name           TEXT NOT NULL,
    register_id          TEXT,
    address              TEXT,
    roles                TEXT NOT NULL DEFAULT '[]',
    categories           TEXT NOT NULL DEFAULT '[]',
    iban                 TEXT,
    kyb_verified         INTEGER NOT NULL DEFAULT 0 CHECK (kyb_verified IN (0, 1)),
    kyb_verified_by      TEXT,
    spending_limit_minor BIGINT NOT NULL DEFAULT 0 CHECK (spending_limit_minor >= 0)
);

CREATE TABLE cat_offers (
    seller_org_id      TEXT NOT NULL,
    offer_id           TEXT NOT NULL,
    title              TEXT NOT NULL,
    description        TEXT,
    category           TEXT NOT NULL,
    price_minor        BIGINT NOT NULL CHECK (price_minor >= 0),
    currency           TEXT NOT NULL,
    delivery_time_s    INTEGER NOT NULL CHECK (delivery_time_s >= 0),
    input_schema       TEXT NOT NULL DEFAULT '{}',
    deliverable        TEXT NOT NULL DEFAULT '{}',
    default_acceptance TEXT NOT NULL DEFAULT '{}',
    active             INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    PRIMARY KEY (seller_org_id, offer_id)
);

CREATE TABLE cat_evaluators (
    evaluator_id  TEXT NOT NULL,
    version       INTEGER NOT NULL CHECK (version >= 1),
    org_id        TEXT NOT NULL,
    did           TEXT,
    description   TEXT,
    deterministic INTEGER NOT NULL DEFAULT 0 CHECK (deterministic IN (0, 1)),
    accepts       TEXT NOT NULL DEFAULT '[]',
    params_schema TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (evaluator_id, version)
);
