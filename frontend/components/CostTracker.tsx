'use client'

import { useEffect, useState } from 'react'
import { useCostStatus } from '@/lib/hooks'
import { getCostBreakdown } from '@/lib/api'
import { formatCost } from '@/lib/utils'

type CostData = {
  budget: number
  spent_month: number
  spent_today: number
  remaining: number
  percent_used: number
  status: string
  reset_date: string
}

type ModelRow = {
  cost: number
  calls: number
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="panel p-4">
      <p className="text-xs text-muted mb-1">{label}</p>
      <p className="text-xl font-semibold">{value}</p>
    </div>
  )
}

export default function CostTracker() {
  const { data, loading, error, refresh } = useCostStatus()
  const [breakdown, setBreakdown] = useState<Record<string, ModelRow> | null>(null)

  useEffect(() => {
    getCostBreakdown()
      .then(d => setBreakdown(d.breakdown))
      .catch(() => setBreakdown(null))
  }, [])

  if (loading) return <p className="text-muted">Loading cost data…</p>
  if (error)   return <p className="text-[color:var(--danger)]">Error: {error}</p>
  if (!data)   return null

  const d = data as CostData
  const statusColor =
    d.percent_used < 50 ? 'text-[color:var(--success)]' :
    d.percent_used < 80 ? 'text-[color:var(--warn)]' :
    'text-[color:var(--danger)]'

  const breakdownEntries = breakdown
    ? Object.entries(breakdown).sort((a, b) => b[1].cost - a[1].cost)
    : []

  return (
    <div className="space-y-6">
      {/* Budget bar */}
      <div className="panel p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="section-title font-semibold">Monthly Budget</h2>
          <span className={`text-sm font-medium uppercase ${statusColor}`}>
            {d.status}
          </span>
        </div>
        <progress
          className="budget-progress h-3 mb-3"
          max={100}
          value={Math.min(d.percent_used, 100)}
        />
        <div className="flex justify-between text-sm text-muted">
          <span>{formatCost(d.spent_month)} spent</span>
          <span>{formatCost(d.budget)} budget</span>
        </div>
        <p className="text-xs text-muted mt-2">
          Resets: {new Date(d.reset_date).toLocaleDateString()}
        </p>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <StatCard label="Remaining"   value={formatCost(d.remaining)} />
        <StatCard label="Spent Today" value={formatCost(d.spent_today)} />
        <StatCard label="% Used"      value={`${d.percent_used.toFixed(1)}%`} />
      </div>

      {/* Breakdown by model */}
      {breakdownEntries.length > 0 && (
        <div className="panel p-5">
          <h3 className="font-medium text-sm mb-4">This month by model</h3>
          <div className="space-y-3">
            {breakdownEntries.map(([model, row]) => {
              const pct = d.spent_month > 0 ? (row.cost / d.spent_month) * 100 : 0
              const shortName = model.split('/').pop() ?? model
              return (
                <div key={model}>
                  <div className="flex items-center justify-between text-xs mb-1">
                    <span className="font-mono truncate max-w-[200px]" title={model}>
                      {shortName}
                    </span>
                    <div className="flex gap-3 text-muted shrink-0">
                      <span>{row.calls} call{row.calls !== 1 ? 's' : ''}</span>
                      <span className="text-[color:var(--text)]">{formatCost(row.cost)}</span>
                    </div>
                  </div>
                  <progress
                    className="budget-progress h-1.5"
                    max={100}
                    value={Math.min(pct, 100)}
                  />
                </div>
              )
            })}
          </div>
        </div>
      )}

      <button
        onClick={() => {
          refresh()
          getCostBreakdown().then(d => setBreakdown(d.breakdown)).catch(() => {})
        }}
        className="text-sm text-[color:var(--accent-2)] hover:opacity-90 transition-opacity"
      >
        Refresh
      </button>
    </div>
  )
}
