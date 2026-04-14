'use client'

import { useState, useMemo, useEffect, useCallback } from 'react'
import { useAgentStream, StreamEvent } from '@/lib/hooks'
import { formatCost } from '@/lib/utils'

function EventLine({ event }: { event: StreamEvent }) {
  switch (event.type) {
    case 'status':
      return <p className="text-gray-400 text-sm">▷ {event.content ?? event.message}</p>
    case 'thinking':
      return <p className="text-purple-400 text-sm italic">💭 {event.content}</p>
    case 'tool_call':
      return (
        <div className="bg-gray-800 rounded p-2 text-xs space-y-1">
          <span className="text-yellow-400 font-medium">⚙ {event.tool_name}</span>
          {event.tool_input && (
            <pre className="text-gray-400 overflow-x-auto whitespace-pre-wrap">
              {JSON.stringify(event.tool_input, null, 2)}
            </pre>
          )}
        </div>
      )
    case 'tool_result':
      return (
        <p className="text-green-400 text-xs bg-gray-800 rounded p-2">
          ✓ {String(event.tool_result ?? '').slice(0, 400)}
          {(event.tool_result?.length ?? 0) > 400 ? '…' : ''}
        </p>
      )
    case 'text_delta':
      return <span className="text-gray-100 whitespace-pre-wrap">{event.content}</span>
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

  return (
    <div className="flex items-center gap-2 text-xs text-gray-400">
      <span>context</span>
      <div className="flex-1 max-w-32 h-1.5 bg-gray-800 rounded-full overflow-hidden">
        <div className={`h-full rounded-full transition-all ${color}`} style={{ width: `${Math.min(pct, 100)}%` }} />
      </div>
      <span className={pct >= 70 ? 'text-yellow-400' : ''}>{pct.toFixed(0)}% — {label}</span>
      {ctx.context_tokens_used != null && (
        <span className="text-gray-600">{ctx.context_tokens_used.toLocaleString()} / {ctx.context_tokens_max?.toLocaleString()} tokens</span>
      )}
    </div>
  )
}

export default function AgentExecutor() {
  const [query, setQuery] = useState('')
  const [context, setContext] = useState('')
  const [copyLabel, setCopyLabel] = useState('Copy response')
  const { events, isRunning, error, conversationId, run, reset, stop, newConversation } = useAgentStream()
  // Merge consecutive text_delta events into a single node for cleaner rendering
  const merged: StreamEvent[] = []
  for (const ev of events) {
    if (ev.type === 'text_delta') {
      const last = merged[merged.length - 1]
      if (last?.type === 'text_delta') {
        last.content = (last.content ?? '') + (ev.content ?? '')
        continue
      }
    }
    merged.push({ ...ev })
  }

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

  const isDone = merged.some(ev => ev.type === 'done')

  // Auto-scroll page to bottom as new events arrive
  useEffect(() => {
    requestAnimationFrame(() => {
      window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' })
    })
  }, [events, isRunning])

  const handleCopy = useCallback(async () => {
    if (!responseText) return
    await navigator.clipboard.writeText(responseText)
    setCopyLabel('Copied!')
    setTimeout(() => setCopyLabel('Copy response'), 2000)
  }, [responseText])

  const handleDownload = useCallback(() => {
    if (!responseText) return
    // Use the written filename if there was exactly one file write, else a generic name
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

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!query.trim() || isRunning) return
    run(query.trim(), context.trim() || undefined, conversationId)
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault()
      if (!query.trim() || isRunning) return
      run(query.trim(), context.trim() || undefined, conversationId)
    }
  }

  return (
    <div className="space-y-4">
      <form onSubmit={handleSubmit} className="space-y-3">
        <div>
          <label className="block text-sm text-gray-400 mb-1">Query</label>
          <textarea
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="What do you want the agent to do? (Ctrl+Enter to run)"
            rows={3}
            disabled={isRunning}
            className="w-full bg-gray-900 rounded-lg px-3 py-2 text-sm border border-gray-700 focus:outline-none focus:border-indigo-500 resize-none disabled:opacity-50"
          />
        </div>
        <div>
          <label className="block text-sm text-gray-400 mb-1">Context (optional)</label>
          <textarea
            value={context}
            onChange={e => setContext(e.target.value)}
            placeholder="Additional context or constraints..."
            rows={2}
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

      {error && (
        <div className="bg-red-900/30 border border-red-700 rounded-lg p-3 text-red-400 text-sm">
          {error}
        </div>
      )}

      <ContextBar events={events} />

      {merged.length > 0 && (
        <div className="space-y-2">
          {/* Copy / Download toolbar — shown once agent finishes */}
          {isDone && responseText && (
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
          )}

          {/* Events log */}
          <div
            className="bg-gray-900 rounded-xl border border-gray-800 p-4 space-y-2 font-mono text-sm"
          >
            {merged.map((ev, i) => (
              <EventLine key={i} event={ev} />
            ))}
            {isRunning && (
              <span className="inline-block w-2 h-4 bg-indigo-400 animate-pulse align-middle" />
            )}
          </div>
        </div>
      )}
    </div>
  )
}
