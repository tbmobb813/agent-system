-- Decision tracking and post-task reflections for agentic learning.
--
-- decisions: every model/tool/approach choice the agent makes, with confidence.
-- reflections: post-task self-evaluation stored after each completed run.
--
-- Reflections that contain generalizable rules are also promoted into the
-- `memory` table (category='pattern') by the reflection module so that the
-- existing context_builder pipeline retrieves them automatically.

CREATE TABLE IF NOT EXISTS decisions (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id         TEXT        NOT NULL,
    user_id         TEXT,
    decision_point  TEXT        NOT NULL,  -- 'model_selection' | 'tool_selection' | 'approach'
    options         JSONB,                 -- list of candidate options considered
    chosen          TEXT        NOT NULL,
    reasoning       TEXT,
    confidence      FLOAT       CHECK (confidence BETWEEN 0 AND 1),
    outcome         TEXT,                  -- 'success' | 'failure' | NULL (pending)
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_decisions_task_id       ON decisions(task_id);
CREATE INDEX IF NOT EXISTS idx_decisions_user_id       ON decisions(user_id);
CREATE INDEX IF NOT EXISTS idx_decisions_decision_point ON decisions(decision_point);
CREATE INDEX IF NOT EXISTS idx_decisions_created_at    ON decisions(created_at DESC);

CREATE TABLE IF NOT EXISTS reflections (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id         TEXT        NOT NULL UNIQUE,
    user_id         TEXT,
    query           TEXT,
    result_summary  TEXT,
    reflection_text TEXT,
    learned_rules   JSONB       DEFAULT '[]',
    self_rating     INTEGER     CHECK (self_rating BETWEEN 1 AND 10),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_reflections_task_id    ON reflections(task_id);
CREATE INDEX IF NOT EXISTS idx_reflections_user_id    ON reflections(user_id);
CREATE INDEX IF NOT EXISTS idx_reflections_created_at ON reflections(created_at DESC);
