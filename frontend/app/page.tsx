'use client'

import Link from 'next/link'
import { useEffect, useState, useCallback } from 'react'
import { getHealth, getCostStatus, getCostBreakdown, getHistory } from '@/lib/api'
import { formatCost } from '@/lib/utils'

const navCards = [
  { href: '/agent',     title: 'Run Agent',           description: 'Execute tasks with real-time streaming output.', icon: '🤖', primary: true },
  { href: '/history',   title: 'History',              description: 'Browse past executions and their results.',      icon: '📋' },
  { href: '/costs',     title: 'Budget',               description: 'Track spending and enforce your monthly cap.',   icon: '💰' },
  { href: '/analytics', title: 'Analytics',            description: 'Review trends, model performance, and tool usage.', icon: '📈' },
  { href: '/documents', title: 'Documents',            description: 'Upload files for the agent to search and use.',  icon: '📄' },
  { href: '/settings',  title: 'Settings',             description: 'Configure models, tools, and preferences.',      icon: '⚙️' },
  { href: '/commands',  title: 'Commands & Reference', description: 'CLI shortcuts, Telegram commands, API routes.',  icon: '📖' },
]

type Task = { id: string; query: string; status: string; cost: number; created_at: string }
type ModelBreakdown = Record<string, { cost: number; calls: number }>

type Stats = {
  agentReady: boolean
  budget: { percent: number; remaining: number; spent_month: number; spent_today: number; status: string } | null
  recentTasks: { total: number; items: Task[] } | null
  modelBreakdown: ModelBreakdown | null
}

const STATUS_COLOR: Record<string, string> = {
  completed: 'text-green-400',
  failed:    'text-red-400',
  stopped:   'text-yellow-400',
  running:   'text-indigo-400',
}

function shortModel(model: string) {
  // "anthropic/claude-3.5-haiku" → "claude-3.5-haiku"
  return model.includes('/') ? model.split('/')[1] : model
}

function timeAgo(iso: string) {
  const diff = Date.now() - new Date(iso).getTime()
  const m = Math.floor(diff / 60000)
  if (m < 1) return 'just now'
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  return `${Math.floor(h / 24)}d ago`
}

export default function DashboardPage() {
  const [stats, setStats] = useState<Stats>({ agentReady: false, budget: null, recentTasks: null, modelBreakdown: null })
  const [loading, setLoading] = useState(true)
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null)

  const load = useCallback(async () => {
    const [health, costs, breakdown, history] = await Promise.allSettled([
      getHealth(),
      getCostStatus(),
      getCostBreakdown(),
      getHistory(5, 0),
    ])

    const agentReady = health.status === 'fulfilled' && health.value?.agent_ready === true

    const budget = costs.status === 'fulfilled' ? {
      percent:     costs.value.percent_used  ?? 0,
      remaining:   costs.value.remaining     ?? 0,
      spent_month: costs.value.spent_month   ?? 0,
      spent_today: costs.value.spent_today   ?? 0,
      status:      costs.value.status        ?? 'ok',
    } : null

    const modelBreakdown = breakdown.status === 'fulfilled' ? (breakdown.value.breakdown as ModelBreakdown) : null

    const tasks = history.status === 'fulfilled' ? history.value.tasks : []
    const recentTasks = history.status === 'fulfilled' ? {
      total: history.value.total ?? 0,
      items: tasks as Task[],
    } : null

    setStats({ agentReady, budget, recentTasks, modelBreakdown })
    setLoading(false)
    setLastRefresh(new Date())
  }, [])

  // Initial load + 30-second auto-refresh
  useEffect(() => {
    load()
    const interval = setInterval(load, 30000)
    return () => clearInterval(interval)
  }, [load])

  const budgetBarColor =
    !stats.budget                    ? 'bg-indigo-500' :
    stats.budget.percent >= 90       ? 'bg-red-500' :
    stats.budget.percent >= 70       ? 'bg-yellow-500' :
    'bg-indigo-500'

  const budgetTextColor =
    !stats.budget       ? 'text-gray-400' :
    stats.budget.percent >= 90 ? 'text-red-400' :
    stats.budget.percent >= 70 ? 'text-yellow-400' :
    'text-green-400'

  return (
    <div className="space-y-8">

      {/* Header */}
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-3xl font-bold mb-1">Dashboard</h1>
          <p className="text-gray-400">Your personal AI co-worker</p>
        </div>
        <div className="flex items-center gap-3">
          {lastRefresh && (
            <span className="text-xs text-gray-600">
              updated {timeAgo(lastRefresh.toISOString())}
            </span>
          )}
          <button
            onClick={load}
            className="px-3 py-1.5 bg-gray-800 hover:bg-gray-700 rounded-lg text-xs text-gray-400 transition-colors"
          >
            Refresh
          </button>
        </div>
      </div>

      {/* Status + budget row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">

        {/* Agent status */}
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 flex items-center gap-4">
          <span className={`w-3 h-3 rounded-full shrink-0 ${loading ? 'bg-gray-600' : stats.agentReady ? 'bg-green-400' : 'bg-red-500'}`} />
          <div>
            <p className="text-sm font-medium text-gray-200">
              Agent {loading ? '…' : stats.agentReady ? 'Online' : 'Offline'}
            </p>
            <p className="text-xs text-gray-500 mt-0.5">
              {stats.recentTasks ? `${stats.recentTasks.total} total tasks` : 'loading…'}
            </p>
          </div>
        </div>

        {/* Budget card */}
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm text-gray-400">Monthly budget</span>
            <span className={`text-sm font-semibold ${budgetTextColor}`}>
              {loading ? '…' : stats.budget ? `${stats.budget.percent.toFixed(1)}%` : 'N/A'}
            </span>
          </div>
          <div className="h-2 bg-gray-800 rounded-full overflow-hidden mb-3">
            <div
              className={`h-full rounded-full transition-all ${budgetBarColor}`}
              style={{ width: `${loading || !stats.budget ? 0 : Math.min(stats.budget.percent, 100)}%` }}
            />
          </div>
          <div className="flex justify-between text-xs text-gray-500">
            <span>spent today: <span className="text-gray-300">{loading || !stats.budget ? '…' : formatCost(stats.budget.spent_today)}</span></span>
            <span>remaining: <span className="text-gray-300">{loading || !stats.budget ? '…' : formatCost(stats.budget.remaining)}</span></span>
          </div>
        </div>
      </div>

      {/* Recent tasks + model breakdown */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">

        {/* Recent tasks */}
        <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
          <div className="flex items-center justify-between px-5 py-3 border-b border-gray-800">
            <h2 className="text-sm font-semibold text-gray-300">Recent Tasks</h2>
            <Link href="/history" className="text-xs text-indigo-400 hover:text-indigo-300 transition-colors">
              View all →
            </Link>
          </div>
          {loading ? (
            <div className="px-5 py-8 text-center text-gray-600 text-sm">Loading…</div>
          ) : !stats.recentTasks?.items.length ? (
            <div className="px-5 py-8 text-center text-gray-600 text-sm">No tasks yet</div>
          ) : (
            <ul>
              {stats.recentTasks.items.map((task, i) => (
                <li
                  key={task.id}
                  className={`px-5 py-3 flex items-center gap-3 ${i < stats.recentTasks!.items.length - 1 ? 'border-b border-gray-800' : ''}`}
                >
                  <span className={`text-xs font-medium shrink-0 w-16 ${STATUS_COLOR[task.status] ?? 'text-gray-400'}`}>
                    {task.status}
                  </span>
                  <span className="text-sm text-gray-200 truncate flex-1">{task.query}</span>
                  <span className="text-xs text-gray-500 shrink-0">{timeAgo(task.created_at)}</span>
                  {task.cost > 0 && (
                    <span className="text-xs text-gray-600 shrink-0">{formatCost(task.cost)}</span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Model breakdown */}
        <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
          <div className="flex items-center justify-between px-5 py-3 border-b border-gray-800">
            <h2 className="text-sm font-semibold text-gray-300">This Month by Model</h2>
            <Link href="/costs" className="text-xs text-indigo-400 hover:text-indigo-300 transition-colors">
              Details →
            </Link>
          </div>
          {loading ? (
            <div className="px-5 py-8 text-center text-gray-600 text-sm">Loading…</div>
          ) : !stats.modelBreakdown || Object.keys(stats.modelBreakdown).length === 0 ? (
            <div className="px-5 py-8 text-center text-gray-600 text-sm">No usage this month</div>
          ) : (
            <ul>
              {Object.entries(stats.modelBreakdown)
                .sort((a, b) => b[1].cost - a[1].cost)
                .map(([model, info], i, arr) => (
                  <li
                    key={model}
                    className={`px-5 py-3 flex items-center gap-3 ${i < arr.length - 1 ? 'border-b border-gray-800' : ''}`}
                  >
                    <span className="text-xs text-gray-300 truncate flex-1 font-mono">
                      {shortModel(model)}
                    </span>
                    <span className="text-xs text-gray-500 shrink-0">{info.calls} call{info.calls !== 1 ? 's' : ''}</span>
                    <span className="text-xs text-gray-300 shrink-0 w-16 text-right">{formatCost(info.cost)}</span>
                  </li>
                ))}
            </ul>
          )}
        </div>
      </div>

      {/* Nav cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {navCards.map(s => (
          <Link
            key={s.href}
            href={s.href}
            className={`block p-6 bg-gray-900 rounded-xl border transition-colors ${
              s.primary
                ? 'border-indigo-600 hover:border-indigo-400'
                : 'border-gray-800 hover:border-indigo-500'
            }`}
          >
            <div className="text-3xl mb-3">{s.icon}</div>
            <h2 className={`text-lg font-semibold mb-1 ${s.primary ? 'text-indigo-300' : ''}`}>{s.title}</h2>
            <p className="text-sm text-gray-400">{s.description}</p>
          </Link>
        ))}
      </div>
    </div>
  )
}
