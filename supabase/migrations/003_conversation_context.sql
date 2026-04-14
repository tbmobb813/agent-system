-- Migration 003: Relax user_id constraints for single-user personal agent
-- The conversations table originally required a FK to the users table.
-- For a personal agent without full auth, we change user_id to TEXT.

-- Drop the view that depends on user_id, alter column, then recreate
DROP VIEW IF EXISTS conversation_summary;

ALTER TABLE conversations
    DROP CONSTRAINT IF EXISTS conversations_user_id_fkey;

ALTER TABLE conversations
    ALTER COLUMN user_id TYPE TEXT USING user_id::TEXT;

-- Recreate the view with the same logic
CREATE OR REPLACE VIEW conversation_summary AS
SELECT
    c.id,
    c.user_id,
    c.thread_id,
    COUNT(m.id) as message_count,
    COALESCE(SUM(m.tokens), 0) as total_tokens,
    c.created_at,
    c.updated_at
FROM conversations c
LEFT JOIN messages m ON c.id = m.conversation_id
GROUP BY c.id;

-- Add updated_at trigger helper (if not already present)
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

DROP TRIGGER IF EXISTS update_conversations_updated_at ON conversations;
CREATE TRIGGER update_conversations_updated_at
    BEFORE UPDATE ON conversations
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
