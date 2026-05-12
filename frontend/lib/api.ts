/**
 * Browser API base URL.
 * - Default: same-origin `/api/backend` (Next rewrites to BACKEND_URL — see next.config.ts).
 * - `NEXT_PUBLIC_API_URL=/api/backend/...` — custom path prefix if needed.
 * - `NEXT_PUBLIC_API_URL=https://api.example.com` — direct backend (must allow CORS for this origin).
 */
function resolveApiBaseUrl(): string {
  const raw = (process.env.NEXT_PUBLIC_API_URL || '').trim()
  if (!raw) return '/api/backend'
  if (raw.startsWith('/')) return raw.replace(/\/$/, '') || '/api/backend'
  if (raw.startsWith('http://') || raw.startsWith('https://')) return raw.replace(/\/$/, '')
  return '/api/backend'
}

const API_URL = resolveApiBaseUrl()

function headers(): Record<string, string> {
  return { 'Content-Type': 'application/json' }
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

export async function getAnalyticsDecisions(days = 30) {
  const res = await fetchWithTimeout(`${API_URL}/analytics/decisions?days=${days}`, { headers: headers() })
  if (!res.ok) throw new Error(`Failed to fetch analytics decisions (${res.status})`)
  return res.json()
}

export async function getAnalyticsCostEfficiency() {
  const res = await fetchWithTimeout(`${API_URL}/analytics/cost-efficiency`, { headers: headers() })
  if (!res.ok) throw new Error(`Failed to fetch cost efficiency (${res.status})`)
  return res.json()
}

export async function getAnalyticsErrors(days = 30) {
  const res = await fetchWithTimeout(`${API_URL}/analytics/errors?days=${days}`, { headers: headers() })
  if (!res.ok) throw new Error(`Failed to fetch error analytics (${res.status})`)
  return res.json()
}

export async function getAnalyticsAbTests(limit = 10) {
  const res = await fetchWithTimeout(`${API_URL}/analytics/ab-tests?limit=${limit}`, { headers: headers() })
  if (!res.ok) throw new Error(`Failed to fetch A/B tests (${res.status})`)
  return res.json()
}

export async function getAnalyticsSkills() {
  const res = await fetchWithTimeout(`${API_URL}/analytics/skills`, { headers: headers() })
  if (!res.ok) throw new Error(`Failed to fetch analytics skills (${res.status})`)
  return res.json()
}

export async function upsertAnalyticsSkill(data: {
  task_type: string
  skill_name: string
  success_rate?: number
  total_uses?: number
  proficiency_level?: string
  required_tools?: string[]
}) {
  const res = await fetchWithTimeout(`${API_URL}/analytics/skills`, {
    method: 'POST',
    headers: headers(),
    body: JSON.stringify(data),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: `Failed to upsert skill (${res.status})` }))
    throw new Error(String(err.detail ?? `Failed to upsert skill (${res.status})`))
  }
  return res.json()
}

export async function deleteAnalyticsSkill(taskType: string) {
  const res = await fetchWithTimeout(`${API_URL}/analytics/skills/${encodeURIComponent(taskType)}`, {
    method: 'DELETE',
    headers: headers(),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: `Failed to delete skill (${res.status})` }))
    throw new Error(String(err.detail ?? `Failed to delete skill (${res.status})`))
  }
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

export async function submitTaskFeedback(
  taskId: string,
  data: { signal: 'up' | 'down'; notes?: string },
): Promise<{ status: string; task_id: string; signal: 'up' | 'down'; notes: string | null; created_at: string }> {
  const res = await fetchWithTimeout(`${API_URL}/history/${taskId}/feedback`, {
    method: 'POST',
    headers: headers(),
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error(`Failed to submit feedback (${res.status})`)
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

export async function getPersonaPreview() {
  const res = await fetchWithTimeout(`${API_URL}/settings/persona/preview`, { headers: headers() })
  if (!res.ok) throw new Error(`Failed to fetch persona preview (${res.status})`)
  return res.json()
}

export async function getTools() {
  const res = await fetchWithTimeout(`${API_URL}/tools`, { headers: headers() })
  if (!res.ok) throw new Error(`Failed to fetch tools (${res.status})`)
  return res.json()
}

export async function getAgentToolsHealth() {
  const res = await fetchWithTimeout(`${API_URL}/agent/tools/health`, { headers: headers() })
  if (!res.ok) throw new Error(`Failed to fetch tools health (${res.status})`)
  return res.json()
}

export async function getAgentStats(days = 7) {
  const res = await fetchWithTimeout(`${API_URL}/agent/stats?days=${days}`, { headers: headers() })
  if (!res.ok) throw new Error(`Failed to fetch agent stats (${res.status})`)
  return res.json()
}

export async function addMcpServer(data: {
  name: string
  transport: 'http_json' | 'sse' | 'stdio'
  url?: string
  command?: string
  args?: string[]
  env?: Record<string, string>
}) {
  const res = await fetchWithTimeout(`${API_URL}/agent/mcp/servers`, {
    method: 'POST',
    headers: headers(),
    body: JSON.stringify(data),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: `Failed to add MCP server (${res.status})` }))
    throw new Error(String(err.detail ?? `Failed to add MCP server (${res.status})`))
  }
  return res.json()
}

export async function getMcpServers() {
  const res = await fetchWithTimeout(`${API_URL}/agent/mcp/servers`, { headers: headers() })
  if (!res.ok) throw new Error(`Failed to fetch MCP servers (${res.status})`)
  return res.json()
}

export async function updateMcpServer(name: string, data: {
  transport: 'http_json' | 'sse' | 'stdio'
  url?: string
  command?: string
  args?: string[]
  env?: Record<string, string>
}) {
  const res = await fetchWithTimeout(`${API_URL}/agent/mcp/servers/${encodeURIComponent(name)}`, {
    method: 'PUT',
    headers: headers(),
    body: JSON.stringify(data),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: `Failed to update MCP server (${res.status})` }))
    throw new Error(String(err.detail ?? `Failed to update MCP server (${res.status})`))
  }
  return res.json()
}

export async function deleteMcpServer(name: string) {
  const res = await fetchWithTimeout(`${API_URL}/agent/mcp/servers/${encodeURIComponent(name)}`, {
    method: 'DELETE',
    headers: headers(),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: `Failed to delete MCP server (${res.status})` }))
    throw new Error(String(err.detail ?? `Failed to delete MCP server (${res.status})`))
  }
  return res.json()
}

export async function testMcpServer(data: {
  transport: 'http_json' | 'sse' | 'stdio'
  url?: string
  command?: string
  args?: string[]
  env?: Record<string, string>
}) {
  const res = await fetchWithTimeout(`${API_URL}/agent/mcp/servers/test`, {
    method: 'POST',
    headers: headers(),
    body: JSON.stringify(data),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: `Failed to test MCP server (${res.status})` }))
    throw new Error(String(err.detail ?? `Failed to test MCP server (${res.status})`))
  }
  return res.json()
}

export async function getAgentModels() {
  const res = await fetchWithTimeout(`${API_URL}/agent/models`, { headers: headers() })
  if (!res.ok) throw new Error(`Failed to fetch models (${res.status})`)
  return res.json()
}

export async function getWorkflowSuggestions(minOccurrences = 3): Promise<{
  suggestions: Array<{
    task_type: string
    tools: string[]
    occurrences: number
    success_rate: number
    updated_at: string | null
    suggested_name: string
    suggested_query: string
  }>
}> {
  const res = await fetchWithTimeout(
    `${API_URL}/agent/workflow-suggestions?min_occurrences=${minOccurrences}`,
    { headers: headers() },
  )
  if (!res.ok) return { suggestions: [] }
  return res.json()
}

export async function getTaskSuggestions(taskId: string): Promise<{ suggestions: string[]; ready: boolean }> {
  const res = await fetchWithTimeout(`${API_URL}/agent/suggestions/${taskId}`, { headers: headers() }, 5000)
  if (!res.ok) return { suggestions: [], ready: false }
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

/** Returns raw Response with SSE body for streaming. */
export function streamAgent(
  query: string,
  context?: string,
  tools?: string[],
  conversationId?: string,
  /** When set, sent as `reasoning_effort` (e.g. `off`, `medium`). When omitted, server uses env default. */
  reasoningEffort?: string,
) {
  const body: Record<string, unknown> = {
    query,
    context: context ?? null,
    tools: tools ?? null,
    conversation_id: conversationId ?? null,
  }
  if (reasoningEffort !== undefined) {
    body.reasoning_effort = reasoningEffort
  }
  return fetch(`${API_URL}/agent/stream`, {
    method: 'POST',
    headers: headers(),
    body: JSON.stringify(body),
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

// ── Connectors ───────────────────────────────────────────────────────────────

export interface ConnectorStatus {
  id: string
  name: string
  description: string
  token_label: string
  token_help: string
  actions: string[]
  configured: boolean
  enabled: boolean
  token_preview: string
}

export async function listConnectors(): Promise<ConnectorStatus[]> {
  const res = await fetchWithTimeout(`${API_URL}/connectors`, { headers: headers() })
  if (!res.ok) throw new Error(`Failed to fetch connectors (${res.status})`)
  return res.json()
}

export async function saveConnector(id: string, data: { token?: string; enabled: boolean }): Promise<ConnectorStatus> {
  const res = await fetchWithTimeout(`${API_URL}/connectors/${id}`, {
    method: 'POST',
    headers: headers(),
    body: JSON.stringify(data),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: `Failed to save connector (${res.status})` }))
    throw new Error(String(err.detail ?? err))
  }
  return res.json()
}

export async function clearConnectorToken(id: string): Promise<ConnectorStatus> {
  const res = await fetchWithTimeout(`${API_URL}/connectors/${id}/token`, {
    method: 'DELETE',
    headers: headers(),
  })
  if (!res.ok) throw new Error(`Failed to clear token (${res.status})`)
  return res.json()
}

export async function testConnector(id: string): Promise<{ ok: boolean; detail: string }> {
  const res = await fetchWithTimeout(`${API_URL}/connectors/${id}/test`, { headers: headers() }, 12000)
  if (!res.ok) throw new Error(`Test request failed (${res.status})`)
  return res.json()
}

// ── Projects ──────────────────────────────────────────────────────────────────

export interface Project {
  id: string
  name: string
  description: string | null
  color: string
  task_count: number
  created_at: string
  updated_at: string
}

export async function listProjects(): Promise<{ projects: Project[] }> {
  const res = await fetchWithTimeout(`${API_URL}/projects`, { headers: headers() })
  if (!res.ok) throw new Error(`Failed to fetch projects (${res.status})`)
  return res.json()
}

export async function createProject(data: { name: string; description?: string; color?: string }): Promise<Project> {
  const res = await fetchWithTimeout(`${API_URL}/projects`, {
    method: 'POST', headers: headers(), body: JSON.stringify(data),
  })
  if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(String((e as Record<string,unknown>).detail ?? `Failed (${res.status})`)) }
  return res.json()
}

export async function updateProject(id: string, data: { name?: string; description?: string; color?: string }): Promise<Project> {
  const res = await fetchWithTimeout(`${API_URL}/projects/${id}`, {
    method: 'PATCH', headers: headers(), body: JSON.stringify(data),
  })
  if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(String((e as Record<string,unknown>).detail ?? `Failed (${res.status})`)) }
  return res.json()
}

export async function deleteProject(id: string): Promise<void> {
  const res = await fetchWithTimeout(`${API_URL}/projects/${id}`, { method: 'DELETE', headers: headers() })
  if (!res.ok) throw new Error(`Failed to delete project (${res.status})`)
}

export async function getProjectTasks(id: string, limit = 50, offset = 0) {
  const res = await fetchWithTimeout(`${API_URL}/projects/${id}/tasks?limit=${limit}&offset=${offset}`, { headers: headers() })
  if (!res.ok) throw new Error(`Failed to fetch project tasks (${res.status})`)
  return res.json()
}

export async function assignTaskToProject(projectId: string, taskId: string): Promise<void> {
  const res = await fetchWithTimeout(`${API_URL}/projects/${projectId}/tasks/${taskId}`, {
    method: 'POST', headers: headers(),
  })
  if (!res.ok) throw new Error(`Failed to assign task (${res.status})`)
}

export async function removeTaskFromProject(projectId: string, taskId: string): Promise<void> {
  const res = await fetchWithTimeout(`${API_URL}/projects/${projectId}/tasks/${taskId}`, {
    method: 'DELETE', headers: headers(),
  })
  if (!res.ok) throw new Error(`Failed to remove task (${res.status})`)
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
