-- 002_cost_tracking.sql
-- Cost tracking and budget management tables

-- Cost tracking table
CREATE TABLE IF NOT EXISTS cost_tracking (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    task_id UUID REFERENCES tasks(id) ON DELETE SET NULL,
    model TEXT NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cost DECIMAL(10, 6) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_cost_tracking_user_id ON cost_tracking(user_id);
CREATE INDEX idx_cost_tracking_task_id ON cost_tracking(task_id);
CREATE INDEX idx_cost_tracking_created_at ON cost_tracking(created_at);
CREATE INDEX idx_cost_tracking_model ON cost_tracking(model);

-- Monthly cost summary (materialized for performance)
CREATE TABLE IF NOT EXISTS cost_summary_monthly (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    month DATE NOT NULL,
    total_cost DECIMAL(10, 4),
    total_input_tokens BIGINT,
    total_output_tokens BIGINT,
    call_count INTEGER,
    last_updated TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id, month)
);

CREATE INDEX idx_cost_summary_user_month ON cost_summary_monthly(user_id, month);

-- Daily cost tracking (for daily limits/alerts)
CREATE TABLE IF NOT EXISTS cost_summary_daily (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    total_cost DECIMAL(10, 4),
    call_count INTEGER,
    last_updated TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id, date)
);

CREATE INDEX idx_cost_summary_daily_user ON cost_summary_daily(user_id, date);

-- Budget alerts
CREATE TABLE IF NOT EXISTS budget_alerts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    alert_type TEXT NOT NULL, -- '80_percent', '95_percent', 'exceeded'
    alert_message TEXT,
    spent DECIMAL(10, 4),
    budget DECIMAL(10, 4),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    acknowledged BOOLEAN DEFAULT false
);

CREATE INDEX idx_budget_alerts_user_id ON budget_alerts(user_id);
CREATE INDEX idx_budget_alerts_created_at ON budget_alerts(created_at);

-- Cost by model (for analytics)
CREATE OR REPLACE VIEW cost_by_model_monthly AS
SELECT
    user_id,
    DATE_TRUNC('month', created_at)::DATE as month,
    model,
    COUNT(*) as calls,
    SUM(input_tokens) as total_input_tokens,
    SUM(output_tokens) as total_output_tokens,
    SUM(cost) as total_cost
FROM cost_tracking
GROUP BY user_id, DATE_TRUNC('month', created_at), model
ORDER BY user_id, month DESC, total_cost DESC;

-- Cost trend (daily)
CREATE OR REPLACE VIEW cost_trend_daily AS
SELECT
    user_id,
    DATE(created_at) as date,
    COUNT(*) as calls,
    SUM(cost) as total_cost,
    AVG(cost) as avg_cost
FROM cost_tracking
GROUP BY user_id, DATE(created_at)
ORDER BY user_id, date DESC;

-- Function to update monthly summary
CREATE OR REPLACE FUNCTION update_cost_summary_monthly()
RETURNS VOID AS $$
DECLARE
    v_user_id UUID;
    v_month DATE;
BEGIN
    -- Get distinct user/month combinations from recent costs
    FOR v_user_id, v_month IN
        SELECT DISTINCT user_id, DATE_TRUNC('month', created_at)::DATE
        FROM cost_tracking
        WHERE created_at > NOW() - INTERVAL '7 days'
    LOOP
        INSERT INTO cost_summary_monthly (user_id, month, total_cost, total_input_tokens, total_output_tokens, call_count)
        SELECT
            v_user_id,
            v_month,
            SUM(cost),
            SUM(input_tokens),
            SUM(output_tokens),
            COUNT(*)
        FROM cost_tracking
        WHERE user_id = v_user_id
            AND DATE_TRUNC('month', created_at)::DATE = v_month
        ON CONFLICT (user_id, month) DO UPDATE SET
            total_cost = EXCLUDED.total_cost,
            total_input_tokens = EXCLUDED.total_input_tokens,
            total_output_tokens = EXCLUDED.total_output_tokens,
            call_count = EXCLUDED.call_count,
            last_updated = NOW();
    END LOOP;
END;
$$ LANGUAGE plpgsql;

-- Function to check budget and create alerts
CREATE OR REPLACE FUNCTION check_budget_alerts()
RETURNS VOID AS $$
DECLARE
    v_user_id UUID;
    v_spent DECIMAL;
    v_budget DECIMAL;
    v_percent FLOAT;
BEGIN
    -- Check each user's spending
    FOR v_user_id, v_spent, v_budget IN
        SELECT
            u.id,
            COALESCE(SUM(ct.cost), 0),
            COALESCE(us.max_monthly_cost, 30.0)
        FROM users u
        LEFT JOIN cost_tracking ct ON u.id = ct.user_id
            AND DATE_TRUNC('month', ct.created_at)::DATE = DATE_TRUNC('month', NOW())::DATE
        LEFT JOIN user_settings us ON u.id = us.user_id
        GROUP BY u.id, us.max_monthly_cost
    LOOP
        v_percent := (v_spent / v_budget) * 100;

        -- Check 95% threshold
        IF v_percent >= 95 THEN
            INSERT INTO budget_alerts (user_id, alert_type, alert_message, spent, budget)
            VALUES (
                v_user_id,
                '95_percent',
                FORMAT('Budget at 95%%: $%.2f of $%.2f', v_spent, v_budget),
                v_spent,
                v_budget
            )
            ON CONFLICT DO NOTHING;
        END IF;

        -- Check 80% threshold
        IF v_percent >= 80 AND v_percent < 95 THEN
            INSERT INTO budget_alerts (user_id, alert_type, alert_message, spent, budget)
            VALUES (
                v_user_id,
                '80_percent',
                FORMAT('Budget at 80%%: $%.2f of $%.2f', v_spent, v_budget),
                v_spent,
                v_budget
            )
            ON CONFLICT DO NOTHING;
        END IF;

        -- Check exceeded
        IF v_spent > v_budget THEN
            INSERT INTO budget_alerts (user_id, alert_type, alert_message, spent, budget)
            VALUES (
                v_user_id,
                'exceeded',
                FORMAT('Budget EXCEEDED: $%.2f of $%.2f', v_spent, v_budget),
                v_spent,
                v_budget
            )
            ON CONFLICT DO NOTHING;
        END IF;
    END LOOP;
END;
$$ LANGUAGE plpgsql;

-- Trigger to update summaries and check alerts after cost insertion
CREATE OR REPLACE FUNCTION on_cost_insert()
RETURNS TRIGGER AS $$
BEGIN
    -- Update daily summary
    INSERT INTO cost_summary_daily (user_id, date, total_cost, call_count)
    SELECT
        NEW.user_id,
        DATE(NOW()),
        SUM(cost),
        COUNT(*)
    FROM cost_tracking
    WHERE user_id = NEW.user_id AND DATE(created_at) = DATE(NOW())
    ON CONFLICT (user_id, date) DO UPDATE SET
        total_cost = EXCLUDED.total_cost,
        call_count = EXCLUDED.call_count,
        last_updated = NOW();

    -- Check budget
    PERFORM check_budget_alerts();

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_cost_insert
AFTER INSERT ON cost_tracking
FOR EACH ROW
EXECUTE FUNCTION on_cost_insert();

-- RLS for cost tracking
ALTER TABLE cost_tracking ENABLE ROW LEVEL SECURITY;
ALTER TABLE cost_summary_monthly ENABLE ROW LEVEL SECURITY;
ALTER TABLE budget_alerts ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own costs"
    ON cost_tracking FOR SELECT
    USING (user_id = auth.uid());

CREATE POLICY "Users can view own cost summaries"
    ON cost_summary_monthly FOR SELECT
    USING (user_id = auth.uid());

CREATE POLICY "Users can view own budget alerts"
    ON budget_alerts FOR SELECT
    USING (user_id = auth.uid());
