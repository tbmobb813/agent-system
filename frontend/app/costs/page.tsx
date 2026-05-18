import CostTracker from '@/components/CostTracker'

export default function CostsPage() {
  return (
    <div className="dr-history-stack">
      <header>
        <p className="eyebrow">Cost</p>
        <h1 className="section-title dr-dashboard-hero-title">Budget & Costs</h1>
        <p className="dr-history-summary">
          Monthly ceiling, burn rate, and what you have left.
        </p>
      </header>
      <div className="panel p-5 md:p-6">
        <CostTracker />
      </div>
    </div>
  )
}
