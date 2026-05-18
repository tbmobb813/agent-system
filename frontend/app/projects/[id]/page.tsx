'use client'

import { useState, useEffect, useCallback } from 'react'
import Link from 'next/link'
import { use } from 'react'
import { getProjectTasks, removeTaskFromProject, type Project } from '@/lib/api'

function ColorDot({ color }: { color: string }) {
  return <span style={{ width: 10, height: 10, borderRadius: '50%', background: color, display: 'inline-block', flexShrink: 0 }} />
}

function formatCost(cost: number) {
  if (cost === 0) return '$0.00'
  if (cost < 0.001) return '<$0.001'
  return `$${cost.toFixed(4)}`
}

function statusColor(status: string) {
  if (status === 'completed') return 'text-[color:var(--success)]'
  if (status === 'failed') return 'text-[color:var(--danger)]'
  if (status === 'running') return 'text-[color:var(--accent-2)]'
  return 'text-muted'
}

type Task = {
  id: string
  query: string
  status: string
  cost: number
  model_used: string | null
  created_at: string
}

export default function ProjectDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params)

  const [project, setProject] = useState<Project | null>(null)
  const [tasks, setTasks] = useState<Task[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [removing, setRemoving] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      // Fetch project info alongside tasks
      const [tasksData, projectRes] = await Promise.all([
        getProjectTasks(id),
        fetch(`/api/backend/projects/${id}`, { headers: { 'Content-Type': 'application/json' } }),
      ])
      if (projectRes.ok) setProject(await projectRes.json())
      setTasks(tasksData.tasks)
      setTotal(tasksData.total)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => { load() }, [load])

  const handleRemove = async (taskId: string) => {
    setRemoving(taskId)
    try {
      await removeTaskFromProject(id, taskId)
      setTasks(prev => prev.filter(t => t.id !== taskId))
      setTotal(prev => prev - 1)
      if (project) setProject({ ...project, task_count: project.task_count - 1 })
    } catch { /* silently fail */ }
    finally { setRemoving(null) }
  }

  return (
    <div className="dr-history-stack">
      <header>
        <div className="flex items-center gap-2 mb-1">
          <Link href="/projects" className="text-xs text-muted hover:text-[color:var(--text)] transition-colors">Projects</Link>
          <span className="text-muted text-xs">/</span>
          {project && <ColorDot color={project.color} />}
        </div>
        <h1 className="section-title dr-dashboard-hero-title">
          {project ? project.name : 'Project'}
        </h1>
        {project?.description && <p className="dr-history-summary">{project.description}</p>}
      </header>

      <div className="flex items-center justify-between gap-3">
        <p className="text-sm text-muted">{total} {total === 1 ? 'task' : 'tasks'}</p>
        <Link href="/history" className="dr-btn-ghost px-3 py-1.5 rounded-lg text-sm">
          Add from History →
        </Link>
      </div>

      {loading && <p className="text-muted text-sm">Loading…</p>}
      {error && <p className="text-[color:var(--danger)] text-sm">{error}</p>}

      {!loading && tasks.length === 0 && (
        <div className="panel p-10 text-center space-y-3">
          <p className="text-2xl">📭</p>
          <p className="text-sm text-muted">No tasks in this project yet.</p>
          <Link href="/history" className="dr-btn-accent px-4 py-2 rounded-lg text-sm inline-block">
            Assign tasks from History
          </Link>
        </div>
      )}

      {tasks.length > 0 && (
        <div className="panel overflow-hidden">
          <div className="grid grid-cols-[minmax(0,1fr)_80px_100px_auto] gap-4 px-5 py-3 text-[10px] uppercase tracking-widest text-muted border-b border-[color:var(--border)]">
            <span>Task</span>
            <span className="text-right">Cost</span>
            <span>Status</span>
            <span />
          </div>
          {tasks.map(task => (
            <div key={task.id} className="grid grid-cols-[minmax(0,1fr)_80px_100px_auto] gap-4 px-5 py-3 text-sm border-b last:border-b-0 border-[color:var(--border)]/50 items-center">
              <Link href={`/history`} className="truncate hover:text-[color:var(--accent)] transition-colors" title={task.query}>
                {task.query}
              </Link>
              <span className="text-right font-mono text-xs text-muted">{formatCost(task.cost)}</span>
              <span className={`text-xs ${statusColor(task.status)}`}>{task.status}</span>
              <button
                type="button"
                onClick={() => void handleRemove(task.id)}
                disabled={removing === task.id}
                className="dr-btn-ghost px-2 py-0.5 rounded text-xs text-[color:var(--danger)] disabled:opacity-50 whitespace-nowrap"
              >
                {removing === task.id ? '…' : 'Remove'}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
