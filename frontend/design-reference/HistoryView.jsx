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
    <div className="dr-history-stack">
      <header>
        <Eyebrow>Logs</Eyebrow>
        <SectionTitle size="32px">History</SectionTitle>
        <p className="dr-history-summary">
          {rows.length} runs · total cost {formatCost(totalCost)}
        </p>
      </header>

      <Panel>
        <div className="dr-history-controls">
          <input
            type="text"
            placeholder="Filter by query…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="dr-history-filter-input"
          />
          <div className="dr-history-status-row">
            {statuses.map(s => (
              <button
                key={s}
                onClick={() => setStatusFilter(s)}
                className={`dr-history-status-btn ${statusFilter === s ? 'is-active' : ''}`}
              >{s}</button>
            ))}
          </div>
        </div>

        <div>
          <div className="dr-history-head-row">
            <span>Status</span>
            <span>Query</span>
            <span>Model</span>
            <span className="dr-align-right">Time</span>
            <span className="dr-align-right">Cost</span>
          </div>
          {rows.map((task) => (
            <div key={task.id} className="dr-history-data-row">
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
          {rows.length === 0 && (
            <div className="dr-history-empty">
              No runs match your filter.
            </div>
          )}
        </div>
      </Panel>
    </div>
  );
}

Object.assign(window, { HistoryView });
