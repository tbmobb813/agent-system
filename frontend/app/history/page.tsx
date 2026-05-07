import Link from 'next/link'
import PageHeader from '@/components/PageHeader'
import TaskHistory from '@/components/TaskHistory'

export default function HistoryPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Execution log"
        title="Task history"
        description={(
          <>
            Search past runs, open a task for full output, export copies, and leave feedback so the agent learns what to repeat or avoid.
            {' '}
            <Link href="/agent" className="text-[color:var(--accent-2)] hover:underline">
              Run the agent
            </Link>
            {' '}
            to add new entries.
          </>
        )}
      />
      <TaskHistory />
    </div>
  )
}
