// HistoryView — full table of past runs with filter & cost summary.

const { useState, useMemo } = React;

function HistoryView({ onNavigate }) {
  const all = window.AGENT_DATA.recentTasks;
  const [filter, setFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');

  const rows = useMemo(() => all.filter(t => {
    if (statusFilter !== 'all' && t.status !== statusFilter) return false;
    if (filter && !t.query.toLowerCase().includes(filter.toLowerCase())) return false;
    return true;
  }), [all, filter, statusFilter]);

  const totalCost = rows.reduce((s, t) => s + (t.cost || 0), 0);

  const statuses = ['all', 'completed', 'running', 'failed', 'stopped'];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      <header>
        <Eyebrow>Logs</Eyebrow>
        <SectionTitle size="32px">History</SectionTitle>
        <p style={{ fontFamily: 'var(--font-body)', fontSize: '15px', color: 'var(--muted)', margin: '8px 0 0', lineHeight: 1.55 }}>
          {rows.length} runs · total cost {formatCost(totalCost)}
        </p>
      </header>

      <Panel>
        <div style={{ display: 'flex', gap: '12px', alignItems: 'center', flexWrap: 'wrap', marginBottom: '14px' }}>
          <input
            type="text"
            placeholder="Filter by query…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            style={{
              background: 'var(--bg-elev)',
              color: 'var(--text)',
              fontFamily: 'inherit',
              fontSize: '13px',
              border: '1px solid var(--border)',
              borderRadius: '8px',
              padding: '8px 12px',
              outline: 'none',
              minWidth: '240px',
              flex: 1,
            }}
          />
          <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
            {statuses.map(s => (
              <button
                key={s}
                onClick={() => setStatusFilter(s)}
                style={{
                  background: statusFilter === s ? 'var(--surface)' : 'transparent',
                  border: '1px solid ' + (statusFilter === s ? 'var(--accent)' : 'var(--border)'),
                  color: statusFilter === s ? 'var(--text)' : 'var(--muted)',
                  fontFamily: 'inherit',
                  fontSize: '11px',
                  letterSpacing: '0.12em',
                  textTransform: 'uppercase',
                  padding: '6px 10px',
                  borderRadius: '6px',
                  cursor: 'pointer',
                }}
              >{s}</button>
            ))}
          </div>
        </div>

        <div>
          <div style={{
            display: 'grid',
            gridTemplateColumns: '90px minmax(0, 1fr) 130px 90px 70px',
            gap: '14px',
            paddingBottom: '8px',
            borderBottom: '1px solid var(--border)',
            fontFamily: 'var(--font-body)',
            fontSize: '10px',
            letterSpacing: '0.18em',
            textTransform: 'uppercase',
            color: 'var(--muted)',
          }}>
            <span>Status</span>
            <span>Query</span>
            <span>Model</span>
            <span style={{ textAlign: 'right' }}>Time</span>
            <span style={{ textAlign: 'right' }}>Cost</span>
          </div>
          {rows.map((task) => (
            <div key={task.id} style={{
              display: 'grid',
              gridTemplateColumns: '90px minmax(0, 1fr) 130px 90px 70px',
              gap: '14px',
              alignItems: 'center',
              padding: '12px 0',
              borderBottom: '1px solid var(--border)',
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
              <span style={{ color: 'var(--text)', fontFamily: 'var(--font-mono)', textAlign: 'right' }}>{formatCost(task.cost)}</span>
            </div>
          ))}
          {rows.length === 0 && (
            <div style={{ padding: '32px', textAlign: 'center', color: 'var(--muted)', fontFamily: 'var(--font-body)', fontSize: '13px' }}>
              No runs match your filter.
            </div>
          )}
        </div>
      </Panel>
    </div>
  );
}

Object.assign(window, { HistoryView });
