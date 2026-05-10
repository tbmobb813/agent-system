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
    <div style={{ display: 'flex', flexDirection: 'column', gap: '32px' }}>

      {/* Hero greeting */}
      <section>
        <Eyebrow>Command Center</Eyebrow>
        <h1 className="section-title" style={{ margin: 0, fontSize: 'clamp(28px, 4vw, 44px)' }}>
          Welcome back, operator.
        </h1>
        <p style={{
          fontFamily: 'var(--font-body)',
          fontSize: '16px',
          color: 'var(--muted)',
          margin: '12px 0 0',
          maxWidth: '720px',
          lineHeight: 1.55,
        }}>
          Five-tier router, four agents, and a live budget. Pick a model or let the cost
          router pick one for you — every run streams here.
        </p>
        <div style={{ display: 'flex', gap: '20px', marginTop: '20px', flexWrap: 'wrap' }}>
          <PillStat color="var(--success)" label="Agent Online"     value={`${recentTasks.length} total`} />
          <PillStat color="var(--accent-2)" label="Completed today"  value={`${completedToday}`} />
          <PillStat color={failed ? 'var(--danger)' : 'var(--muted)'} label="Failed"            value={`${failed}`} />
          <PillStat color="var(--accent)"   label="Cost (recent)"    value={formatCost(totalCost)} />
        </div>
        <div style={{ display: 'flex', gap: '12px', marginTop: '24px' }}>
          <ButtonAccent onClick={() => onNavigate('/agent')} size="lg">Launch Agent</ButtonAccent>
          <ButtonGhost  onClick={() => onNavigate('/history')}>View History</ButtonGhost>
        </div>
      </section>

      {/* Budget + model split */}
      <section style={{
        display: 'grid',
        gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1.2fr)',
        gap: '20px',
      }}>
        <Panel>
          <Eyebrow>Monthly budget</Eyebrow>
          <div style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'baseline',
            marginBottom: '12px',
          }}>
            <SectionTitle size="22px">{formatCost(budget.spent_month)} <span style={{ color: 'var(--muted)', fontSize: '14px', fontWeight: 400 }}>/ {formatCost(budget.budget)}</span></SectionTitle>
            <span className="status-ok" style={{ fontSize: '12px', fontWeight: 700 }}>{budget.percent_used.toFixed(1)}%</span>
          </div>
          <progress className="budget-progress" max="100" value={budget.percent_used} />
          <div style={{
            display: 'flex',
            justifyContent: 'space-between',
            fontFamily: 'var(--font-body)',
            fontSize: '12px',
            color: 'var(--muted)',
            marginTop: '12px',
          }}>
            <span>spent today: <span style={{ color: 'var(--text)' }}>{formatCost(budget.spent_today)}</span></span>
            <span>remaining: <span style={{ color: 'var(--text)' }}>{formatCost(budget.remaining)}</span></span>
          </div>
        </Panel>

        <Panel>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
            <Eyebrow style={{ marginBottom: 0 }}>Model split (30 days)</Eyebrow>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--muted)' }}>
              {breakdownEntries.reduce((s, [, v]) => s + v.calls, 0)} calls
            </span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {breakdownEntries.map(([model, info]) => {
              const pct = (info.cost / totalModelCost) * 100;
              return (
                <div key={model} style={{ display: 'grid', gridTemplateColumns: '1fr 60px 60px', gap: '10px', alignItems: 'center', fontFamily: 'var(--font-body)', fontSize: '12px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: 0 }}>
                    <Code>{shortModel(model)}</Code>
                    <div style={{ flex: 1, height: '6px', background: 'var(--surface-soft)', borderRadius: '999px', overflow: 'hidden', minWidth: '40px' }}>
                      <div style={{ width: `${pct}%`, height: '100%', background: 'linear-gradient(90deg, var(--chart-primary), var(--chart-secondary))' }} />
                    </div>
                  </div>
                  <span style={{ color: 'var(--muted)', textAlign: 'right' }}>{info.calls} calls</span>
                  <span style={{ color: 'var(--text)', textAlign: 'right' }}>{formatCost(info.cost)}</span>
                </div>
              );
            })}
          </div>
        </Panel>
      </section>

      {/* Recent tasks */}
      <section>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
          <SectionTitle>Recent Tasks</SectionTitle>
          <a
            href="/history"
            onClick={(e) => { e.preventDefault(); onNavigate('/history'); }}
            style={{ fontFamily: 'var(--font-body)', fontSize: '13px', color: 'var(--accent-2)', textDecoration: 'none' }}
          >View all →</a>
        </div>
        <Panel>
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            {recentTasks.slice(0, 5).map((task, i) => (
              <div key={task.id} style={{
                display: 'grid',
                gridTemplateColumns: '90px minmax(0, 1fr) 130px 80px 70px',
                gap: '14px',
                alignItems: 'center',
                padding: '12px 0',
                borderBottom: i < 4 ? '1px solid var(--border)' : 'none',
                fontFamily: 'var(--font-body)',
                fontSize: '13px',
              }}>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: '8px' }}>
                  <StatusDot status={task.status} />
                  <StatusText status={task.status} />
                </span>
                <span style={{ color: 'var(--text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {task.query}
                </span>
                <Code style={{ justifySelf: 'start' }}>{shortModel(task.model)}</Code>
                <span style={{ color: 'var(--muted)', fontSize: '11px', textAlign: 'right' }}>{timeAgo(task.created_at)}</span>
                <span style={{ color: 'var(--text)', fontSize: '12px', fontFamily: 'var(--font-mono)', textAlign: 'right' }}>{formatCost(task.cost)}</span>
              </div>
            ))}
          </div>
        </Panel>
      </section>

      {/* Nav cards */}
      <section>
        <SectionTitle style={{ marginBottom: '14px' }}>Quick Actions</SectionTitle>
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))',
          gap: '14px',
        }}>
          {navCards.map(card => (
            <a
              key={card.href}
              href={card.href}
              onClick={(e) => { e.preventDefault(); onNavigate(card.href); }}
              style={{ textDecoration: 'none' }}
            >
              <Panel
                hover
                style={{
                  height: '100%',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '10px',
                  cursor: 'pointer',
                  borderColor: card.primary ? 'var(--accent)' : undefined,
                }}
              >
                <Chip>{card.icon}</Chip>
                <SectionTitle size="16px">{card.title}</SectionTitle>
                <p style={{
                  fontFamily: 'var(--font-body)',
                  fontSize: '13px',
                  color: 'var(--muted)',
                  margin: 0,
                  lineHeight: 1.5,
                }}>{card.description}</p>
                <span style={{
                  fontFamily: 'var(--font-body)',
                  fontSize: '12px',
                  color: 'var(--accent-2)',
                  marginTop: 'auto',
                  paddingTop: '6px',
                }}>Open →</span>
              </Panel>
            </a>
          ))}
        </div>
      </section>
    </div>
  );
}

function PillStat({ color, label, value }) {
  return (
    <span style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: '10px',
      fontFamily: 'var(--font-body)',
      fontSize: '13px',
    }}>
      <span style={{
        width: '10px', height: '10px', borderRadius: '999px',
        background: color, boxShadow: `0 0 12px ${color}`,
      }} />
      <span style={{ color: 'var(--text)', fontWeight: 600 }}>{label}</span>
      <span style={{ color: 'var(--muted)', fontSize: '12px' }}>· {value}</span>
    </span>
  );
}

Object.assign(window, { Dashboard });
