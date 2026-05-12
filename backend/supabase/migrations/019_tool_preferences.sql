-- Per-tool acceptance/rejection tracking for implicit preference learning.
-- Counters are incremented each time a task using that tool receives thumbs-up/down feedback.
CREATE TABLE IF NOT EXISTS tool_preferences (
    user_id         TEXT        NOT NULL,
    tool_name       TEXT        NOT NULL,
    accepted_count  INTEGER     NOT NULL DEFAULT 0,
    rejected_count  INTEGER     NOT NULL DEFAULT 0,
    total_count     INTEGER     NOT NULL DEFAULT 0,
    acceptance_rate FLOAT       NOT NULL DEFAULT 0.5,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, tool_name)
);

CREATE INDEX IF NOT EXISTS idx_tool_preferences_user ON tool_preferences (user_id);
