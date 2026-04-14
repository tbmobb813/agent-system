'use client'

import { useEffect, useState } from 'react'
import { useHistory } from '@/lib/hooks'
import { deleteTask, getTaskDetail } from '@/lib/api'
import { formatCost, formatDate } from '@/lib/utils'

type Task = {
  id: string
  query: string
  status: string
  created_at: string
  cost: number
  model_used: string | null
}

type TaskDetail = {
  task: Task & { result: string | null; execution_time: number | null }
  steps: unknown[]
}

const statusStyles: Record<string, string> = {
  completed: 'bg-green-900/50 text-green-400',
  running:   'bg-blue-900/50 text-blue-400',
  failed:    'bg-red-900/50 text-red-400',
  pending:   'bg-gray-800 text-gray-400',
  stopped:   'bg-yellow-900/50 text-yellow-400',
}

function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full shrink-0 ${statusStyles[status] ?? 'bg-gray-800 text-gray-400'}`}>
      {status}
    </span>
  )
}

function TaskDetailPanel({ taskId, onClose }: { taskId: string; onClose: () => void }) {
  const [detail, setDetail] = useState<TaskDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    getTaskDetail(taskId)
      .then(setDetail)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [taskId])

  async function handleCopy() {
    const text = detail?.task.result
    if (!text) return
    await navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  function handleDownload() {
    const text = detail?.task.result
    if (!text) return
    const blob = new Blob([text], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `task-${taskId.slice(0, 8)}.txt`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="mt-3 border-t border-gray-700 pt-3 space-y-3">
      {loading && <p className="text-gray-500 text-xs">Loading…</p>}
      {error && <p className="text-red-400 text-xs">{error}</p>}
      {detail && (
        <>
          {detail.task.execution_time != null && (
            <p className="text-xs text-gray-500">
              Completed in {detail.task.execution_time.toFixed(1)}s
            </p>
          )}
          {detail.task.result ? (
            <>
              <div className="flex gap-2 justify-end">
                <button
                  onClick={handleCopy}
                  className="px-2 py-1 bg-gray-800 hover:bg-gray-700 rounded text-xs text-gray-300 transition-colors"
                >
                  {copied ? 'Copied!' : 'Copy'}
                </button>
                <button
                  onClick={handleDownload}
                  className="px-2 py-1 bg-gray-800 hover:bg-gray-700 rounded text-xs text-gray-300 transition-colors"
                >
                  Download
                </button>
                <button
                  onClick={onClose}
                  className="px-2 py-1 bg-gray-800 hover:bg-gray-700 rounded text-xs text-gray-400 transition-colors"
                >
                  Collapse
                </button>
              </div>
              <pre className="text-sm text-gray-100 whitespace-pre-wrap font-sans bg-gray-800 rounded-lg p-4 leading-relaxed">
                {detail.task.result}
              </pre>
            </>
          ) : (
            <div className="flex justify-end">
              <button
                onClick={onClose}
                className="px-2 py-1 bg-gray-800 hover:bg-gray-700 rounded text-xs text-gray-400 transition-colors"
              >
                Collapse
              </button>
            </div>
          )}
          {!detail.task.result && (
            <p className="text-gray-500 text-xs italic">No result stored for this task.</p>
          )}
        </>
      )}
    </div>
  )
}

const PAGE_SIZE = 20

export default function TaskHistory() {
  const { data, loading, error, refresh } = useHistory()
  const [deleting, setDeleting] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<string | null>(null)
  const [offset, setOffset] = useState(0)

  useEffect(() => { refresh(PAGE_SIZE, offset) }, [refresh, offset])

  async function handleDelete(id: string) {
    if (expanded === id) setExpanded(null)
    setDeleting(id)
    try {
      await deleteTask(id)
      refresh()
    } finally {
      setDeleting(null)
    }
  }

  function toggleExpand(id: string) {
    setExpanded(prev => prev === id ? null : id)
  }

  if (loading) return <p className="text-gray-400">Loading history…</p>
  if (error)   return <p className="text-red-400">Error: {error}</p>
  if (!data || data.tasks.length === 0) {
    return <p className="text-gray-400">No tasks yet. Run your first agent query!</p>
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-sm text-gray-400">
          {data.total} total tasks
          {data.total > PAGE_SIZE && ` — showing ${offset + 1}–${Math.min(offset + PAGE_SIZE, data.total)}`}
        </p>
        <button
          onClick={() => refresh(PAGE_SIZE, offset)}
          className="text-sm text-indigo-400 hover:text-indigo-300 transition-colors"
        >
          Refresh
        </button>
      </div>

      {(data.tasks as Task[]).map((task) => (
        <div key={task.id} className="bg-gray-900 rounded-xl border border-gray-800 p-4">
          <div
            className="flex items-start justify-between gap-4 cursor-pointer select-none"
            onClick={() => toggleExpand(task.id)}
          >
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium">{task.query}</p>
              <div className="flex flex-wrap gap-3 mt-1 text-xs text-gray-400">
                <span>{formatDate(task.created_at)}</span>
                {task.model_used && (
                  <span className="font-mono truncate max-w-[180px]" title={task.model_used}>
                    {task.model_used.split('/').pop()}
                  </span>
                )}
                <span>{formatCost(task.cost)}</span>
              </div>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <StatusBadge status={task.status} />
              <span className="text-gray-600 text-xs">{expanded === task.id ? '▲' : '▼'}</span>
              <button
                onClick={e => { e.stopPropagation(); handleDelete(task.id) }}
                disabled={deleting === task.id}
                className="text-xs text-gray-500 hover:text-red-400 transition-colors disabled:opacity-50"
                aria-label="Delete task"
              >
                {deleting === task.id ? '…' : '✕'}
              </button>
            </div>
          </div>

          {expanded === task.id && (
            <TaskDetailPanel taskId={task.id} onClose={() => setExpanded(null)} />
          )}
        </div>
      ))}

      {data.total > PAGE_SIZE && (
        <div className="flex items-center justify-between pt-2">
          <button
            onClick={() => { setOffset(o => Math.max(0, o - PAGE_SIZE)); setExpanded(null) }}
            disabled={offset === 0}
            className="px-3 py-1.5 bg-gray-800 hover:bg-gray-700 rounded-lg text-sm disabled:opacity-40 transition-colors"
          >
            ← Newer
          </button>
          <span className="text-xs text-gray-500">
            Page {Math.floor(offset / PAGE_SIZE) + 1} of {Math.ceil(data.total / PAGE_SIZE)}
          </span>
          <button
            onClick={() => { setOffset(o => o + PAGE_SIZE); setExpanded(null) }}
            disabled={offset + PAGE_SIZE >= data.total}
            className="px-3 py-1.5 bg-gray-800 hover:bg-gray-700 rounded-lg text-sm disabled:opacity-40 transition-colors"
          >
            Older →
          </button>
        </div>
      )}
    </div>
  )
}
