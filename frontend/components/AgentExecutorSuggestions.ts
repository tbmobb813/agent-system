export type InputTrigger = { kind: '/' | '@'; start: number; filter: string }

export function parseInputTrigger(value: string, cursor: number): InputTrigger | null {
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

export type SuggestPick =
  | { type: 'replace'; text: string }
  | { type: 'replace_then_reasoning_modal'; text: string }
  | { type: 'expand_context' }
  | { type: 'action_feedback_panel' }
  | { type: 'action_new_thread' }
  | { type: 'action_stop' }
  | { type: 'action_help_modal' }
  | { type: 'action_clear' }
  | { type: 'action_copy_thread' }
  | { type: 'action_download_thread' }
  | { type: 'action_models_modal' }
  | { type: 'action_ops_modal'; panel: 'tools' | 'skills' | 'mcp' | 'stats' | 'history' }
  | { type: 'action_navigate'; path: string }

export type SuggestRow = {
  id: string
  label: string
  hint: string
  pick: SuggestPick
  slashParts?: { muted: string; arg: string }
}

export function filterSuggestRows(rows: SuggestRow[], filter: string): SuggestRow[] {
  const f = filter.toLowerCase()
  if (!f) return rows
  return rows.filter((r) => {
    const k = r.label.slice(1)
    return k.toLowerCase().startsWith(f)
  })
}

export type SlashSuggestCtx =
  | { mode: 'root'; start: number; filter: string }
  | { mode: 'reasoning_sub'; start: number; subFilter: string }

export function isSlashAtLineStart(value: string, slashIndex: number): boolean {
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

export function parseSlashSuggestContext(value: string, cursor: number): SlashSuggestCtx | null {
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

export type SlashRootDef = {
  id: string
  key: string
  label: string
  hint: string
  kind: 'replace' | 'replace_then_reasoning_modal' | 'action_feedback_panel' | 'action_new_thread' | 'action_stop' | 'action_help_modal' | 'action_clear' | 'action_copy_thread' | 'action_download_thread' | 'action_models_modal' | 'action_ops_modal' | 'action_navigate'
  text?: string
  panel?: 'tools' | 'skills' | 'mcp' | 'stats' | 'history'
  path?: string
}

export const SLASH_ROOT: SlashRootDef[] = [
  { id: 'slash-help', key: 'help', label: '/help', hint: 'Slash commands & links', kind: 'action_help_modal' },
  { id: 'slash-fb', key: 'feedback', label: '/feedback', hint: 'Rate the latest reply', kind: 'action_feedback_panel' },
  { id: 'slash-re', key: 'reasoning', label: '/reasoning', hint: 'Open picker: off, low, medium, high…', kind: 'replace_then_reasoning_modal', text: '/reasoning ' },
  { id: 'slash-clear', key: 'clear', label: '/clear', hint: 'Clear transcript in this tab', kind: 'action_clear' },
  { id: 'slash-copy', key: 'copy', label: '/copy', hint: 'Copy thread text to clipboard', kind: 'action_copy_thread' },
  { id: 'slash-download', key: 'download', label: '/download', hint: 'Download thread as .txt', kind: 'action_download_thread' },
  { id: 'slash-models', key: 'models', label: '/models', hint: 'View routing & model list', kind: 'action_models_modal' },
  { id: 'slash-costs', key: 'costs', label: '/costs', hint: 'Budget and latency summary', kind: 'action_ops_modal', panel: 'stats' },
  { id: 'slash-stats', key: 'stats', label: '/stats', hint: 'Latency and endpoint stats', kind: 'action_ops_modal', panel: 'stats' },
  { id: 'slash-skills', key: 'skills', label: '/skills', hint: 'Skills menu (used/available)', kind: 'action_ops_modal', panel: 'skills' },
  { id: 'slash-history', key: 'history', label: '/history', hint: 'Recent run history in chat', kind: 'action_ops_modal', panel: 'history' },
  { id: 'slash-new', key: 'new', label: '/new', hint: 'Start a new conversation thread', kind: 'action_new_thread' },
  { id: 'slash-stop', key: 'stop', label: '/stop', hint: 'Stop the current agent run', kind: 'action_stop' },
  { id: 'slash-tools', key: 'tools', label: '/tools', hint: 'Tools menu (enable/disable)', kind: 'action_ops_modal', panel: 'tools' },
  { id: 'slash-mcp', key: 'mcp', label: '/mcp', hint: 'MCP menu (health & readiness)', kind: 'action_ops_modal', panel: 'mcp' },
]

export function slashRootToPick(r: SlashRootDef): SuggestPick {
  switch (r.kind) {
    case 'action_ops_modal':
      return { type: 'action_ops_modal', panel: r.panel! }
    case 'action_navigate':
      return { type: 'action_navigate', path: r.path! }
    case 'replace':
      return { type: 'replace', text: r.text ?? '' }
    case 'replace_then_reasoning_modal':
      return { type: 'replace_then_reasoning_modal', text: r.text ?? '' }
    case 'action_feedback_panel':
      return { type: 'action_feedback_panel' }
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
    default: {
      const _exhaustive: never = r.kind
      return _exhaustive
    }
  }
}

export function filterRootSlashRows(filter: string): SuggestRow[] {
  const f = filter.toLowerCase()
  return SLASH_ROOT.filter(r => r.key.startsWith(f) || (f.length > 0 && f.startsWith(r.key))).map(r => ({
    id: r.id, label: r.label, hint: r.hint, slashParts: { muted: '/', arg: r.key }, pick: slashRootToPick(r)
  }))
}

export const REASONING_SUB_KEYS = ['off', 'low', 'medium', 'high', 'help', 'default', 'minimal', 'xhigh', 'none'] as const
export const REASONING_SUB_HINTS: Record<string, string> = {
  off: 'Disable reasoning.effort (overrides env)', low: 'Low reasoning effort', medium: 'Medium reasoning effort', high: 'High reasoning effort',
  help: 'Usage & current setting (same as /reasoning help)', default: 'Follow OPENROUTER_REASONING_EFFORT on server',
  minimal: 'Minimal', xhigh: 'Extra high', none: 'Send effort none (provider)'
}

export const AT_STATIC_SUGGEST_ROWS: SuggestRow[] = [
  { id: 'at-context', label: '@context', hint: 'Open the optional context field above', pick: { type: 'expand_context' } },
  { id: 'at-verbose', label: '@verbose', hint: 'Ask for a detailed answer', pick: { type: 'replace', text: 'Explain in detail, step by step. ' } },
  { id: 'at-brief', label: '@brief', hint: 'Ask for a short answer', pick: { type: 'replace', text: 'Keep your answer brief. ' } },
  { id: 'at-docs', label: '@documents', hint: 'Use uploaded documents when relevant', pick: { type: 'replace', text: 'Search and use my uploaded documents when relevant. ' } },
]

export function buildSuggestionRows(value: string, cursor: number, dismissed: boolean, toolNames: string[]): SuggestRow[] {
  if (dismissed) return []
  const slashCtx = parseSlashSuggestContext(value, cursor)
  if (slashCtx) {
    if (slashCtx.mode === 'reasoning_sub') {
      if (slashCtx.subFilter === '') return []
      return REASONING_SUB_KEYS.filter(k => k.startsWith(slashCtx.subFilter)).map(sub => ({
        id: `reasoning-sub-${sub}`, label: `/reasoning ${sub}`, hint: REASONING_SUB_HINTS[sub],
        slashParts: { muted: '/reasoning ', arg: sub }, pick: { type: 'replace', text: `/reasoning ${sub} ` }
      }))
    }
    return filterRootSlashRows(slashCtx.filter)
  }
  const trig = parseInputTrigger(value, cursor)
  if (!trig || trig.kind !== '@') return []
  const toolRows: SuggestRow[] = [...toolNames].sort().map(name => ({
    id: `tool-${name}`, label: `@${name}`, hint: `Prefer the ${name} tool when relevant`,
    pick: { type: 'replace', text: `Use the ${name} tool when needed: ` }
  }))
  return filterSuggestRows([...AT_STATIC_SUGGEST_ROWS, ...toolRows], trig.filter)
}
