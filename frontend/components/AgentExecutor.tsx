'use client'

import { useState, useMemo, useEffect, useCallback, useRef } from 'react'
import dynamic from 'next/dynamic'
import { useAgentStream, StreamEvent } from '@/lib/hooks'
import { submitTaskFeedback } from '@/lib/api'
import { formatCost } from '@/lib/utils'

const MarkdownContent = dynamic(() => import('./MarkdownContent'), { ssr: false })

function ToolCallEvent({ event }: { event: StreamEvent }) {
  const [open, setOpen] = useState(false)
  const hasInput = !!event.tool_input && Object.keys(event.tool_input).length > 0
  return (
    <div className="bg-[color:var(--bg-elev)] border border-[color:var(--border)] rounded p-2 text-xs">
      <button
        onClick={() => setOpen(o => !o)}
        className="flex items-center gap-2 w-full text-left"
      >
        <span className="text-[color:var(--warn)] font-medium">⚙ {event.tool_name}</span>
        {hasInput && (
          <span className="text-muted ml-auto">{open ? '▲ hide' : '▼ show'}</span>
        )}
      </button>
      {open && hasInput && (
        <pre className="mt-2 text-muted overflow-x-auto whitespace-pre-wrap">
          {JSON.stringify(event.tool_input, null, 2)}
        </pre>
      )}
    </div>
  )
}

function ToolResultEvent({ event }: { event: StreamEvent }) {
  const text = String(event.tool_result ?? '')
  const [open, setOpen] = useState(false)
  const truncated = text.length > 300
  const preview = truncated ? text.slice(0, 300) + '…' : text
  return (
    <div className="text-[color:var(--success)] text-xs bg-[color:var(--bg-elev)] border border-[color:var(--border)] rounded p-2">
      <button
        onClick={() => setOpen(o => !o)}
        className="flex items-center gap-2 w-full text-left"
        disabled={!truncated}
      >
        <span>✓ {open ? text : preview}</span>
        {truncated && (
          <span className="text-muted ml-auto shrink-0">{open ? '▲ less' : '▼ more'}</span>
        )}
      </button>
    </div>
  )
}

function EventLine({ event }: { event: StreamEvent }) {
  switch (event.type) {
    case 'user_message':
      return (
        <div className="flex justify-end">
          <div className="max-w-[85%] bg-[color:var(--accent-2)]/15 border border-[color:var(--accent-2)]/35 rounded-2xl rounded-br-md px-3 py-2 text-sm text-[color:var(--text)]">
            <MarkdownContent content={event.content ?? ''} />
          </div>
        </div>
      )
    case 'turn_divider':
      return (
        <div className="relative py-2">
          <div className="h-px bg-[color:var(--border)]" />
          <span className="absolute left-1/2 -translate-x-1/2 -top-1 bg-[color:var(--bg)] px-2 text-[10px] tracking-wide uppercase text-muted">
            {event.content ?? 'Follow-up run'}
          </span>
        </div>
      )
    case 'status':
      return <p className="text-muted text-sm">▷ {event.content ?? event.message}</p>
    case 'thinking':
      return <p className="text-[color:var(--accent-2)] text-sm italic">💭 {event.content}</p>
    case 'tool_call':
      return <ToolCallEvent event={event} />
    case 'tool_result':
      return <ToolResultEvent event={event} />
    case 'text_delta':
      return (
        <div className="flex justify-start">
          <div className="max-w-[85%] bg-[color:var(--surface-soft)] border border-[color:var(--border)] rounded-2xl rounded-bl-md px-3 py-2 text-[color:var(--text)] text-sm">
            <MarkdownContent content={event.content ?? ''} />
          </div>
        </div>
      )
    case 'done':
      return (
        <p className="text-[color:var(--success)] text-sm border-t border-[color:var(--border)] pt-2 mt-1">
          ✓ Done{event.cost != null ? ` — cost: ${formatCost(event.cost)}` : ''}
        </p>
      )
    case 'error':
      return <p className="text-[color:var(--danger)] text-sm">✗ {event.error}</p>
    default:
      return null
  }
}

function ContextBar({ events }: { events: StreamEvent[] }) {
  const ctx = useMemo(() => {
    for (let i = events.length - 1; i >= 0; i--) {
      if (events[i].type === 'context') return events[i]
    }
    return null
  }, [events])

  if (!ctx || ctx.context_percent == null) return null

  const pct = ctx.context_percent
  const color = pct >= 90 ? 'bg-[color:var(--danger)]' : pct >= 70 ? 'bg-[color:var(--warn)]' : 'bg-[color:var(--accent-2)]'
  const label = pct >= 70 ? (pct >= 90 ? 'critical' : 'compacting soon') : 'ok'
  const widthClass = (() => {
    const clamped = Math.max(0, Math.min(pct, 100))
    if (clamped >= 100) return 'w-full'
    if (clamped >= 95) return 'w-[95%]'
    if (clamped >= 90) return 'w-[90%]'
    if (clamped >= 80) return 'w-[80%]'
    if (clamped >= 70) return 'w-[70%]'
    if (clamped >= 60) return 'w-[60%]'
    if (clamped >= 50) return 'w-1/2'
    if (clamped >= 40) return 'w-[40%]'
    if (clamped >= 30) return 'w-[30%]'
    if (clamped >= 20) return 'w-1/5'
    if (clamped >= 10) return 'w-[10%]'
    if (clamped > 0) return 'w-[5%]'
    return 'w-0'
  })()

  return (
    <div className="flex items-center gap-2 text-xs text-muted">
      <span>context</span>
      <div className="flex-1 max-w-32 h-1.5 bg-[color:var(--bg-elev)] border border-[color:var(--border)] rounded-full overflow-hidden">
        <div className={`h-full rounded-full transition-all ${color} ${widthClass}`} />
      </div>
      <span className={pct >= 70 ? 'text-[color:var(--warn)]' : ''}>{pct.toFixed(0)}% — {label}</span>
      {ctx.context_tokens_used != null && (
        <span className="text-muted/80">{ctx.context_tokens_used.toLocaleString()} / {ctx.context_tokens_max?.toLocaleString()} tokens</span>
      )}
    </div>
  )
}

export default function AgentExecutor() {
  const THINKING_PREF_KEY = 'agent_ui_show_thinking_live'
  const [query, setQuery] = useState('')
  const [context, setContext] = useState('')
  const [editLastOpen, setEditLastOpen] = useState(false)
  const [editLastText, setEditLastText] = useState('')
  const [showThinkingLive, setShowThinkingLive] = useState(false)
  const [openThinkingByTurn, setOpenThinkingByTurn] = useState<Record<number, boolean>>({})
  const [showJumpToLatest, setShowJumpToLatest] = useState(false)
  const [copyLabel, setCopyLabel] = useState('Copy response')
  const [feedbackSignal, setFeedbackSignal] = useState<'up' | 'down'>('up')
  const [feedbackNotes, setFeedbackNotes] = useState('')
  const [feedbackSaving, setFeedbackSaving] = useState(false)
  const [feedbackSaved, setFeedbackSaved] = useState(false)
  const [feedbackError, setFeedbackError] = useState<string | null>(null)
  const { events, isRunning, error, conversationId, run, reset, stop, newConversation } = useAgentStream()

  // Merge consecutive text_delta events into a single node for cleaner rendering
  const merged = useMemo(() => {
    const out: StreamEvent[] = []
    for (const ev of events) {
      if (ev.type === 'text_delta') {
        const last = out[out.length - 1]
        if (last?.type === 'text_delta') {
          last.content = (last.content ?? '') + (ev.content ?? '')
          continue
        }
      }
      out.push({ ...ev })
    }
    return out
  }, [events])

  // Build exportable text: file writes first, then the LLM text response
  const fileWrites = merged
    .filter(ev => ev.type === 'tool_call' && ev.tool_name === 'file_operations' && ev.tool_input?.operation === 'write')
    .map(ev => {
      const path = ev.tool_input?.path as string | undefined
      const content = ev.tool_input?.content as string | undefined
      return path && content ? `=== ${path} ===\n${content}` : null
    })
    .filter(Boolean)
    .join('\n\n')

  const textResponse = merged
    .filter(ev => ev.type === 'text_delta')
    .map(ev => ev.content ?? '')
    .join('')

  const responseText = [fileWrites, textResponse].filter(Boolean).join('\n\n')

  const lastUserMessage = useMemo(() => {
    for (let i = merged.length - 1; i >= 0; i--) {
      if (merged[i].type === 'user_message' && (merged[i].content || '').trim()) {
        return (merged[i].content || '').trim()
      }
    }
    return ''
  }, [merged])

  const turnItems = useMemo(() => {
    type TurnItem = {
      kind: 'turn'
      id: number
      user?: StreamEvent
      events: StreamEvent[]
      thinking: StreamEvent[]
    }
    type DividerItem = { kind: 'divider'; event: StreamEvent }

    const items: Array<TurnItem | DividerItem> = []
    let current: TurnItem | null = null
    let nextId = 1

    const flush = () => {
      if (!current) return
      if (current.user || current.events.length > 0 || current.thinking.length > 0) {
        items.push(current)
      }
      current = null
    }

    for (const ev of merged) {
      if (ev.type === 'turn_divider') {
        flush()
        items.push({ kind: 'divider', event: ev })
        continue
      }

      if (ev.type === 'user_message') {
        flush()
        current = {
          kind: 'turn',
          id: nextId++,
          user: ev,
          events: [],
          thinking: [],
        }
        continue
      }

      if (!current) {
        current = {
          kind: 'turn',
          id: nextId++,
          events: [],
          thinking: [],
        }
      }

      if (ev.type === 'thinking') current.thinking.push(ev)
      else current.events.push(ev)
    }

    flush()
    return items
  }, [merged])

  const isDone = merged.some(ev => ev.type === 'done')
  const latestTaskId = useMemo(() => {
    for (let i = merged.length - 1; i >= 0; i--) {
      if (merged[i].task_id) return merged[i].task_id ?? null
    }
    return null
  }, [merged])

  const eventsEndRef = useRef<HTMLDivElement>(null)
  const eventsContainerRef = useRef<HTMLDivElement>(null)

  const formatTs = useCallback((ts?: number) => {
    if (!ts) return ''
    return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  }, [])

  const formatDuration = useCallback((ms: number) => {
    const seconds = ms / 1000
    if (seconds < 10) return `${seconds.toFixed(1)}s`
    if (seconds < 60) return `${Math.round(seconds)}s`
    const mins = Math.floor(seconds / 60)
    const secs = Math.round(seconds % 60)
    return `${mins}m ${secs}s`
  }, [])

  // Auto-scroll the events container to bottom as new events arrive
  useEffect(() => {
    requestAnimationFrame(() => {
      eventsEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    })
  }, [events, isRunning])

  useEffect(() => {
    setFeedbackSignal('up')
    setFeedbackNotes('')
    setFeedbackSaving(false)
    setFeedbackSaved(false)
    setFeedbackError(null)
  }, [latestTaskId])

  useEffect(() => {
    if (typeof window === 'undefined') return
    const raw = localStorage.getItem(THINKING_PREF_KEY)
    if (raw === '1') setShowThinkingLive(true)
  }, [THINKING_PREF_KEY])

  useEffect(() => {
    if (typeof window === 'undefined') return
    localStorage.setItem(THINKING_PREF_KEY, showThinkingLive ? '1' : '0')
  }, [THINKING_PREF_KEY, showThinkingLive])

  useEffect(() => {
    if (!editLastOpen) {
      setEditLastText(lastUserMessage)
    }
  }, [lastUserMessage, editLastOpen])

  const handleCopy = useCallback(async () => {
    if (!responseText) return
    await navigator.clipboard.writeText(responseText)
    setCopyLabel('Copied!')
    setTimeout(() => setCopyLabel('Copy response'), 2000)
  }, [responseText])

  const handleDownload = useCallback(() => {
    if (!responseText) return
    const writes = merged.filter(ev => ev.type === 'tool_call' && ev.tool_name === 'file_operations' && ev.tool_input?.operation === 'write')
    const filename = writes.length === 1
      ? String(writes[0].tool_input?.path ?? '').split('/').pop() || `agent-response-${Date.now()}.txt`
      : `agent-response-${Date.now()}.txt`
    const blob = new Blob([responseText], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  }, [responseText, merged])

  const handleSaveFeedback = useCallback(async () => {
    if (!latestTaskId) return
    setFeedbackSaving(true)
    setFeedbackError(null)
    try {
      await submitTaskFeedback(latestTaskId, {
        signal: feedbackSignal,
        notes: feedbackNotes,
      })
      setFeedbackSaved(true)
      setTimeout(() => setFeedbackSaved(false), 2500)
    } catch (err) {
      setFeedbackError(err instanceof Error ? err.message : 'Failed to save feedback')
    } finally {
      setFeedbackSaving(false)
    }
  }, [latestTaskId, feedbackSignal, feedbackNotes])

  const handleRegenerate = useCallback(() => {
    if (!lastUserMessage || isRunning) return
    run(lastUserMessage, context.trim() || undefined, conversationId)
  }, [lastUserMessage, isRunning, run, context, conversationId])

  const handleResendEdited = useCallback(() => {
    const text = editLastText.trim()
    if (!text || isRunning) return
    run(text, context.trim() || undefined, conversationId)
    setEditLastOpen(false)
    setQuery('')
  }, [editLastText, isRunning, run, context, conversationId])

  const toggleTurnThinking = useCallback((turnId: number) => {
    setOpenThinkingByTurn(prev => ({ ...prev, [turnId]: !prev[turnId] }))
  }, [])

  const handleEventsScroll = useCallback(() => {
    const el = eventsContainerRef.current
    if (!el) return
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight
    setShowJumpToLatest(distanceFromBottom > 140)
  }, [])

  const jumpToLatest = useCallback(() => {
    eventsEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    setShowJumpToLatest(false)
  }, [])

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!query.trim() || isRunning) return
    const nextQuery = query.trim()
    run(nextQuery, context.trim() || undefined, conversationId)
    setQuery('')
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      if (!query.trim() || isRunning) return
      const nextQuery = query.trim()
      run(nextQuery, context.trim() || undefined, conversationId)
      setQuery('')
    }
  }

  return (
    <div className="flex flex-col h-full gap-3">

      {/* ── Events log — fills all available space ── */}
      <div className="flex-1 min-h-0 flex flex-col">
        {merged.length > 0 ? (
          <div className="flex flex-col h-full">
            {/* Copy / Download toolbar */}
            {isDone && responseText && (
              <div className="space-y-3 mb-2 shrink-0">
                <div className="flex gap-2 justify-end">
                  <button
                    type="button"
                    onClick={handleCopy}
                    className="btn-ghost px-3 py-1.5 rounded-lg text-xs"
                  >
                    {copyLabel}
                  </button>
                  <button
                    type="button"
                    onClick={handleDownload}
                    className="btn-ghost px-3 py-1.5 rounded-lg text-xs"
                  >
                    Download .txt
                  </button>
                </div>

                {latestTaskId && (
                  <div className="panel panel-soft rounded-lg p-3 space-y-3">
                    <div className="flex items-center justify-between gap-3 flex-wrap">
                      <p className="text-xs text-muted">Teach the agent from this response</p>
                      <span className="text-xs text-muted font-mono">task: {latestTaskId.slice(0, 8)}…</span>
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
                      <label htmlFor="live-feedback-notes" className="block text-xs text-muted mb-1">
                        Notes for future behavior
                      </label>
                      <textarea
                        id="live-feedback-notes"
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
                        className="btn-accent px-3 py-1.5 rounded text-xs disabled:opacity-50"
                      >
                        {feedbackSaving ? 'Saving…' : 'Save feedback'}
                      </button>
                      {feedbackSaved && <span className="text-xs text-[color:var(--success)]">Feedback saved</span>}
                      {feedbackError && <span className="text-xs text-[color:var(--danger)]">{feedbackError}</span>}
                    </div>
                  </div>
                )}
              </div>
            )}
            <div
              ref={eventsContainerRef}
              onScroll={handleEventsScroll}
              className="flex-1 min-h-0 overflow-y-auto bg-[color:var(--bg-elev)] rounded-xl border border-[color:var(--border)] p-4 space-y-2 font-mono text-sm relative"
            >
              {turnItems.map((item, i) => {
                if (item.kind === 'divider') {
                  return <EventLine key={`divider-${i}`} event={item.event} />
                }

                const turnDoneEvent = [...item.events].reverse().find(ev => ev.type === 'done')
                const turnStartedAt = item.user?.client_ts
                const turnEndedAt = turnDoneEvent?.client_ts
                const turnDuration = turnStartedAt && turnEndedAt ? Math.max(0, turnEndedAt - turnStartedAt) : null

                return (
                  <div key={`turn-${item.id}`} className="space-y-2">
                    {(turnStartedAt || turnDuration) && (
                      <div className="flex items-center gap-2 text-[10px] text-muted ml-1">
                        {turnStartedAt ? <span>{formatTs(turnStartedAt)}</span> : null}
                        {turnDuration != null ? <span>• {formatDuration(turnDuration)}</span> : null}
                      </div>
                    )}
                    {item.user && <EventLine event={item.user} />}

                    {showThinkingLive && item.thinking.map((ev, idx) => (
                      <EventLine key={`turn-${item.id}-thinking-live-${idx}`} event={ev} />
                    ))}

                    {item.events.map((ev, idx) => (
                      <EventLine key={`turn-${item.id}-event-${idx}`} event={ev} />
                    ))}

                    {item.thinking.length > 0 && (
                      <div className="ml-1 mr-8 panel panel-soft rounded-lg p-2 space-y-2">
                        <div className="flex items-center justify-between gap-2 flex-wrap">
                          <p className="text-xs text-muted">
                            Reasoning for this turn: {item.thinking.length} {item.thinking.length === 1 ? 'event' : 'events'}
                          </p>
                          <button
                            type="button"
                            onClick={() => toggleTurnThinking(item.id)}
                            className="btn-ghost px-2 py-1 rounded text-xs"
                          >
                            {openThinkingByTurn[item.id] ? 'Hide reasoning' : 'View reasoning'}
                          </button>
                        </div>

                        {openThinkingByTurn[item.id] && (
                          <div className="max-h-40 overflow-y-auto space-y-2 pr-1">
                            {item.thinking.map((ev, idx) => (
                              <div key={`turn-${item.id}-thinking-${idx}`} className="bg-[color:var(--bg-elev)] border border-[color:var(--border)] rounded px-2 py-1.5 text-xs text-[color:var(--text)]">
                                <span className="text-[color:var(--accent-2)] mr-1">💭</span>
                                {ev.content || '(empty reasoning event)'}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )
              })}
              {isRunning && (
                <div className="flex justify-start">
                  <div className="max-w-[85%] bg-[color:var(--surface-soft)] border border-[color:var(--border)] rounded-2xl rounded-bl-md px-3 py-2 text-muted text-sm">
                    <span className="inline-flex items-center gap-2">
                      <span>Assistant is typing</span>
                      <span className="inline-flex gap-1">
                        <span className="w-1.5 h-1.5 rounded-full bg-[color:var(--accent-2)] animate-bounce [animation-delay:-0.2s]" />
                        <span className="w-1.5 h-1.5 rounded-full bg-[color:var(--accent-2)] animate-bounce [animation-delay:-0.1s]" />
                        <span className="w-1.5 h-1.5 rounded-full bg-[color:var(--accent-2)] animate-bounce" />
                      </span>
                    </span>
                  </div>
                </div>
              )}

              {showJumpToLatest && (
                <button
                  type="button"
                  onClick={jumpToLatest}
                  className="absolute bottom-3 right-3 btn-accent px-3 py-1.5 rounded-full text-xs shadow-lg"
                >
                  Jump to latest
                </button>
              )}
              <div ref={eventsEndRef} />
            </div>
          </div>
        ) : (
          <div className="flex-1 min-h-0 flex items-center justify-center text-muted text-sm select-none text-center px-6">
            <div>
              <p>Start chatting to see responses here.</p>
              <p className="text-xs text-muted/90 mt-2">Enter to send, Shift+Enter for newline. Reasoning can stay hidden until you need it.</p>
            </div>
          </div>
        )}
      </div>

      {/* ── Bottom controls — pinned ── */}
      <div className="shrink-0 space-y-3 sticky bottom-0 bg-[color:var(--bg)]/95 backdrop-blur-sm pt-2 border-t border-[color:var(--border)]">
        <ContextBar events={events} />

        <div className="flex items-center gap-2">
          <label className="flex items-center gap-2 text-xs text-muted">
            <input
              type="checkbox"
              checked={showThinkingLive}
              onChange={e => setShowThinkingLive(e.target.checked)}
              className="w-3.5 h-3.5 accent-[color:var(--accent)]"
            />
            Show reasoning while streaming
          </label>
        </div>

        {!isRunning && lastUserMessage && (
          <div className="flex items-center gap-2 flex-wrap">
            <button
              type="button"
              onClick={handleRegenerate}
              className="btn-ghost px-3 py-1.5 rounded-lg text-xs"
            >
              Regenerate last response
            </button>
            <button
              type="button"
              onClick={() => {
                setEditLastOpen(v => !v)
                setEditLastText(lastUserMessage)
              }}
              className="btn-ghost px-3 py-1.5 rounded-lg text-xs"
            >
              {editLastOpen ? 'Close edit' : 'Edit & resend last message'}
            </button>
          </div>
        )}

        {editLastOpen && !isRunning && (
          <div className="panel panel-soft rounded-lg p-3 space-y-2">
            <label htmlFor="edit-last-message" className="block text-xs text-muted">Edit last user message</label>
            <textarea
              id="edit-last-message"
              value={editLastText}
              onChange={e => setEditLastText(e.target.value)}
              rows={3}
              className="w-full bg-[color:var(--bg-elev)] rounded-lg px-3 py-2 text-sm border border-[color:var(--border)] focus:outline-none focus:border-[color:var(--accent)] resize-none"
            />
            <div className="flex gap-2">
              <button
                type="button"
                onClick={handleResendEdited}
                disabled={!editLastText.trim()}
                className="btn-accent px-3 py-1.5 rounded text-xs disabled:opacity-50"
              >
                Resend edited message
              </button>
            </div>
          </div>
        )}

        {error && (
          <div className="border border-[color:var(--danger)]/45 bg-[color:var(--danger)]/10 rounded-lg p-3 text-[color:var(--danger)] text-sm">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label className="block text-sm text-muted mb-1">Context <span className="text-muted/70">(optional)</span></label>
            <textarea
              value={context}
              onChange={e => setContext(e.target.value)}
              placeholder="Additional context or constraints..."
              rows={2}
              disabled={isRunning}
              className="w-full bg-[color:var(--bg-elev)] rounded-lg px-3 py-2 text-sm border border-[color:var(--border)] focus:outline-none focus:border-[color:var(--accent)] resize-none disabled:opacity-50"
            />
          </div>
          <div>
            <label className="block text-sm text-muted mb-1">Query</label>
            <textarea
              value={query}
              onChange={e => setQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Message the agent (Enter to send, Shift+Enter for newline)"
              rows={3}
              disabled={isRunning}
              className="w-full bg-[color:var(--bg-elev)] rounded-lg px-3 py-2 text-sm border border-[color:var(--border)] focus:outline-none focus:border-[color:var(--accent)] resize-none disabled:opacity-50"
            />
          </div>
          <div className="flex gap-3 items-center flex-wrap">
            <button
              type="submit"
              disabled={isRunning || !query.trim()}
              className="btn-accent px-4 py-2 rounded-lg text-sm disabled:opacity-50"
            >
              {isRunning ? 'Running…' : 'Run Agent'}
            </button>
            {isRunning && (
              <button
                type="button"
                onClick={stop}
                className="px-4 py-2 border border-[color:var(--danger)]/50 bg-[color:var(--danger)]/15 text-[color:var(--danger)] rounded-lg text-sm transition-colors hover:bg-[color:var(--danger)]/25"
              >
                Stop
              </button>
            )}
            {(merged.length > 0 || error) && !isRunning && (
              <button
                type="button"
                onClick={reset}
                className="btn-ghost px-4 py-2 rounded-lg text-sm"
              >
                Clear
              </button>
            )}
            {conversationId && !isRunning && (
              <button
                type="button"
                onClick={newConversation}
                className="btn-ghost px-4 py-2 rounded-lg text-sm"
              >
                New Conversation
              </button>
            )}
            {conversationId && (
              <span className="text-xs text-muted font-mono">
                thread: {conversationId.slice(0, 8)}…
              </span>
            )}
          </div>
        </form>
      </div>
    </div>
  )
}
