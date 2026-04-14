import AgentExecutor from '@/components/AgentExecutor'

export default function AgentPage() {
  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Run Agent</h1>
      <AgentExecutor />
    </div>
  )
}
