const configuredApiUrl = (process.env.NEXT_PUBLIC_API_URL || '').trim()
const API_URL = configuredApiUrl.startsWith('/api/backend') ? configuredApiUrl : '/api/backend'

// SSE streaming must bypass the Next.js proxy (which buffers responses).
// Connect directly to the backend — CORS is configured to allow this.
const STREAM_URL = (process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000').trim()

function headers(): Record<string, string> {
  return { 'Content-Type': 'application/json' }
}

/** Auth header for direct-to-backend calls that bypass the Next.js middleware. */
function streamHeaders(): Record<string, string> {
  const key = process.env.NEXT_PUBLIC_BACKEND_API_KEY
  return key ? { 'Content-Type': 'application/json', Authorization: `Bearer ${key}` } : headers()
}

/** Fetch with a timeout. Throws if the server doesn't respond in time. */
async function fetchWithTimeout(url: string, options: RequestInit = {}, timeoutMs = 10000): Promise<Response> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    return await fetch(url, { ...options, signal: controller.signal })
  } catch (err) {
    if ((err as Error).name === 'AbortError') throw new Error('Request timed out')
    throw err
  } finally {
    clearTimeout(timer)
  }
}

export async function getHealth() {
  const res = await fetchWithTimeout(`${API_URL}/health`)
  if (!res.ok) throw new Error('Health check failed')
  return res.json()
}

export async function getCostBreakdown() {
  const res = await fetchWithTimeout(`${API_URL}/status/costs/breakdown`, { headers: headers() })
  if (!res.ok) throw new Error(`Failed to fetch cost breakdown (${res.status})`)
  return res.json()
}

export async function getCostStatus() {
  const res = await fetchWithTimeout(`${API_URL}/status/costs`, { headers: headers() })
  if (!res.ok) throw new Error(`Failed to fetch cost status (${res.status})`)
  return res.json()
}

export async function getAnalyticsOverview() {
  const res = await fetchWithTimeout(`${API_URL}/analytics/overview`, { headers: headers() })
  if (!res.ok) throw new Error(`Failed to fetch analytics overview (${res.status})`)
  return res.json()
}

export async function getAnalyticsDaily(days = 7) {
  const res = await fetchWithTimeout(`${API_URL}/analytics/daily?days=${days}`, { headers: headers() })
  if (!res.ok) throw new Error(`Failed to fetch analytics daily (${res.status})`)
  return res.json()
}

export async function getAnalyticsModels(days = 30) {
  const res = await fetchWithTimeout(`${API_URL}/analytics/models?days=${days}`, { headers: headers() })
  if (!res.ok) throw new Error(`Failed to fetch analytics models (${res.status})`)
  return res.json()
}

export async function getAnalyticsTools(days = 30) {
  const res = await fetchWithTimeout(`${API_URL}/analytics/tools?days=${days}`, { headers: headers() })
  if (!res.ok) throw new Error(`Failed to fetch analytics tools (${res.status})`)
  return res.json()
}

export async function getAnalyticsAlerts(days = 30) {
  const res = await fetchWithTimeout(`${API_URL}/analytics/alerts?days=${days}`, { headers: headers() })
  if (!res.ok) throw new Error(`Failed to fetch analytics alerts (${res.status})`)
  return res.json()
}

export async function getHistory(limit = 20, offset = 0, q?: string) {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) })
  if (q && q.trim()) params.set('q', q.trim())
  const res = await fetchWithTimeout(`${API_URL}/history?${params}`, { headers: headers() })
  if (!res.ok) throw new Error(`Failed to fetch history (${res.status})`)
  return res.json()
}

export async function getTaskDetail(taskId: string) {
  const res = await fetchWithTimeout(`${API_URL}/history/${taskId}`, { headers: headers() })
  if (!res.ok) throw new Error(`Failed to fetch task (${res.status})`)
  return res.json()
}

export async function deleteTask(taskId: string) {
  const res = await fetchWithTimeout(`${API_URL}/history/${taskId}`, {
    method: 'DELETE',
    headers: headers(),
  })
  if (!res.ok) throw new Error(`Failed to delete task (${res.status})`)
  return res.json()
}

export async function getSettings() {
  const res = await fetchWithTimeout(`${API_URL}/settings`, { headers: headers() })
  if (!res.ok) throw new Error(`Failed to fetch settings (${res.status})`)
  return res.json()
}

export async function updateSettings(data: object) {
  const res = await fetchWithTimeout(`${API_URL}/settings`, {
    method: 'POST',
    headers: headers(),
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error(`Failed to update settings (${res.status})`)
  return res.json()
}

export async function getTools() {
  const res = await fetchWithTimeout(`${API_URL}/tools`, { headers: headers() })
  if (!res.ok) throw new Error(`Failed to fetch tools (${res.status})`)
  return res.json()
}

export async function stopAgent(taskId: string) {
  const res = await fetchWithTimeout(`${API_URL}/agent/stop?task_id=${taskId}`, {
    method: 'POST',
    headers: headers(),
  })
  if (!res.ok) throw new Error(`Stop failed (${res.status})`)
  return res.json()
}

/** Returns raw Response with SSE body for streaming.
 *  Goes directly to the backend to avoid Next.js dev-server response buffering.
 */
export function streamAgent(query: string, context?: string, tools?: string[], conversationId?: string) {
  return fetch(`${STREAM_URL}/agent/stream`, {
    method: 'POST',
    headers: streamHeaders(),
    body: JSON.stringify({ query, context, tools, conversation_id: conversationId ?? null }),
  })
}

export async function getDocuments(limit = 20, offset = 0) {
  const res = await fetchWithTimeout(`${API_URL}/documents?limit=${limit}&offset=${offset}`, {
    headers: headers(),
  })
  if (!res.ok) throw new Error(`Failed to fetch documents (${res.status})`)
  return res.json()
}

export async function uploadDocument(file: File) {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${API_URL}/documents/upload`, {
    method: 'POST',
    body: form,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || `Upload failed (${res.status})`)
  }
  return res.json()
}

export async function deleteDocument(documentId: string) {
  const res = await fetchWithTimeout(`${API_URL}/documents/${documentId}`, {
    method: 'DELETE',
    headers: headers(),
  })
  if (!res.ok) throw new Error(`Failed to delete document (${res.status})`)
  return res.json()
}

export async function runAgent(query: string, context?: string, tools?: string[]) {
  const res = await fetch(`${API_URL}/agent/run`, {
    method: 'POST',
    headers: headers(),
    body: JSON.stringify({ query, context, tools }),
  })
  if (!res.ok) throw new Error('Agent run failed')
  return res.json()
}
