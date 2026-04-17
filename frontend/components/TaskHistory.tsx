'use client'

import { useEffect, useRef, useState } from 'react'
import dynamic from 'next/dynamic'
import { useHistory } from '@/lib/hooks'
import { deleteTask, getTaskDetail, submitTaskFeedback } from '@/lib/api'
import { formatCost, formatDate } from '@/lib/utils'
import { exportElementToPdf } from '@/lib/pdf'

const MarkdownContent = dynamic(() => import('./MarkdownContent'), { ssr: false })

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
  feedback?: {
    signal: 'up' | 'down'
    notes: string | null
    created_at: string
  } | null
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
  const [feedbackSignal, setFeedbackSignal] = useState<'up' | 'down'>('up')
  const [feedbackNotes, setFeedbackNotes] = useState('')
  const [feedbackSaving, setFeedbackSaving] = useState(false)
  const [feedbackSaved, setFeedbackSaved] = useState(false)
  const contentRef = useRef<HTMLDivElement>(null)
  const feedbackSavedTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    getTaskDetail(taskId)
      .then(payload => {
        setDetail(payload)
        if (payload.feedback) {
          setFeedbackSignal(payload.feedback.signal)
          setFeedbackNotes(payload.feedback.notes ?? '')
        } else {
          setFeedbackSignal('up')
          setFeedbackNotes('')
          setFeedbackSaved(false)
        }
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [taskId])

  useEffect(() => {
    return () => {
      if (feedbackSavedTimerRef.current) clearTimeout(feedbackSavedTimerRef.current)
    }
  }, [])

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

  async function handleExportPdf() {
    if (!contentRef.current) return
    await exportElementToPdf(contentRef.current, `task-${taskId.slice(0, 8)}.pdf`)
  }

  async function handleSaveFeedback() {
    setFeedbackSaving(true)
    setError(null)
    try {
      const payload = await submitTaskFeedback(taskId, {
        signal: feedbackSignal,
        notes: feedbackNotes,
      })
      setDetail(prev => prev ? {
        ...prev,
        feedback: {
          signal: payload.signal,
          notes: payload.notes,
          created_at: payload.created_at,
        },
      } : prev)
      setFeedbackSaved(true)
      if (feedbackSavedTimerRef.current) clearTimeout(feedbackSavedTimerRef.current)
      feedbackSavedTimerRef.current = setTimeout(() => setFeedbackSaved(false), 2500)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save feedback')
    } finally {
      setFeedbackSaving(false)
    }
  }

  return (
    <div className="mt-3 border-t border-gray-700 pt-3 space-y-3">
      {loading && <p className="text-gray-500 text-xs">Loading…</p>}
      {error && <p className="text-red-400 text-xs">{error}</p>}
      {detail && (
        <>
          <div className="bg-gray-900/60 border border-gray-800 rounded-lg p-3 space-y-3">
            <div className="flex items-center justify-between gap-3 flex-wrap">
              <p className="text-xs text-gray-400">Teach the agent from this result</p>
              {detail.feedback && (
                <span className="text-xs text-gray-500">
                  Last feedback: {detail.feedback.signal === 'up' ? 'helpful' : 'needs work'}
                </span>
              )}
            </div>

            <div className="flex gap-2 flex-wrap">
              <button
                type="button"
                onClick={() => setFeedbackSignal('up')}
                className={`px-3 py-1.5 rounded text-xs transition-colors ${feedbackSignal === 'up' ? 'bg-green-900/60 text-green-300 border border-green-700' : 'bg-gray-800 text-gray-300 hover:bg-gray-700'}`}
              >
                Helpful
              </button>
              <button
                type="button"
                onClick={() => setFeedbackSignal('down')}
                className={`px-3 py-1.5 rounded text-xs transition-colors ${feedbackSignal === 'down' ? 'bg-red-900/60 text-red-300 border border-red-700' : 'bg-gray-800 text-gray-300 hover:bg-gray-700'}`}
              >
                Needs work
              </button>
            </div>

            <div>
              <label htmlFor={`feedback-notes-${taskId}`} className="block text-xs text-gray-400 mb-1">
                Notes for future behavior
              </label>
              <textarea
                id={`feedback-notes-${taskId}`}
                value={feedbackNotes}
                onChange={e => setFeedbackNotes(e.target.value)}
                rows={3}
                placeholder="What should the agent repeat or avoid next time?"
                className="w-full bg-gray-800 rounded-lg px-3 py-2 text-sm border border-gray-700 focus:outline-none focus:border-indigo-500 resize-none"
              />
            </div>

            <div className="flex items-center gap-3 flex-wrap">
              <button
                type="button"
                onClick={handleSaveFeedback}
                disabled={feedbackSaving}
                className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 rounded text-xs font-medium disabled:opacity-50 transition-colors"
              >
                {feedbackSaving ? 'Saving…' : 'Save feedback'}
              </button>
              {feedbackSaved && <span className="text-xs text-green-400">Feedback saved</span>}
            </div>
          </div>

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
                  onClick={handleExportPdf}
                  className="px-2 py-1 bg-gray-800 hover:bg-gray-700 rounded text-xs text-gray-300 transition-colors"
                >
                  PDF
                </button>
                <button
                  onClick={onClose}
                  className="px-2 py-1 bg-gray-800 hover:bg-gray-700 rounded text-xs text-gray-400 transition-colors"
                >
                  Collapse
                </button>
              </div>
              <div ref={contentRef} className="text-sm text-gray-100 bg-gray-800 rounded-lg p-4 leading-relaxed">
                <MarkdownContent content={detail.task.result} />
              </div>
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
  const [search, setSearch] = useState('')
  const [activeSearch, setActiveSearch] = useState('')
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Debounce search input — fire after 350ms of no typing
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      setActiveSearch(search)
      setOffset(0)
      setExpanded(null)
    }, 350)
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current) }
  }, [search])

  useEffect(() => {
    refresh(PAGE_SIZE, offset, activeSearch || undefined)
  }, [offset, activeSearch]) // eslint-disable-line react-hooks/exhaustive-deps

  async function handleDelete(id: string) {
    if (expanded === id) setExpanded(null)
    setDeleting(id)
    try {
      await deleteTask(id)
      refresh(PAGE_SIZE, offset, activeSearch || undefined)
    } finally {
      setDeleting(null)
    }
  }

  function toggleExpand(id: string) {
    setExpanded(prev => prev === id ? null : id)
  }

  return (
    <div className="space-y-4">
      {/* Search bar */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1">
          <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500 text-sm select-none">⌕</span>
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search queries and results…"
            className="w-full bg-gray-900 border border-gray-700 rounded-lg pl-8 pr-3 py-2 text-sm focus:outline-none focus:border-indigo-500 placeholder:text-gray-600"
          />
          {search && (
            <button
              onClick={() => setSearch('')}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300 text-xs"
            >
              ✕
            </button>
          )}
        </div>
        <button
          onClick={() => refresh(PAGE_SIZE, offset, activeSearch || undefined)}
          className="text-sm text-indigo-400 hover:text-indigo-300 transition-colors shrink-0"
        >
          Refresh
        </button>
      </div>

      {/* Status line */}
      {!loading && data && (
        <p className="text-sm text-gray-400">
          {activeSearch
            ? `${data.total} result${data.total !== 1 ? 's' : ''} for "${activeSearch}"`
            : `${data.total} total task${data.total !== 1 ? 's' : ''}`}
          {data.total > PAGE_SIZE && ` — showing ${offset + 1}–${Math.min(offset + PAGE_SIZE, data.total)}`}
        </p>
      )}

      {loading && <p className="text-gray-400 text-sm">Loading…</p>}
      {error && <p className="text-red-400 text-sm">Error: {error}</p>}

      {!loading && data && data.tasks.length === 0 && (
        <p className="text-gray-400 text-sm">
          {activeSearch ? `No tasks match "${activeSearch}".` : 'No tasks yet. Run your first agent query!'}
        </p>
      )}

      {(data?.tasks as Task[] ?? []).map((task) => (
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

      {data && data.total > PAGE_SIZE && (
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
