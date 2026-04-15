'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  getAnalyticsAlerts,
  getAnalyticsDaily,
  getAnalyticsModels,
  getAnalyticsOverview,
  getAnalyticsTools,
} from '@/lib/api'
import { formatCost } from '@/lib/utils'

type Overview = {
  budget: number
  spent_month: number
  spent_today: number
  remaining: number
  daily_average: number
  projected_total: number
  percent_used: number
  days_elapsed: number
  days_in_month: number
  is_overspend_risk: boolean
}

type DailyPoint = {
  date: string
  cost: number
  calls: number
}

type ModelMetric = {
  model: string
  tasks: number
  successful: number
  success_rate: number
  avg_execution_time: number
  avg_cost: number
  total_cost: number
}

type ToolMetric = {
  tool_name: string
  uses: number
  unique_tasks: number
  total_task_cost: number
}

type AlertRow = {
  type: string
  message: string
  spent: number
  budget: number
  created_at: string | null
  acknowledged: boolean
}

type AlertsPayload = {
  risk_level: 'ok' | 'medium' | 'high'
  projected_total: number
  budget: number
  delta: number
  alerts: AlertRow[]
}

function StatCard({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
      <p className="text-xs text-gray-500 mb-1">{label}</p>
      <p className="text-2xl font-semibold text-gray-100">{value}</p>
      {hint ? <p className="text-xs text-gray-500 mt-2">{hint}</p> : null}
    </div>
  )
}

function shortModel(model: string) {
  return model.includes('/') ? model.split('/')[1] : model
}

export default function AnalyticsDashboard() {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [overview, setOverview] = useState<Overview | null>(null)
  const [daily, setDaily] = useState<DailyPoint[]>([])
  const [models, setModels] = useState<ModelMetric[]>([])
  const [tools, setTools] = useState<ToolMetric[]>([])
  const [alerts, setAlerts] = useState<AlertsPayload | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [o, d, m, t, a] = await Promise.all([
        getAnalyticsOverview(),
        getAnalyticsDaily(7),
        getAnalyticsModels(30),
        getAnalyticsTools(30),
        getAnalyticsAlerts(30),
      ])
      setOverview(o as Overview)
      setDaily((d.points ?? []) as DailyPoint[])
      setModels((m.metrics ?? []) as ModelMetric[])
      setTools((t.tools ?? []) as ToolMetric[])
      setAlerts(a as AlertsPayload)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load analytics data')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
    const interval = setInterval(load, 300000)
    return () => clearInterval(interval)
  }, [load])

  const maxDaily = useMemo(() => {
    if (!daily.length) return 0
    return Math.max(...daily.map(p => p.cost))
  }, [daily])

  if (loading) return <p className="text-gray-400">Loading analytics...</p>
  if (error) return <p className="text-red-400">Error: {error}</p>
  if (!overview) return <p className="text-gray-400">No analytics data yet.</p>

  const riskColor =
    !alerts ? 'text-gray-400' :
    alerts.risk_level === 'high' ? 'text-red-400' :
    alerts.risk_level === 'medium' ? 'text-yellow-400' :
    'text-green-400'

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold">Cost & Performance Analytics</h2>
        <button
          onClick={load}
          className="px-3 py-1.5 text-sm bg-gray-800 hover:bg-gray-700 rounded-lg transition-colors"
        >
          Refresh
        </button>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Spent This Month" value={formatCost(overview.spent_month)} />
        <StatCard label="Remaining Budget" value={formatCost(overview.remaining)} />
        <StatCard label="Daily Average" value={formatCost(overview.daily_average)} hint={`${overview.days_elapsed}/${overview.days_in_month} days`} />
        <StatCard label="Projected Month End" value={formatCost(overview.projected_total)} />
      </div>

      <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-gray-300">7-Day Cost Trend</h3>
          <span className="text-xs text-gray-500">{formatCost(overview.spent_today)} today</span>
        </div>
        {!daily.length ? (
          <p className="text-sm text-gray-500">No daily trend data yet.</p>
        ) : (
          <div className="space-y-2">
            {daily.map(point => {
              const width = maxDaily > 0 ? (point.cost / maxDaily) * 100 : 0
              return (
                <div key={point.date} className="grid grid-cols-[96px_1fr_72px] items-center gap-3">
                  <span className="text-xs text-gray-500">{new Date(point.date).toLocaleDateString()}</span>
                  <progress
                    className="w-full h-2 [&::-webkit-progress-bar]:bg-gray-800 [&::-webkit-progress-bar]:rounded-full [&::-webkit-progress-value]:bg-indigo-500 [&::-webkit-progress-value]:rounded-full [&::-moz-progress-bar]:bg-indigo-500"
                    max={100}
                    value={Math.max(width, 1)}
                  />
                  <span className="text-xs text-gray-300 text-right">{formatCost(point.cost)}</span>
                </div>
              )
            })}
          </div>
        )}
      </div>

      <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
        <h3 className="text-sm font-semibold text-gray-300 mb-3">Model Performance (30 Days)</h3>
        {!models.length ? (
          <p className="text-sm text-gray-500">No model performance data yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-500 border-b border-gray-800">
                  <th className="py-2 pr-3">Model</th>
                  <th className="py-2 pr-3">Tasks</th>
                  <th className="py-2 pr-3">Success</th>
                  <th className="py-2 pr-3">Avg Time</th>
                  <th className="py-2 pr-3">Avg Cost</th>
                  <th className="py-2">Total</th>
                </tr>
              </thead>
              <tbody>
                {models.map(row => (
                  <tr key={row.model} className="border-b border-gray-800/60 text-gray-200">
                    <td className="py-2 pr-3 font-mono text-xs">{shortModel(row.model)}</td>
                    <td className="py-2 pr-3">{row.tasks}</td>
                    <td className="py-2 pr-3">{row.success_rate.toFixed(1)}%</td>
                    <td className="py-2 pr-3">{row.avg_execution_time.toFixed(2)}s</td>
                    <td className="py-2 pr-3">{formatCost(row.avg_cost)}</td>
                    <td className="py-2">{formatCost(row.total_cost)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
          <h3 className="text-sm font-semibold text-gray-300 mb-3">Tool Usage (30 Days)</h3>
          {!tools.length ? (
            <p className="text-sm text-gray-500">No tool call data yet.</p>
          ) : (
            <ul className="space-y-2">
              {tools.slice(0, 8).map(tool => (
                <li key={tool.tool_name} className="flex items-center justify-between text-sm">
                  <span className="font-mono text-xs text-gray-300 truncate pr-2">{tool.tool_name}</span>
                  <span className="text-gray-400">
                    {tool.uses} uses • {formatCost(tool.total_task_cost)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
          <h3 className="text-sm font-semibold text-gray-300 mb-2">Budget Alerts</h3>
          <p className={`text-sm font-semibold mb-2 ${riskColor}`}>
            Risk: {alerts?.risk_level.toUpperCase() ?? 'UNKNOWN'}
          </p>
          <p className="text-xs text-gray-500 mb-3">
            Projected {formatCost(alerts?.projected_total ?? overview.projected_total)} against budget {formatCost(alerts?.budget ?? overview.budget)}
          </p>
          {!alerts?.alerts?.length ? (
            <p className="text-sm text-gray-500">No recorded alert events in the last 30 days.</p>
          ) : (
            <ul className="space-y-2 max-h-44 overflow-auto pr-1">
              {alerts.alerts.map((alert, index) => (
                <li key={`${alert.type}-${index}`} className="text-xs text-gray-300 border border-gray-800 rounded-md px-2 py-1.5">
                  <p className="font-medium text-gray-200">{alert.type}</p>
                  <p className="text-gray-400">{alert.message}</p>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  )
}
