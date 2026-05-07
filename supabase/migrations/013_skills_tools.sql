-- Phase 2 learning tables: skill registry, tool recommendations, error patterns.

-- skills: what task types the agent has demonstrated competence in.
-- Populated and refreshed by the background skill_registry.update_skills() job.
CREATE TABLE IF NOT EXISTS skills (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    task_type         TEXT        NOT NULL UNIQUE,
    skill_name        TEXT        NOT NULL,
    success_rate      FLOAT,
    total_uses        INTEGER     DEFAULT 0,
    proficiency_level TEXT,       -- 'novice' | 'competent' | 'expert'
    required_tools    JSONB       DEFAULT '[]',
    last_computed     TIMESTAMPTZ DEFAULT NOW(),
    created_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_skills_task_type      ON skills(task_type);
CREATE INDEX IF NOT EXISTS idx_skills_success_rate   ON skills(success_rate DESC);

-- tool_recommendations: most effective tool sequences per task type.
-- Updated by tool_learning.learn_tool_chains().
CREATE TABLE IF NOT EXISTS tool_recommendations (
    id                   UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    task_type            TEXT        NOT NULL UNIQUE,
    recommended_sequence JSONB       NOT NULL DEFAULT '[]',
    success_rate         FLOAT,
    sample_count         INTEGER     DEFAULT 0,
    updated_at           TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tool_rec_task_type ON tool_recommendations(task_type);

-- error_patterns: every classified API error logged for trend analysis.
-- Used to surface recovery hints and identify unreliable models/tools.
CREATE TABLE IF NOT EXISTS error_patterns (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    error_type          TEXT        NOT NULL,  -- FailoverReason value
    task_id             TEXT,
    model_used          TEXT,
    query_snippet       TEXT,
    recovery_strategy   TEXT,                  -- 'retry' | 'rotate_model' | 'compress' | 'abort'
    recovery_successful BOOLEAN,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_error_patterns_error_type  ON error_patterns(error_type);
CREATE INDEX IF NOT EXISTS idx_error_patterns_model       ON error_patterns(model_used);
CREATE INDEX IF NOT EXISTS idx_error_patterns_created_at  ON error_patterns(created_at DESC);
