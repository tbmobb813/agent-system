import { useState, useMemo, useEffect, useCallback, useRef } from 'react'
import { useAgentStream, StreamEvent } from '@/lib/hooks'
import {
  getAgentModels,
  getAgentToolsHealth,
  getAgentStats,
  getAnalyticsSkills,
  getCostStatus,
  getHistory,
  getMcpServers,
  getSettings,
  getSkillChains,
  getTaskSuggestions,
  getTools,
  getWorkflowSuggestions,
  listConnectors,
  saveConnector,
  type ConnectorStatus,
} from '@/lib/api'
import { OpsPanel } from './AgentExecutorUI'

const FEEDBACK_NUDGE_EVERY = 5
const REASONING_EFFORT_STORAGE_KEY = 'agent_ui_reasoning_effort'

type OpsPanelSlice = 'loading' | { ok: unknown } | { err: string }

export type OpsModalState = Record<OpsPanel, OpsPanelSlice>

const INITIAL_OPS_MODAL_STATE: OpsModalState = {
  tools: 'loading',
  skills: 'loading',
  mcp: 'loading',
  stats: 'loading',
  history: 'loading',
  connectors: 'loading',
  workflows: 'loading',
  skill_chains: 'loading',
}

function errMessage(e: unknown): string {
  return e instanceof Error ? e.message : String(e)
}

export function useAgentExecutorState() {
  const [query, setQuery] = useState('')
  const [context, setContext] = useState('')
  const [attachedImages, setAttachedImages] = useState<string[]>([])
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
  const [opsModalState, setOpsModalState] = useState<OpsModalState>(() => ({ ...INITIAL_OPS_MODAL_STATE }))
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

  // ── Follow-up suggestions (Feature #1) ──────────────────────────────────
  const [suggestions, setSuggestions] = useState<string[]>([])

  // Clear suggestions when a new run starts
  useEffect(() => { if (isRunning) setSuggestions([]) }, [isRunning])

  // After each completed run, wait briefly for the background generator then fetch
  useEffect(() => {
    if (completedRuns === 0) return
    const doneEvent = [...merged].reverse().find(ev => ev.type === 'done')
    const tid = doneEvent?.task_id
    if (!tid) return
    let cancelled = false
    const timer = setTimeout(async () => {
      try {
        const data = await getTaskSuggestions(tid)
        if (!cancelled && data.ready && Array.isArray(data.suggestions) && data.suggestions.length > 0) {
          setSuggestions(data.suggestions)
        }
      } catch { /* non-critical */ }
    }, 1800)
    return () => { cancelled = true; clearTimeout(timer) }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [completedRuns])

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
    setOpsModalState((prev) => ({ ...prev, [panel]: 'loading' }))
    if (panel === 'tools') {
      Promise.all([getTools(), getSettings()])
        .then(([toolsData, settingsData]) => {
          const td = toolsData as { tools?: unknown }
          const rawTools = Array.isArray(td.tools) ? td.tools : []
          const tools = rawTools.map((t): { name: string; description: string } => {
            if (typeof t === 'string') return { name: t, description: '' }
            if (t && typeof t === 'object' && 'name' in t) {
              const o = t as { name: unknown; description?: unknown }
              return {
                name: String(o.name),
                description: typeof o.description === 'string' ? o.description : '',
              }
            }
            return { name: '', description: '' }
          })
          const sd = settingsData as { default_tools?: unknown }
          const defaultsRaw = sd.default_tools
          const defaults = Array.isArray(defaultsRaw)
            ? defaultsRaw.filter((x): x is string => typeof x === 'string')
            : []
          setOpsModalState((prev) => ({
            ...prev,
            tools: { ok: { tools, enabledSet: new Set(defaults) } },
          }))
        })
        .catch((e: unknown) => setOpsModalState((prev) => ({ ...prev, tools: { err: errMessage(e) } })))
    } else if (panel === 'skills') {
      getAnalyticsSkills()
        .then((d: unknown) => {
          const o = d as { skills?: unknown; growth_areas?: unknown }
          setOpsModalState((prev) => ({
            ...prev,
            skills: {
              ok: {
                skills: Array.isArray(o.skills) ? o.skills : [],
                growthAreas: Array.isArray(o.growth_areas) ? o.growth_areas : [],
              },
            },
          }))
        })
        .catch((e: unknown) => setOpsModalState((prev) => ({ ...prev, skills: { err: errMessage(e) } })))
    } else if (panel === 'stats') {
      Promise.all([getCostStatus(), getAgentStats(7)])
        .then(([c, s]) => {
          const cost = c as Record<string, unknown>
          const stats = s as Record<string, unknown>
          const latency = stats.latency_by_endpoint
          setOpsModalState((prev) => ({
            ...prev,
            stats: {
              ok: {
                budget: {
                  spentToday: cost.spent_today,
                  spentMonth: cost.spent_month,
                  remaining: cost.remaining,
                  percentUsed: cost.percent_used,
                  status: cost.status,
                },
                latency: Array.isArray(latency) ? latency : [],
              },
            },
          }))
        })
        .catch((e: unknown) => setOpsModalState((prev) => ({ ...prev, stats: { err: errMessage(e) } })))
    } else if (panel === 'history') {
      getHistory(8, 0)
        .then((d: unknown) => {
          const o = d as { tasks?: unknown; total?: unknown }
          setOpsModalState((prev) => ({
            ...prev,
            history: {
              ok: {
                tasks: Array.isArray(o.tasks) ? o.tasks : [],
                total: typeof o.total === 'number' ? o.total : 0,
              },
            },
          }))
        })
        .catch((e: unknown) => setOpsModalState((prev) => ({ ...prev, history: { err: errMessage(e) } })))
    } else if (panel === 'connectors') {
      listConnectors()
        .then((data: ConnectorStatus[]) => {
          setOpsModalState((prev) => ({ ...prev, connectors: { ok: { connectors: data } } }))
        })
        .catch((e: unknown) => setOpsModalState((prev) => ({ ...prev, connectors: { err: errMessage(e) } })))
    } else if (panel === 'mcp') {
      Promise.all([getAgentToolsHealth(), getMcpServers()])
        .then(([h, sv]) => {
          const health = h as Record<string, unknown>
          const servers = sv as Record<string, unknown>
          setOpsModalState((prev) => ({
            ...prev,
            mcp: {
              ok: {
                checks: Array.isArray(health.checks) ? health.checks : [],
                healthyCount:
                  typeof health.healthy_count === 'number' ? health.healthy_count : 0,
                total: typeof health.total === 'number' ? health.total : 0,
                servers: Array.isArray(servers.servers) ? servers.servers : [],
              },
            },
          }))
        })
        .catch((e: unknown) => setOpsModalState((prev) => ({ ...prev, mcp: { err: errMessage(e) } })))
    } else if (panel === 'workflows') {
      getWorkflowSuggestions()
        .then((d) => {
          setOpsModalState((prev) => ({
            ...prev,
            workflows: { ok: { suggestions: Array.isArray(d.suggestions) ? d.suggestions : [] } },
          }))
        })
        .catch((e: unknown) => setOpsModalState((prev) => ({ ...prev, workflows: { err: errMessage(e) } })))
    } else if (panel === 'skill_chains') {
      getSkillChains()
        .then((d) => {
          setOpsModalState((prev) => ({
            ...prev,
            skill_chains: { ok: { chains: Array.isArray(d.chains) ? d.chains : [] } },
          }))
        })
        .catch((e: unknown) => setOpsModalState((prev) => ({ ...prev, skill_chains: { err: errMessage(e) } })))
    }
  }, [])

  const openOpsPanel = useCallback((panel: OpsPanel) => { setOpsPanel(panel); setOpsModalOpen(true); loadOpsPanel(panel) }, [loadOpsPanel])

  return {
    query, setQuery, context, setContext, attachedImages, setAttachedImages, editLastOpen, setEditLastOpen, showThinkingLive, setShowThinkingLive,
    reasoningPhaseOpenByTurn, setReasoningPhaseOpenByTurn, reasoningEffortForRequest, setReasoningEffortForRequest,
    showFeedbackNudge, dismissFeedbackNudge, feedbackDetailsRef, contextPanelRef, queryInputRef,
    toolNames, queryCursor, setQueryCursor, suggestDismissed, setSuggestDismissed, suggestHighlight, setSuggestHighlight,
    quickActionsOpen, setQuickActionsOpen, reasoningArgModal, setReasoningArgModal, helpModalOpen, setHelpModalOpen,
    modelsModalOpen, setModelsModalOpen, modelsModalState, opsModalOpen, setOpsModalOpen, opsPanel, opsModalState,
    mcpDeleteBusyName, setMcpDeleteBusyName, quickActionsRef, quickActionsButtonRef,
    events, merged, isRunning, error, conversationId, run, reset, stop, newConversation,
    latestRunCost, lastUserMessage, openOpsPanel, loadModelsForModal, skipReasoningModalSig,
    suggestions,
  }
}
