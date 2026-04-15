-- Relax user_id constraints on tasks for single-user personal agent.
-- Matches what was already done for conversations (003) and memory (006).
-- The agent runs without a users table row — user_id is informational only.

ALTER TABLE tasks DISABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Users can view own tasks" ON tasks;
DROP POLICY IF EXISTS "Users can insert own tasks" ON tasks;
DROP POLICY IF EXISTS "Users can update own tasks" ON tasks;
ALTER TABLE tasks DROP CONSTRAINT IF EXISTS tasks_user_id_fkey;
ALTER TABLE tasks ALTER COLUMN user_id DROP NOT NULL;
ALTER TABLE tasks ALTER COLUMN user_id TYPE TEXT USING user_id::TEXT;
