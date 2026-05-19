'use client'

import { useEffect, useRef, useState, useCallback, type KeyboardEvent } from 'react'
import dynamic from 'next/dynamic'
import { useHistory } from '@/lib/hooks'
import { deleteTask, getTaskDetail, getConversationMessages, submitTaskFeedback, listProjects, assignTaskToProject, removeTaskFromProject, type Project } from '@/lib/api'
import { formatCost, formatDate } from '@/lib/utils'
import { exportElementToPdf } from '@/lib/pdf'

const MarkdownContent = dynamic(() => import('./MarkdownContent'), { ssr: false })

// A thread groups multiple task rows that share a conversation_id.
// A standalone task has no conversation_id — shown as a single row.
type HistoryEntry = {
  entry_type: 'thread' | 'task'
  // thread fields
  conversation_id?: string | null
  message_count: number
  total_cost: number
  updated_at: string
  // shared
  id?: string | null       // only set for standalone tasks
  query: string            // first_query for threads, query for tasks
  status: string
  created_at: string
  model_used: string | null
  feedback_signal?: string | null
}

type ThreadMessage = {
  id: string
  query: string
  status: string
  result: string | null
  created_at: string
  execution_time: number | null
  cost: number
  model_used: string | null
  feedback_signal: string | null
}

type TaskDetail = {
  task: ThreadMessage
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

function ProjectPicker({
  taskId,
  projects,
  currentProjectId,
  onAssigned,
  onClose,
}: {
  taskId: string
  projects: Project[]
  currentProjectId: string | null
  onAssigned: (projectId: string | null) => void
  onClose: () => void
}) {
  const [busy, setBusy] = useState<string | null>(null)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose()
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [onClose])

  const handlePick = async (projectId: string) => {
    setBusy(projectId)
    try {
      if (currentProjectId === projectId) {
        await removeTaskFromProject(projectId, taskId)
        onAssigned(null)
      } else {
        await assignTaskToProject(projectId, taskId)
        onAssigned(projectId)
      }
      onClose()
    } catch { /* silently fail */ }
    finally { setBusy(null) }
  }

  return (
    <div
      ref={ref}
      className="absolute right-6 top-full mt-1 z-50 w-52 rounded-xl border border-[color:var(--border)] bg-[color:var(--bg)] shadow-2xl overflow-hidden"
      onClick={e => e.stopPropagation()}
    >
      <div className="px-3 py-2 text-[10px] uppercase tracking-widest text-muted border-b border-[color:var(--border)]/60">
        Add to project
      </div>
      {projects.length === 0 && (
        <p className="px-3 py-2 text-xs text-muted">No projects yet.</p>
      )}
      {projects.map(p => (
        <button
          key={p.id}
          type="button"
          disabled={busy === p.id}
          onClick={() => void handlePick(p.id)}
          className={`w-full flex items-center gap-2 px-3 py-2 text-sm text-left hover:bg-[color:var(--surface-soft)] transition-colors disabled:opacity-50 ${currentProjectId === p.id ? 'text-[color:var(--accent)]' : 'text-[color:var(--text)]'}`}
        >
          <span style={{ width: 8, height: 8, borderRadius: '50%', background: p.color, flexShrink: 0, display: 'inline-block' }} />
          <span className="flex-1 truncate">{p.name}</span>
          {currentProjectId === p.id && <span className="text-xs text-muted shrink-0">✓</span>}
          {busy === p.id && <span className="text-xs text-muted shrink-0">…</span>}
        </button>
      ))}
    </div>
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
      {loadError && (
        <div className="flex items-center gap-3">
          <p className="text-[color:var(--danger)] text-xs">{loadError}</p>
          <button type="button" onClick={() => { setLoadError(null); setLoading(true); getTaskDetail(taskId).then(p => { setDetail(p); if (p.feedback) { setFeedbackSignal(p.feedback.signal); setFeedbackNotes(p.feedback.notes ?? '') } }).catch(e => setLoadError(e instanceof Error ? e.message : String(e))).finally(() => setLoading(false)) }} className="btn-ghost px-2 py-1 rounded text-xs">Retry</button>
        </div>
      )}
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
            <div className="space-y-2">
              <p className="text-muted text-xs italic">No result stored for this task.</p>
              <div className="flex justify-end">
                <button
                  type="button"
                  onClick={onClose}
                  className="btn-ghost px-2 py-1 rounded text-xs text-muted"
                >
                  Collapse
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}

function ThreadPanel({ conversationId, onClose }: { conversationId: string; onClose: () => void }) {
  const [messages, setMessages] = useState<ThreadMessage[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    getConversationMessages(conversationId)
      .then(data => { if (!cancelled) setMessages(data.messages) })
      .catch(e => { if (!cancelled) setError(e instanceof Error ? e.message : String(e)) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [conversationId])

  return (
    <div className="mt-3 border-t border-[color:var(--border)] pt-3 space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-xs text-muted">{messages.length} message{messages.length !== 1 ? 's' : ''} in this thread</span>
        <button type="button" onClick={onClose} className="btn-ghost px-2 py-1 rounded text-xs text-muted">Collapse</button>
      </div>

      {loading && <p className="text-muted text-xs">Loading thread…</p>}
      {error && <p className="text-[color:var(--danger)] text-xs">{error}</p>}

      {messages.map((msg, i) => (
        <div key={msg.id} className="border border-[color:var(--border)] rounded-lg overflow-hidden">
          <div
            role="button"
            tabIndex={0}
            className="flex items-start gap-3 px-3 py-2.5 cursor-pointer hover:bg-[color:var(--surface-soft)] transition-colors"
            onClick={() => setExpanded(p => p === msg.id ? null : msg.id)}
            onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setExpanded(p => p === msg.id ? null : msg.id) } }}
            aria-expanded={expanded === msg.id}
          >
            <span className="text-[10px] text-muted shrink-0 pt-0.5 w-4 text-center">{i + 1}</span>
            <span className="flex-1 text-sm truncate">{msg.query}</span>
            <span className="shrink-0 flex items-center gap-2">
              <StatusBadge status={msg.status} />
              <span className="text-xs text-muted">{formatCost(msg.cost)}</span>
              <span className="text-xs text-muted">{formatDate(msg.created_at)}</span>
            </span>
          </div>
          {expanded === msg.id && msg.result && (
            <div className="border-t border-[color:var(--border)] px-3 py-3 text-sm bg-[color:var(--bg-elev)] leading-relaxed">
              <MarkdownContent content={msg.result} />
            </div>
          )}
          {expanded === msg.id && !msg.result && (
            <p className="border-t border-[color:var(--border)] px-3 py-2 text-xs text-muted italic">No result stored.</p>
          )}
        </div>
      ))}
    </div>
  )
}

const PAGE_SIZE = 15

export default function TaskHistory() {
  const { data, loading, error, refresh } = useHistory()
  const [offset, setOffset] = useState(0)
  const [expanded, setExpanded] = useState<string | null>(null)
  const [expandedThread, setExpandedThread] = useState<string | null>(null)
  const [deleting, setDeleting] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [activeSearch, setActiveSearch] = useState('')
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [projects, setProjects] = useState<Project[]>([])
  const [pickerOpen, setPickerOpen] = useState<string | null>(null)
  // track which project each task belongs to (populated lazily from picker interactions)
  const [taskProjects, setTaskProjects] = useState<Record<string, string | null>>({})

  const loadProjects = useCallback(async () => {
    try { const d = await listProjects(); setProjects(d.projects) } catch { /* silently fail */ }
  }, [])

  useEffect(() => { void loadProjects() }, [loadProjects])

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
  }, [offset, activeSearch, refresh])

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
      <div className="dr-history-controls">
        <input
          type="text"
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Filter by query…"
          className="dr-history-filter-input"
          aria-label="Filter tasks by query"
        />
        <button
          type="button"
          onClick={() => refresh(PAGE_SIZE, offset, activeSearch || undefined)}
          className="dr-dashboard-link"
          aria-label="Refresh task history"
        >
          Refresh
        </button>
      </div>

      {loading && <p className="dr-history-summary">Loading...</p>}
      {error && <p className="dr-history-summary text-error">Error: {error}</p>}

      {!loading && data && (
        <>
          <p className="dr-history-summary">
            {activeSearch
              ? `${data.total} result${data.total !== 1 ? 's' : ''} for "${activeSearch}"`
              : `${data.total} conversation${data.total !== 1 ? 's' : ''}`}
            {data.total > PAGE_SIZE && ` · showing ${offset + 1}–${Math.min(offset + PAGE_SIZE, data.total)}`}
          </p>

          <div>
            <div className="dr-history-head-row">
              <span>Status</span>
              <span>Thread / Query</span>
              <span>Model</span>
              <span className="dr-align-right">Time</span>
              <span className="dr-align-right">Cost</span>
            </div>

            {(Array.isArray(data.tasks) ? data.tasks : []).length === 0 && (
              <div className="dr-history-empty">
                {activeSearch ? `No runs match "${activeSearch}".` : 'No runs yet.'}
              </div>
            )}

            {(Array.isArray(data.tasks) ? data.tasks as HistoryEntry[] : []).map((entry) => {
              const isThread = entry.entry_type === 'thread'
              // Threads are keyed by conversation_id, standalone tasks by id
              const rowKey = isThread ? entry.conversation_id! : entry.id!
              const isExpanded = expanded === rowKey
              const displayQuery = entry.query

              return (
                <div key={rowKey}>
                  <div
                    role="button"
                    tabIndex={0}
                    aria-label={isExpanded ? `Collapse: ${displayQuery}` : `Expand: ${displayQuery}`}
                    className="dr-history-data-row"
                    onClick={() => toggleExpand(rowKey)}
                    onKeyDown={e => rowKeyToggle(e, rowKey)}
                  >
                    <span className="dr-inline-status">
                      <StatusBadge status={entry.status} />
                      {!isThread && entry.feedback_signal && <FeedbackHint signal={entry.feedback_signal} />}
                    </span>
                    <span className="dr-row-query flex items-center gap-2" title={displayQuery}>
                      {isThread && (
                        <span className="shrink-0 text-[10px] px-1.5 py-0.5 rounded-full border border-[color:var(--accent)]/40 bg-[color:var(--accent)]/10 text-[color:var(--accent)] font-medium">
                          💬 {entry.message_count}
                        </span>
                      )}
                      <span className="truncate">{displayQuery}</span>
                    </span>
                    <code className="dr-code dr-code-start" title={entry.model_used ?? ''}>{(entry.model_used ?? 'unknown').split('/').pop()}</code>
                    <span className="dr-row-time">{formatDate(isThread ? entry.updated_at : entry.created_at)}</span>
                    <span className="dr-row-cost">{formatCost(entry.total_cost)}</span>
                    <div className="relative flex items-center gap-1.5" onClick={e => e.stopPropagation()} onKeyDown={e => e.stopPropagation()}>
                      {!isThread && entry.conversation_id && (
                        <button
                          type="button"
                          onClick={() => setExpandedThread(p => p === entry.conversation_id ? null : entry.conversation_id!)}
                          className="text-xs text-muted hover:text-[color:var(--accent)] transition-colors"
                          aria-label="View conversation thread"
                          title="View thread"
                        >
                          💬
                        </button>
                      )}
                      {!isThread && entry.id && (
                        <>
                          <button
                            type="button"
                            onClick={() => { setPickerOpen(p => p === entry.id ? null : entry.id!) }}
                            className="text-xs text-muted hover:text-[color:var(--accent)] transition-colors"
                            aria-label="Add to project"
                            title="Add to project"
                          >
                            📁
                          </button>
                          <button
                            type="button"
                            onClick={() => handleDelete(entry.id!)}
                            disabled={deleting === entry.id}
                            className="text-xs text-muted hover:text-[color:var(--danger)] transition-colors disabled:opacity-50"
                            aria-label="Delete task"
                            title="Delete task"
                          >
                            {deleting === entry.id ? '…' : '✕'}
                          </button>
                          {pickerOpen === entry.id && (
                            <ProjectPicker
                              taskId={entry.id}
                              projects={projects}
                              currentProjectId={taskProjects[entry.id] ?? null}
                              onAssigned={pid => setTaskProjects(prev => ({ ...prev, [entry.id!]: pid }))}
                              onClose={() => setPickerOpen(null)}
                            />
                          )}
                        </>
                      )}
                    </div>
                  </div>

                  {isExpanded && isThread && entry.conversation_id && (
                    <ThreadPanel
                      conversationId={entry.conversation_id}
                      onClose={() => setExpanded(null)}
                    />
                  )}
                  {!isThread && entry.conversation_id && expandedThread === entry.conversation_id && (
                    <ThreadPanel
                      conversationId={entry.conversation_id}
                      onClose={() => setExpandedThread(null)}
                    />
                  )}
                  {isExpanded && !isThread && entry.id && (
                    <TaskDetailPanel
                      taskId={entry.id}
                      onClose={() => setExpanded(null)}
                      onFeedbackSaved={() => refresh(PAGE_SIZE, offset, activeSearch || undefined)}
                    />
                  )}
                </div>
              )
            })}
          </div>

          {data.total > PAGE_SIZE && (
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
        </>
      )}
    </div>
  )
}