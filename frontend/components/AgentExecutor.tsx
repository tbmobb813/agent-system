'use client'

import { useState, useMemo, useEffect, useLayoutEffect, useCallback, useRef } from 'react'
import dynamic from 'next/dynamic'
import { useAgentStream, StreamEvent } from '@/lib/hooks'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { getAgentModels, getSettings, getTools, submitTaskFeedback } from '@/lib/api'
import { formatCost } from '@/lib/utils'

const MarkdownContent = dynamic(() => import('./MarkdownContent'), { ssr: false })

/** After this many completed assistant runs, offer a soft feedback reminder (per conversation milestones). */
const FEEDBACK_NUDGE_EVERY = 5

/** Persisted OpenRouter `reasoning.effort` override for the chat UI (`/reasoning` slash command). */
const REASONING_EFFORT_STORAGE_KEY = 'agent_ui_reasoning_effort'

type InputTrigger = { kind: '/' | '@'; start: number; filter: string }

/** Active `/…` or `@…` token at cursor (start of line or after whitespace only). */
function parseInputTrigger(value: string, cursor: number): InputTrigger | null {
  const before = value.slice(0, cursor)
  const lastSlash = before.lastIndexOf('/')
  const lastAt = before.lastIndexOf('@')
  const i = Math.max(lastSlash, lastAt)
  if (i < 0) return null
  const ch = value[i]
  if (ch !== '/' && ch !== '@') return null
  if (i > 0 && !/\s/.test(value[i - 1])) return null
  const tail = before.slice(i + 1)
  if (/\s/.test(tail)) return null
  return { kind: ch as '/' | '@', start: i, filter: tail }
}

type SuggestPick =
  | { type: 'replace'; text: string }
  /** Insert `text` then open the reasoning-effort dialog (same as typing `/reasoning `). */
  | { type: 'replace_then_reasoning_modal'; text: string }
  | { type: 'expand_context' }
  | { type: 'action_new_thread' }
  | { type: 'action_stop' }
  | { type: 'action_help_modal' }
  | { type: 'action_clear' }
  | { type: 'action_copy_thread' }
  | { type: 'action_download_thread' }
  | { type: 'action_models_modal' }
  | { type: 'action_navigate'; path: string }

type SuggestRow = {
  id: string
  label: string
  hint: string
  pick: SuggestPick
  /** Slash palette: dim prefix + command (Claude Code–style). */
  slashParts?: { muted: string; arg: string }
}

function filterSuggestRows(rows: SuggestRow[], filter: string): SuggestRow[] {
  const f = filter.toLowerCase()
  if (!f) return rows
  return rows.filter((r) => {
    const k = r.label.slice(1)
    return k.toLowerCase().startsWith(f)
  })
}

/** Hierarchical `/` menu: root → `/reasoning …` → effort sub-keys. */
type SlashSuggestCtx =
  | { mode: 'root'; start: number; filter: string }
  | { mode: 'reasoning_sub'; start: number; subFilter: string }

/** Slash commands only at start of the message or start of a line (after optional spaces), like Claude Code. */
function isSlashAtLineStart(value: string, slashIndex: number): boolean {
  if (slashIndex < 0) return false
  let j = slashIndex - 1
  while (j >= 0) {
    const c = value[j]
    if (c === '\n') return true
    if (c !== ' ' && c !== '\t') return false
    j -= 1
  }
  return true
}

function parseSlashSuggestContext(value: string, cursor: number): SlashSuggestCtx | null {
  const before = value.slice(0, cursor)
  const i = before.lastIndexOf('/')
  if (i < 0) return null
  if (!isSlashAtLineStart(value, i)) return null
  const tail = before.slice(i + 1)

  const subMatch = tail.match(/^reasoning\s+(.*)$/i)
  if (subMatch) {
    return { mode: 'reasoning_sub', start: i, subFilter: subMatch[1].trim().toLowerCase() }
  }

  if (/\s/.test(tail)) {
    const first = tail.match(/^(\S+)/)?.[1]?.toLowerCase()
    if (first && first !== 'reasoning') return null
  }

  return { mode: 'root', start: i, filter: tail.toLowerCase() }
}

type SlashRootDef =
  | {
      id: string
      key: string
      label: string
      hint: string
      kind: 'replace'
      text: string
    }
  | {
      id: string
      key: string
      label: string
      hint: string
      kind: 'replace_then_reasoning_modal'
      text: string
    }
  | {
      id: string
      key: string
      label: string
      hint: string
      kind: 'action_new_thread'
    }
  | {
      id: string
      key: string
      label: string
      hint: string
      kind: 'action_stop'
    }
  | {
      id: string
      key: string
      label: string
      hint: string
      kind: 'action_help_modal'
    }
  | {
      id: string
      key: string
      label: string
      hint: string
      kind: 'action_clear'
    }
  | {
      id: string
      key: string
      label: string
      hint: string
      kind: 'action_copy_thread'
    }
  | {
      id: string
      key: string
      label: string
      hint: string
      kind: 'action_download_thread'
    }
  | {
      id: string
      key: string
      label: string
      hint: string
      kind: 'action_models_modal'
    }
  | {
      id: string
      key: string
      label: string
      hint: string
      kind: 'action_navigate'
      path: string
    }

const SLASH_ROOT: SlashRootDef[] = [
  {
    id: 'slash-help',
    key: 'help',
    label: '/help',
    hint: 'Slash commands & links',
    kind: 'action_help_modal',
  },
  {
    id: 'slash-fb',
    key: 'feedback',
    label: '/feedback',
    hint: 'Rate the latest reply',
    kind: 'replace',
    text: '/feedback ',
  },
  {
    id: 'slash-re',
    key: 'reasoning',
    label: '/reasoning',
    hint: 'Open picker: off, low, medium, high…',
    kind: 'replace_then_reasoning_modal',
    text: '/reasoning ',
  },
  {
    id: 'slash-clear',
    key: 'clear',
    label: '/clear',
    hint: 'Clear transcript in this tab',
    kind: 'action_clear',
  },
  {
    id: 'slash-copy',
    key: 'copy',
    label: '/copy',
    hint: 'Copy thread text to clipboard',
    kind: 'action_copy_thread',
  },
  {
    id: 'slash-download',
    key: 'download',
    label: '/download',
    hint: 'Download thread as .txt',
    kind: 'action_download_thread',
  },
  {
    id: 'slash-models',
    key: 'models',
    label: '/models',
    hint: 'View routing & model list',
    kind: 'action_models_modal',
  },
  {
    id: 'slash-costs',
    key: 'costs',
    label: '/costs',
    hint: 'Open budget page',
    kind: 'action_navigate',
    path: '/costs',
  },
  {
    id: 'slash-history',
    key: 'history',
    label: '/history',
    hint: 'Open run history',
    kind: 'action_navigate',
    path: '/history',
  },
  {
    id: 'slash-new',
    key: 'new',
    label: '/new',
    hint: 'Start a new conversation thread',
    kind: 'action_new_thread',
  },
  {
    id: 'slash-stop',
    key: 'stop',
    label: '/stop',
    hint: 'Stop the current agent run',
    kind: 'action_stop',
  },
]

function slashRootToPick(r: SlashRootDef): SuggestPick {
  switch (r.kind) {
    case 'replace':
      return { type: 'replace', text: r.text }
    case 'replace_then_reasoning_modal':
      return { type: 'replace_then_reasoning_modal', text: r.text }
    case 'action_new_thread':
      return { type: 'action_new_thread' }
    case 'action_stop':
      return { type: 'action_stop' }
    case 'action_help_modal':
      return { type: 'action_help_modal' }
    case 'action_clear':
      return { type: 'action_clear' }
    case 'action_copy_thread':
      return { type: 'action_copy_thread' }
    case 'action_download_thread':
      return { type: 'action_download_thread' }
    case 'action_models_modal':
      return { type: 'action_models_modal' }
    case 'action_navigate':
      return { type: 'action_navigate', path: r.path }
  }
}

function filterRootSlashRows(filter: string): SuggestRow[] {
  const f = filter.toLowerCase()
  return SLASH_ROOT.filter(
    (r) => r.key.startsWith(f) || (f.length > 0 && f.startsWith(r.key)),
  ).map((r) => ({
    id: r.id,
    label: r.label,
    hint: r.hint,
    slashParts: { muted: '/', arg: r.key },
    pick: slashRootToPick(r),
  }))
}

/** Shown after `/reasoning ` — order: common levels first, then extras. */
const REASONING_SUB_KEYS = [
  'off',
  'low',
  'medium',
  'high',
  'help',
  'default',
  'minimal',
  'xhigh',
  'none',
] as const

const REASONING_SUB_HINTS: Record<(typeof REASONING_SUB_KEYS)[number], string> = {
  off: 'Disable reasoning.effort (overrides env)',
  low: 'Low reasoning effort',
  medium: 'Medium reasoning effort',
  high: 'High reasoning effort',
  help: 'Usage & current setting (same as /reasoning help)',
  default: 'Follow OPENROUTER_REASONING_EFFORT on server',
  minimal: 'Minimal',
  xhigh: 'Extra high',
  none: 'Send effort none (provider)',
}

function SuggestPrimaryLabel({ row }: { row: SuggestRow }) {
  if (row.slashParts) {
    return (
      <span className="font-mono text-[13px] leading-tight shrink-0 tracking-tight">
        <span className="text-muted/85">{row.slashParts.muted}</span>
        <span className="text-[color:var(--text)]">{row.slashParts.arg}</span>
      </span>
    )
  }
  return (
    <span className="font-mono text-[13px] leading-tight text-[color:var(--text)] shrink-0">{row.label}</span>
  )
}

const AT_STATIC_SUGGEST_ROWS: SuggestRow[] = [
  {
    id: 'at-context',
    label: '@context',
    hint: 'Open the optional context field above',
    pick: { type: 'expand_context' },
  },
  {
    id: 'at-verbose',
    label: '@verbose',
    hint: 'Ask for a detailed answer',
    pick: { type: 'replace', text: 'Explain in detail, step by step. ' },
  },
  {
    id: 'at-brief',
    label: '@brief',
    hint: 'Ask for a short answer',
    pick: { type: 'replace', text: 'Keep your answer brief. ' },
  },
  {
    id: 'at-docs',
    label: '@documents',
    hint: 'Use uploaded documents when relevant',
    pick: { type: 'replace', text: 'Search and use my uploaded documents when relevant. ' },
  },
]

function buildSuggestionRows(
  value: string,
  cursor: number,
  dismissed: boolean,
  toolNames: string[],
): SuggestRow[] {
  if (dismissed) return []

  const slashCtx = parseSlashSuggestContext(value, cursor)
  if (slashCtx) {
    if (slashCtx.mode === 'reasoning_sub') {
      // Empty argument: full-screen picker opens (see useLayoutEffect). Partial typing: inline filter.
      if (slashCtx.subFilter === '') return []
      return REASONING_SUB_KEYS.filter((k) => k.startsWith(slashCtx.subFilter)).map((sub) => ({
        id: `reasoning-sub-${sub}`,
        label: `/reasoning ${sub}`,
        hint: REASONING_SUB_HINTS[sub],
        slashParts: { muted: '/reasoning ', arg: sub },
        pick: { type: 'replace', text: `/reasoning ${sub} ` } as const,
      }))
    }
    return filterRootSlashRows(slashCtx.filter)
  }

  const trig = parseInputTrigger(value, cursor)
  if (!trig || trig.kind !== '@') return []
  const toolRows: SuggestRow[] = [...toolNames]
    .sort()
    .map((name) => ({
      id: `tool-${name}`,
      label: `@${name}`,
      hint: `Prefer the ${name} tool when relevant`,
      pick: { type: 'replace', text: `Use the ${name} tool when needed: ` } as const,
    }))
  return filterSuggestRows([...AT_STATIC_SUGGEST_ROWS, ...toolRows], trig.filter)
}

/** Exportable plain text for the thread (file writes + assistant text), same as Download. */
function buildThreadExportText(merged: StreamEvent[]): string {
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
  return [fileWrites, textResponse].filter(Boolean).join('\n\n')
}

function ToolCallEvent({ event }: { event: StreamEvent }) {
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

/** Compact line for web_search payloads instead of dumping raw JSON in the transcript. */
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
    // Legacy streams: Python repr (single quotes) — one line, no raw dump
    return '✓ Web search completed'
  }
}

function ToolResultEvent({ event }: { event: StreamEvent }) {
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

function EventLine({ event }: { event: StreamEvent }) {
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

/** Retrieval / session setup / context housekeeping — omit from the transcript column. */
function isHiddenChatStatus(ev: StreamEvent): boolean {
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

function visibleChatEvents(events: StreamEvent[]): StreamEvent[] {
  return events.filter(e => !isHiddenChatStatus(e))
}

/**
 * Leading orchestrator phase (status + thinking) until the model moves past internal work
 * (first tool call/result, assistant text, terminal event, or explicit "responding" status).
 */
function splitLeadingPhaseEvents(events: StreamEvent[]): { phase: StreamEvent[]; rest: StreamEvent[] } {
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

function phaseSummaryPreview(events: StreamEvent[]): string {
  const last = events[events.length - 1]
  if (!last) return 'Processing…'
  if (last.type === 'thinking') {
    const t = (last.content ?? '').trim()
    return t ? `💭 ${t.slice(0, 72)}${t.length > 72 ? '…' : ''}` : '💭 Thinking…'
  }
  const line = (last.content ?? last.message ?? '').trim()
  return line ? `▷ ${line.slice(0, 72)}${line.length > 72 ? '…' : ''}` : '▷ Processing…'
}

/** Events after the most recent user message (current assistant turn tail). */
function tailAfterLastUserMessage(events: StreamEvent[]): StreamEvent[] {
  let last = -1
  for (let j = events.length - 1; j >= 0; j--) {
    if (events[j].type === 'user_message') {
      last = j
      break
    }
  }
  if (last < 0) return events
  return events.slice(last + 1)
}

/** One-line status for the activity strip while a run is in progress. */
function deriveLiveActivitySummary(events: StreamEvent[], isRunning: boolean): string | null {
  if (!isRunning) return null
  const tail = tailAfterLastUserMessage(events)
  const vis = visibleChatEvents(tail)
  const { phase } = splitLeadingPhaseEvents(vis)
  if (phase.length > 0) return phaseSummaryPreview(phase)
  const tc = [...vis].reverse().find(e => e.type === 'tool_call')
  if (tc) return `Tool · ${tc.tool_name || 'tool'}`
  const tr = [...vis].reverse().find(e => e.type === 'tool_result')
  if (tr) return `Result · ${tr.tool_name || 'tool'}`
  if (vis.some(e => e.type === 'text_delta')) return 'Generating reply…'
  if (vis.some(e => e.type === 'reasoning_delta')) return 'Model reasoning…'
  for (let k = vis.length - 1; k >= 0; k--) {
    const e = vis[k]
    if (e.type === 'status' && !isHiddenChatStatus(e)) {
      const t = (e.content ?? e.message ?? '').trim()
      if (t) return t.length > 72 ? `${t.slice(0, 72)}…` : t
    }
  }
  return 'Working…'
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

function IconClipboard({ className }: { className?: string }) {
  return (
    <svg className={className} width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
    </svg>
  )
}

function IconDownload({ className }: { className?: string }) {
  return (
    <svg className={className} width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <polyline points="7 10 12 15 17 10" />
      <line x1="12" y1="15" x2="12" y2="3" />
    </svg>
  )
}

function IconStar({ className }: { className?: string }) {
  return (
    <svg className={className} width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
    </svg>
  )
}

function TurnCopyIcon({ text }: { text: string }) {
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

function ThreadDownloadIconButton({ disabled, onClick }: { disabled: boolean; onClick: () => void }) {
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

function TurnFeedbackDetails({
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

function TurnQuickThumbs({
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

/** Completed-turn footer: cost on the left; copy, feedback, and (latest turn only) full-thread download on the right. */
function TurnDoneFooter({
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
  /** Latest run: hide dollar line here; shown as “Last cost” in the activity strip. */
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

function AgentActivityStrip({
  reasoningEffortLabel,
  liveActivitySummary,
  isRunning,
  streamEvents,
  latestRunCost,
  className = '',
}: {
  reasoningEffortLabel: string
  liveActivitySummary: string | null
  isRunning: boolean
  streamEvents: StreamEvent[]
  /** Most recent completed run (last `done` with a cost), for a quick read at the bottom. */
  latestRunCost: number | null
  /** Extra layout classes (e.g. flush horizontal margins in transcript). */
  className?: string
}) {
  return (
    <div
      className={`border-t border-[color:var(--border)] bg-[color:var(--bg-elev)]/95 backdrop-blur-sm px-3 sm:px-4 py-2 font-sans text-[11px] text-muted ${className}`.trim()}
      role="status"
      aria-live={isRunning ? 'polite' : undefined}
    >
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="text-[color:var(--text)]/90">
          <span className="uppercase tracking-wide text-[10px] text-muted">Reasoning effort</span>
          {' · '}
          <span className="font-mono">{reasoningEffortLabel}</span>
        </span>
        {latestRunCost != null ? (
          <span className="text-[color:var(--success)] shrink-0">
            <span className="uppercase tracking-wide text-[10px] text-muted">Last cost</span>
            {' · '}
            <span className="font-mono">{formatCost(latestRunCost)}</span>
          </span>
        ) : null}
        {liveActivitySummary ? (
          <span className="min-w-0 flex-1 truncate" title={liveActivitySummary}>
            <span className="uppercase tracking-wide text-[10px] text-muted">Activity</span>
            {' · '}
            <span className="text-[color:var(--text)]/85">{liveActivitySummary}</span>
          </span>
        ) : null}
      </div>
      <ContextMetricsCompact events={streamEvents} />
    </div>
  )
}

/** Latest context window usage — compact row for the activity strip. */
function ContextMetricsCompact({ events }: { events: StreamEvent[] }) {
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
    <div className="mt-3 flex flex-wrap items-center gap-x-2 gap-y-1 text-[10px] text-muted tabular-nums">
      <span className="uppercase tracking-wide text-muted shrink-0">Context</span>
      <div className="h-1.5 w-16 sm:w-24 shrink-0 rounded-full border border-[color:var(--border)] bg-[color:var(--bg)] overflow-hidden">
        <div className={`h-full rounded-full transition-all ${color} ${widthClass}`} />
      </div>
      <span className={pct >= 70 ? 'text-[color:var(--warn)]' : ''}>
        {pct.toFixed(0)}% — {label}
      </span>
      {ctx.context_tokens_used != null && (
        <span className="text-muted/85">
          {ctx.context_tokens_used.toLocaleString()} / {ctx.context_tokens_max?.toLocaleString()} tok
        </span>
      )}
    </div>
  )
}

export default function AgentExecutor() {
  const [query, setQuery] = useState('')
  const [context, setContext] = useState('')
  const [editLastOpen, setEditLastOpen] = useState(false)
  const [editLastText, setEditLastText] = useState('')
  /** Mirrors Settings → “Show planning stream in chat”; default on, refetched when tab becomes visible. */
  const [showThinkingLive, setShowThinkingLive] = useState(true)
  /** After auto-collapse, user can re-open the inline phase block per turn. */
  const [reasoningPhaseOpenByTurn, setReasoningPhaseOpenByTurn] = useState<Record<number, boolean>>({})
  const [showJumpToLatest, setShowJumpToLatest] = useState(false)
  const [feedbackCmdHint, setFeedbackCmdHint] = useState<string | null>(null)
  const [reasoningCmdHint, setReasoningCmdHint] = useState<string | null>(null)
  const [reasoningEffortForRequest, setReasoningEffortForRequest] = useState<string | undefined>(undefined)
  const [reasoningPrefHydrated, setReasoningPrefHydrated] = useState(false)
  const [showFeedbackNudge, setShowFeedbackNudge] = useState(false)
  const lastFeedbackNudgeDismissedAt = useRef(0)
  const prevConversationId = useRef<string | null>(null)
  const feedbackDetailsRef = useRef<HTMLDetailsElement>(null)
  const contextPanelRef = useRef<HTMLDetailsElement>(null)
  const queryInputRef = useRef<HTMLTextAreaElement>(null)
  const [toolNames, setToolNames] = useState<string[]>([])
  const [queryCursor, setQueryCursor] = useState(0)
  const [suggestDismissed, setSuggestDismissed] = useState(false)
  const [suggestHighlight, setSuggestHighlight] = useState(0)
  const [reasoningArgModal, setReasoningArgModal] = useState<null | { from: number; to: number }>(null)
  const skipReasoningModalSig = useRef<string | null>(null)
  const queryRef = useRef(query)
  const [helpModalOpen, setHelpModalOpen] = useState(false)
  const [modelsModalOpen, setModelsModalOpen] = useState(false)
  const [modelsModalState, setModelsModalState] = useState<
    'loading' | { ok: Record<string, unknown> } | { err: string }
  >('loading')
  const router = useRouter()
  const { events, isRunning, error, conversationId, run, reset, stop, newConversation } = useAgentStream()

  useEffect(() => {
    let cancelled = false
    getTools()
      .then((data: { tools?: string[] }) => {
        const list = Array.isArray(data?.tools) ? data.tools : []
        if (!cancelled) setToolNames(list)
      })
      .catch(() => {
        if (!cancelled) setToolNames([])
      })
    return () => {
      cancelled = true
    }
  }, [])

  const suggestionRows = useMemo(
    () => buildSuggestionRows(query, queryCursor, suggestDismissed, toolNames),
    [query, queryCursor, suggestDismissed, toolNames],
  )

  const slashMenuCtx = useMemo(
    () => parseSlashSuggestContext(query, queryCursor),
    [query, queryCursor],
  )

  const suggestionRowKey = suggestionRows.map((r) => r.id).join('|')
  useEffect(() => {
    setSuggestHighlight(0)
  }, [suggestionRowKey])

  useEffect(() => {
    queryRef.current = query
  }, [query])

  useEffect(() => {
    const ctx = parseSlashSuggestContext(query, queryCursor)
    if (!ctx || ctx.mode !== 'reasoning_sub' || ctx.subFilter !== '') {
      skipReasoningModalSig.current = null
    }
  }, [query, queryCursor])

  useLayoutEffect(() => {
    if (reasoningArgModal || helpModalOpen || modelsModalOpen) return
    const ctx = parseSlashSuggestContext(query, queryCursor)
    if (!ctx || ctx.mode !== 'reasoning_sub' || ctx.subFilter !== '') return
    const sig = `${ctx.start}:${query}`
    if (skipReasoningModalSig.current === sig) return
    setReasoningArgModal({ from: ctx.start, to: queryCursor })
    setSuggestDismissed(true)
  }, [query, queryCursor, reasoningArgModal, helpModalOpen, modelsModalOpen])

  const commitReasoningArg = useCallback((opt: string, range: { from: number; to: number }) => {
    skipReasoningModalSig.current = null
    const insert = `/reasoning ${opt} `
    setQuery((q) => q.slice(0, range.from) + insert + q.slice(range.to))
    setReasoningArgModal(null)
    const pos = range.from + insert.length
    queueMicrotask(() => {
      const el = queryInputRef.current
      if (el) {
        el.focus()
        el.setSelectionRange(pos, pos)
      }
    })
    setQueryCursor(pos)
    setSuggestDismissed(true)
  }, [])

  const cancelReasoningArgModal = useCallback(() => {
    setReasoningArgModal(null)
    queueMicrotask(() => {
      const q = queryRef.current
      const c = queryInputRef.current?.selectionStart ?? q.length
      const ctx = parseSlashSuggestContext(q, c)
      if (ctx?.mode === 'reasoning_sub' && ctx.subFilter === '') {
        skipReasoningModalSig.current = `${ctx.start}:${q}`
      }
    })
  }, [])

  // Merge consecutive text_delta / reasoning_delta events for cleaner rendering
  const merged = useMemo(() => {
    const out: StreamEvent[] = []
    for (const ev of events) {
      if (ev.type === 'text_delta') {
        const last = out[out.length - 1]
        if (last?.type === 'text_delta') {
          last.content = (last.content ?? '') + (ev.content ?? '')
          if (ev.task_id) last.task_id = ev.task_id
          continue
        }
      }
      if (ev.type === 'reasoning_delta') {
        const last = out[out.length - 1]
        if (last?.type === 'reasoning_delta') {
          last.content = (last.content ?? '') + (ev.content ?? '')
          if (ev.task_id) last.task_id = ev.task_id
          continue
        }
      }
      out.push({ ...ev })
    }
    return out
  }, [events])

  const responseText = useMemo(() => buildThreadExportText(merged), [merged])

  const reasoningEffortLabel = useMemo(
    () =>
      reasoningEffortForRequest === undefined
        ? 'server default'
        : reasoningEffortForRequest === 'off'
          ? 'off'
          : reasoningEffortForRequest,
    [reasoningEffortForRequest],
  )

  const liveActivitySummary = useMemo(
    () => deriveLiveActivitySummary(merged, isRunning),
    [merged, isRunning],
  )

  const latestRunCost = useMemo(() => {
    for (let i = merged.length - 1; i >= 0; i--) {
      if (merged[i].type === 'done' && merged[i].cost != null) return merged[i].cost as number
    }
    return null
  }, [merged])

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
    }
    type DividerItem = { kind: 'divider'; event: StreamEvent }

    const items: Array<TurnItem | DividerItem> = []
    let current: TurnItem | null = null
    let nextId = 1

    const flush = () => {
      if (!current) return
      if (current.user || current.events.length > 0) {
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
        }
        continue
      }

      if (!current) {
        current = {
          kind: 'turn',
          id: nextId++,
          events: [],
        }
      }

      current.events.push(ev)
    }

    flush()
    return items
  }, [merged])

  const isDone = merged.some(ev => ev.type === 'done')
  const completedRuns = useMemo(() => merged.filter(ev => ev.type === 'done').length, [merged])

  const dismissFeedbackNudge = useCallback(() => {
    lastFeedbackNudgeDismissedAt.current = completedRuns
    setShowFeedbackNudge(false)
  }, [completedRuns])

  useEffect(() => {
    if (prevConversationId.current !== conversationId) {
      lastFeedbackNudgeDismissedAt.current = 0
      setShowFeedbackNudge(false)
      prevConversationId.current = conversationId
    }
  }, [conversationId])

  useEffect(() => {
    if (completedRuns === 0) return
    if (completedRuns % FEEDBACK_NUDGE_EVERY !== 0) return
    if (completedRuns <= lastFeedbackNudgeDismissedAt.current) return
    setShowFeedbackNudge(true)
  }, [completedRuns])

  const lastCompletedTurnMeta = useMemo(() => {
    for (let i = turnItems.length - 1; i >= 0; i--) {
      const it = turnItems[i]
      if (it.kind !== 'turn') continue
      if (!it.events.some(ev => ev.type === 'done')) continue
      return {
        id: it.id,
        taskId: turnTaskIdFromEvents(it.events),
        exportText: buildTurnExportableText(it.events),
      }
    }
    return null
  }, [turnItems])

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

  const refreshAgentUiSettings = useCallback(() => {
    getSettings()
      .then((data: { agent_show_thinking_while_streaming?: boolean }) => {
        setShowThinkingLive(data.agent_show_thinking_while_streaming !== false)
      })
      .catch(() => setShowThinkingLive(true))
  }, [])

  useEffect(() => {
    refreshAgentUiSettings()
  }, [refreshAgentUiSettings])

  useEffect(() => {
    if (typeof window === 'undefined') return
    const onVis = () => {
      if (document.visibilityState === 'visible') refreshAgentUiSettings()
    }
    document.addEventListener('visibilitychange', onVis)
    return () => document.removeEventListener('visibilitychange', onVis)
  }, [refreshAgentUiSettings])

  useEffect(() => {
    if (typeof window === 'undefined') return
    const v = localStorage.getItem(REASONING_EFFORT_STORAGE_KEY)
    if (v) setReasoningEffortForRequest(v)
    setReasoningPrefHydrated(true)
  }, [])

  useEffect(() => {
    if (typeof window === 'undefined' || !reasoningPrefHydrated) return
    if (reasoningEffortForRequest === undefined) {
      localStorage.removeItem(REASONING_EFFORT_STORAGE_KEY)
    } else {
      localStorage.setItem(REASONING_EFFORT_STORAGE_KEY, reasoningEffortForRequest)
    }
  }, [reasoningEffortForRequest, reasoningPrefHydrated])

  useEffect(() => {
    if (!editLastOpen) {
      setEditLastText(lastUserMessage)
    }
  }, [lastUserMessage, editLastOpen])

  useEffect(() => {
    if (merged.length === 0) setReasoningPhaseOpenByTurn({})
  }, [merged.length])

  const handleDownloadThread = useCallback(() => {
    const exportText = buildThreadExportText(merged)
    if (!exportText) return
    const writes = merged.filter(ev => ev.type === 'tool_call' && ev.tool_name === 'file_operations' && ev.tool_input?.operation === 'write')
    const filename = writes.length === 1
      ? String(writes[0].tool_input?.path ?? '').split('/').pop() || `agent-thread-${Date.now()}.txt`
      : `agent-thread-${Date.now()}.txt`
    const blob = new Blob([exportText], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  }, [merged])

  const loadModelsForModal = useCallback(() => {
    setModelsModalState('loading')
    getAgentModels()
      .then((data: unknown) => {
        setModelsModalState({ ok: data as Record<string, unknown> })
      })
      .catch((e: unknown) => {
        setModelsModalState({ err: e instanceof Error ? e.message : String(e) })
      })
  }, [])

  const tryHandleChatSlashCommand = useCallback(
    (rawTrimmed: string): boolean => {
      const rawLower = rawTrimmed.toLowerCase()
      if (rawLower === '/help') {
        setHelpModalOpen(true)
        return true
      }
      if (rawLower === '/clear') {
        reset()
        return true
      }
      if (rawLower === '/copy') {
        const text = buildThreadExportText(merged)
        if (!text.trim()) {
          setReasoningCmdHint('Nothing to copy yet.')
          window.setTimeout(() => setReasoningCmdHint(null), 3200)
        } else {
          void navigator.clipboard.writeText(text).then(
            () => {
              setReasoningCmdHint('Copied thread export to clipboard.')
              window.setTimeout(() => setReasoningCmdHint(null), 3200)
            },
            () => {
              setFeedbackCmdHint('Clipboard unavailable; try Download instead.')
              window.setTimeout(() => setFeedbackCmdHint(null), 4000)
            },
          )
        }
        return true
      }
      if (rawLower === '/download') {
        handleDownloadThread()
        return true
      }
      if (rawLower === '/models') {
        setModelsModalOpen(true)
        loadModelsForModal()
        return true
      }
      if (rawLower === '/costs') {
        router.push('/costs')
        return true
      }
      if (rawLower === '/history') {
        router.push('/history')
        return true
      }
      if (rawLower === '/new') {
        newConversation()
        return true
      }
      if (rawLower === '/stop') {
        if (isRunning) void stop()
        else {
          setFeedbackCmdHint('Nothing is running.')
          window.setTimeout(() => setFeedbackCmdHint(null), 3200)
        }
        return true
      }
      return false
    },
    [merged, handleDownloadThread, loadModelsForModal, router, reset, newConversation, isRunning, stop],
  )

  const applySuggestionPick = useCallback(
    (row: SuggestRow, cursorPos: number) => {
      const slashSc = parseSlashSuggestContext(query, cursorPos)
      const atTrig = parseInputTrigger(query, cursorPos)

      const focusPos = (pos: number) => {
        queueMicrotask(() => {
          const el = queryInputRef.current
          if (el) {
            el.focus()
            el.setSelectionRange(pos, pos)
          }
        })
        setQueryCursor(pos)
        setSuggestDismissed(true)
      }

      const stripSlashAndFocus = (start: number) => {
        const next = query.slice(0, start) + query.slice(cursorPos)
        setQuery(next)
        focusPos(start)
      }

      if (row.pick.type === 'replace' || row.pick.type === 'replace_then_reasoning_modal') {
        const start = slashSc ? slashSc.start : atTrig?.start
        if (start === undefined) return
        let repl = row.pick.text
        if (repl.startsWith('/') && !/\s$/.test(repl)) repl += ' '
        const next = query.slice(0, start) + repl + query.slice(cursorPos)
        setQuery(next)
        const pos = start + repl.length
        focusPos(pos)
        if (row.pick.type === 'replace_then_reasoning_modal') {
          skipReasoningModalSig.current = null
          setReasoningArgModal({ from: start, to: pos })
        }
        return
      }

      if (row.pick.type === 'action_help_modal') {
        if (!slashSc) return
        stripSlashAndFocus(slashSc.start)
        setHelpModalOpen(true)
        return
      }

      if (row.pick.type === 'action_clear') {
        if (!slashSc) return
        stripSlashAndFocus(slashSc.start)
        reset()
        return
      }

      if (row.pick.type === 'action_copy_thread') {
        if (!slashSc) return
        stripSlashAndFocus(slashSc.start)
        const text = buildThreadExportText(merged)
        if (!text.trim()) {
          setReasoningCmdHint('Nothing to copy yet.')
          window.setTimeout(() => setReasoningCmdHint(null), 3200)
          return
        }
        void navigator.clipboard.writeText(text).then(
          () => {
            setReasoningCmdHint('Copied thread export to clipboard.')
            window.setTimeout(() => setReasoningCmdHint(null), 3200)
          },
          () => {
            setFeedbackCmdHint('Clipboard unavailable; try Download instead.')
            window.setTimeout(() => setFeedbackCmdHint(null), 4000)
          },
        )
        return
      }

      if (row.pick.type === 'action_download_thread') {
        if (!slashSc) return
        stripSlashAndFocus(slashSc.start)
        handleDownloadThread()
        return
      }

      if (row.pick.type === 'action_models_modal') {
        if (!slashSc) return
        stripSlashAndFocus(slashSc.start)
        setModelsModalOpen(true)
        loadModelsForModal()
        return
      }

      if (row.pick.type === 'action_navigate') {
        if (!slashSc) return
        stripSlashAndFocus(slashSc.start)
        router.push(row.pick.path)
        return
      }

      if (row.pick.type === 'action_new_thread') {
        if (!slashSc) return
        stripSlashAndFocus(slashSc.start)
        newConversation()
        return
      }

      if (row.pick.type === 'action_stop') {
        if (!slashSc) return
        stripSlashAndFocus(slashSc.start)
        if (isRunning) void stop()
        else {
          setFeedbackCmdHint('Nothing is running.')
          window.setTimeout(() => setFeedbackCmdHint(null), 3200)
        }
        return
      }

      if (row.pick.type === 'expand_context') {
        if (!atTrig || atTrig.kind !== '@') return
        const panel = contextPanelRef.current
        if (panel) {
          panel.open = true
          panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
        }
        const next = query.slice(0, atTrig.start) + query.slice(cursorPos)
        setQuery(next)
        focusPos(atTrig.start)
      }
    },
    [query, isRunning, newConversation, stop, merged, handleDownloadThread, loadModelsForModal, reset, router],
  )

  const handleResendEdited = useCallback(() => {
    const text = editLastText.trim()
    if (!text || isRunning) return
    run(text, context.trim() || undefined, conversationId, reasoningEffortForRequest)
    setEditLastOpen(false)
    setQuery('')
  }, [editLastText, isRunning, run, context, conversationId, reasoningEffortForRequest])

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

  const tryHandleReasoningSlashCommand = useCallback(
    (raw: string): boolean => {
      const m = raw.match(/^\/reasoning(?:\s+(\S+))?$/i)
      if (!m) return false
      const sub = (m[1] || '').toLowerCase()
      const allowed = new Set(['minimal', 'low', 'medium', 'high', 'xhigh', 'none'])
      const currentLabel =
        reasoningEffortForRequest === undefined
          ? 'server default (OPENROUTER_REASONING_EFFORT if set)'
          : reasoningEffortForRequest === 'off'
            ? 'off (no reasoning.effort sent; overrides env)'
            : reasoningEffortForRequest

      const hint = (msg: string) => {
        setReasoningCmdHint(msg)
        window.setTimeout(() => setReasoningCmdHint(null), 5500)
      }

      if (!sub || sub === 'help' || sub === '?') {
        hint(
          `Usage: /reasoning off | minimal | low | medium | high | xhigh | none — or /reasoning default for server env. Current: ${currentLabel}`,
        )
        return true
      }
      if (sub === 'off' || sub === 'disable') {
        setReasoningEffortForRequest('off')
        hint('Reasoning effort disabled for upcoming runs (overrides server env).')
        return true
      }
      if (sub === 'default' || sub === 'clear' || sub === 'env') {
        setReasoningEffortForRequest(undefined)
        hint('Using server default for reasoning effort on upcoming runs.')
        return true
      }
      if (allowed.has(sub)) {
        setReasoningEffortForRequest(sub)
        hint(`Set reasoning effort to "${sub}" for upcoming runs.`)
        return true
      }
      hint(`Unknown "${m[1]}". Try /reasoning help`)
      return true
    },
    [reasoningEffortForRequest],
  )

  const tryOpenFeedbackPanel = useCallback((): boolean => {
    if (lastCompletedTurnMeta?.taskId && isDone) {
      setFeedbackCmdHint(null)
      queueMicrotask(() => {
        const el = feedbackDetailsRef.current
        if (!el) return
        el.open = true
        el.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
      })
      return true
    }
    setFeedbackCmdHint('Finish a run first, then use the star icon under the latest reply or /feedback.')
    window.setTimeout(() => setFeedbackCmdHint(null), 4500)
    return false
  }, [lastCompletedTurnMeta, isDone])

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (reasoningArgModal || helpModalOpen || modelsModalOpen) return
    const raw = query.trim()
    if (!raw || isRunning) return
    if (tryHandleReasoningSlashCommand(raw)) {
      setQuery('')
      return
    }
    if (raw.toLowerCase() === '/feedback') {
      tryOpenFeedbackPanel()
      setQuery('')
      return
    }
    if (tryHandleChatSlashCommand(raw)) {
      setQuery('')
      return
    }
    run(raw, context.trim() || undefined, conversationId, reasoningEffortForRequest)
    setQuery('')
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    const el = e.currentTarget
    const cursor = el.selectionStart ?? query.length
    setQueryCursor(cursor)

    if (reasoningArgModal) {
      if (e.key === 'Escape') {
        e.preventDefault()
        cancelReasoningArgModal()
        return
      }
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault()
        return
      }
    }

    if (helpModalOpen || modelsModalOpen) {
      if (e.key === 'Escape') {
        e.preventDefault()
        if (helpModalOpen) setHelpModalOpen(false)
        if (modelsModalOpen) {
          setModelsModalOpen(false)
          setModelsModalState('loading')
        }
        return
      }
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault()
        return
      }
    }

    const rows = buildSuggestionRows(query, cursor, suggestDismissed, toolNames)
    if (rows.length > 0 && !isRunning) {
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        setSuggestHighlight((h) => (h + 1) % rows.length)
        return
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault()
        setSuggestHighlight((h) => (h - 1 + rows.length) % rows.length)
        return
      }
      if (e.key === 'Escape') {
        e.preventDefault()
        setSuggestDismissed(true)
        return
      }
      if (e.key === 'Tab' && !e.shiftKey) {
        e.preventDefault()
        const hi = Math.min(suggestHighlight, rows.length - 1)
        applySuggestionPick(rows[hi], cursor)
        return
      }
    }

    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      if (rows.length > 0 && !isRunning) {
        const hi = Math.min(suggestHighlight, rows.length - 1)
        applySuggestionPick(rows[hi], cursor)
        return
      }
      const raw = query.trim()
      if (!raw || isRunning) return
      if (tryHandleReasoningSlashCommand(raw)) {
        setQuery('')
        return
      }
      if (raw.toLowerCase() === '/feedback') {
        tryOpenFeedbackPanel()
        setQuery('')
        return
      }
      if (tryHandleChatSlashCommand(raw)) {
        setQuery('')
        return
      }
      run(raw, context.trim() || undefined, conversationId, reasoningEffortForRequest)
      setQuery('')
    }
  }

  return (
    <div className="flex flex-col h-full gap-2 min-h-0">

      {/* ── Events log — fills all available space ── */}
      <div className="flex-1 min-h-0 flex flex-col">
        {merged.length > 0 ? (
          <div className="flex-1 min-h-0 flex flex-col rounded-xl border border-[color:var(--border)] bg-[color:var(--bg-elev)] overflow-hidden font-mono text-sm">
            {/* Messages scroll; activity strip sits below (standard chat layout). */}
            <div
              ref={eventsContainerRef}
              onScroll={handleEventsScroll}
              className="flex-1 min-h-0 overflow-y-auto p-3 sm:p-4 relative"
            >
              <div className="space-y-2">
              {turnItems.map((item, i) => {
                if (item.kind === 'divider') {
                  return <EventLine key={`divider-${i}`} event={item.event} />
                }

                const turnDoneEvent = [...item.events].reverse().find(ev => ev.type === 'done')
                const turnHasDone = !!turnDoneEvent
                const turnStartedAt = item.user?.client_ts
                const turnEndedAt = turnDoneEvent?.client_ts
                const turnDuration = turnStartedAt && turnEndedAt ? Math.max(0, turnEndedAt - turnStartedAt) : null

                const chatEvents = visibleChatEvents(item.events)
                const { phase, rest } = splitLeadingPhaseEvents(chatEvents)
                const replyPhaseStarted = rest.some(
                  e =>
                    e.type === 'text_delta'
                    || e.type === 'tool_call'
                    || e.type === 'tool_result'
                    || (e.type === 'status'
                      && (e.content ?? e.message ?? '').toLowerCase().includes('responding')),
                )
                const autoExpandPhase =
                  showThinkingLive && phase.length > 0 && !replyPhaseStarted && !turnHasDone
                const phaseDetailsOpen =
                  autoExpandPhase || reasoningPhaseOpenByTurn[item.id] === true
                const eventsToRender = showThinkingLive && phase.length > 0 ? rest : chatEvents

                return (
                  <div key={`turn-${item.id}`} className="space-y-2">
                    {(turnStartedAt || turnDuration) && (
                      <div className="flex items-center gap-2 text-[10px] text-muted ml-1">
                        {turnStartedAt ? <span>{formatTs(turnStartedAt)}</span> : null}
                        {turnDuration != null ? <span>• {formatDuration(turnDuration)}</span> : null}
                      </div>
                    )}
                    {item.user && <EventLine event={item.user} />}

                    {showThinkingLive && phase.length > 0 && (
                      <div className="flex justify-start">
                        <details
                          className="max-w-[min(92%,42rem)] w-full rounded-2xl rounded-bl-md border border-[color:var(--border)] bg-[color:var(--surface-soft)] px-3 py-2 text-sm"
                          open={phaseDetailsOpen}
                          onToggle={e => {
                            if (autoExpandPhase) return
                            setReasoningPhaseOpenByTurn(prev => ({
                              ...prev,
                              [item.id]: e.currentTarget.open,
                            }))
                          }}
                        >
                          <summary
                            className="text-muted text-sm cursor-pointer list-none [&::-webkit-details-marker]:hidden flex items-start gap-2"
                            onClick={e => {
                              if (autoExpandPhase) e.preventDefault()
                            }}
                          >
                            <span className="shrink-0 opacity-70" aria-hidden>
                              ▸
                            </span>
                            <span className="truncate min-w-0">{phaseSummaryPreview(phase)}</span>
                          </summary>
                          <div className="mt-2 max-h-48 space-y-1 overflow-y-auto border-t border-[color:var(--border)]/50 pt-2">
                            {phase.map((ev, idx) => (
                              <EventLine key={`turn-${item.id}-phase-${idx}`} event={ev} />
                            ))}
                          </div>
                        </details>
                      </div>
                    )}

                    {eventsToRender
                      .filter(ev => ev.type !== 'done')
                      .map((ev, idx) => (
                        <EventLine key={`turn-${item.id}-event-${idx}`} event={ev} />
                      ))}
                    {turnHasDone ? (
                      <TurnDoneFooter
                        turnId={item.id}
                        events={item.events}
                        isRunning={isRunning}
                        dismissFeedbackNudge={dismissFeedbackNudge}
                        registerFeedbackRef={
                          item.id === lastCompletedTurnMeta?.id
                            ? el => {
                                feedbackDetailsRef.current = el
                              }
                            : undefined
                        }
                        showThreadDownload={item.id === lastCompletedTurnMeta?.id}
                        threadExportEmpty={!responseText.trim()}
                        onDownloadThread={handleDownloadThread}
                        omitDoneCost={item.id === lastCompletedTurnMeta?.id}
                      />
                    ) : null}
                  </div>
                )
              })}
              {showFeedbackNudge && lastCompletedTurnMeta?.taskId && isDone && (
                <div className="rounded-lg border border-[color:var(--accent-2)]/35 bg-[color:var(--accent-2)]/10 px-3 py-2.5 text-xs text-[color:var(--text)] font-sans">
                  <p className="text-muted mb-2">
                    Every {FEEDBACK_NUDGE_EVERY} completed runs in this thread, you can leave a quick rating to steer future behavior.
                  </p>
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      className="btn-accent px-3 py-1 rounded text-xs"
                      onClick={() => {
                        dismissFeedbackNudge()
                        queueMicrotask(() => {
                          const el = feedbackDetailsRef.current
                          if (!el) return
                          el.open = true
                          el.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
                        })
                      }}
                    >
                      Open rating
                    </button>
                    <button type="button" className="btn-ghost px-3 py-1 rounded text-xs" onClick={dismissFeedbackNudge}>
                      Not now
                    </button>
                  </div>
                </div>
              )}
              {isRunning && (
                <div className="flex justify-start">
                  <div className="max-w-[min(92%,42rem)] bg-[color:var(--surface-soft)] border border-[color:var(--border)] rounded-2xl rounded-bl-md px-3 py-2 text-muted text-sm">
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
                  className="absolute bottom-3 right-3 z-20 btn-accent px-3 py-1.5 rounded-full text-xs shadow-lg"
                >
                  Jump to latest
                </button>
              )}
              <div ref={eventsEndRef} />
              </div>
            </div>
            <AgentActivityStrip
              reasoningEffortLabel={reasoningEffortLabel}
              liveActivitySummary={liveActivitySummary}
              isRunning={isRunning}
              streamEvents={events}
              latestRunCost={latestRunCost}
              className="shrink-0"
            />
          </div>
        ) : (
          <div className="flex-1 min-h-0 flex flex-col rounded-xl border border-[color:var(--border)] bg-[color:var(--bg-elev)] overflow-hidden font-mono text-sm">
            <div className="flex-1 min-h-0 flex items-center justify-center text-muted text-sm select-none text-center px-6">
              <div>
                <p>Start chatting to see responses here.</p>
                <p className="text-xs text-muted/90 mt-2">
                  Enter to send, Shift+Enter for newline. After each reply, copy or rate from the row next to cost; download the full thread from the latest reply. Use <span className="font-mono">Edit & resend</span> (below the message box) to retry with changes. Put <span className="font-mono">/</span> at the <strong className="text-[color:var(--text)] font-normal">start of a line</strong> for commands (<span className="font-mono">/reasoning</span> opens a picker; <span className="font-mono">/new</span>, <span className="font-mono">/stop</span>, <span className="font-mono">/feedback</span>) or <span className="font-mono">@</span> after whitespace for snippets and tools.
                </p>
              </div>
            </div>
            <AgentActivityStrip
              reasoningEffortLabel={reasoningEffortLabel}
              liveActivitySummary={liveActivitySummary}
              isRunning={isRunning}
              streamEvents={events}
              latestRunCost={latestRunCost}
              className="shrink-0"
            />
          </div>
        )}
      </div>

      {/* ── Bottom controls — pinned (z-20 so slash/@ palette above transcript when it extends upward) ── */}
      <div className="shrink-0 space-y-3 sticky bottom-0 z-20 bg-[color:var(--bg)]/95 backdrop-blur-sm pt-2 border-t border-[color:var(--border)]">
        {error && (
          <div className="border border-[color:var(--danger)]/45 bg-[color:var(--danger)]/10 rounded-lg p-3 text-[color:var(--danger)] text-sm">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-2">
          <details ref={contextPanelRef} className="group rounded-lg border border-[color:var(--border)] bg-[color:var(--surface-soft)]/40 px-3 py-2">
            <summary className="text-xs text-muted cursor-pointer list-none [&::-webkit-details-marker]:hidden">
              Optional context for the next message
              <span className="text-muted/60 ml-1">(click to expand)</span>
            </summary>
            <textarea
              value={context}
              onChange={e => setContext(e.target.value)}
              placeholder="Constraints, tone, files to assume…"
              rows={2}
              disabled={isRunning}
              className="mt-2 w-full bg-[color:var(--bg-elev)] rounded-lg px-3 py-2 text-sm border border-[color:var(--border)] focus:outline-none focus:border-[color:var(--accent)] resize-none disabled:opacity-50"
            />
          </details>
          <div>
            <label className="block text-sm text-muted mb-1" htmlFor="agent-message-input">
              Message
            </label>
            <div className="relative isolate z-30">
            {suggestionRows.length > 0 && !isRunning && (
              <div
                className="absolute left-0 right-0 bottom-full z-40 mb-1 flex max-h-[min(42vh,288px)] flex-col overflow-hidden rounded-md border border-[color:var(--border)] bg-[color:var(--bg)] text-left font-sans shadow-[0_-6px_28px_rgba(0,0,0,0.2)] ring-1 ring-[color:var(--border)]/30"
                role="listbox"
                aria-label={slashMenuCtx?.mode === 'reasoning_sub' ? 'Arguments' : slashMenuCtx ? 'Commands' : 'Insert'}
                onMouseDown={(ev) => ev.preventDefault()}
              >
                <div className="flex shrink-0 items-center justify-between gap-2 border-b border-[color:var(--border)]/80 bg-[color:var(--surface-soft)]/55 px-2.5 py-1.5">
                  <span className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted">
                    {!slashMenuCtx ? 'Insert' : slashMenuCtx.mode === 'reasoning_sub' ? 'Arguments' : 'Commands'}
                  </span>
                  {slashMenuCtx?.mode === 'reasoning_sub' ? (
                    <span className="truncate text-right font-mono text-[11px] text-muted/90">/reasoning</span>
                  ) : null}
                </div>
                <div className="min-h-0 flex-1 overflow-y-auto py-0.5">
                  {suggestionRows.map((row, idx) => {
                    const active = idx === Math.min(suggestHighlight, suggestionRows.length - 1)
                    return (
                      <button
                        key={row.id}
                        type="button"
                        role="option"
                        aria-selected={active}
                        aria-label={`${row.label}. ${row.hint}`}
                        className={`group flex w-full items-stretch gap-0 text-left outline-none ${
                          active ? 'bg-[color:var(--surface-soft)]' : 'hover:bg-[color:var(--surface-soft)]/65'
                        }`}
                        onMouseEnter={() => setSuggestHighlight(idx)}
                        onClick={() => {
                          const el = queryInputRef.current
                          const c = el?.selectionStart ?? queryCursor
                          applySuggestionPick(row, c)
                        }}
                      >
                        <span
                          className={`w-[3px] shrink-0 self-stretch rounded-full ${
                            active
                              ? 'bg-[color:var(--accent)]'
                              : 'bg-transparent group-hover:bg-[color:var(--border)]'
                          }`}
                          aria-hidden
                        />
                        <span className="flex min-w-0 flex-1 items-center justify-between gap-3 py-1.5 pl-1 pr-2.5">
                          <SuggestPrimaryLabel row={row} />
                          <span className="max-w-[min(54%,15rem)] text-right text-[11px] leading-snug text-muted line-clamp-2">
                            {row.hint}
                          </span>
                        </span>
                      </button>
                    )
                  })}
                </div>
                <div className="shrink-0 border-t border-[color:var(--border)]/70 bg-[color:var(--surface-soft)]/35 px-2.5 py-1 text-[10px] tabular-nums text-muted/90">
                  <span>↑↓</span>
                  <span className="mx-1 opacity-50">·</span>
                  <span>↵</span>
                  <span className="ml-0.5 opacity-80">{slashMenuCtx ? 'apply' : 'select'}</span>
                  <span className="mx-1 opacity-50">·</span>
                  <span>tab</span>
                  <span className="ml-0.5 opacity-80">complete</span>
                  <span className="mx-1 opacity-50">·</span>
                  <span>esc</span>
                  <span className="ml-0.5 opacity-80">close</span>
                </div>
              </div>
            )}
            <textarea
              id="agent-message-input"
              ref={queryInputRef}
              value={query}
              onChange={(e) => {
                const v = e.target.value
                const c = e.target.selectionStart ?? v.length
                setQuery(v)
                setQueryCursor(c)
                if (!parseSlashSuggestContext(v, c) && !parseInputTrigger(v, c)) setSuggestDismissed(false)
              }}
              onClick={(e) => setQueryCursor(e.currentTarget.selectionStart ?? query.length)}
              onSelect={(e) => setQueryCursor(e.currentTarget.selectionStart ?? query.length)}
              onKeyDown={handleKeyDown}
              placeholder="Message — / at line start for commands, @ for inserts. Enter send · Shift+Enter newline"
              rows={2}
              disabled={isRunning}
              className="relative z-10 w-full bg-[color:var(--bg-elev)] rounded-lg px-3 py-2 text-sm border border-[color:var(--border)] focus:outline-none focus:border-[color:var(--accent)] resize-none disabled:opacity-50"
            />
            </div>
            {feedbackCmdHint && (
              <p className="text-xs text-[color:var(--danger)] mt-1.5">{feedbackCmdHint}</p>
            )}
            {reasoningCmdHint && (
              <p className="text-xs text-muted mt-1.5">{reasoningCmdHint}</p>
            )}
          </div>
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
          <div className="flex gap-3 items-center flex-wrap">
            {isRunning && (
              <button
                type="button"
                onClick={stop}
                className="px-4 py-2 border border-[color:var(--danger)]/50 bg-[color:var(--danger)]/15 text-[color:var(--danger)] rounded-lg text-sm transition-colors hover:bg-[color:var(--danger)]/25"
              >
                Stop
              </button>
            )}
            {!isRunning && lastUserMessage && (
              <button
                type="button"
                onClick={() => {
                  setEditLastOpen(v => !v)
                  setEditLastText(lastUserMessage)
                }}
                className="btn-ghost px-4 py-2 rounded-lg text-sm"
              >
                {editLastOpen ? 'Close edit' : 'Edit & resend'}
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

      {reasoningArgModal && (
        <div
          className="fixed inset-0 z-[100] flex items-center justify-center p-4 font-sans"
          role="dialog"
          aria-modal="true"
          aria-labelledby="reasoning-arg-title"
        >
          <button
            type="button"
            className="absolute inset-0 bg-black/45"
            aria-label="Dismiss"
            onClick={cancelReasoningArgModal}
          />
          <div className="relative z-10 w-full max-w-lg rounded-xl border border-[color:var(--border)] bg-[color:var(--bg)] shadow-2xl ring-1 ring-[color:var(--border)]/40">
            <div className="border-b border-[color:var(--border)]/80 px-4 py-3">
              <h2 id="reasoning-arg-title" className="text-sm font-semibold text-[color:var(--text)]">
                Reasoning effort
              </h2>
              <p className="mt-1 text-xs text-muted">
                Pick a value to complete <span className="font-mono">/reasoning …</span> (no need to type the argument).
              </p>
            </div>
            <div className="max-h-[min(60vh,22rem)] overflow-y-auto px-3 py-3">
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                {REASONING_SUB_KEYS.map((opt) => (
                  <button
                    key={opt}
                    type="button"
                    className="rounded-lg border border-[color:var(--border)] bg-[color:var(--bg-elev)] px-2 py-2.5 text-left text-sm transition-colors hover:border-[color:var(--accent)] hover:bg-[color:var(--surface-soft)]"
                    onClick={() => {
                      const m = reasoningArgModal
                      if (!m) return
                      commitReasoningArg(opt, m)
                    }}
                  >
                    <span className="font-mono text-[color:var(--text)]">{opt}</span>
                    <span className="mt-0.5 block text-[10px] leading-snug text-muted line-clamp-2">
                      {REASONING_SUB_HINTS[opt]}
                    </span>
                  </button>
                ))}
              </div>
            </div>
            <div className="flex justify-end gap-2 border-t border-[color:var(--border)]/70 bg-[color:var(--surface-soft)]/40 px-3 py-2">
              <button
                type="button"
                className="btn-ghost px-3 py-1.5 rounded-lg text-xs"
                onClick={cancelReasoningArgModal}
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {helpModalOpen && (
        <div
          className="fixed inset-0 z-[100] flex items-center justify-center p-4 font-sans"
          role="dialog"
          aria-modal="true"
          aria-labelledby="slash-help-title"
        >
          <button
            type="button"
            className="absolute inset-0 bg-black/45"
            aria-label="Dismiss"
            onClick={() => setHelpModalOpen(false)}
          />
          <div className="relative z-10 w-full max-w-lg rounded-xl border border-[color:var(--border)] bg-[color:var(--bg)] shadow-2xl ring-1 ring-[color:var(--border)]/40">
            <div className="border-b border-[color:var(--border)]/80 px-4 py-3">
              <h2 id="slash-help-title" className="text-sm font-semibold text-[color:var(--text)]">
                Slash commands
              </h2>
              <p className="mt-1 text-xs text-muted">
                Type <span className="font-mono">/</span> at the start of a line in the message box to open the palette, or enter a command and press Enter.
              </p>
            </div>
            <div className="max-h-[min(60vh,22rem)] overflow-y-auto px-4 py-3 text-sm">
              <ul className="space-y-2">
                {SLASH_ROOT.map((r) => (
                  <li key={r.id} className="flex flex-col gap-0.5 border-b border-[color:var(--border)]/40 pb-2 last:border-0 last:pb-0">
                    <span className="font-mono text-[color:var(--text)]">{r.label}</span>
                    <span className="text-xs text-muted">{r.hint}</span>
                  </li>
                ))}
              </ul>
              <p className="mt-4 text-xs text-muted">
                <Link href="/commands" className="text-[color:var(--accent)] underline underline-offset-2 hover:opacity-90">
                  Full command reference
                </Link>
                {' '}— pages, CLI, and Telegram.
              </p>
            </div>
            <div className="flex justify-end gap-2 border-t border-[color:var(--border)]/70 bg-[color:var(--surface-soft)]/40 px-3 py-2">
              <button
                type="button"
                className="btn-ghost px-3 py-1.5 rounded-lg text-xs"
                onClick={() => setHelpModalOpen(false)}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {modelsModalOpen && (
        <div
          className="fixed inset-0 z-[100] flex items-center justify-center p-4 font-sans"
          role="dialog"
          aria-modal="true"
          aria-labelledby="models-modal-title"
        >
          <button
            type="button"
            className="absolute inset-0 bg-black/45"
            aria-label="Dismiss"
            onClick={() => {
              setModelsModalOpen(false)
              setModelsModalState('loading')
            }}
          />
          <div className="relative z-10 w-full max-w-2xl rounded-xl border border-[color:var(--border)] bg-[color:var(--bg)] shadow-2xl ring-1 ring-[color:var(--border)]/40">
            <div className="border-b border-[color:var(--border)]/80 px-4 py-3">
              <h2 id="models-modal-title" className="text-sm font-semibold text-[color:var(--text)]">
                Agent models
              </h2>
              <p className="mt-1 text-xs text-muted">Routing and model list from the server (same as <span className="font-mono">GET /agent/models</span>).</p>
            </div>
            <div className="max-h-[min(65vh,28rem)] overflow-y-auto px-4 py-3">
              {modelsModalState === 'loading' ? (
                <p className="text-sm text-muted">Loading…</p>
              ) : 'err' in modelsModalState ? (
                <p className="text-sm text-[color:var(--danger)]">{modelsModalState.err}</p>
              ) : (
                <pre className="overflow-x-auto rounded-lg border border-[color:var(--border)]/80 bg-[color:var(--bg-elev)] p-3 text-[11px] leading-relaxed text-[color:var(--text)] font-mono">
                  {JSON.stringify(modelsModalState.ok, null, 2)}
                </pre>
              )}
            </div>
            <div className="flex justify-end gap-2 border-t border-[color:var(--border)]/70 bg-[color:var(--surface-soft)]/40 px-3 py-2">
              <button
                type="button"
                className="btn-ghost px-3 py-1.5 rounded-lg text-xs"
                onClick={() => {
                  setModelsModalOpen(false)
                  setModelsModalState('loading')
                }}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
