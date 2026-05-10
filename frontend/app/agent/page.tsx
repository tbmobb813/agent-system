import AgentExecutor from '@/components/AgentExecutor'

export default function AgentPage() {
  return (
    <div className="dr-history-stack">
      <header>
        <p className="eyebrow">Agent</p>
        <h1 className="section-title dr-dashboard-hero-title">Run a task</h1>
        <p className="dr-history-summary">
          Output streams over SSE — you&apos;ll see status updates, tool calls, and the
          model&apos;s text token-by-token. Cost lands at the end.
        </p>
      </header>

      <div className="panel p-5 md:p-6">
        <div className="min-h-[520px]">
          <AgentExecutor />
        </div>
      </div>
    </div>
  )
}
