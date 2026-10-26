-- The test stack's table API role: PostgREST serves the key log, decision log and
-- exception queue as this role, which can read, add and update rows and call the
-- key-log functions in schema.sql, but never delete a row itself. For your own deployment, give the API real authentication
-- (PostgREST JWT roles, or your platform's equivalent); this role has none.
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'web_anon') THEN CREATE ROLE web_anon NOLOGIN; END IF;
END $$;
GRANT USAGE ON SCHEMA public TO web_anon;
GRANT SELECT, INSERT, UPDATE ON key_log, decision_log, exception_queue TO web_anon;
GRANT USAGE ON SEQUENCE decision_log_id_seq, exception_queue_id_seq TO web_anon;
GRANT EXECUTE ON FUNCTION reserve_key(text, text, boolean), reserve_keys(text, text[]), finish_keys(text, text[], text, text),
  release_key(text, text), release_keys_for(text, text), add_exception_once(text, text, text, text, text) TO web_anon;
GRANT web_anon TO companion;
