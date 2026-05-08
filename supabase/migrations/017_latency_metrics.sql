-- Request latency samples (best-effort inserts from agent routes).

CREATE TABLE IF NOT EXISTS latency_metrics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    endpoint TEXT NOT NULL,
    duration_ms INTEGER NOT NULL,
    status TEXT NOT NULL,
    task_id TEXT,
    user_id TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_latency_metrics_endpoint_created
    ON latency_metrics (endpoint, created_at DESC);
