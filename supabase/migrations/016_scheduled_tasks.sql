-- User-defined cron schedules → deferred agent runs (via orchestration queue).

CREATE TABLE IF NOT EXISTS scheduled_tasks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id TEXT,
    cron_expr TEXT NOT NULL,
    prompt TEXT NOT NULL,
    context TEXT,
    router_tier TEXT,
    max_iterations INTEGER DEFAULT 10,
    enabled BOOLEAN DEFAULT true,
    last_run_at TIMESTAMPTZ,
    next_run_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_scheduled_tasks_due
    ON scheduled_tasks (next_run_at)
    WHERE enabled = true;

COMMENT ON TABLE scheduled_tasks IS 'Cron-style prompts enqueued by OrchestrationRuntime user_cron_dispatch job';
