-- Relax memory.user_id constraint for single-user personal agent.
-- Mirrors what migration 003 did for conversations.user_id.
-- The agent uses a plain text "default" user_id, not a UUID from the users table.

ALTER TABLE memory DISABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Users can view own memory" ON memory;
DROP POLICY IF EXISTS "Users can insert own memory" ON memory;
ALTER TABLE memory DROP CONSTRAINT IF EXISTS memory_user_id_fkey;
ALTER TABLE memory ALTER COLUMN user_id TYPE TEXT USING user_id::TEXT;
