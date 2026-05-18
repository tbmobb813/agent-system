-- conversation_summary is a stale view created before the `archived` column
-- was added in 003_conversation_context.sql. No application code queries it;
-- the canonical table is `conversations`.
DROP VIEW IF EXISTS conversation_summary;
