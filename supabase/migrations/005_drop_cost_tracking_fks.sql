-- Drop FK constraints on cost_tracking so cost records can be inserted
-- without requiring a corresponding tasks/users row.
-- This allows the /agent/run sync endpoint and Telegram bot to track costs
-- without pre-inserting a task row.

ALTER TABLE cost_tracking DROP CONSTRAINT IF EXISTS cost_tracking_task_id_fkey;
ALTER TABLE cost_tracking DROP CONSTRAINT IF EXISTS cost_tracking_user_id_fkey;

-- Drop the on_cost_insert trigger — it tries to aggregate into cost_summary_daily
-- which requires non-null user_id. CostTracker queries cost_tracking directly.
DROP TRIGGER IF EXISTS trigger_cost_insert ON cost_tracking;
