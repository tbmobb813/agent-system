-- Dead-letter rows for deferred worker failures (optional; gated by pillars error_handling.dead_letter.enabled)

CREATE TABLE IF NOT EXISTS failed_tasks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  task_id uuid REFERENCES tasks(id) ON DELETE SET NULL,
  error text NOT NULL,
  payload jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_failed_tasks_created_at ON failed_tasks (created_at DESC);

COMMENT ON TABLE failed_tasks IS 'Persists payload snapshot when deferred queue worker fails and dead_letter is enabled.';
