import AgentExecutor from '@/components/AgentExecutor'

export default function AgentPage() {
  return (
    <div className="flex flex-col h-[calc(100vh-113px)]">
      <h1 className="text-2xl font-bold mb-4 shrink-0">Run Agent</h1>
      <div className="flex-1 min-h-0">
        <AgentExecutor />
      </div>
    </div>
  )
}
