-- Link each task row to its conversation thread.
-- Populated on task completion from the orchestrator's DONE event.

ALTER TABLE tasks ADD COLUMN IF NOT EXISTS conversation_id TEXT;

CREATE INDEX IF NOT EXISTS idx_tasks_conversation_id
    ON tasks (conversation_id)
    WHERE conversation_id IS NOT NULL;

COMMENT ON COLUMN tasks.conversation_id IS
    'Groups multiple task rows that belong to the same chat session thread.';
