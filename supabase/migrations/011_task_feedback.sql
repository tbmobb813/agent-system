-- Persist explicit user feedback on completed tasks and use it to improve
-- future responses through backend-managed memory promotion.

CREATE TABLE IF NOT EXISTS task_feedback (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    user_id TEXT,
    signal TEXT NOT NULL CHECK (signal IN ('up', 'down')),
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_task_feedback_task_id_created_at
    ON task_feedback (task_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_task_feedback_user_id
    ON task_feedback (user_id);

ALTER TABLE task_feedback ENABLE ROW LEVEL SECURITY;

-- Intentionally no public policies. Backend-only writes/reads via direct DB access.