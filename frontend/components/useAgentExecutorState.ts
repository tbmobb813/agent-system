import { useState, useMemo, useEffect, useLayoutEffect, useCallback, useRef } from 'react'
import { useAgentStream, StreamEvent } from '@/lib/hooks'
import {
  getAgentModels,
  getAgentToolsHealth,
  getAnalyticsSkills,
  getCostStatus,
  getHistory,
  getMcpServers,
  getSettings,
  getTools,
  deleteMcpServer,
} from '@/lib/api'
import {
  visibleChatEvents,
  splitLeadingPhaseEvents,
  phaseSummaryPreview,
} from './AgentExecutorChat'
import { OpsPanel } from './AgentExecutorUI'

const FEEDBACK_NUDGE_EVERY = 5
const REASONING_EFFORT_STORAGE_KEY = 'agent_ui_reasoning_effort'

export function useAgentExecutorState() {
  const [query, setQuery] = useState('')
  const [context, setContext] = useState('')
  const [editLastOpen, setEditLastOpen] = useState(false)
  const [showThinkingLive, setShowThinkingLive] = useState(true)
  const [reasoningPhaseOpenByTurn, setReasoningPhaseOpenByTurn] = useState<Record<number, boolean>>({})
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
  const [quickActionsOpen, setQuickActionsOpen] = useState(false)
  const [reasoningArgModal, setReasoningArgModal] = useState<null | { from: number; to: number }>(null)
  const skipReasoningModalSig = useRef<string | null>(null)
  const queryRef = useRef(query)
  const [helpModalOpen, setHelpModalOpen] = useState(false)
  const [modelsModalOpen, setModelsModalOpen] = useState(false)
  const [modelsModalState, setModelsModalState] = useState<'loading' | { ok: Record<string, unknown> } | { err: string }>('loading')
  const [opsModalOpen, setOpsModalOpen] = useState(false)
  const [opsPanel, setOpsPanel] = useState<OpsPanel>('tools')
  const [mcpDeleteBusyName, setMcpDeleteBusyName] = useState<string | null>(null)
  const [opsModalState, setOpsModalState] = useState<any>({ tools: 'loading', skills: 'loading', mcp: 'loading', stats: 'loading', history: 'loading' })
  const quickActionsRef = useRef<HTMLDivElement>(null)
  const quickActionsButtonRef = useRef<HTMLButtonElement>(null)

  const { events, isRunning, error, conversationId, run, reset, stop, newConversation } = useAgentStream()

  useEffect(() => {
    let cancelled = false
    getTools().then((data: { tools?: string[] }) => {
      if (!cancelled) setToolNames(Array.isArray(data?.tools) ? data.tools : [])
    }).catch(() => { if (!cancelled) setToolNames([]) })
    return () => { cancelled = true }
  }, [])

  useEffect(() => { queryRef.current = query }, [query])

  useEffect(() => {
    if (typeof window === 'undefined') return
    const v = localStorage.getItem(REASONING_EFFORT_STORAGE_KEY)
    if (v) setReasoningEffortForRequest(v)
    setReasoningPrefHydrated(true)
  }, [])

  useEffect(() => {
    if (typeof window === 'undefined' || !reasoningPrefHydrated) return
    if (reasoningEffortForRequest === undefined) localStorage.removeItem(REASONING_EFFORT_STORAGE_KEY)
    else localStorage.setItem(REASONING_EFFORT_STORAGE_KEY, reasoningEffortForRequest)
  }, [reasoningEffortForRequest, reasoningPrefHydrated])

  const merged = useMemo(() => {
    const out: StreamEvent[] = []
    for (const ev of events) {
      if (ev.type === 'text_delta' || ev.type === 'reasoning_delta') {
        const last = out[out.length - 1]
        if (last?.type === ev.type) {
          last.content = (last.content ?? '') + (ev.content ?? '')
          if (ev.task_id) last.task_id = ev.task_id
          continue
        }
      }
      out.push({ ...ev })
    }
    return out
  }, [events])

  const latestRunCost = useMemo(() => {
    for (let i = merged.length - 1; i >= 0; i--) if (merged[i].type === 'done' && merged[i].cost != null) return merged[i].cost as number
    return null
  }, [merged])

  const lastUserMessage = useMemo(() => {
    for (let i = merged.length - 1; i >= 0; i--) if (merged[i].type === 'user_message' && (merged[i].content || '').trim()) return (merged[i].content || '').trim()
    return ''
  }, [merged])

  const completedRuns = useMemo(() => merged.filter(ev => ev.type === 'done').length, [merged])
  const dismissFeedbackNudge = useCallback(() => { lastFeedbackNudgeDismissedAt.current = completedRuns; setShowFeedbackNudge(false) }, [completedRuns])

  useEffect(() => {
    if (prevConversationId.current !== conversationId) {
      lastFeedbackNudgeDismissedAt.current = 0
      setShowFeedbackNudge(false)
      prevConversationId.current = conversationId
    }
  }, [conversationId])

  useEffect(() => {
    if (completedRuns > 0 && completedRuns % FEEDBACK_NUDGE_EVERY === 0 && completedRuns > lastFeedbackNudgeDismissedAt.current) {
      setShowFeedbackNudge(true)
    }
  }, [completedRuns])

  const loadModelsForModal = useCallback(() => {
    setModelsModalState('loading')
    getAgentModels().then((data: unknown) => setModelsModalState({ ok: data as Record<string, unknown> }))
      .catch((e: unknown) => setModelsModalState({ err: e instanceof Error ? e.message : String(e) }))
  }, [])

  const loadOpsPanel = useCallback((panel: OpsPanel) => {
    setOpsModalState((s: any) => ({ ...s, [panel]: 'loading' }))
    if (panel === 'tools') {
      Promise.all([getTools(), getSettings()]).then(([toolsData, settingsData]) => {
        const rawTools = (toolsData as any)?.tools || []
        const tools = rawTools.map((t: any) => typeof t === 'string' ? { name: t, description: '' } : { name: t.name, description: t.description || '' })
        const defaults = (settingsData as any)?.default_tools || []
        setOpsModalState((s: any) => ({ ...s, tools: { ok: { tools, enabledSet: new Set(defaults) } } }))
      }).catch((e) => setOpsModalState((s: any) => ({ ...s, tools: { err: String(e) } })))
    } else if (panel === 'skills') {
      getAnalyticsSkills().then((d: any) => {
        setOpsModalState((s: any) => ({ ...s, skills: { ok: { skills: d.skills || [], growthAreas: d.growth_areas || [] } } }))
      }).catch((e) => setOpsModalState((s: any) => ({ ...s, skills: { err: String(e) } })))
    } else if (panel === 'stats') {
      Promise.all([getCostStatus(), getAgentStats(7)]).then(([c, s]: any) => {
        setOpsModalState((s2: any) => ({ ...s2, stats: { ok: { budget: { spentToday: c.spent_today, spentMonth: c.spent_month, remaining: c.remaining, percentUsed: c.percent_used, status: c.status }, latency: s.latency_by_endpoint || [] } } }))
      }).catch((e) => setOpsModalState((s: any) => ({ ...s, stats: { err: String(e) } })))
    } else if (panel === 'history') {
      getHistory(8, 0).then((d: any) => {
        setOpsModalState((s: any) => ({ ...s, history: { ok: { tasks: d.tasks || [], total: d.total || 0 } } }))
      }).catch((e) => setOpsModalState((s: any) => ({ ...s, history: { err: String(e) } })))
    } else if (panel === 'mcp') {
      Promise.all([getAgentToolsHealth(), getMcpServers()]).then(([h, sv]: any) => {
        setOpsModalState((s: any) => ({ ...s, mcp: { ok: { checks: h.checks || [], healthyCount: h.healthy_count || 0, total: h.total || 0, servers: sv.servers || [] } } }))
      }).catch((e) => setOpsModalState((s: any) => ({ ...s, mcp: { err: String(e) } })))
    }
  }, [])

  const openOpsPanel = useCallback((panel: OpsPanel) => { setOpsPanel(panel); setOpsModalOpen(true); loadOpsPanel(panel) }, [loadOpsPanel])

  return {
    query, setQuery, context, setContext, editLastOpen, setEditLastOpen, showThinkingLive, setShowThinkingLive,
    reasoningPhaseOpenByTurn, setReasoningPhaseOpenByTurn, reasoningEffortForRequest, setReasoningEffortForRequest,
    showFeedbackNudge, dismissFeedbackNudge, feedbackDetailsRef, contextPanelRef, queryInputRef,
    toolNames, queryCursor, setQueryCursor, suggestDismissed, setSuggestDismissed, suggestHighlight, setSuggestHighlight,
    quickActionsOpen, setQuickActionsOpen, reasoningArgModal, setReasoningArgModal, helpModalOpen, setHelpModalOpen,
    modelsModalOpen, setModelsModalOpen, modelsModalState, opsModalOpen, setOpsModalOpen, opsPanel, opsModalState,
    mcpDeleteBusyName, setMcpDeleteBusyName, quickActionsRef, quickActionsButtonRef,
    events, merged, isRunning, error, conversationId, run, reset, stop, newConversation,
    latestRunCost, lastUserMessage, openOpsPanel, loadModelsForModal, skipReasoningModalSig
  }
}
