import AnalyticsDashboard from '@/components/AnalyticsDashboard'
import PageHeader from '@/components/PageHeader'

export default function AnalyticsPage() {
  return (
    <div>
      <PageHeader
        eyebrow="Telemetry"
        title="Analytics"
        description="Trends across spend, models, tools, and alert signals. Use this alongside Budget for day-to-day caps."
      />
      <AnalyticsDashboard />
    </div>
  )
}
