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
    <div className="bg-gray-800 rounded p-2 text-xs">
      <button
        onClick={() => setOpen(o => !o)}
        className="flex items-center gap-2 w-full text-left"
      >
        <span className="text-yellow-400 font-medium">⚙ {event.tool_name}</span>
        {hasInput && (
          <span className="text-gray-500 ml-auto">{open ? '▲ hide' : '▼ show'}</span>
        )}
      </button>
      {open && hasInput && (
        <pre className="mt-2 text-gray-400 overflow-x-auto whitespace-pre-wrap">
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
    <div className="text-green-400 text-xs bg-gray-800 rounded p-2">
      <button
        onClick={() => setOpen(o => !o)}
        className="flex items-center gap-2 w-full text-left"
        disabled={!truncated}
      >
        <span>✓ {open ? text : preview}</span>
        {truncated && (
          <span className="text-gray-500 ml-auto shrink-0">{open ? '▲ less' : '▼ more'}</span>
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
          <div className="max-w-[85%] bg-indigo-600/20 border border-indigo-500/40 rounded-2xl rounded-br-md px-3 py-2 text-sm text-indigo-100">
            <MarkdownContent content={event.content ?? ''} />
          </div>
        </div>
      )
    case 'turn_divider':
      return (
        <div className="relative py-2">
          <div className="h-px bg-gray-800" />
          <span className="absolute left-1/2 -translate-x-1/2 -top-1 bg-gray-900 px-2 text-[10px] tracking-wide uppercase text-gray-500">
            {event.content ?? 'Follow-up run'}
          </span>
        </div>
      )
    case 'status':
      return <p className="text-gray-400 text-sm">▷ {event.content ?? event.message}</p>
    case 'thinking':
      return <p className="text-purple-400 text-sm italic">💭 {event.content}</p>
    case 'tool_call':
      return <ToolCallEvent event={event} />
    case 'tool_result':
      return <ToolResultEvent event={event} />
    case 'text_delta':
      return (
        <div className="flex justify-start">
          <div className="max-w-[85%] bg-gray-800/70 border border-gray-700 rounded-2xl rounded-bl-md px-3 py-2 text-gray-100 text-sm">
            <MarkdownContent content={event.content ?? ''} />
          </div>
        </div>
      )
    case 'done':
      return (
        <p className="text-green-400 text-sm border-t border-gray-800 pt-2 mt-1">
          ✓ Done{event.cost != null ? ` — cost: ${formatCost(event.cost)}` : ''}
        </p>
      )
    case 'error':
      return <p className="text-red-400 text-sm">✗ {event.error}</p>
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
  const color = pct >= 90 ? 'bg-red-500' : pct >= 70 ? 'bg-yellow-500' : 'bg-indigo-500'
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
    <div className="flex items-center gap-2 text-xs text-gray-400">
      <span>context</span>
      <div className="flex-1 max-w-32 h-1.5 bg-gray-800 rounded-full overflow-hidden">
        <div className={`h-full rounded-full transition-all ${color} ${widthClass}`} />
      </div>
      <span className={pct >= 70 ? 'text-yellow-400' : ''}>{pct.toFixed(0)}% — {label}</span>
      {ctx.context_tokens_used != null && (
        <span className="text-gray-600">{ctx.context_tokens_used.toLocaleString()} / {ctx.context_tokens_max?.toLocaleString()} tokens</span>
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
  const feedbackSavedTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

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
    if (feedbackSavedTimerRef.current) clearTimeout(feedbackSavedTimerRef.current)
    setFeedbackSignal('up')
    setFeedbackNotes('')
    setFeedbackSaving(false)
    setFeedbackSaved(false)
    setFeedbackError(null)
  }, [latestTaskId])

  useEffect(() => {
    return () => {
      if (feedbackSavedTimerRef.current) clearTimeout(feedbackSavedTimerRef.current)
    }
  }, [])

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
      if (feedbackSavedTimerRef.current) clearTimeout(feedbackSavedTimerRef.current)
      feedbackSavedTimerRef.current = setTimeout(() => setFeedbackSaved(false), 2500)
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
                    onClick={handleCopy}
                    className="px-3 py-1.5 bg-gray-800 hover:bg-gray-700 rounded-lg text-xs text-gray-300 transition-colors"
                  >
                    {copyLabel}
                  </button>
                  <button
                    onClick={handleDownload}
                    className="px-3 py-1.5 bg-gray-800 hover:bg-gray-700 rounded-lg text-xs text-gray-300 transition-colors"
                  >
                    Download .txt
                  </button>
                </div>

                {latestTaskId && (
                  <div className="bg-gray-900/60 border border-gray-800 rounded-lg p-3 space-y-3">
                    <div className="flex items-center justify-between gap-3 flex-wrap">
                      <p className="text-xs text-gray-400">Teach the agent from this response</p>
                      <span className="text-xs text-gray-600 font-mono">task: {latestTaskId.slice(0, 8)}…</span>
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
                      <label htmlFor="live-feedback-notes" className="block text-xs text-gray-400 mb-1">
                        Notes for future behavior
                      </label>
                      <textarea
                        id="live-feedback-notes"
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
                      {feedbackError && <span className="text-xs text-red-400">{feedbackError}</span>}
                    </div>
                  </div>
                )}
              </div>
            )}
            <div
              ref={eventsContainerRef}
              onScroll={handleEventsScroll}
              className="flex-1 min-h-0 overflow-y-auto bg-gray-900 rounded-xl border border-gray-800 p-4 space-y-2 font-mono text-sm relative"
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
                      <div className="flex items-center gap-2 text-[10px] text-gray-500 ml-1">
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
                      <div className="ml-1 mr-8 bg-gray-900/60 border border-gray-800 rounded-lg p-2 space-y-2">
                        <div className="flex items-center justify-between gap-2 flex-wrap">
                          <p className="text-xs text-gray-400">
                            Reasoning for this turn: {item.thinking.length} {item.thinking.length === 1 ? 'event' : 'events'}
                          </p>
                          <button
                            type="button"
                            onClick={() => toggleTurnThinking(item.id)}
                            className="px-2 py-1 bg-gray-800 hover:bg-gray-700 rounded text-xs text-gray-300 transition-colors"
                          >
                            {openThinkingByTurn[item.id] ? 'Hide reasoning' : 'View reasoning'}
                          </button>
                        </div>

                        {openThinkingByTurn[item.id] && (
                          <div className="max-h-40 overflow-y-auto space-y-2 pr-1">
                            {item.thinking.map((ev, idx) => (
                              <div key={`turn-${item.id}-thinking-${idx}`} className="bg-gray-800/80 border border-gray-700 rounded px-2 py-1.5 text-xs text-purple-200">
                                <span className="text-purple-400 mr-1">💭</span>
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
                  <div className="max-w-[85%] bg-gray-800/70 border border-gray-700 rounded-2xl rounded-bl-md px-3 py-2 text-gray-300 text-sm">
                    <span className="inline-flex items-center gap-2">
                      <span>Assistant is typing</span>
                      <span className="inline-flex gap-1">
                        <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 animate-bounce [animation-delay:-0.2s]" />
                        <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 animate-bounce [animation-delay:-0.1s]" />
                        <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 animate-bounce" />
                      </span>
                    </span>
                  </div>
                </div>
              )}

              {showJumpToLatest && (
                <button
                  type="button"
                  onClick={jumpToLatest}
                  className="absolute bottom-3 right-3 px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 rounded-full text-xs font-medium text-white shadow-lg transition-colors"
                >
                  Jump to latest
                </button>
              )}
              <div ref={eventsEndRef} />
            </div>
          </div>
        ) : (
          <div className="flex-1 min-h-0 flex items-center justify-center text-gray-600 text-sm select-none text-center px-6">
            <div>
              <p>Start chatting to see responses here.</p>
              <p className="text-xs text-gray-500 mt-2">Enter to send, Shift+Enter for newline. Reasoning can stay hidden until you need it.</p>
            </div>
          </div>
        )}
      </div>

      {/* ── Bottom controls — pinned ── */}
      <div className="shrink-0 space-y-3 sticky bottom-0 bg-gray-950/95 backdrop-blur-sm pt-2 border-t border-gray-800">
        <ContextBar events={events} />

        <div className="flex items-center gap-2">
          <label className="flex items-center gap-2 text-xs text-gray-400">
            <input
              type="checkbox"
              checked={showThinkingLive}
              onChange={e => setShowThinkingLive(e.target.checked)}
              className="w-3.5 h-3.5 accent-indigo-500"
            />
            Show reasoning while streaming
          </label>
        </div>

        {!isRunning && lastUserMessage && (
          <div className="flex items-center gap-2 flex-wrap">
            <button
              type="button"
              onClick={handleRegenerate}
              className="px-3 py-1.5 bg-gray-800 hover:bg-gray-700 rounded-lg text-xs text-gray-300 transition-colors"
            >
              Regenerate last response
            </button>
            <button
              type="button"
              onClick={() => {
                setEditLastOpen(v => !v)
                setEditLastText(lastUserMessage)
              }}
              className="px-3 py-1.5 bg-gray-800 hover:bg-gray-700 rounded-lg text-xs text-gray-300 transition-colors"
            >
              {editLastOpen ? 'Close edit' : 'Edit & resend last message'}
            </button>
          </div>
        )}

        {editLastOpen && !isRunning && (
          <div className="bg-gray-900/70 border border-gray-800 rounded-lg p-3 space-y-2">
            <label htmlFor="edit-last-message" className="block text-xs text-gray-400">Edit last user message</label>
            <textarea
              id="edit-last-message"
              value={editLastText}
              onChange={e => setEditLastText(e.target.value)}
              rows={3}
              className="w-full bg-gray-900 rounded-lg px-3 py-2 text-sm border border-gray-700 focus:outline-none focus:border-indigo-500 resize-none"
            />
            <div className="flex gap-2">
              <button
                type="button"
                onClick={handleResendEdited}
                disabled={!editLastText.trim()}
                className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 rounded text-xs font-medium disabled:opacity-50 transition-colors"
              >
                Resend edited message
              </button>
            </div>
          </div>
        )}

        {error && (
          <div className="bg-red-900/30 border border-red-700 rounded-lg p-3 text-red-400 text-sm">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label className="block text-sm text-gray-400 mb-1">Context <span className="text-gray-600">(optional)</span></label>
            <textarea
              value={context}
              onChange={e => setContext(e.target.value)}
              placeholder="Additional context or constraints..."
              rows={2}
              disabled={isRunning}
              className="w-full bg-gray-900 rounded-lg px-3 py-2 text-sm border border-gray-700 focus:outline-none focus:border-indigo-500 resize-none disabled:opacity-50"
            />
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-1">Query</label>
            <textarea
              value={query}
              onChange={e => setQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Message the agent (Enter to send, Shift+Enter for newline)"
              rows={3}
              disabled={isRunning}
              className="w-full bg-gray-900 rounded-lg px-3 py-2 text-sm border border-gray-700 focus:outline-none focus:border-indigo-500 resize-none disabled:opacity-50"
            />
          </div>
          <div className="flex gap-3 items-center flex-wrap">
            <button
              type="submit"
              disabled={isRunning || !query.trim()}
              className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 rounded-lg text-sm font-medium disabled:opacity-50 transition-colors"
            >
              {isRunning ? 'Running…' : 'Run Agent'}
            </button>
            {isRunning && (
              <button
                type="button"
                onClick={stop}
                className="px-4 py-2 bg-red-900/60 hover:bg-red-800 text-red-300 rounded-lg text-sm transition-colors"
              >
                Stop
              </button>
            )}
            {(merged.length > 0 || error) && !isRunning && (
              <button
                type="button"
                onClick={reset}
                className="px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-sm transition-colors"
              >
                Clear
              </button>
            )}
            {conversationId && !isRunning && (
              <button
                type="button"
                onClick={newConversation}
                className="px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-sm transition-colors"
              >
                New Conversation
              </button>
            )}
            {conversationId && (
              <span className="text-xs text-gray-500 font-mono">
                thread: {conversationId.slice(0, 8)}…
              </span>
            )}
          </div>
        </form>
      </div>
    </div>
  )
}
