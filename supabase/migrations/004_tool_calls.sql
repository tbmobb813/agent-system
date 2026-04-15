-- Tool calls table — structured per-call logging for the ReAct loop.
-- Enables: debugging, loop detection, per-run token accounting, audit trail.

CREATE TABLE IF NOT EXISTS tool_calls (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id       TEXT        NOT NULL,
    conversation_id TEXT,
    iteration     INTEGER     NOT NULL,
    tool_name     TEXT        NOT NULL,
    input_json    JSONB,
    output_text   TEXT,
    error         TEXT,
    duration_ms   INTEGER,
    truncated     BOOLEAN     DEFAULT FALSE,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tool_calls_task    ON tool_calls(task_id);
CREATE INDEX IF NOT EXISTS idx_tool_calls_conv    ON tool_calls(conversation_id);
CREATE INDEX IF NOT EXISTS idx_tool_calls_created ON tool_calls(created_at DESC);
