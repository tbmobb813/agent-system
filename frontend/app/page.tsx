'use client'

import Link from 'next/link'
import { useEffect, useState, useCallback } from 'react'
import { getHealth, getCostStatus, getCostBreakdown, getHistory, getSettings } from '@/lib/api'
import { dashboardWelcomeLine } from '@/lib/greeting'
import { formatCost } from '@/lib/utils'

const navCards = [
  { href: '/agent',     title: 'Run Agent',           description: 'Execute tasks with real-time streaming output.', icon: 'CORE', primary: true },
  { href: '/history',   title: 'History',              description: 'Browse runs, export results, and leave feedback the agent learns from.', icon: 'LOGS' },
  { href: '/costs',     title: 'Budget',               description: 'Track spending and enforce your monthly cap.',   icon: 'COST' },
  { href: '/analytics', title: 'Analytics',            description: 'Review trends, model performance, and tool usage.', icon: 'DATA' },
  { href: '/documents', title: 'Documents',            description: 'Upload files for the agent to search and use.',  icon: 'DOCS' },
  { href: '/settings',  title: 'Settings',             description: 'Configure models, tools, and preferences.',      icon: 'CONF' },
  { href: '/commands',  title: 'Commands & Reference', description: 'CLI shortcuts, Telegram commands, API routes.',  icon: 'CMD' },
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
  completed: 'text-[color:var(--success)]',
  failed:    'text-[color:var(--danger)]',
  stopped:   'text-[color:var(--warn)]',
  running:   'text-[color:var(--accent-2)]',
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

type GreetContext = { displayName: string | null; timezone: string }

export default function DashboardPage() {
  const [stats, setStats] = useState<Stats>({ agentReady: false, budget: null, recentTasks: null, modelBreakdown: null })
  const [loading, setLoading] = useState(true)
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null)
  const [greetContext, setGreetContext] = useState<GreetContext>({ displayName: null, timezone: 'UTC' })
  const [, setMinutePulse] = useState(0)

  const load = useCallback(async () => {
    const [health, costs, breakdown, history, settings] = await Promise.allSettled([
      getHealth(),
      getCostStatus(),
      getCostBreakdown(),
      getHistory(5, 0),
      getSettings(),
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

    if (settings.status === 'fulfilled' && settings.value) {
      const s = settings.value as { display_name?: string | null; timezone?: string }
      const raw = typeof s.display_name === 'string' ? s.display_name.trim() : ''
      setGreetContext({
        displayName: raw || null,
        timezone: typeof s.timezone === 'string' && s.timezone.trim() ? s.timezone.trim() : 'UTC',
      })
    }

    setLoading(false)
    setLastRefresh(new Date())
  }, [])

  // Initial load + 30-second auto-refresh
  useEffect(() => {
    load()
    const interval = setInterval(load, 30000)
    return () => clearInterval(interval)
  }, [load])

  // Recompute greeting when the hour might change (without waiting for the next data refresh).
  useEffect(() => {
    const id = setInterval(() => setMinutePulse(t => t + 1), 60_000)
    return () => clearInterval(id)
  }, [])

  const welcomeLine = dashboardWelcomeLine(greetContext.displayName, greetContext.timezone)

  const budgetTextColor =
    !stats.budget       ? 'text-muted' :
    stats.budget.percent >= 90 ? 'text-[color:var(--danger)]' :
    stats.budget.percent >= 70 ? 'text-[color:var(--warn)]' :
    'text-[color:var(--success)]'

  return (
    <div className="space-y-8">

      {/* Header */}
      <div className="panel panel-soft fade-up p-6 md:p-7 flex flex-col gap-5 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.22em] text-muted mb-2">Command Center</p>
          <h1 className="section-title text-3xl md:text-4xl font-bold mb-2">{welcomeLine}</h1>
          <p className="text-muted max-w-xl">
            Telemetry, budget, and execution history in one live operations deck.
            {!greetContext.displayName && (
              <span className="block mt-2 text-xs">
                Tip: add a display name in{' '}
                <Link href="/settings" className="text-[color:var(--accent-2)] hover:underline">Settings</Link>
                {' '}to personalize this line.
              </span>
            )}
          </p>
        </div>
        <div className="flex items-center gap-3">
          {lastRefresh && (
            <span className="text-xs text-muted">
              updated {timeAgo(lastRefresh.toISOString())}
            </span>
          )}
          <button
            onClick={load}
            className="btn-ghost rounded-lg px-3 py-2 text-xs"
          >
            Refresh
          </button>
          <Link href="/agent" className="btn-accent rounded-lg px-3 py-2 text-xs">
            Launch Agent
          </Link>
        </div>
      </div>

      {/* Status + budget row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 fade-up-delay">

        {/* Agent status */}
        <div className="panel p-5 flex items-center gap-4">
          <span className={`w-3 h-3 rounded-full shrink-0 ${loading ? 'bg-[color:var(--muted)]' : stats.agentReady ? 'bg-[color:var(--success)]' : 'bg-[color:var(--danger)]'}`} />
          <div>
            <p className="text-sm font-medium">
              Agent {loading ? '…' : stats.agentReady ? 'Online' : 'Offline'}
            </p>
            <p className="text-xs text-muted mt-0.5">
              {stats.recentTasks ? `${stats.recentTasks.total} total tasks` : 'loading…'}
            </p>
          </div>
        </div>

        {/* Budget card */}
        <div className="panel p-5">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm text-muted">Monthly budget</span>
            <span className={`text-sm font-semibold ${budgetTextColor}`}>
              {loading ? '…' : stats.budget ? `${stats.budget.percent.toFixed(1)}%` : 'N/A'}
            </span>
          </div>
          <progress
            className="budget-progress mb-3"
            max={100}
            value={loading || !stats.budget ? 0 : Math.min(stats.budget.percent, 100)}
          />
          <div className="flex justify-between text-xs text-muted">
            <span>spent today: <span className="text-[color:var(--text)]">{loading || !stats.budget ? '…' : formatCost(stats.budget.spent_today)}</span></span>
            <span>remaining: <span className="text-[color:var(--text)]">{loading || !stats.budget ? '…' : formatCost(stats.budget.remaining)}</span></span>
          </div>
        </div>
      </div>

      {/* Recent tasks + model breakdown */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">

        {/* Recent tasks */}
        <div className="panel overflow-hidden">
          <div className="flex items-center justify-between px-5 py-3 border-b border-[color:var(--border)]">
            <h2 className="text-sm font-semibold">Recent Tasks</h2>
            <Link href="/history" className="text-xs text-[color:var(--accent-2)] hover:opacity-90 transition-opacity">
              View all →
            </Link>
          </div>
          {loading ? (
            <div className="px-5 py-8 text-center text-muted text-sm">Loading…</div>
          ) : !stats.recentTasks?.items.length ? (
            <div className="px-5 py-8 text-center text-muted text-sm">No tasks yet</div>
          ) : (
            <ul>
              {stats.recentTasks.items.map((task, i) => (
                <li
                  key={task.id}
                  className={`px-5 py-3 flex items-center gap-3 ${i < stats.recentTasks!.items.length - 1 ? 'border-b border-[color:var(--border)]' : ''}`}
                >
                  <span className={`text-xs font-medium shrink-0 w-16 ${STATUS_COLOR[task.status] ?? 'text-muted'}`}>
                    {task.status}
                  </span>
                  <span className="text-sm truncate flex-1">{task.query}</span>
                  <span className="text-xs text-muted shrink-0">{timeAgo(task.created_at)}</span>
                  {task.cost > 0 && (
                    <span className="text-xs text-muted shrink-0">{formatCost(task.cost)}</span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Model breakdown */}
        <div className="panel overflow-hidden">
          <div className="flex items-center justify-between px-5 py-3 border-b border-[color:var(--border)]">
            <h2 className="text-sm font-semibold">This Month by Model</h2>
            <Link href="/costs" className="text-xs text-[color:var(--accent-2)] hover:opacity-90 transition-opacity">
              Details →
            </Link>
          </div>
          {loading ? (
            <div className="px-5 py-8 text-center text-muted text-sm">Loading…</div>
          ) : !stats.modelBreakdown || Object.keys(stats.modelBreakdown).length === 0 ? (
            <div className="px-5 py-8 text-center text-muted text-sm">No usage this month</div>
          ) : (
            <ul>
              {Object.entries(stats.modelBreakdown)
                .sort((a, b) => b[1].cost - a[1].cost)
                .map(([model, info], i, arr) => (
                  <li
                    key={model}
                    className={`px-5 py-3 flex items-center gap-3 ${i < arr.length - 1 ? 'border-b border-[color:var(--border)]' : ''}`}
                  >
                    <span className="text-xs truncate flex-1 font-mono">
                      {shortModel(model)}
                    </span>
                    <span className="text-xs text-muted shrink-0">{info.calls} call{info.calls !== 1 ? 's' : ''}</span>
                    <span className="text-xs shrink-0 w-16 text-right">{formatCost(info.cost)}</span>
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
            className={`panel block p-6 transition-all hover:-translate-y-0.5 ${
              s.primary
                ? 'ring-1 ring-[color:var(--accent)]/50'
                : 'hover:border-[color:var(--accent-2)]'
            }`}
          >
            <div className="inline-flex items-center rounded-md border border-[color:var(--border)] bg-[color:var(--surface-soft)] px-2 py-1 text-[10px] tracking-[0.2em] uppercase text-muted mb-3">{s.icon}</div>
            <h2 className={`text-lg font-semibold mb-1 ${s.primary ? 'text-[color:var(--accent)]' : ''}`}>{s.title}</h2>
            <p className="text-sm text-muted">{s.description}</p>
          </Link>
        ))}
      </div>
    </div>
  )
}
