'use client'

import { useMemo, useCallback, useEffect, useRef, useState } from 'react'
import type { StreamEvent } from '@/lib/hooks'
import {
  addMcpServer,
  deleteMcpServer,
  deleteAnalyticsSkill,
  getSettings,
  updateSettings,
  uploadDocument,
  upsertAnalyticsSkill,
  saveConnector,
  testConnector,
  type ConnectorStatus,
} from '@/lib/api'
import {
  EventLine,
  TurnDoneFooter,
  visibleChatEvents,
  splitLeadingPhaseEvents,
  phaseSummaryPreview,
} from './AgentExecutorChat'
import {
  IconPlus,
  IconClock,
  IconPaperclip,
  IconSend,
  IconStop,
} from './Icons'
import {
  QuickActionsMenu,
} from './AgentExecutorUI'
import { useAgentExecutorState } from './useAgentExecutorState'
import {
  buildSuggestionRows,
  parseSlashSuggestContext,
  parseInputTrigger,
  REASONING_SUB_KEYS,
  type SuggestRow,
} from './AgentExecutorSuggestions'

const STARTER_PROMPTS = [
  'Summarize my recent task history',
  'Search the web for the latest AI news',
  'What tools do you have available?',
  'Help me write a Python script',
]

function ChatEmptyState({ onPrompt }: { onPrompt: (p: string) => void }) {
  return (
    <div className="dr-chat-empty">
      <div className="dr-chat-empty-inner">
        <div className="dr-chat-empty-glyph">✦</div>
        <h2 className="dr-chat-empty-title">What can I help with?</h2>
        <div className="dr-chat-starter-grid">
          {STARTER_PROMPTS.map(p => (
            <button key={p} type="button" onClick={() => onPrompt(p)} className="dr-chat-starter-chip">
              {p}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

function ConnectorOpsRow({
  connector,
  onToggle,
  onTest,
}: {
  connector: ConnectorStatus
  onToggle: (enabled: boolean) => Promise<void>
  onTest: () => Promise<void>
}) {
  const [busy, setBusy] = useState(false)
  const act = async (fn: () => Promise<void>) => { setBusy(true); try { await fn() } finally { setBusy(false) } }

  return (
    <div className="panel panel-soft p-3 rounded-lg flex items-center gap-3">
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium">{connector.name}</p>
        <p className="text-xs text-muted mt-0.5">
          {connector.configured
            ? connector.token_preview
            : 'Not configured — add a token in Connectors settings'}
        </p>
      </div>
      <div className="flex items-center gap-2 shrink-0">
        {connector.configured && (
          <button
            type="button"
            disabled={busy}
            onClick={() => act(() => onTest())}
            className="dr-btn-ghost px-2 py-1 rounded text-xs disabled:opacity-50"
          >
            Test
          </button>
        )}
        <button
          type="button"
          disabled={busy || !connector.configured}
          onClick={() => act(() => onToggle(!connector.enabled))}
          title={connector.enabled ? 'Disable' : 'Enable'}
          className={`relative inline-flex h-5 w-9 items-center rounded-full border transition-colors disabled:opacity-40 ${
            connector.enabled
              ? 'bg-[color:var(--accent)] border-[color:var(--accent)]'
              : 'bg-[color:var(--surface-soft)] border-[color:var(--border)]'
          }`}
        >
          <span className={`inline-block h-3.5 w-3.5 rounded-full bg-white shadow transition-transform ${connector.enabled ? 'translate-x-4' : 'translate-x-0.5'}`} />
        </button>
      </div>
    </div>
  )
}

export default function AgentExecutor() {
  useEffect(() => {
    document.documentElement.setAttribute('data-page', 'agent')
    return () => document.documentElement.removeAttribute('data-page')
  }, [])

  const {
    query, setQuery, editLastOpen, setEditLastOpen, showThinkingLive,
    reasoningPhaseOpenByTurn, reasoningEffortForRequest, setReasoningEffortForRequest,
    dismissFeedbackNudge, feedbackDetailsRef, queryInputRef,
    toolNames, queryCursor, setQueryCursor, suggestDismissed, setSuggestDismissed, suggestHighlight, setSuggestHighlight,
    quickActionsOpen, setQuickActionsOpen, reasoningArgModal, setReasoningArgModal, helpModalOpen, setHelpModalOpen,
    modelsModalOpen, setModelsModalOpen, modelsModalState, opsModalOpen, setOpsModalOpen, opsPanel, opsModalState,
    quickActionsRef, quickActionsButtonRef,
    events, merged, isRunning, error, conversationId, run, stop, reset, newConversation,
    latestRunCost, lastUserMessage, openOpsPanel, loadModelsForModal, skipReasoningModalSig
  } = useAgentExecutorState()

  type PendingAttachment = {
    id: string
    filename: string
    status: 'uploading' | 'ready' | 'error'
    error?: string
  }

  const [attachments, setAttachments] = useState<PendingAttachment[]>([])
  const [editText, setEditText] = useState('')
  const editInputRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const streamEndRef = useRef<HTMLDivElement>(null)
  const [opsBusy, setOpsBusy] = useState<string | null>(null)
  const [opsNotice, setOpsNotice] = useState<string | null>(null)
  const [mcpForm, setMcpForm] = useState({ name: '', transport: 'http_json', url: '', command: '', args: '' })
  const [skillForm, setSkillForm] = useState({ task_type: '', skill_name: '', required_tools: '' })

  const suggestionRows = useMemo(
    () => buildSuggestionRows(query, queryCursor, suggestDismissed, toolNames),
    [query, queryCursor, suggestDismissed, toolNames],
  )

  const reasoningEffortLabel = useMemo(() => 
    reasoningEffortForRequest === undefined ? 'server default' : reasoningEffortForRequest === 'off' ? 'off' : reasoningEffortForRequest, 
  [reasoningEffortForRequest])

  const liveActivitySummary = useMemo(() => {
    // This could also be moved to useAgentExecutorState if preferred
    return '' // Simplified for now, or import deriveLiveActivitySummary
  }, [])

  const commitReasoningArg = useCallback((opt: string, range: { from: number; to: number }) => {
    skipReasoningModalSig.current = null
    setReasoningArgModal(null)
    if (range.from === -1) {
      setSuggestDismissed(true)
      if (opt === 'default' || opt === 'clear' || opt === 'env') setReasoningEffortForRequest(undefined)
      else if (opt === 'off' || opt === 'disable') setReasoningEffortForRequest('off')
      else if (opt !== 'help' && opt !== '?') setReasoningEffortForRequest(opt)
      queueMicrotask(() => queryInputRef.current?.focus())
      return
    }
    const insert = `/reasoning ${opt} `
    setQuery((q) => q.slice(0, range.from) + insert + q.slice(range.to))
    const pos = range.from + insert.length
    queueMicrotask(() => {
      const el = queryInputRef.current
      if (el) { el.focus(); el.setSelectionRange(pos, pos) }
    })
    setQueryCursor(pos)
    setSuggestDismissed(true)
  }, [setReasoningEffortForRequest, setQuery, setQueryCursor, setSuggestDismissed, setReasoningArgModal, skipReasoningModalSig, queryInputRef])

  const handleDownloadThread = useCallback(() => {
    // Implementation details...
  }, [])

  const tryOpenFeedbackPanel = useCallback(() => {
    // Implementation details...
    return false
  }, [])

  const applySuggestionPick = useCallback((row: SuggestRow, cursorPos: number) => {
    const slashSc = parseSlashSuggestContext(query, cursorPos)
    const atTrig = parseInputTrigger(query, cursorPos)
    const focusPos = (pos: number) => { 
      queueMicrotask(() => { 
        const el = queryInputRef.current
        if (el) { el.focus(); el.setSelectionRange(pos, pos) } 
      })
      setQueryCursor(pos)
      setSuggestDismissed(true) 
    }
    if (row.pick.type === 'replace' || row.pick.type === 'replace_then_reasoning_modal') {
      const start = slashSc ? slashSc.start : atTrig?.start
      if (start === undefined) return
      let repl = row.pick.text; if (repl.startsWith('/') && !/\s$/.test(repl)) repl += ' '
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
    if (row.pick.type === 'action_feedback_panel') { tryOpenFeedbackPanel(); return }
    if (row.pick.type === 'action_clear') { reset(); return }
    if (row.pick.type === 'action_new_thread') { newConversation(); return }
    if (row.pick.type === 'action_stop') { void stop(); return }
  }, [query, reset, newConversation, stop, tryOpenFeedbackPanel, setQuery, setQueryCursor, setSuggestDismissed, setReasoningArgModal, skipReasoningModalSig, queryInputRef])

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    const el = e.currentTarget; const cursor = el.selectionStart ?? query.length; setQueryCursor(cursor)
    const rows = suggestionRows
    if (rows.length > 0 && !isRunning) {
      if (e.key === 'ArrowDown') { e.preventDefault(); setSuggestHighlight((h) => (h + 1) % rows.length); return }
      if (e.key === 'ArrowUp') { e.preventDefault(); setSuggestHighlight((h) => (h - 1 + rows.length) % rows.length); return }
      if (e.key === 'Tab') { e.preventDefault(); applySuggestionPick(rows[suggestHighlight % rows.length], cursor); return }
    }
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault(); const raw = el.value.trim(); if (!raw || isRunning) return
      const readyNames = attachments.filter(a => a.status === 'ready').map(a => a.filename)
      const attachmentContext = readyNames.length > 0
        ? `Attached files in document store: ${readyNames.join(', ')}`
        : undefined
      run(raw, attachmentContext, conversationId, reasoningEffortForRequest); setQuery('')
    }
  }

  const handlePickFiles = useCallback(() => {
    fileInputRef.current?.click()
  }, [])

  const handleAttachFiles = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? [])
    if (files.length === 0) return

    const queue = files.map(file => ({
      id: `${file.name}-${file.size}-${file.lastModified}-${Math.random().toString(36).slice(2, 8)}`,
      filename: file.name,
      status: 'uploading' as const,
    }))

    setAttachments(prev => [...queue, ...prev])

    await Promise.all(queue.map(async (item, idx) => {
      try {
        await uploadDocument(files[idx])
        setAttachments(prev => prev.map(a => a.id === item.id ? { ...a, status: 'ready' } : a))
      } catch (err) {
        const msg = err instanceof Error ? err.message : 'Upload failed'
        setAttachments(prev => prev.map(a => a.id === item.id ? { ...a, status: 'error', error: msg } : a))
      }
    }))

    // Allow selecting the same file again later.
    e.currentTarget.value = ''
  }, [])

  const removeAttachment = useCallback((id: string) => {
    setAttachments(prev => prev.filter(a => a.id !== id))
  }, [])

  useEffect(() => {
    streamEndRef.current?.scrollIntoView({ block: 'end', behavior: 'auto' })
  }, [merged])

  useEffect(() => {
    if (editLastOpen && lastUserMessage) {
      setEditText(lastUserMessage)
      queueMicrotask(() => {
        const el = editInputRef.current
        if (el) { el.focus(); el.setSelectionRange(el.value.length, el.value.length) }
      })
    }
  }, [editLastOpen, lastUserMessage])

  const refreshOpsPanel = useCallback(() => {
    openOpsPanel(opsPanel)
  }, [openOpsPanel, opsPanel])

  const toggleDefaultTool = useCallback(async (toolName: string, enable: boolean) => {
    setOpsBusy(`tool:${toolName}`)
    setOpsNotice(null)
    try {
      const current = await getSettings() as { default_tools?: string[] | null }
      const nextSet = new Set(Array.isArray(current.default_tools) ? current.default_tools : [])
      if (enable) nextSet.add(toolName)
      else nextSet.delete(toolName)
      await updateSettings({ ...current, default_tools: Array.from(nextSet) })
      setOpsNotice(`Tool ${enable ? 'enabled' : 'disabled'}: ${toolName}`)
      openOpsPanel('tools')
    } catch (err) {
      setOpsNotice(err instanceof Error ? err.message : 'Tool update failed')
    } finally {
      setOpsBusy(null)
    }
  }, [openOpsPanel])

  const createMcpServer = useCallback(async () => {
    const name = mcpForm.name.trim()
    const transport = mcpForm.transport as 'http_json' | 'sse' | 'stdio'
    if (!name) {
      setOpsNotice('MCP name is required')
      return
    }

    setOpsBusy('mcp:add')
    setOpsNotice(null)
    try {
      if (transport === 'stdio') {
        await addMcpServer({
          name,
          transport,
          command: mcpForm.command.trim(),
          args: mcpForm.args.split(',').map(s => s.trim()).filter(Boolean),
        })
      } else {
        await addMcpServer({
          name,
          transport,
          url: mcpForm.url.trim(),
        })
      }
      setOpsNotice(`MCP server added: ${name}`)
      setMcpForm({ name: '', transport: 'http_json', url: '', command: '', args: '' })
      openOpsPanel('mcp')
    } catch (err) {
      setOpsNotice(err instanceof Error ? err.message : 'Could not add MCP server')
    } finally {
      setOpsBusy(null)
    }
  }, [mcpForm, openOpsPanel])

  const removeMcpServer = useCallback(async (name: string) => {
    setOpsBusy(`mcp:del:${name}`)
    setOpsNotice(null)
    try {
      await deleteMcpServer(name)
      setOpsNotice(`MCP server deleted: ${name}`)
      openOpsPanel('mcp')
    } catch (err) {
      setOpsNotice(err instanceof Error ? err.message : 'Could not delete MCP server')
    } finally {
      setOpsBusy(null)
    }
  }, [openOpsPanel])

  const addSkill = useCallback(async () => {
    const taskType = skillForm.task_type.trim()
    const skillName = skillForm.skill_name.trim()
    if (!taskType || !skillName) {
      setOpsNotice('Skill task type and name are required')
      return
    }
    setOpsBusy('skill:add')
    setOpsNotice(null)
    try {
      await upsertAnalyticsSkill({
        task_type: taskType,
        skill_name: skillName,
        required_tools: skillForm.required_tools.split(',').map(s => s.trim()).filter(Boolean),
      })
      setOpsNotice(`Skill saved: ${taskType}`)
      setSkillForm({ task_type: '', skill_name: '', required_tools: '' })
      openOpsPanel('skills')
    } catch (err) {
      setOpsNotice(err instanceof Error ? err.message : 'Could not save skill')
    } finally {
      setOpsBusy(null)
    }
  }, [skillForm, openOpsPanel])

  const removeSkill = useCallback(async (taskType: string) => {
    setOpsBusy(`skill:del:${taskType}`)
    setOpsNotice(null)
    try {
      await deleteAnalyticsSkill(taskType)
      setOpsNotice(`Skill deleted: ${taskType}`)
      openOpsPanel('skills')
    } catch (err) {
      setOpsNotice(err instanceof Error ? err.message : 'Could not delete skill')
    } finally {
      setOpsBusy(null)
    }
  }, [openOpsPanel])

  const turnItems = useMemo(() => {
    type TurnItem = { kind: 'turn'; id: number; user?: StreamEvent; events: StreamEvent[] }
    type DividerItem = { kind: 'divider'; event: StreamEvent }
    const items: Array<TurnItem | DividerItem> = []
    let current: TurnItem | null = null
    let nextId = 1
    const flush = () => { if (current && (current.user || current.events.length > 0)) items.push(current); current = null }
    for (const ev of merged) {
      if (ev.type === 'turn_divider') { flush(); items.push({ kind: 'divider', event: ev }); continue }
      if (ev.type === 'user_message') { flush(); current = { kind: 'turn', id: nextId++, user: ev, events: [] }; continue }
      if (!current) current = { kind: 'turn', id: nextId++, events: [] }
      current.events.push(ev)
    }
    flush()
    return items
  }, [merged])

  const opsPanelContent = useMemo(() => {
    const state = opsModalState[opsPanel]
    if (state === 'loading') {
      return <p className="text-sm text-muted">Loading {opsPanel}…</p>
    }
    if ('err' in state) {
      return <p className="text-sm text-[color:var(--danger)]">{state.err}</p>
    }

    const data = state.ok as Record<string, unknown>

    if (opsPanel === 'tools') {
      const tools = Array.isArray(data.tools) ? data.tools as Array<{ name?: string; description?: string }> : []
      const enabledSet = data.enabledSet instanceof Set ? data.enabledSet as Set<string> : new Set<string>()
      return (
        <div className="space-y-3">
          <div className="text-xs text-muted">{tools.length} available · {enabledSet.size} enabled by default</div>
          {tools.length === 0 ? <p className="text-sm text-muted">No tools available.</p> : null}
          {tools.map((tool, i) => (
            <div key={`${tool.name ?? 'tool'}-${i}`} className="panel panel-soft p-3 rounded-lg flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-sm font-medium truncate">{tool.name ?? 'Unnamed tool'}</p>
                {tool.description ? <p className="text-xs text-muted mt-1 leading-relaxed">{tool.description}</p> : null}
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <span className={`text-[10px] uppercase tracking-[0.14em] px-2 py-1 rounded border ${enabledSet.has(tool.name ?? '') ? 'border-[color:var(--success)] text-[color:var(--success)]' : 'border-[color:var(--border)] text-muted'}`}>
                  {enabledSet.has(tool.name ?? '') ? 'enabled' : 'optional'}
                </span>
                <button
                  type="button"
                  disabled={!tool.name || opsBusy === `tool:${tool.name}`}
                  onClick={() => {
                    if (!tool.name) return
                    void toggleDefaultTool(tool.name, !enabledSet.has(tool.name))
                  }}
                  className="dr-btn-ghost px-2 py-1 rounded text-xs disabled:opacity-50"
                >
                  {enabledSet.has(tool.name ?? '') ? 'Disable' : 'Enable'}
                </button>
              </div>
            </div>
          ))}
        </div>
      )
    }

    if (opsPanel === 'skills') {
      const skills = Array.isArray(data.skills) ? data.skills : []
      const growthAreas = Array.isArray(data.growthAreas) ? data.growthAreas : []
      const allSkills = [...skills, ...growthAreas] as Array<Record<string, unknown>>
      return (
        <div className="space-y-3">
          <div className="panel panel-soft p-3 rounded-lg space-y-2">
            <p className="text-xs uppercase tracking-[0.14em] text-muted">Add or update skill</p>
            <div className="grid sm:grid-cols-2 gap-2">
              <input value={skillForm.task_type} onChange={(e) => setSkillForm(prev => ({ ...prev, task_type: e.target.value }))} placeholder="task type (e.g. coding)" className="dr-agent-model-select h-9" />
              <input value={skillForm.skill_name} onChange={(e) => setSkillForm(prev => ({ ...prev, skill_name: e.target.value }))} placeholder="skill name" className="dr-agent-model-select h-9" />
            </div>
            <input value={skillForm.required_tools} onChange={(e) => setSkillForm(prev => ({ ...prev, required_tools: e.target.value }))} placeholder="required tools (comma separated)" className="dr-agent-model-select h-9 w-full" />
            <button type="button" onClick={() => void addSkill()} disabled={opsBusy === 'skill:add'} className="dr-btn-accent px-3 py-1.5 rounded text-xs disabled:opacity-50">{opsBusy === 'skill:add' ? 'Saving…' : 'Save Skill'}</button>
          </div>
          <div className="grid sm:grid-cols-2 gap-3">
            <div className="panel panel-soft p-3 rounded-lg">
              <p className="text-xs uppercase tracking-[0.14em] text-muted">Tracked skills</p>
              <p className="text-lg font-semibold mt-1">{skills.length}</p>
            </div>
            <div className="panel panel-soft p-3 rounded-lg">
              <p className="text-xs uppercase tracking-[0.14em] text-muted">Growth areas</p>
              <p className="text-lg font-semibold mt-1">{growthAreas.length}</p>
            </div>
          </div>
          {skills.length === 0 ? <p className="text-sm text-muted">No skill analytics found yet.</p> : null}
          {skills.length > 0 ? (
            <div className="panel panel-soft rounded-lg overflow-hidden">
              <div className="grid grid-cols-[1.5fr_0.8fr_0.8fr] gap-3 px-3 py-2 text-[10px] uppercase tracking-[0.14em] text-muted border-b border-[color:var(--border)]">
                <span>Skill</span>
                <span className="text-right">Success</span>
                <span className="text-right">Uses</span>
              </div>
              {skills.map((skill, i) => {
                const row = skill as Record<string, unknown>
                const name = String(row.skill ?? row.name ?? `Skill ${i + 1}`)
                const taskType = String(row.task_type ?? row.taskType ?? name)
                const success = row.success_rate ?? row.success ?? row.win_rate
                const uses = row.count ?? row.uses ?? row.total ?? '—'
                return (
                  <div key={`skill-row-${i}`} className="grid grid-cols-[1.5fr_0.8fr_0.8fr] gap-3 px-3 py-2 text-sm border-b last:border-b-0 border-[color:var(--border)]/50">
                    <div className="min-w-0 flex items-center gap-2">
                      <span className="truncate" title={name}>{name}</span>
                      <button type="button" onClick={() => void removeSkill(taskType)} disabled={opsBusy === `skill:del:${taskType}`} className="dr-btn-ghost px-2 py-0.5 rounded text-[10px] disabled:opacity-50">Delete</button>
                    </div>
                    <span className="text-right text-muted">{success == null ? '—' : String(success)}</span>
                    <span className="text-right text-muted">{String(uses)}</span>
                  </div>
                )
              })}
            </div>
          ) : null}
          {growthAreas.length > 0 ? (
            <div className="panel panel-soft p-3 rounded-lg">
              <p className="text-xs uppercase tracking-[0.14em] text-muted mb-2">Top growth areas</p>
              <div className="flex flex-wrap gap-2">
                {growthAreas.map((area, i) => (
                  <span key={`growth-${i}`} className="text-xs px-2 py-1 rounded border border-[color:var(--border)] bg-[color:var(--surface-soft)]">{String(area)}</span>
                ))}
              </div>
            </div>
          ) : null}
          {allSkills.length === 0 ? <p className="text-xs text-muted">Skills can be learned automatically or added manually above.</p> : null}
        </div>
      )
    }

    if (opsPanel === 'stats') {
      const budget = (data.budget ?? {}) as Record<string, unknown>
      const latency = Array.isArray(data.latency) ? data.latency : []

      const percentUsed = typeof budget.percentUsed === 'number' ? budget.percentUsed : Number(budget.percentUsed ?? 0)
      const safePercent = Number.isFinite(percentUsed) ? Math.max(0, Math.min(100, percentUsed)) : 0

      return (
        <div className="space-y-3">
          <div className="panel panel-soft p-3 rounded-lg space-y-3">
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted">Budget usage</span>
              <span className="font-semibold">{safePercent.toFixed(1)}%</span>
            </div>
            <progress className="budget-progress" max={100} value={safePercent} />
            <div className="grid sm:grid-cols-2 gap-2 text-sm">
              <p>Spent today: <span className="text-[color:var(--text)]">{String(budget.spentToday ?? '—')}</span></p>
              <p>Spent month: <span className="text-[color:var(--text)]">{String(budget.spentMonth ?? '—')}</span></p>
              <p>Remaining: <span className="text-[color:var(--text)]">{String(budget.remaining ?? '—')}</span></p>
              <p>Status: <span className="text-[color:var(--text)]">{String(budget.status ?? '—')}</span></p>
            </div>
          </div>
          <div className="panel panel-soft rounded-lg overflow-hidden">
            <div className="grid grid-cols-[1.4fr_0.8fr_0.8fr] gap-3 px-3 py-2 text-[10px] uppercase tracking-[0.14em] text-muted border-b border-[color:var(--border)]">
              <span>Endpoint</span>
              <span className="text-right">P50</span>
              <span className="text-right">P95</span>
            </div>
            {latency.length === 0 ? <p className="px-3 py-3 text-sm text-muted">No latency stats yet.</p> : null}
            {latency.map((entry, i) => {
              const row = entry as Record<string, unknown>
              return (
                <div key={`latency-${i}`} className="grid grid-cols-[1.4fr_0.8fr_0.8fr] gap-3 px-3 py-2 text-sm border-b last:border-b-0 border-[color:var(--border)]/50">
                  <span className="truncate" title={String(row.endpoint ?? row.path ?? 'endpoint')}>{String(row.endpoint ?? row.path ?? 'endpoint')}</span>
                  <span className="text-right text-muted">{String(row.p50_ms ?? row.p50 ?? '—')}</span>
                  <span className="text-right text-muted">{String(row.p95_ms ?? row.p95 ?? '—')}</span>
                </div>
              )
            })}
          </div>
        </div>
      )
    }

    if (opsPanel === 'connectors') {
      const connectors = Array.isArray(data.connectors) ? data.connectors as ConnectorStatus[] : []
      return (
        <div className="space-y-3">
          {connectors.length === 0 && <p className="text-sm text-muted">No connectors available.</p>}
          {connectors.map((c) => (
            <ConnectorOpsRow
              key={c.id}
              connector={c}
              onToggle={async (enabled) => {
                try {
                  await saveConnector(c.id, { enabled })
                  openOpsPanel('connectors')
                } catch (e) {
                  setOpsNotice(e instanceof Error ? e.message : 'Toggle failed')
                }
              }}
              onTest={async () => {
                setOpsNotice('Testing…')
                try {
                  const r = await testConnector(c.id)
                  setOpsNotice(r.ok ? `✓ ${r.detail}` : `✗ ${r.detail}`)
                } catch (e) {
                  setOpsNotice(e instanceof Error ? e.message : 'Test failed')
                }
              }}
            />
          ))}
          <a href="/settings?tab=connectors" className="block text-xs text-[color:var(--accent-2)] hover:underline pt-1">
            Manage tokens &amp; add connectors →
          </a>
        </div>
      )
    }

    if (opsPanel === 'history') {
      const tasks = Array.isArray(data.tasks) ? data.tasks as Array<Record<string, unknown>> : []
      return (
        <div className="space-y-3">
          <div className="text-xs text-muted">Showing {tasks.length} recent tasks</div>
          {tasks.length === 0 ? <p className="text-sm text-muted">No task history available.</p> : null}
          {tasks.map((task, i) => (
            <div key={`hist-${i}`} className="panel panel-soft p-3 rounded-lg text-sm space-y-1">
              <div className="flex items-start justify-between gap-3">
                <p className="font-medium truncate">{String(task.query ?? 'No query')}</p>
                <span className="text-[10px] uppercase tracking-[0.14em] px-2 py-1 rounded border border-[color:var(--border)] text-muted shrink-0">{String(task.status ?? 'unknown')}</span>
              </div>
              <p className="text-xs text-muted">{String(task.created_at ?? '')}</p>
            </div>
          ))}
        </div>
      )
    }

    if (opsPanel === 'mcp') {
      const checks = Array.isArray(data.checks) ? data.checks : []
      const servers = Array.isArray(data.servers) ? data.servers : []
      const healthyCount = typeof data.healthyCount === 'number' ? data.healthyCount : 0
      const total = typeof data.total === 'number' ? data.total : 0
      return (
        <div className="space-y-3">
          <div className="panel panel-soft p-3 rounded-lg space-y-2">
            <p className="text-xs uppercase tracking-[0.14em] text-muted">Add MCP server</p>
            <div className="grid sm:grid-cols-2 gap-2">
              <input value={mcpForm.name} onChange={(e) => setMcpForm(prev => ({ ...prev, name: e.target.value }))} placeholder="server name" className="dr-agent-model-select h-9" />
              <select aria-label="MCP transport" title="MCP transport" value={mcpForm.transport} onChange={(e) => setMcpForm(prev => ({ ...prev, transport: e.target.value }))} className="dr-agent-model-select h-9">
                <option value="http_json">http_json</option>
                <option value="sse">sse</option>
                <option value="stdio">stdio</option>
              </select>
            </div>
            {mcpForm.transport === 'stdio' ? (
              <div className="grid sm:grid-cols-2 gap-2">
                <input value={mcpForm.command} onChange={(e) => setMcpForm(prev => ({ ...prev, command: e.target.value }))} placeholder="command (e.g. npx)" className="dr-agent-model-select h-9" />
                <input value={mcpForm.args} onChange={(e) => setMcpForm(prev => ({ ...prev, args: e.target.value }))} placeholder="args comma-separated" className="dr-agent-model-select h-9" />
              </div>
            ) : (
              <input value={mcpForm.url} onChange={(e) => setMcpForm(prev => ({ ...prev, url: e.target.value }))} placeholder="server URL" className="dr-agent-model-select h-9 w-full" />
            )}
            <button type="button" onClick={() => void createMcpServer()} disabled={opsBusy === 'mcp:add'} className="dr-btn-accent px-3 py-1.5 rounded text-xs disabled:opacity-50">{opsBusy === 'mcp:add' ? 'Adding…' : 'Add MCP Server'}</button>
          </div>
          <div className="grid sm:grid-cols-3 gap-3">
            <div className="panel panel-soft p-3 rounded-lg">
              <p className="text-xs uppercase tracking-[0.14em] text-muted">Healthy</p>
              <p className="text-lg font-semibold mt-1">{healthyCount}</p>
            </div>
            <div className="panel panel-soft p-3 rounded-lg">
              <p className="text-xs uppercase tracking-[0.14em] text-muted">Total checks</p>
              <p className="text-lg font-semibold mt-1">{total || checks.length}</p>
            </div>
            <div className="panel panel-soft p-3 rounded-lg">
              <p className="text-xs uppercase tracking-[0.14em] text-muted">Servers</p>
              <p className="text-lg font-semibold mt-1">{servers.length}</p>
            </div>
          </div>
          <div className="panel panel-soft rounded-lg overflow-hidden">
            <div className="grid grid-cols-[1.2fr_0.8fr_0.8fr] gap-3 px-3 py-2 text-[10px] uppercase tracking-[0.14em] text-muted border-b border-[color:var(--border)]">
              <span>Name</span>
              <span>Status</span>
              <span>Transport</span>
            </div>
            {servers.length === 0 ? <p className="px-3 py-3 text-sm text-muted">No MCP servers configured.</p> : null}
            {servers.map((sv, i) => {
              const row = sv as Record<string, unknown>
              const status = String(row.status ?? 'unknown')
              const name = String(row.name ?? `server-${i + 1}`)
              return (
                <div key={`mcp-${i}`} className="grid grid-cols-[1.2fr_0.8fr_0.8fr] gap-3 px-3 py-2 text-sm border-b last:border-b-0 border-[color:var(--border)]/50">
                  <div className="min-w-0 flex items-center gap-2">
                    <span className="truncate" title={name}>{name}</span>
                    <button type="button" onClick={() => void removeMcpServer(name)} disabled={opsBusy === `mcp:del:${name}`} className="dr-btn-ghost px-2 py-0.5 rounded text-[10px] disabled:opacity-50">Delete</button>
                  </div>
                  <span className={status === 'healthy' ? 'text-[color:var(--success)]' : 'text-muted'}>{status}</span>
                  <span className="text-muted">{String(row.transport ?? '—')}</span>
                </div>
              )
            })}
          </div>
        </div>
      )
    }

    return (
      <div className="panel panel-soft p-3 rounded-lg text-xs font-mono overflow-x-auto">
        {JSON.stringify(data, null, 2)}
      </div>
    )
  }, [
    addSkill,
    createMcpServer,
    mcpForm,
    opsBusy,
    opsModalState,
    opsPanel,
    openOpsPanel,
    removeMcpServer,
    removeSkill,
    setOpsNotice,
    skillForm,
    toggleDefaultTool,
  ])

  return (
    <div className="dr-chat-layout">

      {/* ── Messages ─────────────────────────────── */}
      <div className="dr-chat-scroll-area">
        {merged.length === 0 ? (
          <ChatEmptyState onPrompt={(p) => {
            setQuery(p)
            queueMicrotask(() => queryInputRef.current?.focus())
          }} />
        ) : (
          <div className="dr-chat-thread">
            {turnItems.map((item, i) => {
              if (item.kind === 'divider') return <EventLine key={`divider-${i}`} event={item.event} />
              const chatEvents = visibleChatEvents(item.events)
              const { phase, rest } = splitLeadingPhaseEvents(chatEvents)
              const turnHasDone = item.events.some(ev => ev.type === 'done')
              const phaseDetailsOpen = (showThinkingLive && !turnHasDone) || reasoningPhaseOpenByTurn[item.id] === true
              return (
                <div key={`turn-${item.id}`} className="space-y-3">
                  {item.user && <EventLine event={item.user} />}
                  {showThinkingLive && phase.length > 0 && (
                    <div className="flex justify-start">
                      <details className="max-w-[min(90%,42rem)] w-full rounded-2xl rounded-bl-md border border-[color:var(--border)] bg-[color:var(--surface-soft)] px-3 py-2 text-sm" open={phaseDetailsOpen}>
                        <summary className="text-muted text-sm cursor-pointer list-none [&::-webkit-details-marker]:hidden flex items-start gap-2">
                          <span className="shrink-0 opacity-70">▸</span><span className="truncate min-w-0">{phaseSummaryPreview(phase)}</span>
                        </summary>
                        <div className="mt-2 max-h-48 space-y-1 overflow-y-auto border-t border-[color:var(--border)]/50 pt-2">
                          {phase.map((ev, idx) => <EventLine key={`turn-${item.id}-phase-${idx}`} event={ev} />)}
                        </div>
                      </details>
                    </div>
                  )}
                  {(showThinkingLive && phase.length > 0 ? rest : chatEvents).filter(ev => ev.type !== 'done').map((ev, idx) => <EventLine key={`turn-${item.id}-event-${idx}`} event={ev} />)}
                  {turnHasDone && (
                    <TurnDoneFooter
                      turnId={item.id}
                      events={item.events}
                      isRunning={isRunning}
                      dismissFeedbackNudge={dismissFeedbackNudge}
                      registerFeedbackRef={(el) => { feedbackDetailsRef.current = el }}
                      showThreadDownload={true}
                      threadExportEmpty={false}
                      onDownloadThread={handleDownloadThread}
                      omitDoneCost={false}
                    />
                  )}
                </div>
              )
            })}
            <div ref={streamEndRef} aria-hidden="true" />
          </div>
        )}
      </div>



      {/* ── Input zone ───────────────────────────── */}
      <div className="dr-chat-input-zone">
        <div className="dr-chat-input-inner">
          <form onSubmit={(e) => e.preventDefault()}>
            {error ? <p className="text-sm text-[color:var(--danger)] mb-2 px-1" role="alert">{error}</p> : null}
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*,.pdf,.doc,.docx,.txt,.md,.csv,.json,.yaml,.yml"
              multiple
              aria-label="Attach files and photos"
              title="Attach files and photos"
              className="hidden"
              onChange={handleAttachFiles}
            />
            {attachments.length > 0 ? (
              <div className="dr-agent-attachments mb-2">
                {attachments.map(item => (
                  <span key={item.id} className={`dr-agent-attachment-chip ${item.status === 'error' ? 'is-error' : item.status === 'ready' ? 'is-ready' : ''}`}>
                    <span className="truncate" title={item.filename}>{item.filename}</span>
                    <span className="dr-agent-attachment-status">
                      {item.status === 'uploading' ? 'uploading' : item.status === 'ready' ? 'ready' : 'error'}
                    </span>
                    <button type="button" onClick={() => removeAttachment(item.id)} className="dr-agent-attachment-remove" aria-label={`Remove ${item.filename}`}>×</button>
                  </span>
                ))}
              </div>
            ) : null}
            {editLastOpen && (
              <div className="dr-chat-input-card mb-2">
                <div className="flex items-center gap-2 px-4 pt-3 pb-1">
                  <span className="text-[10px] uppercase tracking-widest text-muted">Editing last message</span>
                  <button type="button" onClick={() => setEditLastOpen(false)} className="ml-auto text-xs text-muted hover:text-[color:var(--text)]">✕ Cancel</button>
                </div>
                <textarea
                  ref={editInputRef}
                  value={editText}
                  onChange={(e) => {
                    setEditText(e.target.value)
                    e.target.style.height = 'auto'
                    e.target.style.height = `${Math.min(e.target.scrollHeight, 200)}px`
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault()
                      const text = editText.trim()
                      if (!text || isRunning) return
                      run(text, undefined, conversationId, reasoningEffortForRequest)
                      setEditLastOpen(false)
                      setEditText('')
                    }
                    if (e.key === 'Escape') setEditLastOpen(false)
                  }}
                  rows={2}
                  className="dr-chat-input-textarea"
                  placeholder="Edit your message…"
                />
                <div className="dr-chat-input-toolbar">
                  <div className="flex-1" />
                  <button
                    type="button"
                    disabled={isRunning || !editText.trim()}
                    onClick={() => {
                      const text = editText.trim()
                      if (!text || isRunning) return
                      run(text, undefined, conversationId, reasoningEffortForRequest)
                      setEditLastOpen(false)
                      setEditText('')
                    }}
                    className="dr-btn-accent px-3 py-1.5 rounded-lg text-sm disabled:opacity-50"
                  >
                    Resend
                  </button>
                </div>
              </div>
            )}
            <div className="dr-chat-input-card">
              <textarea
                data-testid="agent-message-input"
                ref={queryInputRef}
                value={query}
                onChange={(e) => {
                  setQuery(e.target.value)
                  e.target.style.height = 'auto'
                  e.target.style.height = `${Math.min(e.target.scrollHeight, 200)}px`
                }}
                onKeyDown={handleKeyDown}
                placeholder="Ask the agent anything…"
                rows={1}
                disabled={isRunning}
                className="dr-chat-input-textarea disabled:opacity-50"
              />
              <div className="dr-chat-input-toolbar">
                <div className="relative" ref={quickActionsRef}>
                  <button type="button" ref={quickActionsButtonRef} onClick={() => setQuickActionsOpen(!quickActionsOpen)} className="dr-btn-ghost flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-sm">
                    <IconPlus /> Actions
                  </button>
                  {quickActionsOpen && (
                    <QuickActionsMenu
                      isRunning={isRunning}
                      hasMessages={merged.length > 0}
                      hasLastMessage={!!lastUserMessage}
                      reasoningEffortLabel={reasoningEffortLabel}
                      threadExportEmpty={false}
                      onNewConversation={() => { newConversation(); setQuickActionsOpen(false) }}
                      onStop={() => { void stop(); setQuickActionsOpen(false) }}
                      onClear={() => { reset(); setQuickActionsOpen(false) }}
                      onOpenOps={(p) => { openOpsPanel(p); setQuickActionsOpen(false) }}
                      onOpenModels={() => { setModelsModalOpen(true); loadModelsForModal(); setQuickActionsOpen(false) }}
                      onOpenHelp={() => { setHelpModalOpen(true); setQuickActionsOpen(false) }}
                      onOpenReasoningPicker={() => { setSuggestDismissed(true); setReasoningArgModal({ from: -1, to: -1 }); setQuickActionsOpen(false) }}
                      onCopyThread={() => { setQuickActionsOpen(false) }}
                      onFeedback={() => { tryOpenFeedbackPanel(); setQuickActionsOpen(false) }}
                      onEditResend={() => { setEditLastOpen(!editLastOpen); setQuickActionsOpen(false) }}
                    />
                  )}
                </div>
                <button type="button" aria-label="Attach files and photos" title="Attach files and photos" onClick={handlePickFiles} className="dr-btn-ghost p-1.5 rounded-lg">
                  <IconPaperclip />
                </button>
                <div className="flex-1" />
                <button type="button" onClick={() => setReasoningArgModal({ from: -1, to: -1 })} className="dr-agent-hint dr-btn-ghost flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs text-muted font-mono">
                  <IconClock /> {reasoningEffortLabel}
                </button>
                {isRunning ? (
                  <button type="button" aria-label="Stop" onClick={() => void stop()} className="dr-btn-ghost flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-sm text-[color:var(--danger)]">
                    <IconStop /> Stop
                  </button>
                ) : (
                  <button
                    type="submit"
                    data-testid="agent-send-button"
                    aria-label="Send"
                    onClick={() => {
                      const readyNames = attachments.filter(a => a.status === 'ready').map(a => a.filename)
                      const attachmentContext = readyNames.length > 0
                        ? `Attached files in document store: ${readyNames.join(', ')}`
                        : undefined
                      run(query, attachmentContext, conversationId, reasoningEffortForRequest)
                      setQuery('')
                      if (queryInputRef.current) queryInputRef.current.style.height = 'auto'
                    }}
                    className="dr-btn-accent dr-btn-accent-lg px-3 py-1.5 rounded-lg text-sm"
                  >
                    <IconSend />
                  </button>
                )}
              </div>
            </div>
          </form>
          <p className="dr-chat-disclaimer">Agent can make mistakes. Verify important information.</p>
        </div>
      </div>

      {/* ── Modals ───────────────────────────────── */}
      {helpModalOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
          <div className="bg-[color:var(--bg)] p-6 rounded-xl border border-[color:var(--border)] shadow-2xl max-w-lg w-full">
            <h3>Help</h3>
            <button onClick={() => setHelpModalOpen(false)}>Close</button>
          </div>
        </div>
      )}
      {modelsModalOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
          <div className="bg-[color:var(--bg)] p-6 rounded-xl border border-[color:var(--border)] shadow-2xl max-w-lg w-full">
            <h3>Models</h3>
            <pre className="text-xs">{JSON.stringify(modelsModalState, null, 2)}</pre>
            <button onClick={() => setModelsModalOpen(false)}>Close</button>
          </div>
        </div>
      )}
      {opsModalOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
          <div className="bg-[color:var(--bg)] p-6 rounded-xl border border-[color:var(--border)] shadow-2xl max-w-3xl w-full max-h-[80vh] overflow-y-auto space-y-4">
            <div className="flex items-center justify-between gap-3">
              <h3 className="section-title dr-title-16">Ops: {opsPanel}</h3>
              <div className="flex items-center gap-2">
                <button className="dr-btn-ghost px-3 py-1.5 rounded-lg text-sm" onClick={refreshOpsPanel}>Refresh</button>
                <button className="dr-btn-ghost px-3 py-1.5 rounded-lg text-sm" onClick={() => setOpsModalOpen(false)}>Close</button>
              </div>
            </div>
            {opsNotice ? <p className="text-xs text-muted">{opsNotice}</p> : null}
            {opsPanelContent}
          </div>
        </div>
      )}
      {reasoningArgModal && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
          <div className="bg-[color:var(--bg)] p-6 rounded-xl border border-[color:var(--border)] shadow-2xl max-w-lg w-full">
            <h3>Reasoning</h3>
            <div className="grid grid-cols-2 gap-2">
              {REASONING_SUB_KEYS.map(opt => (
                <button key={opt} onClick={() => commitReasoningArg(opt, reasoningArgModal)} className="p-2 border rounded">{opt}</button>
              ))}
            </div>
            <button onClick={() => setReasoningArgModal(null)}>Cancel</button>
          </div>
        </div>
      )}
    </div>
  )
}
