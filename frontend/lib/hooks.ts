'use client'

import { useState, useCallback, useEffect } from 'react'
import { streamAgent, stopAgent, getCostStatus, getHistory } from './api'

export type StreamEvent = {
  type: string
  message?: string
  content?: string
  tool_name?: string
  tool_input?: Record<string, unknown>
  tool_result?: string
  error?: string
  cost?: number
  conversation_id?: string
  task_id?: string
  context_tokens_used?: number
  context_tokens_max?: number
  context_percent?: number
}

const STORAGE_KEY = 'agent_session'

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
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ events, conversationId }))
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

  // Restore session from localStorage on mount
  useEffect(() => {
    const session = loadSession()
    if (session.events.length > 0 || session.conversationId) {
      setEvents(session.events)
      setConversationId(session.conversationId)
    }
    setHydrated(true)
  }, [])

  // Persist session whenever events or conversationId change (after hydration)
  useEffect(() => {
    if (!hydrated) return
    saveSession(events, conversationId)
  }, [events, conversationId, hydrated])

  const run = useCallback(async (query: string, context?: string, convId?: string | null) => {
    setEvents([])
    setError(null)
    setIsRunning(true)

    try {
      const response = await streamAgent(query, context, undefined, convId ?? undefined)
      if (!response.body) throw new Error('No response body')

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const event: StreamEvent = JSON.parse(line.slice(6))
              setEvents(prev => [...prev, event])
              if (event.task_id) setTaskId(event.task_id)
              if (event.type === 'done') {
                if (event.conversation_id) setConversationId(event.conversation_id)
                setIsRunning(false)
                setTaskId(null)
              }
              if (event.type === 'error') {
                setIsRunning(false)
                setTaskId(null)
              }
            } catch {
              // skip malformed lines
            }
          }
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error')
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
  const [loading, setLoading] = useState(false)
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

  return { data, loading, error, refresh }
}

export function useHistory() {
  const [data, setData] = useState<{ tasks: unknown[]; total: number } | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async (limit = 20, offset = 0) => {
    setLoading(true)
    setError(null)
    try {
      const result = await getHistory(limit, offset)
      setData(result)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [])

  return { data, loading, error, refresh }
}
