import Link from 'next/link'
import TaskHistory from '@/components/TaskHistory'

export default function HistoryPage() {
  return (
    <div className="dr-history-stack">
      <header>
        <p className="eyebrow">Logs</p>
        <h1 className="section-title dr-dashboard-hero-title">History</h1>
        <p className="dr-history-summary">
          Search past runs, open a task for full output, export copies, and leave feedback so the agent learns what to repeat or avoid.
          {' '}
          <Link href="/agent" className="dr-dashboard-link">Run the agent</Link>
          {' '}to add new entries.
        </p>
      </header>

      <div className="panel p-5 md:p-6">
        <TaskHistory />
      </div>
    </div>
  )
}
