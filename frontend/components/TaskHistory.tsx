'use client'

import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
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
  feedback_signal?: string | null
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
  completed: 'border border-[color:var(--success)]/35 bg-[color:var(--success)]/10 text-[color:var(--success)]',
  running:   'border border-[color:var(--accent-2)]/35 bg-[color:var(--accent-2)]/10 text-[color:var(--accent-2)]',
  failed:    'border border-[color:var(--danger)]/35 bg-[color:var(--danger)]/10 text-[color:var(--danger)]',
  pending:   'border border-[color:var(--border)] bg-[color:var(--surface-soft)] text-muted',
  stopped:   'border border-[color:var(--warn)]/35 bg-[color:var(--warn)]/10 text-[color:var(--warn)]',
}

function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full shrink-0 ${statusStyles[status] ?? 'border border-[color:var(--border)] bg-[color:var(--surface-soft)] text-muted'}`}>
      {status}
    </span>
  )
}

function FeedbackHint({ signal }: { signal: string }) {
  if (signal !== 'up' && signal !== 'down') return null
  const up = signal === 'up'
  const label = up ? 'Marked helpful' : 'Marked needs work'
  return (
    <span
      className={`text-[10px] px-2 py-0.5 rounded-full border shrink-0 ${up
        ? 'border-[color:var(--success)]/40 bg-[color:var(--success)]/10 text-[color:var(--success)]'
        : 'border-[color:var(--danger)]/40 bg-[color:var(--danger)]/10 text-[color:var(--danger)]'}`}
      title={label}
      aria-label={label}
    >
      {up ? 'Helpful' : 'Needs work'}
    </span>
  )
}

function TaskDetailPanel({ taskId, onClose, onFeedbackSaved }: { taskId: string; onClose: () => void; onFeedbackSaved?: () => void }) {
  const [detail, setDetail] = useState<TaskDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [feedbackError, setFeedbackError] = useState<string | null>(null)
  const [pdfError, setPdfError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const [feedbackSignal, setFeedbackSignal] = useState<'up' | 'down'>('up')
  const [feedbackNotes, setFeedbackNotes] = useState('')
  const [feedbackSaving, setFeedbackSaving] = useState(false)
  const [feedbackSaved, setFeedbackSaved] = useState(false)
  const contentRef = useRef<HTMLDivElement>(null)
  const feedbackSavedTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setLoadError(null)
    setFeedbackError(null)
    setPdfError(null)
    getTaskDetail(taskId)
      .then(payload => {
        if (cancelled) return
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
      .catch(e => {
        if (cancelled) return
        setLoadError(e instanceof Error ? e.message : String(e))
      })
      .finally(() => {
        if (cancelled) return
        setLoading(false)
      })

    return () => {
      cancelled = true
    }
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
    setPdfError(null)
    try {
      await exportElementToPdf(contentRef.current, `task-${taskId.slice(0, 8)}.pdf`)
    } catch (e) {
      setPdfError(e instanceof Error ? e.message : 'PDF export failed')
    }
  }

  async function handleSaveFeedback() {
    setFeedbackSaving(true)
    setFeedbackError(null)
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
      onFeedbackSaved?.()
      if (feedbackSavedTimerRef.current) clearTimeout(feedbackSavedTimerRef.current)
      feedbackSavedTimerRef.current = setTimeout(() => setFeedbackSaved(false), 2500)
    } catch (e) {
      setFeedbackError(e instanceof Error ? e.message : 'Failed to save feedback')
    } finally {
      setFeedbackSaving(false)
    }
  }

  return (
    <div className="mt-3 border-t border-[color:var(--border)] pt-3 space-y-3">
      {loading && <p className="text-muted text-xs">Loading…</p>}
      {loadError && <p className="text-[color:var(--danger)] text-xs">{loadError}</p>}
      {detail && (
        <>
          <div className="panel panel-soft rounded-lg p-3 space-y-3">
            <div className="flex items-center justify-between gap-3 flex-wrap">
              <p className="text-xs text-muted">Teach the agent from this result</p>
              {detail.feedback && (
                <span className="text-xs text-muted">
                  Last feedback: {detail.feedback.signal === 'up' ? 'helpful' : 'needs work'}
                </span>
              )}
            </div>

            <div className="flex gap-2 flex-wrap">
              <button
                type="button"
                onClick={() => setFeedbackSignal('up')}
                className={`px-3 py-1.5 rounded text-xs transition-colors ${feedbackSignal === 'up' ? 'border border-[color:var(--success)]/50 bg-[color:var(--success)]/15 text-[color:var(--success)]' : 'btn-ghost text-muted'}`}
              >
                Helpful
              </button>
              <button
                type="button"
                onClick={() => setFeedbackSignal('down')}
                className={`px-3 py-1.5 rounded text-xs transition-colors ${feedbackSignal === 'down' ? 'border border-[color:var(--danger)]/50 bg-[color:var(--danger)]/15 text-[color:var(--danger)]' : 'btn-ghost text-muted'}`}
              >
                Needs work
              </button>
            </div>

            <div>
              <label htmlFor={`feedback-notes-${taskId}`} className="block text-xs text-muted mb-1">
                Notes for future behavior
              </label>
              <textarea
                id={`feedback-notes-${taskId}`}
                value={feedbackNotes}
                onChange={e => setFeedbackNotes(e.target.value)}
                rows={3}
                placeholder="What should the agent repeat or avoid next time?"
                className="w-full bg-[color:var(--bg-elev)] rounded-lg px-3 py-2 text-sm border border-[color:var(--border)] focus:outline-none focus:border-[color:var(--accent)] resize-none"
              />
            </div>

            <div className="flex items-center gap-3 flex-wrap">
              <button
                type="button"
                onClick={handleSaveFeedback}
                disabled={feedbackSaving}
                className="btn-accent px-3 py-1.5 rounded text-xs font-medium disabled:opacity-50"
              >
                {feedbackSaving ? 'Saving…' : 'Save feedback'}
              </button>
              {feedbackSaved && <span className="text-xs text-[color:var(--success)]">Feedback saved</span>}
              {feedbackError && <span className="text-xs text-[color:var(--danger)]">{feedbackError}</span>}
            </div>
          </div>

          {detail.task.execution_time != null && (
            <p className="text-xs text-muted">
              Completed in {detail.task.execution_time.toFixed(1)}s
            </p>
          )}
          {detail.task.result ? (
            <>
              <div className="flex gap-2 justify-end">
                <button
                  type="button"
                  onClick={handleCopy}
                  className="btn-ghost px-2 py-1 rounded text-xs"
                >
                  {copied ? 'Copied!' : 'Copy'}
                </button>
                <button
                  type="button"
                  onClick={handleDownload}
                  className="btn-ghost px-2 py-1 rounded text-xs"
                >
                  Download
                </button>
                <button
                  type="button"
                  onClick={handleExportPdf}
                  className="btn-ghost px-2 py-1 rounded text-xs"
                >
                  PDF
                </button>
                <button
                  type="button"
                  onClick={onClose}
                  className="btn-ghost px-2 py-1 rounded text-xs text-muted"
                >
                  Collapse
                </button>
              </div>
              {pdfError && (
                <p className="text-[color:var(--danger)] text-xs text-right">{pdfError}</p>
              )}
              <div ref={contentRef} className="text-sm bg-[color:var(--bg-elev)] border border-[color:var(--border)] rounded-lg p-4 leading-relaxed">
                <MarkdownContent content={detail.task.result} />
              </div>
            </>
          ) : (
            <div className="flex justify-end">
              <button
                type="button"
                onClick={onClose}
                className="btn-ghost px-2 py-1 rounded text-xs text-muted"
              >
                Collapse
              </button>
            </div>
          )}
          {!detail.task.result && (
            <p className="text-muted text-xs italic">No result stored for this task.</p>
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
    if (!window.confirm('Delete this task and its stored result from history?')) return
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

  function rowKeyToggle(e: KeyboardEvent, id: string) {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      toggleExpand(id)
    }
  }

  return (
    <div className="space-y-4">
      {/* Search bar */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1">
          <span className="absolute left-3 top-1/2 -translate-y-1/2 text-muted text-sm select-none">⌕</span>
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search queries and results…"
            className="w-full bg-[color:var(--bg-elev)] border border-[color:var(--border)] rounded-lg pl-8 pr-3 py-2 text-sm focus:outline-none focus:border-[color:var(--accent)] placeholder:text-muted"
          />
          {search && (
            <button
              onClick={() => setSearch('')}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-muted hover:text-[color:var(--text)] text-xs"
            >
              ✕
            </button>
          )}
        </div>
        <button
          onClick={() => refresh(PAGE_SIZE, offset, activeSearch || undefined)}
          className="text-sm text-[color:var(--accent-2)] hover:opacity-90 transition-opacity shrink-0"
        >
          Refresh
        </button>
      </div>

      {/* Status line */}
      {!loading && data && (
        <p className="text-sm text-muted">
          {activeSearch
            ? `${data.total} result${data.total !== 1 ? 's' : ''} for "${activeSearch}"`
            : `${data.total} total task${data.total !== 1 ? 's' : ''}`}
          {data.total > PAGE_SIZE && ` — showing ${offset + 1}–${Math.min(offset + PAGE_SIZE, data.total)}`}
        </p>
      )}

      {loading && <p className="text-muted text-sm">Loading…</p>}
      {error && <p className="text-[color:var(--danger)] text-sm">Error: {error}</p>}

      {!loading && data && data.tasks.length === 0 && (
        <p className="text-muted text-sm">
          {activeSearch ? `No tasks match "${activeSearch}".` : 'No tasks yet. Run your first agent query!'}
        </p>
      )}

      {(data?.tasks as Task[] ?? []).map((task) => (
        <div key={task.id} className="panel p-4">
          <div
            role="button"
            tabIndex={0}
            aria-expanded={expanded === task.id}
            aria-label={expanded === task.id ? `Collapse task: ${task.query}` : `Expand task: ${task.query}`}
            className="flex items-start justify-between gap-4 cursor-pointer select-none rounded-lg outline-none focus-visible:ring-2 focus-visible:ring-[color:var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[color:var(--bg)]"
            onClick={() => toggleExpand(task.id)}
            onKeyDown={e => rowKeyToggle(e, task.id)}
          >
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium">{task.query}</p>
              <div className="flex flex-wrap gap-3 mt-1 text-xs text-muted">
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
              {task.feedback_signal && (
                <FeedbackHint signal={task.feedback_signal} />
              )}
              <StatusBadge status={task.status} />
              <span className="text-muted text-xs" aria-hidden>{expanded === task.id ? '▲' : '▼'}</span>
              <button
                type="button"
                onClick={e => { e.stopPropagation(); handleDelete(task.id) }}
                onKeyDown={e => e.stopPropagation()}
                disabled={deleting === task.id}
                className="text-xs text-muted hover:text-[color:var(--danger)] transition-colors disabled:opacity-50"
                aria-label="Delete task"
              >
                {deleting === task.id ? '…' : '✕'}
              </button>
            </div>
          </div>

          {expanded === task.id && (
            <TaskDetailPanel
              taskId={task.id}
              onClose={() => setExpanded(null)}
              onFeedbackSaved={() => refresh(PAGE_SIZE, offset, activeSearch || undefined)}
            />
          )}
        </div>
      ))}

      {data && data.total > PAGE_SIZE && (
        <div className="flex items-center justify-between pt-2">
          <button
            onClick={() => { setOffset(o => Math.max(0, o - PAGE_SIZE)); setExpanded(null) }}
            disabled={offset === 0}
            className="btn-ghost px-3 py-1.5 rounded-lg text-sm disabled:opacity-40"
          >
            ← Newer
          </button>
          <span className="text-xs text-muted">
            Page {Math.floor(offset / PAGE_SIZE) + 1} of {Math.ceil(data.total / PAGE_SIZE)}
          </span>
          <button
            onClick={() => { setOffset(o => o + PAGE_SIZE); setExpanded(null) }}
            disabled={offset + PAGE_SIZE >= data.total}
            className="btn-ghost px-3 py-1.5 rounded-lg text-sm disabled:opacity-40"
          >
            Older →
          </button>
        </div>
      )}
    </div>
  )
}
