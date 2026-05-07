import AgentExecutor from '@/components/AgentExecutor'
import PageHeader from '@/components/PageHeader'

export default function AgentPage() {
  return (
    <div className="flex flex-col h-[calc(100vh-113px)]">
      <PageHeader
        eyebrow="Live session"
        title="Run agent"
        description="Streamed turns, tools, and costs. When a run finishes, use the feedback card to rate the reply and add notes—they sync to task history and inform future behavior."
      />
      <div className="flex-1 min-h-0">
        <AgentExecutor />
      </div>
    </div>
  )
}
