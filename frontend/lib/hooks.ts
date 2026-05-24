'use client'

import { useState, useCallback, useEffect, useRef } from 'react'
import { streamAgent, stopAgent, getCostStatus, getHistory } from './api'

async function notifyTaskDone() {
  if (typeof window === 'undefined' || !('__TAURI__' in window)) return
  try {
    const { isPermissionGranted, requestPermission, sendNotification } =
      await import('@tauri-apps/plugin-notification')
    let granted = await isPermissionGranted()
    if (!granted) {
      const perm = await requestPermission()
      granted = perm === 'granted'
    }
    if (granted) sendNotification({ title: 'Agent System', body: 'Task completed.' })
  } catch {
    // not in Tauri context or plugin unavailable — ignore
  }
}

/** One SSE payload from the agent stream (`reasoning_delta` = OpenRouter model reasoning when enabled). */
export type StreamEvent = {
  type: string
  message?: string
  content?: string
  /** Base64 data URLs attached to a user_message event (rendered as image thumbnails). */
  images?: string[]
  tool_name?: string
  tool_input?: Record<string, unknown>
  tool_result?: string
  error?: string
  cost?: number
  /** Present on streamed events once the backend attaches it (needed for feedback after `done`). */
  task_id?: string
  conversation_id?: string
  context_tokens_used?: number
  context_tokens_max?: number
  context_percent?: number
  client_ts?: number
}

const STORAGE_KEY = 'agent_session'
const MAX_STORED_EVENTS = 200
const MAX_STORED_TOOL_RESULT_CHARS = 2000

function compactEventsForStorage(events: StreamEvent[]): StreamEvent[] {
  return events
    .slice(-MAX_STORED_EVENTS)
    .map((event) => {
      if (!event.tool_result || event.tool_result.length <= MAX_STORED_TOOL_RESULT_CHARS) return event
      return {
        ...event,
        tool_result: `${event.tool_result.slice(0, MAX_STORED_TOOL_RESULT_CHARS)}…`,
      }
    })
}

function loadSession(): { events: StreamEvent[]; conversationId: string | null } {
  if (typeof window === 'undefined') return { events: [], conversationId: null }
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return { events: [], conversationId: null }
    return JSON.parse(raw)
  } catch {
    return { events: [], conversationId: null }
  }
}

function saveSession(events: StreamEvent[], conversationId: string | null) {
  if (typeof window === 'undefined') return
  try {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        events: compactEventsForStorage(events),
        conversationId,
      }),
    )
  } catch {
    // storage full — ignore
  }
}

export function useAgentStream() {
  const [events, setEvents] = useState<StreamEvent[]>([])
  const [isRunning, setIsRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [taskId, setTaskId] = useState<string | null>(null)
  const [hydrated, setHydrated] = useState(false)
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const pendingSaveRef = useRef<{ events: StreamEvent[]; conversationId: string | null } | null>(
    null,
  )

  const flushPendingSave = () => {
    if (!pendingSaveRef.current) return
    saveSession(pendingSaveRef.current.events, pendingSaveRef.current.conversationId)
    pendingSaveRef.current = null
  }

  // Restore session from localStorage on mount
  useEffect(() => {
    const session = loadSession()
    if (session.events.length > 0 || session.conversationId) {
      setEvents(session.events)
      setConversationId(session.conversationId)
    }
    setHydrated(true)
  }, [])

  // Persist session whenever events or conversationId change (after hydration).
  // Throttled to at most one write per 200 ms while streaming.
  useEffect(() => {
    if (!hydrated) return
    pendingSaveRef.current = { events, conversationId }
    if (saveTimerRef.current) return
    saveTimerRef.current = setTimeout(() => {
      saveTimerRef.current = null
      flushPendingSave()
    }, 200)
  }, [events, conversationId, hydrated])

  useEffect(() => {
    return () => {
      if (saveTimerRef.current) {
        clearTimeout(saveTimerRef.current)
        saveTimerRef.current = null
      }
      flushPendingSave()
    }
  }, [])

  const run = useCallback(async (
    query: string,
    context?: string,
    convId?: string | null,
    reasoningEffort?: string,
    images?: string[],
  ) => {
    setTaskId(null)
    setEvents(prev => {
      const next = [...prev]
      if (next.length > 0) {
        next.push({
          type: 'turn_divider',
          content: 'Follow-up run',
          client_ts: Date.now(),
        })
      }
      next.push({
        type: 'user_message',
        content: query,
        images: images && images.length > 0 ? images : undefined,
        client_ts: Date.now(),
      })
      return next
    })
    setError(null)
    setIsRunning(true)

    try {
      const response = await streamAgent(
        query,
        context,
        undefined,
        convId ?? undefined,
        reasoningEffort,
        images,
      )
      if (!response.ok) {
        let detail = ''
        try {
          const payload = await response.json()
          detail = payload?.detail || payload?.error || ''
        } catch {
          detail = await response.text().catch(() => '')
        }
        if (response.status === 401) {
          throw new Error(detail || 'Unauthorized (401): configure BACKEND_API_KEY for the /api/backend proxy.')
        }
        throw new Error(detail || `Stream request failed (${response.status})`)
      }
      if (!response.body) throw new Error('No response body')

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      const processEventBlock = (block: string) => {
        const dataLines: string[] = []
        for (const rawLine of block.split(/\r?\n/)) {
          if (rawLine.startsWith('data:')) {
            dataLines.push(rawLine.slice(5).trimStart())
          }
        }
        if (dataLines.length === 0) return

        try {
          const event: StreamEvent = {
            ...JSON.parse(dataLines.join('\n')),
            client_ts: Date.now(),
          }
          setEvents(prev => [...prev, event])
          if (event.task_id) setTaskId(event.task_id)
          if (event.type === 'done') {
            if (event.conversation_id) setConversationId(event.conversation_id)
            setIsRunning(false)
            setTaskId(null)
            notifyTaskDone()
          }
          if (event.type === 'error') {
            setIsRunning(false)
            setTaskId(null)
          }
        } catch {
          // skip malformed data payloads
        }
      }

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const blocks = buffer.split(/\r?\n\r?\n/)
        buffer = blocks.pop() ?? ''

        for (const block of blocks) {
          processEventBlock(block)
        }
      }

      if (buffer.trim()) {
        processEventBlock(buffer)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error')
      setTaskId(null)
    } finally {
      setIsRunning(false)
    }
  }, [])

  const stop = useCallback(async () => {
    if (taskId) {
      try { await stopAgent(taskId) } catch { /* ignore */ }
    }
    setIsRunning(false)
    setTaskId(null)
  }, [taskId])

  const reset = useCallback(() => {
    setEvents([])
    setError(null)
    setIsRunning(false)
    setTaskId(null)
    saveSession([], null)
  }, [])

  const newConversation = useCallback(() => {
    setConversationId(null)
    setEvents([])
    setError(null)
    saveSession([], null)
  }, [])

  return { events, isRunning, error, conversationId, taskId, run, reset, stop, newConversation }
}

export function useCostStatus() {
  const [data, setData] = useState<Record<string, unknown> | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await getCostStatus()
      setData(result)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { refresh() }, [refresh])

  return { data, loading, error, refresh }
}

export function useHistory() {
  const [data, setData] = useState<{ tasks: unknown[]; total: number } | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async (limit = 20, offset = 0, q?: string) => {
    setLoading(true)
    setError(null)
    try {
      const result = await getHistory(limit, offset, q)
      setData(result)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [])

  return { data, loading, error, refresh }
}
