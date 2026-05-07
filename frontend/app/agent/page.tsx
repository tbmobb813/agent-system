import AgentExecutor from '@/components/AgentExecutor'
import PageHeader from '@/components/PageHeader'

/** Reserve space for sticky nav + page chrome; transcript uses the rest of the viewport. */
export default function AgentPage() {
  return (
    <div className="flex flex-col h-[calc(100dvh-7rem)] max-h-[calc(100dvh-7rem)] min-h-[420px] -my-2 md:-my-4">
      <PageHeader className="!mb-2 md:!mb-3 shrink-0" eyebrow="Live session" title="Agent" />
      <div className="flex-1 min-h-0">
        <AgentExecutor />
      </div>
    </div>
  )
}
