// Dashboard view — the main "/" route.
// Hero greeting + status pills, two-column row of budget + model split,
// Recent Tasks list, then nav cards.

const { useMemo } = React;

function Dashboard({ onNavigate }) {
  const { recentTasks, modelBreakdown, budget, navCards } = window.AGENT_DATA;

  const completedToday = recentTasks.filter(t => t.status === 'completed').length;
  const failed         = recentTasks.filter(t => t.status === 'failed').length;
  const totalCost      = recentTasks.reduce((sum, t) => sum + (t.cost || 0), 0);

  const breakdownEntries = useMemo(
    () => Object.entries(modelBreakdown).sort((a, b) => b[1].cost - a[1].cost),
    [modelBreakdown]
  );
  const totalModelCost = breakdownEntries.reduce((s, [, v]) => s + v.cost, 0);

  return (
    <div className="dr-dashboard-stack">

      {/* Hero greeting */}
      <section>
        <Eyebrow>Command Center</Eyebrow>
        <h1 className="section-title dr-dashboard-hero-title">
          Welcome back, operator.
        </h1>
        <p className="dr-dashboard-hero-copy">
          Five-tier router, four agents, and a live budget. Pick a model or let the cost
          router pick one for you — every run streams here.
        </p>
        <div className="dr-dashboard-pill-row">
          <PillStat tone="ok" label="Agent Online" value={`${recentTasks.length} total`} />
          <PillStat tone="running" label="Completed today" value={`${completedToday}`} />
          <PillStat tone={failed ? 'danger' : 'muted'} label="Failed" value={`${failed}`} />
          <PillStat tone="accent" label="Cost (recent)" value={formatCost(totalCost)} />
        </div>
        <div className="dr-dashboard-actions">
          <ButtonAccent onClick={() => onNavigate('/agent')} size="lg">Launch Agent</ButtonAccent>
          <ButtonGhost  onClick={() => onNavigate('/history')}>View History</ButtonGhost>
        </div>
      </section>

      {/* Budget + model split */}
      <section className="dr-dashboard-top-grid">
        <Panel>
          <Eyebrow>Monthly budget</Eyebrow>
          <div className="dr-dashboard-budget-head">
            <SectionTitle size="22px">
              {formatCost(budget.spent_month)} <span className="dr-dashboard-budget-total">/ {formatCost(budget.budget)}</span>
            </SectionTitle>
            <span className="status-ok dr-dashboard-budget-pct">{budget.percent_used.toFixed(1)}%</span>
          </div>
          <progress className="budget-progress" max="100" value={budget.percent_used} />
          <div className="dr-dashboard-budget-meta">
            <span>spent today: <span className="dr-dashboard-emph">{formatCost(budget.spent_today)}</span></span>
            <span>remaining: <span className="dr-dashboard-emph">{formatCost(budget.remaining)}</span></span>
          </div>
        </Panel>

        <Panel>
          <div className="dr-dashboard-model-head">
            <Eyebrow className="dr-eyebrow-inline">Model split (30 days)</Eyebrow>
            <span className="dr-dashboard-model-calls">
              {breakdownEntries.reduce((s, [, v]) => s + v.calls, 0)} calls
            </span>
          </div>
          <div className="dr-dashboard-model-list">
            {breakdownEntries.map(([model, info]) => {
              const pct = (info.cost / totalModelCost) * 100;
              return (
                <div key={model} className="dr-dashboard-model-row">
                  <div className="dr-dashboard-model-main">
                    <Code>{shortModel(model)}</Code>
                    <progress className="dr-dashboard-model-progress budget-progress" max="100" value={pct} />
                  </div>
                  <span className="dr-dashboard-model-calls-cell">{info.calls} calls</span>
                  <span className="dr-dashboard-model-cost-cell">{formatCost(info.cost)}</span>
                </div>
              );
            })}
          </div>
        </Panel>
      </section>

      {/* Recent tasks */}
      <section>
        <div className="dr-dashboard-section-head">
          <SectionTitle>Recent Tasks</SectionTitle>
          <a
            href="/history"
            onClick={(e) => { e.preventDefault(); onNavigate('/history'); }}
            className="dr-dashboard-link"
          >View all →</a>
        </div>
        <Panel>
          <div className="dr-dashboard-tasks-list">
            {recentTasks.slice(0, 5).map((task, i) => (
              <div key={task.id} className={`dr-dashboard-task-row ${i < 4 ? 'with-divider' : ''}`}>
                <span className="dr-inline-status">
                  <StatusDot status={task.status} />
                  <StatusText status={task.status} />
                </span>
                <span className="dr-row-query">
                  {task.query}
                </span>
                <Code className="dr-code-start">{shortModel(task.model)}</Code>
                <span className="dr-row-time">{timeAgo(task.created_at)}</span>
                <span className="dr-row-cost">{formatCost(task.cost)}</span>
              </div>
            ))}
          </div>
        </Panel>
      </section>

      {/* Nav cards */}
      <section>
        <SectionTitle className="dr-mb-14">Quick Actions</SectionTitle>
        <div className="dr-dashboard-cards-grid">
          {navCards.map(card => (
            <a
              key={card.href}
              href={card.href}
              onClick={(e) => { e.preventDefault(); onNavigate(card.href); }}
              className="dr-dashboard-card-link"
            >
              <Panel
                hover
                className={`dr-dashboard-card ${card.primary ? 'is-primary' : ''}`}
              >
                <Chip>{card.icon}</Chip>
                <SectionTitle size="16px">{card.title}</SectionTitle>
                <p className="dr-dashboard-card-copy">{card.description}</p>
                <span className="dr-dashboard-card-cta">Open →</span>
              </Panel>
            </a>
          ))}
        </div>
      </section>
    </div>
  );
}

function PillStat({ tone, label, value }) {
  return (
    <span className="dr-pill-stat">
      <span className={`dr-pill-stat-dot dr-pill-tone-${tone}`} />
      <span className="dr-pill-stat-label">{label}</span>
      <span className="dr-pill-stat-value">· {value}</span>
    </span>
  );
}

Object.assign(window, { Dashboard });
