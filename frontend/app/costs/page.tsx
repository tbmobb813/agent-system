import CostTracker from '@/components/CostTracker'
import PageHeader from '@/components/PageHeader'

export default function CostsPage() {
  return (
    <div>
      <PageHeader
        eyebrow="Spend guard"
        title="Budget & costs"
        description="Monthly ceiling, burn rate, and what you have left. Pair with Analytics when you are tuning models or tools."
      />
      <CostTracker />
    </div>
  )
}
