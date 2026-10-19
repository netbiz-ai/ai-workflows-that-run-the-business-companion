-- The three small tables every recipe's n8n build uses, as the book defines them.
-- PostgreSQL; any hosted Postgres your n8n can reach works. One schema per company
-- if you build for several (book Chapter 2: one key log per client).
-- Keep all three for 13 months by default and write the period on each governance card
-- (book Chapter 3); delete older rows on a schedule.

-- Key log (book Chapter 2): the key column refuses a second copy in the same step
-- that reserves the key, which is what makes the write duplicate-safe.
CREATE TABLE IF NOT EXISTS key_log (
    recipe          text        NOT NULL,              -- recipe ID, such as 'R4.1'
    key             text        NOT NULL,              -- the idempotency key
    status          text        NOT NULL CHECK (status IN ('in progress', 'done', 'failed')),
    reserved_at     timestamptz NOT NULL DEFAULT now(),
    result          text,                              -- the write's result, or the failure
    record_created  text,                              -- the record in the system of record, if any
    copies_skipped  integer     NOT NULL DEFAULT 0,
    PRIMARY KEY (recipe, key)
);

-- Decision log (book Chapter 3): each item, what the workflow decided, which rules
-- passed or failed, who approved, and when. Never the item's confidential content.
CREATE TABLE IF NOT EXISTS decision_log (
    id           bigserial   PRIMARY KEY,
    recipe       text        NOT NULL,
    item         text        NOT NULL,                 -- the item's ID, never its content
    decision     text        NOT NULL,
    rules        jsonb       NOT NULL DEFAULT '{}',    -- rule name -> passed / failed / detail
    approved_by  text,
    decided_at   timestamptz NOT NULL DEFAULT now()
);

-- Exception queue (book Chapters 2 and 16): stuck items a named person works through.
CREATE TABLE IF NOT EXISTS exception_queue (
    id           bigserial   PRIMARY KEY,
    recipe       text        NOT NULL,
    item         text        NOT NULL,
    reason       text        NOT NULL,                 -- the reason code
    detail       text,
    owner        text,                                 -- the named person who works the queue
    status       text        NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'resolved')),
    created_at   timestamptz NOT NULL DEFAULT now(),
    resolved_at  timestamptz
);

-- Reserve a key: inserts and returns one row if the key is new; returns nothing if
-- it was already there, and counts the skipped copy. Used as one statement, so two
-- copies of an event arriving together cannot both get through.
--   WITH reserved AS (
--     INSERT INTO key_log (recipe, key, status) VALUES ($1, $2, 'in progress')
--     ON CONFLICT (recipe, key) DO NOTHING RETURNING key
--   ), skipped AS (
--     UPDATE key_log SET copies_skipped = copies_skipped + 1
--     WHERE recipe = $1 AND key = $2 AND NOT EXISTS (SELECT 1 FROM reserved)
--   )
--   SELECT (SELECT count(*) FROM reserved) = 1 AS is_new;
