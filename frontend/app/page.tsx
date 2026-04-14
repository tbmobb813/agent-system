'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'
import { getHealth, getCostStatus, getHistory } from '@/lib/api'
import { formatCost } from '@/lib/utils'

const sections = [
  { href: '/agent',     title: 'Run Agent',  description: 'Execute tasks with real-time streaming output.', icon: '🤖' },
  { href: '/history',   title: 'History',    description: 'Browse past executions and their results.',      icon: '📋' },
  { href: '/costs',     title: 'Budget',     description: 'Track spending and enforce your $30/month cap.', icon: '💰' },
  { href: '/documents', title: 'Documents',  description: 'Upload files for the agent to search and use.',  icon: '📄' },
  { href: '/settings',  title: 'Settings',   description: 'Configure models, tools, and preferences.',      icon: '⚙️' },
]

type Stats = {
  agentReady: boolean
  budget: { percent: number; remaining: number; status: string } | null
  recentTasks: { count: number; lastQuery: string | null; lastCost: number } | null
}

function StatPill({ label, value, color = 'text-gray-200' }: { label: string; value: string; color?: string }) {
  return (
    <div className="flex flex-col items-center bg-gray-900 border border-gray-800 rounded-xl px-5 py-3 min-w-[110px]">
      <span className={`text-lg font-semibold ${color}`}>{value}</span>
      <span className="text-xs text-gray-500 mt-0.5">{label}</span>
    </div>
  )
}

export default function DashboardPage() {
  const [stats, setStats] = useState<Stats>({ agentReady: false, budget: null, recentTasks: null })
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function load() {
      const [health, costs, history] = await Promise.allSettled([
        getHealth(),
        getCostStatus(),
        getHistory(5, 0),
      ])

      const agentReady = health.status === 'fulfilled' && health.value?.agent_ready === true

      const budget = costs.status === 'fulfilled' ? {
        percent: costs.value.percent_used ?? 0,
        remaining: costs.value.remaining ?? 0,
        status: costs.value.status ?? 'ok',
      } : null

      const tasks = history.status === 'fulfilled' ? history.value.tasks : []
      const recentTasks = history.status === 'fulfilled' ? {
        count: history.value.total ?? 0,
        lastQuery: tasks[0]?.query ?? null,
        lastCost: tasks[0]?.cost ?? 0,
      } : null

      setStats({ agentReady, budget, recentTasks })
      setLoading(false)
    }
    load()
  }, [])

  const budgetColor =
    !stats.budget ? 'text-gray-400' :
    stats.budget.percent < 50 ? 'text-green-400' :
    stats.budget.percent < 80 ? 'text-yellow-400' :
    'text-red-400'

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold mb-1">Dashboard</h1>
        <p className="text-gray-400">Your personal AI co-worker</p>
      </div>

      {/* Live stats bar */}
      <div className="flex flex-wrap gap-3">
        <StatPill
          label="Agent"
          value={loading ? '…' : stats.agentReady ? 'Online' : 'Offline'}
          color={loading ? 'text-gray-500' : stats.agentReady ? 'text-green-400' : 'text-red-400'}
        />
        <StatPill
          label="Budget used"
          value={loading ? '…' : stats.budget ? `${stats.budget.percent.toFixed(1)}%` : 'N/A'}
          color={budgetColor}
        />
        <StatPill
          label="Remaining"
          value={loading ? '…' : stats.budget ? formatCost(stats.budget.remaining) : 'N/A'}
        />
        <StatPill
          label="Total tasks"
          value={loading ? '…' : stats.recentTasks ? String(stats.recentTasks.count) : 'N/A'}
        />
      </div>

      {/* Last run snippet */}
      {!loading && stats.recentTasks?.lastQuery && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl px-5 py-4">
          <p className="text-xs text-gray-500 mb-1">Last task</p>
          <p className="text-sm text-gray-200 truncate">{stats.recentTasks.lastQuery}</p>
          {stats.recentTasks.lastCost > 0 && (
            <p className="text-xs text-gray-500 mt-1">{formatCost(stats.recentTasks.lastCost)}</p>
          )}
        </div>
      )}

      {/* Nav cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {sections.map(s => (
          <Link
            key={s.href}
            href={s.href}
            className="block p-6 bg-gray-900 rounded-xl border border-gray-800 hover:border-indigo-500 transition-colors"
          >
            <div className="text-3xl mb-3">{s.icon}</div>
            <h2 className="text-lg font-semibold mb-1">{s.title}</h2>
            <p className="text-sm text-gray-400">{s.description}</p>
          </Link>
        ))}
      </div>
    </div>
  )
}
