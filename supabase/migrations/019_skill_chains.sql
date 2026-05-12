-- Skill chains: user-defined or auto-generated ordered tool sequences.
-- Each chain targets a task type; when the orchestrator detects a matching
-- query it injects the chain as a structured plan hint into the system prompt.
CREATE TABLE IF NOT EXISTS skill_chains (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name             TEXT        NOT NULL UNIQUE,
    description      TEXT,
    task_type        TEXT        NOT NULL,
    steps            JSONB       NOT NULL DEFAULT '[]',
    -- [{tool: str, description: str, hint: str|null}]
    trigger_keywords JSONB       NOT NULL DEFAULT '[]',
    success_rate     FLOAT,
    total_runs       INTEGER     NOT NULL DEFAULT 0,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_skill_chains_task_type  ON skill_chains(task_type);
CREATE INDEX IF NOT EXISTS idx_skill_chains_success    ON skill_chains(success_rate DESC NULLS LAST);
