-- A/B test results table for Phase 3 cost-quality optimization.
--
-- Stores the outcome of running the same task against two different
-- configurations (different system prompts, models, or tool sets).
-- Populated by the ab_testing module; queried by /analytics/ab-tests.

CREATE TABLE IF NOT EXISTS ab_tests (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    task_description TEXT       NOT NULL,
    approach_a      JSONB       NOT NULL DEFAULT '{}',  -- {model, system_prompt_tag, tools}
    approach_b      JSONB       NOT NULL DEFAULT '{}',
    result_a        JSONB       DEFAULT '{}',           -- {cost, tokens, time_ms, success, output_preview}
    result_b        JSONB       DEFAULT '{}',
    winner          TEXT,                               -- 'a' | 'b' | 'tie' | NULL (pending)
    win_reason      TEXT,                               -- 'cost' | 'quality' | 'speed'
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ab_tests_created_at ON ab_tests(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ab_tests_winner     ON ab_tests(winner);
