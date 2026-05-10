import AnalyticsDashboard from '@/components/AnalyticsDashboard'

export default function AnalyticsPage() {
  return (
    <div className="dr-history-stack">
      <header>
        <p className="eyebrow">Data</p>
        <h1 className="section-title dr-dashboard-hero-title">Analytics</h1>
        <p className="dr-history-summary">
          Trends across spend, models, tools, and alert signals.
        </p>
      </header>
      <div className="panel p-5 md:p-6">
        <AnalyticsDashboard />
      </div>
    </div>
  )
}
