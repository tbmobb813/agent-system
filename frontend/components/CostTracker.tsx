'use client'

import { useEffect, useState } from 'react'
import { useCostStatus } from '@/lib/hooks'
import { getCostBreakdown } from '@/lib/api'
import { formatCost, percentColor } from '@/lib/utils'

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
    <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
      <p className="text-xs text-gray-400 mb-1">{label}</p>
      <p className="text-xl font-semibold">{value}</p>
    </div>
  )
}

export default function CostTracker() {
  const { data, loading, error, refresh } = useCostStatus()
  const [breakdown, setBreakdown] = useState<Record<string, ModelRow> | null>(null)

  useEffect(() => {
    refresh()
    getCostBreakdown()
      .then(d => setBreakdown(d.breakdown))
      .catch(() => setBreakdown(null))
  }, [refresh])

  if (loading) return <p className="text-gray-400">Loading cost data…</p>
  if (error)   return <p className="text-red-400">Error: {error}</p>
  if (!data)   return null

  const d = data as CostData
  const barWidth = Math.min(d.percent_used, 100)
  const barColor =
    d.percent_used < 50 ? 'bg-green-500' :
    d.percent_used < 80 ? 'bg-yellow-500' :
    'bg-red-500'

  const breakdownEntries = breakdown
    ? Object.entries(breakdown).sort((a, b) => b[1].cost - a[1].cost)
    : []

  return (
    <div className="space-y-6">
      {/* Budget bar */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-semibold">Monthly Budget</h2>
          <span className={`text-sm font-medium uppercase ${percentColor(d.percent_used)}`}>
            {d.status}
          </span>
        </div>
        <div className="w-full bg-gray-800 rounded-full h-3 mb-3">
          <div
            className={`h-3 rounded-full transition-all ${barColor}`}
            style={{ width: `${barWidth}%` }}
          />
        </div>
        <div className="flex justify-between text-sm text-gray-400">
          <span>{formatCost(d.spent_month)} spent</span>
          <span>{formatCost(d.budget)} budget</span>
        </div>
        <p className="text-xs text-gray-500 mt-2">
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
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-5">
          <h3 className="font-medium text-sm mb-4 text-gray-300">This month by model</h3>
          <div className="space-y-3">
            {breakdownEntries.map(([model, row]) => {
              const pct = d.spent_month > 0 ? (row.cost / d.spent_month) * 100 : 0
              const shortName = model.split('/').pop() ?? model
              return (
                <div key={model}>
                  <div className="flex items-center justify-between text-xs mb-1">
                    <span className="font-mono text-gray-300 truncate max-w-[200px]" title={model}>
                      {shortName}
                    </span>
                    <div className="flex gap-3 text-gray-400 shrink-0">
                      <span>{row.calls} call{row.calls !== 1 ? 's' : ''}</span>
                      <span className="text-gray-200">{formatCost(row.cost)}</span>
                    </div>
                  </div>
                  <div className="w-full bg-gray-800 rounded-full h-1.5">
                    <div
                      className="h-1.5 rounded-full bg-indigo-500 transition-all"
                      style={{ width: `${Math.min(pct, 100)}%` }}
                    />
                  </div>
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
        className="text-sm text-indigo-400 hover:text-indigo-300 transition-colors"
      >
        Refresh
      </button>
    </div>
  )
}
