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
  { href: '/commands',  title: 'Commands',             description: 'CLI shortcuts, Telegram commands, API routes.',  icon: 'CMD' },
]

type Task = { id: string; query: string; status: string; cost: number; created_at: string; model?: string }
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

function statusTone(status: string) {
  if (status === 'completed') return 'ok'
  if (status === 'running') return 'running'
  if (status === 'failed') return 'danger'
  if (status === 'stopped') return 'warn'
  return 'muted'
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

  const completedToday = stats.recentTasks?.items.filter(t => t.status === 'completed').length ?? 0
  const failedCount = stats.recentTasks?.items.filter(t => t.status === 'failed').length ?? 0
  const recentCost = stats.recentTasks?.items.reduce((sum, t) => sum + (t.cost || 0), 0) ?? 0
  const breakdownEntries = Object.entries(stats.modelBreakdown ?? {}).sort((a, b) => b[1].cost - a[1].cost)
  const totalModelCost = breakdownEntries.reduce((sum, [, v]) => sum + v.cost, 0)

  return (
    <div className="dr-dashboard-stack">
      <section>
        <p className="eyebrow">Command Center</p>
        <h1 className="section-title dr-dashboard-hero-title">{greetContext.displayName ? welcomeLine : 'Welcome back, operator.'}</h1>
        <p className="dr-dashboard-hero-copy">
          Five-tier router, four agents, and a live budget. Pick a model or let the cost
          router pick one for you — every run streams here.
        </p>
        <div className="dr-dashboard-pill-row">
          <span className="dr-pill-stat">
            <span className="dr-pill-stat-dot dr-pill-tone-ok" />
            <span className="dr-pill-stat-label">Agent Online</span>
            <span className="dr-pill-stat-value">· {stats.recentTasks?.total ?? 0} total</span>
          </span>
          <span className="dr-pill-stat">
            <span className="dr-pill-stat-dot dr-pill-tone-running" />
            <span className="dr-pill-stat-label">Completed today</span>
            <span className="dr-pill-stat-value">· {completedToday}</span>
          </span>
          <span className="dr-pill-stat">
            <span className={`dr-pill-stat-dot ${failedCount > 0 ? 'dr-pill-tone-danger' : 'dr-pill-tone-muted'}`} />
            <span className="dr-pill-stat-label">Failed</span>
            <span className="dr-pill-stat-value">· {failedCount}</span>
          </span>
          <span className="dr-pill-stat">
            <span className="dr-pill-stat-dot dr-pill-tone-accent" />
            <span className="dr-pill-stat-label">Cost (recent)</span>
            <span className="dr-pill-stat-value">· {formatCost(recentCost)}</span>
          </span>
        </div>
        <div className="dr-dashboard-actions">
          <Link href="/agent" className="btn-accent dr-btn-accent dr-btn-accent-lg">Launch Agent</Link>
          <Link href="/history" className="btn-ghost dr-btn-ghost">View History</Link>
          <button type="button" onClick={load} className="btn-ghost dr-btn-ghost">Refresh</button>
        </div>
      </section>

      <section className="dr-dashboard-top-grid">
        <div className="panel p-5">
          <p className="eyebrow">Monthly budget</p>
          <div className="dr-dashboard-budget-head">
            <h2 className="section-title dr-title-22">
              {loading || !stats.budget ? '—' : formatCost(stats.budget.spent_month)}{' '}
              <span className="dr-dashboard-budget-total">/ {loading || !stats.budget ? '—' : formatCost(stats.budget.remaining + stats.budget.spent_month)}</span>
            </h2>
            <span className={stats.budget && stats.budget.percent >= 90 ? 'status-danger dr-dashboard-budget-pct' : stats.budget && stats.budget.percent >= 70 ? 'status-warn dr-dashboard-budget-pct' : 'status-ok dr-dashboard-budget-pct'}>
              {loading || !stats.budget ? '—' : `${stats.budget.percent.toFixed(1)}%`}
            </span>
          </div>
          <progress className="budget-progress" max={100} value={loading || !stats.budget ? 0 : Math.min(stats.budget.percent, 100)} />
          <div className="dr-dashboard-budget-meta">
            <span>spent today: <span className="dr-dashboard-emph">{loading || !stats.budget ? '—' : formatCost(stats.budget.spent_today)}</span></span>
            <span>remaining: <span className="dr-dashboard-emph">{loading || !stats.budget ? '—' : formatCost(stats.budget.remaining)}</span></span>
          </div>
        </div>

        <div className="panel p-5">
          <div className="dr-dashboard-model-head">
            <p className="eyebrow dr-eyebrow-inline">Model split (30 days)</p>
            <span className="dr-dashboard-model-calls">{breakdownEntries.reduce((sum, [, v]) => sum + v.calls, 0)} calls</span>
          </div>
          <div className="dr-dashboard-model-list">
            {(loading ? [] : breakdownEntries).map(([model, info]) => {
              const pct = totalModelCost > 0 ? (info.cost / totalModelCost) * 100 : 0
              return (
                <div key={model} className="dr-dashboard-model-row">
                  <div className="dr-dashboard-model-main">
                    <code className="dr-code">{shortModel(model)}</code>
                    <progress className="dr-dashboard-model-progress budget-progress" max={100} value={pct} />
                  </div>
                  <span className="dr-dashboard-model-calls-cell">{info.calls} calls</span>
                  <span className="dr-dashboard-model-cost-cell">{formatCost(info.cost)}</span>
                </div>
              )
            })}
            {!loading && breakdownEntries.length === 0 && <span className="text-muted text-sm">No usage this month</span>}
          </div>
        </div>
      </section>

      <section>
        <div className="dr-dashboard-section-head">
          <h2 className="section-title">Recent Tasks</h2>
          <Link href="/history" className="dr-dashboard-link">View all →</Link>
        </div>
        <div className="panel p-5">
          <div className="dr-dashboard-tasks-list">
            {(loading ? [] : stats.recentTasks?.items.slice(0, 5) ?? []).map((task, i, arr) => {
              const tone = statusTone(task.status)
              return (
                <div key={task.id} className={`dr-dashboard-task-row ${i < arr.length - 1 ? 'with-divider' : ''}`}>
                  <span className="dr-inline-status">
                    <span className={`dr-status-dot dr-status-dot-${tone}`} />
                    <span className={`dr-status-text ${STATUS_COLOR[task.status] ?? 'text-muted'}`}>{task.status}</span>
                  </span>
                  <span className="dr-row-query">{task.query}</span>
                  <code className="dr-code dr-code-start">{shortModel(task.model ?? 'unknown')}</code>
                  <span className="dr-row-time">{timeAgo(task.created_at)}</span>
                  <span className="dr-row-cost">{formatCost(task.cost || 0)}</span>
                </div>
              )
            })}
            {!loading && !(stats.recentTasks?.items.length) && <span className="text-muted text-sm">No tasks yet</span>}
          </div>
        </div>
      </section>

      <section>
        <h2 className="section-title dr-mb-14">Quick Actions</h2>
        <div className="dr-dashboard-cards-grid">
          {navCards.map(card => (
            <Link key={card.href} href={card.href} className="dr-dashboard-card-link">
              <div className={`panel p-5 dr-panel dr-panel-hover dr-dashboard-card ${card.primary ? 'is-primary' : ''}`}>
                <span className="dr-chip">{card.icon}</span>
                <h3 className="section-title dr-title-16">{card.title}</h3>
                <p className="dr-dashboard-card-copy">{card.description}</p>
                <span className="dr-dashboard-card-cta">Open →</span>
              </div>
            </Link>
          ))}
        </div>
      </section>
    </div>
  )
}
