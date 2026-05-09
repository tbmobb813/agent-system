import { useState, useMemo, useEffect, useRef } from 'react'
import dynamic from 'next/dynamic'
import { StreamEvent } from '@/lib/hooks'
import { formatCost } from '@/lib/utils'
import { submitTaskFeedback } from '@/lib/api'
import {
  IconClipboard,
  IconDownload,
  IconStar,
} from './Icons'

const MarkdownContent = dynamic(() => import('./MarkdownContent'), { ssr: false })

export function ToolCallEvent({ event }: { event: StreamEvent }) {
  const [open, setOpen] = useState(false)
  const name = event.tool_name ?? ''
  const input = event.tool_input
  const hasInput = !!input && Object.keys(input).length > 0

  if (name === 'web_search' && input && typeof input.query === 'string') {
    const q = input.query.trim()
    const qShort = q.length > 72 ? `${q.slice(0, 72)}…` : q
    return (
      <div className="bg-[color:var(--bg-elev)] border border-[color:var(--border)] rounded p-2 text-xs">
        <details className="group/ws">
          <summary className="text-[color:var(--warn)] font-medium cursor-pointer list-none [&::-webkit-details-marker]:hidden flex items-baseline gap-2">
            <span className="shrink-0">⚙</span>
            <span className="min-w-0 break-words">
              Web search · <span className="text-[color:var(--text)] font-normal">“{qShort}”</span>
            </span>
            <span className="text-muted text-[10px] shrink-0 ml-auto">args</span>
          </summary>
          <pre className="mt-2 text-muted overflow-x-auto whitespace-pre-wrap border-t border-[color:var(--border)]/60 pt-2">
            {JSON.stringify(input, null, 2)}
          </pre>
        </details>
      </div>
    )
  }

  return (
    <div className="bg-[color:var(--bg-elev)] border border-[color:var(--border)] rounded p-2 text-xs">
      <button
        onClick={() => setOpen(o => !o)}
        className="flex items-center gap-2 w-full text-left"
      >
        <span className="text-[color:var(--warn)] font-medium">⚙ {name || 'tool'}</span>
        {hasInput && (
          <span className="text-muted ml-auto">{open ? '▲ hide' : '▼ show'}</span>
        )}
      </button>
      {open && hasInput && (
        <pre className="mt-2 text-muted overflow-x-auto whitespace-pre-wrap">
          {JSON.stringify(input, null, 2)}
        </pre>
      )}
    </div>
  )
}

function formatWebSearchToolSummary(raw: string): string | null {
  const trimmed = raw.trim()
  if (!trimmed.startsWith('{')) return null
  const looksLikeWebSearch =
    /['"]query['"]/.test(trimmed) && /['"]results['"]/.test(trimmed)
  if (!looksLikeWebSearch) return null

  try {
    const j = JSON.parse(trimmed) as Record<string, unknown>
    if (!j || typeof j !== 'object') return null
    if (!Array.isArray(j.results) || typeof j.query !== 'string') return null
    const err = j.error
    if (typeof err === 'string' && err.trim()) return `✗ Web search: ${err.trim()}`

    const results = j.results as unknown[]
    const total = typeof j.total === 'number' ? j.total : results.length
    const provider = typeof j.provider === 'string' && j.provider ? ` · ${j.provider}` : ''
    return `✓ ${total} hit${total === 1 ? '' : 's'}${provider}`
  } catch {
    return '✓ Web search completed'
  }
}

export function ToolResultEvent({ event }: { event: StreamEvent }) {
  const [open, setOpen] = useState(false)
  const text = String(event.tool_result ?? '')
  const webSummary =
    (event.tool_name === 'web_search' || event.tool_name == null || event.tool_name === '')
      ? formatWebSearchToolSummary(text)
      : null

  if (webSummary != null) {
    return (
      <div className="text-[color:var(--success)] text-xs bg-[color:var(--bg-elev)] border border-[color:var(--border)] rounded p-2">
        <p className="text-left break-words">{webSummary}</p>
      </div>
    )
  }

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

export function EventLine({ event }: { event: StreamEvent }) {
  switch (event.type) {
    case 'user_message':
      return (
        <div className="flex justify-end">
          <div className="max-w-[min(92%,42rem)] bg-[color:var(--accent-2)]/15 border border-[color:var(--accent-2)]/35 rounded-2xl rounded-br-md px-3 py-2 text-sm text-[color:var(--text)]">
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
    case 'reasoning_delta':
      return (
        <div className="flex justify-start">
          <div className="max-w-[min(92%,42rem)] border-l-2 border-[color:var(--accent-2)]/45 bg-[color:var(--accent-2)]/10 rounded-r-lg rounded-bl-md px-3 py-2 text-xs text-[color:var(--text)] whitespace-pre-wrap break-words">
            <span className="text-[10px] uppercase tracking-wide text-muted block mb-1">Model reasoning</span>
            {event.content ?? ''}
          </div>
        </div>
      )
    case 'thinking':
      return <p className="text-[color:var(--accent-2)] text-sm italic">💭 {event.content}</p>
    case 'tool_call':
      return <ToolCallEvent event={event} />
    case 'tool_result':
      return <ToolResultEvent event={event} />
    case 'text_delta':
      return (
        <div className="flex justify-start">
          <div className="max-w-[min(92%,42rem)] bg-[color:var(--surface-soft)] border border-[color:var(--border)] rounded-2xl rounded-bl-md px-3 py-2 text-[color:var(--text)] text-sm">
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

function buildTurnExportableText(events: StreamEvent[]): string {
  const fileWrites = events
    .filter(ev => ev.type === 'tool_call' && ev.tool_name === 'file_operations' && ev.tool_input?.operation === 'write')
    .map(ev => {
      const path = ev.tool_input?.path as string | undefined
      const content = ev.tool_input?.content as string | undefined
      return path && content ? `=== ${path} ===\n${content}` : null
    })
    .filter(Boolean)
    .join('\n\n')
  const textResponse = events
    .filter(ev => ev.type === 'text_delta')
    .map(ev => ev.content ?? '')
    .join('')
  return [fileWrites, textResponse].filter(Boolean).join('\n\n')
}

function turnTaskIdFromEvents(events: StreamEvent[]): string | null {
  for (let i = events.length - 1; i >= 0; i--) {
    const ev = events[i]
    if (ev.type === 'done' && ev.task_id) return ev.task_id
  }
  for (let i = events.length - 1; i >= 0; i--) {
    if (events[i].task_id) return events[i].task_id ?? null
  }
  return null
}

export function TurnCopyIcon({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(() => () => {
    if (timerRef.current) clearTimeout(timerRef.current)
  }, [])
  const handle = async () => {
    const t = text.trim()
    if (!t) return
    await navigator.clipboard.writeText(text)
    setCopied(true)
    if (timerRef.current) clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => setCopied(false), 2000)
  }
  const empty = !text.trim()
  return (
    <button
      type="button"
      onClick={() => void handle()}
      disabled={empty}
      className="btn-ghost p-1.5 rounded-lg disabled:opacity-40"
      title={copied ? 'Copied' : 'Copy this reply'}
      aria-label={copied ? 'Copied to clipboard' : 'Copy this reply'}
    >
      <IconClipboard className={copied ? 'text-[color:var(--success)]' : undefined} />
    </button>
  )
}

export function ThreadDownloadIconButton({ disabled, onClick }: { disabled: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="btn-ghost p-1.5 rounded-lg disabled:opacity-40"
      title="Download full thread as .txt"
      aria-label="Download full thread"
    >
      <IconDownload />
    </button>
  )
}

export function TurnFeedbackDetails({
  taskId,
  turnId,
  dismissFeedbackNudge,
  detailsRef,
}: {
  taskId: string
  turnId: number
  dismissFeedbackNudge: () => void
  detailsRef?: (el: HTMLDetailsElement | null) => void
}) {
  const [signal, setSignal] = useState<'up' | 'down'>('up')
  const [notes, setNotes] = useState('')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const savedTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    return () => {
      if (savedTimerRef.current) clearTimeout(savedTimerRef.current)
    }
  }, [])

  const save = async () => {
    setSaving(true)
    setError(null)
    try {
      await submitTaskFeedback(taskId, { signal, notes: notes })
      setSaved(true)
      if (savedTimerRef.current) clearTimeout(savedTimerRef.current)
      savedTimerRef.current = setTimeout(() => setSaved(false), 2500)
      dismissFeedbackNudge()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save feedback')
    } finally {
      setSaving(false)
    }
  }

  return (
    <details ref={detailsRef} className="relative group/fb">
      <summary
        className="btn-ghost p-1.5 rounded-lg cursor-pointer list-none [&::-webkit-details-marker]:hidden inline-flex"
        title="Rate this response"
        aria-label="Rate this response"
      >
        <IconStar />
      </summary>
      <div
        className="absolute right-0 top-full mt-1 z-30 w-[min(100vw-2rem,22rem)] panel panel-soft p-3 space-y-3 shadow-lg border border-[color:var(--border)]"
        onMouseDown={e => e.stopPropagation()}
        onClick={e => e.stopPropagation()}
      >
        <p className="text-xs text-muted">Teach the agent from this reply (saved to task history).</p>
        <p className="text-[10px] text-muted font-mono truncate" title={taskId}>
          Task {taskId.slice(0, 8)}…
        </p>
        <div className="flex gap-2 flex-wrap">
          <button
            type="button"
            onClick={() => setSignal('up')}
            className={`px-3 py-1.5 rounded text-xs transition-colors ${signal === 'up' ? 'border border-[color:var(--success)]/50 bg-[color:var(--success)]/15 text-[color:var(--success)]' : 'btn-ghost text-muted'}`}
          >
            Helpful
          </button>
          <button
            type="button"
            onClick={() => setSignal('down')}
            className={`px-3 py-1.5 rounded text-xs transition-colors ${signal === 'down' ? 'border border-[color:var(--danger)]/50 bg-[color:var(--danger)]/15 text-[color:var(--danger)]' : 'btn-ghost text-muted'}`}
          >
            Needs work
          </button>
        </div>
        <div>
          <label htmlFor={`live-feedback-notes-${turnId}`} className="block text-xs text-muted mb-1">
            Notes for future behavior
          </label>
          <textarea
            id={`live-feedback-notes-${turnId}`}
            value={notes}
            onChange={e => setNotes(e.target.value)}
            rows={3}
            placeholder="What should the agent repeat or avoid next time?"
            className="w-full bg-[color:var(--bg-elev)] rounded-lg px-3 py-2 text-sm border border-[color:var(--border)] focus:outline-none focus:border-[color:var(--accent)] resize-none"
          />
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          <button
            type="button"
            onClick={e => {
              e.preventDefault()
              e.stopPropagation()
              void save()
            }}
            disabled={saving}
            className="btn-accent px-3 py-1.5 rounded text-xs disabled:opacity-50"
          >
            {saving ? 'Saving…' : 'Save feedback'}
          </button>
          {saved && <span className="text-xs text-[color:var(--success)]">Saved</span>}
          {error && <span className="text-xs text-[color:var(--danger)]">{error}</span>}
        </div>
      </div>
    </details>
  )
}

export function TurnQuickThumbs({
  taskId,
  dismissFeedbackNudge,
}: {
  taskId: string
  dismissFeedbackNudge: () => void
}) {
  const [busy, setBusy] = useState<'up' | 'down' | null>(null)
  const [flash, setFlash] = useState<string | null>(null)
  const tRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    return () => {
      if (tRef.current) clearTimeout(tRef.current)
    }
  }, [])

  const vote = async (signal: 'up' | 'down') => {
    setBusy(signal)
    try {
      await submitTaskFeedback(taskId, { signal, notes: '' })
      dismissFeedbackNudge()
      setFlash(signal === 'up' ? 'Marked helpful' : 'Noted for next time')
      if (tRef.current) clearTimeout(tRef.current)
      tRef.current = setTimeout(() => setFlash(null), 2200)
    } catch {
      setFlash('Could not save — try the star menu')
      if (tRef.current) clearTimeout(tRef.current)
      tRef.current = setTimeout(() => setFlash(null), 3200)
    } finally {
      setBusy(null)
    }
  }

  return (
    <span className="inline-flex items-center gap-0.5" title="One-tap feedback">
      <button
        type="button"
        disabled={busy !== null}
        onClick={() => void vote('up')}
        className="btn-ghost p-1.5 rounded-lg text-sm disabled:opacity-40"
        aria-label="Mark this reply as helpful"
        title="Helpful"
      >
        👍
      </button>
      <button
        type="button"
        disabled={busy !== null}
        onClick={() => void vote('down')}
        className="btn-ghost p-1.5 rounded-lg text-sm disabled:opacity-40"
        aria-label="Mark this reply as needs work"
        title="Needs work"
      >
        👎
      </button>
      {flash ? <span className="text-[10px] text-muted max-w-[9rem] truncate">{flash}</span> : null}
    </span>
  )
}

export function isHiddenChatStatus(ev: StreamEvent): boolean {
  if (ev.type !== 'status') return false
  const c = (ev.content ?? ev.message ?? '').trim().toLowerCase()
  if (!c) return false
  if (c === 'initializing') return true
  if (c === 'planning...') return true
  if (c.includes('searching memory')) return true
  if (c.includes('resuming conversation')) return true
  if (c.startsWith('context at')) return true
  if (c.includes('context too large')) return true
  if (c.includes('compacting conversation')) return true
  return false
}

export function visibleChatEvents(events: StreamEvent[]): StreamEvent[] {
  return events.filter(e => !isHiddenChatStatus(e))
}

export function splitLeadingPhaseEvents(events: StreamEvent[]): { phase: StreamEvent[]; rest: StreamEvent[] } {
  const phase: StreamEvent[] = []
  let i = 0
  while (i < events.length) {
    const e = events[i]
    if (e.type === 'thinking') {
      phase.push(e)
      i++
      continue
    }
    if (e.type === 'status') {
      const raw = (e.content ?? e.message ?? '').trim().toLowerCase()
      if (raw.includes('responding')) break
      phase.push(e)
      i++
      continue
    }
    if (
      e.type === 'tool_call'
      || e.type === 'tool_result'
      || e.type === 'text_delta'
      || e.type === 'reasoning_delta'
      || e.type === 'done'
      || e.type === 'error'
      || e.type === 'context'
    ) {
      break
    }
    break
  }
  return { phase, rest: events.slice(i) }
}

export function phaseSummaryPreview(events: StreamEvent[]): string {
  const last = events[events.length - 1]
  if (!last) return 'Processing…'
  if (last.type === 'thinking') {
    const t = (last.content ?? '').trim()
    return t ? `💭 ${t.slice(0, 72)}${t.length > 72 ? '…' : ''}` : '💭 Thinking…'
  }
  const line = (last.content ?? last.message ?? '').trim()
  return line ? `▷ ${line.slice(0, 72)}${line.length > 72 ? '…' : ''}` : '▷ Processing…'
}

export function TurnDoneFooter({
  turnId,
  events,
  isRunning,
  dismissFeedbackNudge,
  registerFeedbackRef,
  showThreadDownload,
  threadExportEmpty,
  onDownloadThread,
  omitDoneCost,
}: {
  turnId: number
  events: StreamEvent[]
  isRunning: boolean
  dismissFeedbackNudge: () => void
  registerFeedbackRef?: (el: HTMLDetailsElement | null) => void
  showThreadDownload: boolean
  threadExportEmpty: boolean
  onDownloadThread: () => void
  omitDoneCost: boolean
}) {
  const doneEvent = useMemo(() => {
    for (let i = events.length - 1; i >= 0; i--) {
      if (events[i].type === 'done') return events[i]
    }
    return null
  }, [events])
  const exportText = useMemo(() => buildTurnExportableText(events), [events])
  const taskId = useMemo(() => turnTaskIdFromEvents(events), [events])

  if (!doneEvent) return null

  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between sm:gap-3 mt-1 border-t border-[color:var(--border)] pt-2 font-sans">
      <p className="text-[color:var(--success)] text-sm shrink-0 min-w-0">
        ✓ Done
        {!omitDoneCost && doneEvent.cost != null ? ` — cost: ${formatCost(doneEvent.cost)}` : ''}
      </p>
      <div className="flex items-center justify-end gap-0.5 flex-wrap">
        <TurnCopyIcon text={exportText} />
        {taskId ? (
          <TurnQuickThumbs taskId={taskId} dismissFeedbackNudge={dismissFeedbackNudge} />
        ) : null}
        {taskId ? (
          <TurnFeedbackDetails
            taskId={taskId}
            turnId={turnId}
            dismissFeedbackNudge={dismissFeedbackNudge}
            detailsRef={registerFeedbackRef}
          />
        ) : null}
        {showThreadDownload ? (
          <ThreadDownloadIconButton
            disabled={threadExportEmpty || isRunning}
            onClick={onDownloadThread}
          />
        ) : null}
      </div>
    </div>
  )
}
