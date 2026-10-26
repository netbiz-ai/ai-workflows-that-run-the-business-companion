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

-- The key-log steps as functions, for a platform that reaches these tables over a
-- table API instead of a database connection (the Make builds call them through
-- PostgREST as POST /rpc/<name> with named arguments). Each does one narrow thing,
-- so the API's role can call them without the right to delete rows itself.

-- Reserve a key: true for a new key, false for a copy (the copy is counted).
-- p_reopen_done: a key whose earlier run is done may be reserved again (R9.3: a
-- closed request may be asked again; an open one may not).
DROP FUNCTION IF EXISTS reserve_key(text, text);
CREATE OR REPLACE FUNCTION reserve_key(p_recipe text, p_key text, p_reopen_done boolean DEFAULT false) RETURNS boolean
LANGUAGE sql AS $f$
  WITH reserved AS (
    INSERT INTO key_log (recipe, key, status) VALUES (p_recipe, p_key, 'in progress')
    ON CONFLICT (recipe, key) DO UPDATE SET status = 'in progress', result = NULL, reserved_at = now()
      WHERE p_reopen_done AND key_log.status = 'done'
    RETURNING key
  ), skipped AS (
    UPDATE key_log SET copies_skipped = copies_skipped + 1
    WHERE recipe = p_recipe AND key = p_key AND NOT EXISTS (SELECT 1 FROM reserved)
  )
  SELECT (SELECT count(*) FROM reserved) = 1
$f$;

-- Reserve several keys in one step; returns the keys that were new.
CREATE OR REPLACE FUNCTION reserve_keys(p_recipe text, p_keys text[]) RETURNS SETOF text
LANGUAGE sql AS $f$
  WITH input AS (SELECT DISTINCT unnest(p_keys) AS key),
  reserved AS (
    INSERT INTO key_log (recipe, key, status) SELECT p_recipe, key, 'in progress' FROM input
    ON CONFLICT (recipe, key) DO NOTHING RETURNING key
  ), skipped AS (
    UPDATE key_log SET copies_skipped = copies_skipped + 1
    WHERE recipe = p_recipe AND key IN (SELECT key FROM input) AND key NOT IN (SELECT key FROM reserved)
  )
  SELECT key FROM reserved
$f$;

-- Mark several keys done or failed in one step.
CREATE OR REPLACE FUNCTION finish_keys(p_recipe text, p_keys text[], p_status text, p_result text) RETURNS integer
LANGUAGE sql AS $f$
  WITH done AS (
    UPDATE key_log SET status = p_status, result = p_result WHERE recipe = p_recipe AND key = ANY (p_keys) RETURNING 1
  ) SELECT count(*)::int FROM done
$f$;

-- Release a key, so the same item runs again (nothing was written for it).
CREATE OR REPLACE FUNCTION release_key(p_recipe text, p_key text) RETURNS boolean
LANGUAGE sql SECURITY DEFINER SET search_path = public AS $f$
  WITH gone AS (DELETE FROM key_log WHERE recipe = p_recipe AND key = p_key RETURNING 1)
  SELECT count(*) > 0 FROM gone
$f$;

-- Release every key of one item, written as '<item>:<rest>' (R7.3: a call-back closes a hold).
CREATE OR REPLACE FUNCTION release_keys_for(p_recipe text, p_item text) RETURNS integer
LANGUAGE sql SECURITY DEFINER SET search_path = public AS $f$
  WITH gone AS (DELETE FROM key_log WHERE recipe = p_recipe AND left(key, length(p_item) + 1) = p_item || ':' RETURNING 1)
  SELECT count(*)::int FROM gone
$f$;

-- Add an exception-queue row unless the item already has an open one; true if added.
CREATE OR REPLACE FUNCTION add_exception_once(p_recipe text, p_item text, p_reason text, p_detail text, p_owner text) RETURNS boolean
LANGUAGE sql AS $f$
  WITH added AS (
    INSERT INTO exception_queue (recipe, item, reason, detail, owner)
    SELECT p_recipe, p_item, p_reason, p_detail, p_owner
    WHERE NOT EXISTS (SELECT 1 FROM exception_queue WHERE recipe = p_recipe AND item = p_item AND status = 'open')
    RETURNING 1
  ) SELECT count(*) > 0 FROM added
$f$;
