'use client'

import { useState, useEffect, useCallback } from 'react'
import {
  getSettings,
  updateSettings,
  getPersonaPreview,
  getTools,
  getAgentToolsHealth,
  getMcpServers,
  addMcpServer,
  deleteMcpServer,
  getAnalyticsSkills,
  upsertAnalyticsSkill,
  deleteAnalyticsSkill,
  listConnectors,
  saveConnector,
  clearConnectorToken,
  testConnector,
  type ConnectorStatus,
} from '@/lib/api'

// ── Autostart (Tauri desktop only) ───────────────────────────────────────────

async function getAutostartEnabled(): Promise<boolean | null> {
  if (typeof window === 'undefined' || !('__TAURI__' in window)) return null
  try { const { isEnabled } = await import('@tauri-apps/plugin-autostart'); return isEnabled() }
  catch { return null }
}
async function setAutostart(enabled: boolean) {
  if (typeof window === 'undefined' || !('__TAURI__' in window)) return
  try { const { enable, disable } = await import('@tauri-apps/plugin-autostart'); if (enabled) await enable(); else await disable() }
  catch { /* not in Tauri */ }
}

// ── Types ─────────────────────────────────────────────────────────────────────

type Tab = 'general' | 'tools' | 'mcp' | 'skills' | 'connectors'

type SettingsData = {
  display_name: string | null
  preferred_model: string | null
  max_monthly_cost: number
  enable_notifications: boolean
  auto_save_results: boolean
  context_window_target_percent: number
  default_tools: string[] | null
  timezone: string
  agent_persona_enabled: boolean
  agent_persona_path: string
  agent_show_thinking_while_streaming: boolean
  metadata: Record<string, unknown>
}

type ToolItem = { name: string; description: string }
type McpServer = Record<string, unknown>
type SkillRow = Record<string, unknown>

// ── Shared primitives ─────────────────────────────────────────────────────────

function SectionCard({ children }: { children: React.ReactNode }) {
  return <div className="panel p-5 space-y-4">{children}</div>
}

function FieldLabel({ htmlFor, children }: { htmlFor?: string; children: React.ReactNode }) {
  return <label htmlFor={htmlFor} className="block text-xs uppercase tracking-widest text-muted mb-1">{children}</label>
}

function TextInput({ id, value, onChange, placeholder, type = 'text', className = '' }: {
  id?: string; value: string | number; onChange: (v: string) => void
  placeholder?: string; type?: string; className?: string
}) {
  return (
    <input
      id={id} type={type} value={value} placeholder={placeholder}
      onChange={e => onChange(e.target.value)}
      className={`w-full bg-[color:var(--bg-elev)] border border-[color:var(--border)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[color:var(--accent)] ${className}`}
    />
  )
}

function Toggle({ id, checked, onChange, label, description }: {
  id: string; checked: boolean; onChange: (v: boolean) => void; label: string; description?: string
}) {
  return (
    <div className="flex items-start gap-3">
      <input type="checkbox" id={id} checked={checked} onChange={e => onChange(e.target.checked)} className="w-4 h-4 accent-[color:var(--accent)] mt-0.5 shrink-0" />
      <div>
        <label htmlFor={id} className="text-sm cursor-pointer">{label}</label>
        {description && <p className="text-xs text-muted mt-0.5 leading-relaxed">{description}</p>}
      </div>
    </div>
  )
}

// ── Connector card ────────────────────────────────────────────────────────────

function ConnectorCard({ connector, onUpdate }: { connector: ConnectorStatus; onUpdate: (c: ConnectorStatus) => void }) {
  const [token, setToken] = useState('')
  const [showToken, setShowToken] = useState(false)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [clearing, setClearing] = useState(false)
  const [testResult, setTestResult] = useState<{ ok: boolean; detail: string } | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [expanded, setExpanded] = useState(!connector.configured)

  const flash = (msg: string) => { setNotice(msg); setTimeout(() => setNotice(null), 3500) }

  const handleSave = async () => {
    if (!token.trim() && !connector.configured) return
    setSaving(true)
    try { const u = await saveConnector(connector.id, { token: token.trim() || undefined, enabled: true }); onUpdate(u); setToken(''); setExpanded(false); flash('Saved and enabled.') }
    catch (e) { flash(e instanceof Error ? e.message : 'Save failed') }
    finally { setSaving(false) }
  }
  const handleToggle = async () => {
    setSaving(true)
    try { onUpdate(await saveConnector(connector.id, { enabled: !connector.enabled })) }
    catch (e) { flash(e instanceof Error ? e.message : 'Toggle failed') }
    finally { setSaving(false) }
  }
  const handleClear = async () => {
    setClearing(true); setTestResult(null)
    try { onUpdate(await clearConnectorToken(connector.id)); setExpanded(true); flash('Token removed.') }
    catch (e) { flash(e instanceof Error ? e.message : 'Clear failed') }
    finally { setClearing(false) }
  }
  const handleTest = async () => {
    setTesting(true); setTestResult(null)
    try { setTestResult(await testConnector(connector.id)) }
    catch (e) { setTestResult({ ok: false, detail: e instanceof Error ? e.message : 'Test failed' }) }
    finally { setTesting(false) }
  }

  return (
    <div className={`panel p-5 space-y-4 ${connector.enabled ? 'border-[color:var(--accent)]/30' : ''}`}>
      <div className="flex items-start gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="section-title dr-title-16">{connector.name}</h3>
            {connector.configured
              ? <span className={`text-[10px] uppercase tracking-widest px-2 py-0.5 rounded border font-semibold ${connector.enabled ? 'border-[color:var(--success)]/50 text-[color:var(--success)] bg-[color:var(--success)]/10' : 'border-[color:var(--border)] text-muted'}`}>{connector.enabled ? 'Enabled' : 'Disabled'}</span>
              : <span className="text-[10px] uppercase tracking-widest px-2 py-0.5 rounded border border-[color:var(--border)] text-muted">Not configured</span>
            }
          </div>
          <p className="text-sm text-muted mt-1">{connector.description}</p>
          {connector.configured && connector.token_preview && <p className="text-xs font-mono text-muted mt-1">{connector.token_label}: {connector.token_preview}</p>}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {connector.configured && (
            <button type="button" onClick={handleToggle} disabled={saving} className={`relative inline-flex h-6 w-11 items-center rounded-full border transition-colors disabled:opacity-50 ${connector.enabled ? 'bg-[color:var(--accent)] border-[color:var(--accent)]' : 'bg-[color:var(--surface-soft)] border-[color:var(--border)]'}`}>
              <span className={`inline-block h-4 w-4 rounded-full bg-white shadow transition-transform ${connector.enabled ? 'translate-x-6' : 'translate-x-1'}`} />
            </button>
          )}
          <button type="button" onClick={() => setExpanded(e => !e)} className="dr-btn-ghost px-2.5 py-1 text-xs rounded-lg">{expanded ? 'Collapse' : 'Configure'}</button>
        </div>
      </div>
      {connector.configured && !expanded && <div className="flex flex-wrap gap-1.5">{connector.actions.map(a => <span key={a} className="dr-chip dr-chip-tool">{a}</span>)}</div>}
      {expanded && (
        <div className="space-y-3 border-t border-[color:var(--border)] pt-4">
          <div className="space-y-1">
            <FieldLabel>{connector.token_label}</FieldLabel>
            <div className="relative">
              <input type={showToken ? 'text' : 'password'} value={token} onChange={e => setToken(e.target.value)} placeholder={connector.configured ? 'Enter new token to replace existing' : 'Paste token here'} className="w-full bg-[color:var(--bg-elev)] border border-[color:var(--border)] rounded-lg px-3 py-2 text-sm font-mono pr-16 focus:outline-none focus:border-[color:var(--accent)]" />
              <button type="button" onClick={() => setShowToken(s => !s)} className="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-muted px-1 hover:text-[color:var(--text)]">{showToken ? 'hide' : 'show'}</button>
            </div>
            <a href={connector.token_help} target="_blank" rel="noopener noreferrer" className="text-xs text-[color:var(--accent-2)] hover:underline">How to get a token ↗</a>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <button type="button" onClick={handleSave} disabled={saving || (!token.trim() && !connector.configured)} className="dr-btn-accent px-3 py-1.5 rounded-lg text-xs disabled:opacity-50">{saving ? 'Saving…' : connector.configured ? 'Update token' : 'Save & enable'}</button>
            <button type="button" onClick={handleTest} disabled={testing || !connector.configured} className="dr-btn-ghost px-3 py-1.5 rounded-lg text-xs disabled:opacity-50">{testing ? 'Testing…' : 'Test connection'}</button>
            {connector.configured && <button type="button" onClick={handleClear} disabled={clearing} className="dr-btn-ghost px-3 py-1.5 rounded-lg text-xs text-[color:var(--danger)] disabled:opacity-50 ml-auto">{clearing ? 'Removing…' : 'Remove token'}</button>}
          </div>
          {testResult && <p className={`text-xs px-3 py-2 rounded-lg border ${testResult.ok ? 'text-[color:var(--success)] border-[color:var(--success)]/30 bg-[color:var(--success)]/10' : 'text-[color:var(--danger)] border-[color:var(--danger)]/30 bg-[color:var(--danger)]/10'}`}>{testResult.ok ? '✓' : '✗'} {testResult.detail}</p>}
        </div>
      )}
      {notice && <p className="text-xs text-muted border-t border-[color:var(--border)] pt-3">{notice}</p>}
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

const TABS: { id: Tab; label: string }[] = [
  { id: 'general', label: 'General' },
  { id: 'tools', label: 'Tools' },
  { id: 'mcp', label: 'MCP Servers' },
  { id: 'skills', label: 'Skills' },
  { id: 'connectors', label: 'Connectors' },
]

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState<Tab>('general')

  useEffect(() => {
    const p = new URLSearchParams(window.location.search)
    const t = p.get('tab') as Tab | null
    if (t && TABS.some(tab => tab.id === t)) setActiveTab(t)
  }, [])

  // ── General ────────────────────────────────────────────────────────────────
  const [settings, setSettings] = useState<SettingsData | null>(null)
  const [loadingSettings, setLoadingSettings] = useState(true)
  const [savingSettings, setSavingSettings] = useState(false)
  const [savedSettings, setSavedSettings] = useState(false)
  const [settingsError, setSettingsError] = useState<string | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [autostart, setAutostartState] = useState<boolean | null>(null)
  const [personaPreview, setPersonaPreview] = useState('')
  const [previewLoading, setPreviewLoading] = useState(false)
  const [previewError, setPreviewError] = useState<string | null>(null)

  useEffect(() => { getAutostartEnabled().then(setAutostartState) }, [])
  useEffect(() => {
    getSettings()
      .then((d: Record<string, unknown>) => setSettings({
        display_name: (d.display_name as string | null) ?? null,
        preferred_model: (d.preferred_model as string | null) ?? null,
        max_monthly_cost: typeof d.max_monthly_cost === 'number' ? d.max_monthly_cost : 30,
        enable_notifications: d.enable_notifications !== false,
        auto_save_results: d.auto_save_results !== false,
        context_window_target_percent: typeof d.context_window_target_percent === 'number' ? d.context_window_target_percent : 0.75,
        default_tools: Array.isArray(d.default_tools) ? d.default_tools as string[] : null,
        timezone: typeof d.timezone === 'string' ? d.timezone : 'UTC',
        agent_persona_enabled: d.agent_persona_enabled !== false,
        agent_persona_path: typeof d.agent_persona_path === 'string' ? d.agent_persona_path : 'data/persona',
        agent_show_thinking_while_streaming: d.agent_show_thinking_while_streaming !== false,
        metadata: typeof d.metadata === 'object' && d.metadata ? d.metadata as Record<string, unknown> : {},
      }))
      .catch(e => setSettingsError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoadingSettings(false))
  }, [])

  const handleSaveSettings = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!settings) return
    setSavingSettings(true); setSaveError(null)
    try {
      const payload = { ...settings, display_name: settings.display_name?.trim() || null }
      await updateSettings(payload); setSettings(payload); setSavedSettings(true)
      setTimeout(() => setSavedSettings(false), 3000)
    } catch (err) { setSaveError(err instanceof Error ? err.message : 'Save failed') }
    finally { setSavingSettings(false) }
  }

  // ── Tools ──────────────────────────────────────────────────────────────────
  const [tools, setTools] = useState<ToolItem[]>([])
  const [enabledTools, setEnabledTools] = useState<Set<string>>(new Set())
  const [loadingTools, setLoadingTools] = useState(false)
  const [toolsBusy, setToolsBusy] = useState<string | null>(null)
  const [toolsNotice, setToolsNotice] = useState<string | null>(null)

  const loadTools = useCallback(async () => {
    setLoadingTools(true)
    try {
      const [td, sd] = await Promise.all([getTools(), getSettings()])
      const raw = (td as { tools?: unknown }).tools
      setTools(Array.isArray(raw) ? raw.map((t: unknown) =>
        typeof t === 'string' ? { name: t, description: '' } :
        (t && typeof t === 'object' && 'name' in t ? { name: String((t as { name: unknown }).name), description: typeof (t as Record<string, unknown>).description === 'string' ? String((t as Record<string, unknown>).description) : '' } : { name: '', description: '' })
      ) : [])
      const defaults = (sd as { default_tools?: unknown }).default_tools
      setEnabledTools(new Set(Array.isArray(defaults) ? defaults.filter((x): x is string => typeof x === 'string') : []))
    } catch { /* silently handled — user sees empty state */ }
    finally { setLoadingTools(false) }
  }, [])

  const toggleTool = async (name: string, enable: boolean) => {
    setToolsBusy(name); setToolsNotice(null)
    try {
      const next = new Set(enabledTools)
      if (enable) next.add(name); else next.delete(name)
      const current = await getSettings() as { default_tools?: string[] | null }
      await updateSettings({ ...current, default_tools: Array.from(next) })
      setEnabledTools(next)
      setToolsNotice(`Tool ${enable ? 'enabled' : 'disabled'}: ${name}`)
    } catch (e) { setToolsNotice(e instanceof Error ? e.message : 'Update failed') }
    finally { setToolsBusy(null) }
  }

  useEffect(() => { if (activeTab === 'tools' && tools.length === 0 && !loadingTools) loadTools() }, [activeTab, tools.length, loadingTools, loadTools])

  // ── MCP ────────────────────────────────────────────────────────────────────
  const [mcpServers, setMcpServers] = useState<McpServer[]>([])
  const [mcpHealth, setMcpHealth] = useState<{ healthyCount: number; total: number }>({ healthyCount: 0, total: 0 })
  const [loadingMcp, setLoadingMcp] = useState(false)
  const [mcpBusy, setMcpBusy] = useState<string | null>(null)
  const [mcpNotice, setMcpNotice] = useState<string | null>(null)
  const [mcpForm, setMcpForm] = useState({ name: '', transport: 'http_json', url: '', command: '', args: '' })

  const loadMcp = useCallback(async () => {
    setLoadingMcp(true)
    try {
      const [h, sv] = await Promise.all([getAgentToolsHealth(), getMcpServers()])
      const health = h as Record<string, unknown>
      const sdata = sv as Record<string, unknown>
      setMcpServers(Array.isArray(sdata.servers) ? sdata.servers as McpServer[] : [])
      setMcpHealth({ healthyCount: typeof health.healthy_count === 'number' ? health.healthy_count : 0, total: typeof health.total === 'number' ? health.total : 0 })
    } catch { /* silently handled */ }
    finally { setLoadingMcp(false) }
  }, [])

  const handleAddMcp = async () => {
    if (!mcpForm.name.trim()) { setMcpNotice('Server name is required'); return }
    setMcpBusy('add'); setMcpNotice(null)
    try {
      const transport = mcpForm.transport as 'http_json' | 'sse' | 'stdio'
      if (transport === 'stdio') await addMcpServer({ name: mcpForm.name.trim(), transport, command: mcpForm.command.trim(), args: mcpForm.args.split(',').map(s => s.trim()).filter(Boolean) })
      else await addMcpServer({ name: mcpForm.name.trim(), transport, url: mcpForm.url.trim() })
      setMcpForm({ name: '', transport: 'http_json', url: '', command: '', args: '' })
      setMcpNotice(`Added: ${mcpForm.name}`)
      await loadMcp()
    } catch (e) { setMcpNotice(e instanceof Error ? e.message : 'Add failed') }
    finally { setMcpBusy(null) }
  }

  const handleDeleteMcp = async (name: string) => {
    setMcpBusy(`del:${name}`); setMcpNotice(null)
    try { await deleteMcpServer(name); setMcpNotice(`Removed: ${name}`); await loadMcp() }
    catch (e) { setMcpNotice(e instanceof Error ? e.message : 'Delete failed') }
    finally { setMcpBusy(null) }
  }

  useEffect(() => { if (activeTab === 'mcp' && mcpServers.length === 0 && !loadingMcp) loadMcp() }, [activeTab, mcpServers.length, loadingMcp, loadMcp])

  // ── Skills ─────────────────────────────────────────────────────────────────
  const [skills, setSkills] = useState<SkillRow[]>([])
  const [growthAreas, setGrowthAreas] = useState<string[]>([])
  const [loadingSkills, setLoadingSkills] = useState(false)
  const [skillsBusy, setSkillsBusy] = useState<string | null>(null)
  const [skillsNotice, setSkillsNotice] = useState<string | null>(null)
  const [skillForm, setSkillForm] = useState({ task_type: '', skill_name: '', required_tools: '' })

  const loadSkills = useCallback(async () => {
    setLoadingSkills(true)
    try {
      const d = await getAnalyticsSkills() as { skills?: unknown; growth_areas?: unknown }
      setSkills(Array.isArray(d.skills) ? d.skills as SkillRow[] : [])
      setGrowthAreas(Array.isArray(d.growth_areas) ? d.growth_areas.map(String) : [])
    } catch { /* silently handled */ }
    finally { setLoadingSkills(false) }
  }, [])

  const handleAddSkill = async () => {
    if (!skillForm.task_type.trim() || !skillForm.skill_name.trim()) { setSkillsNotice('Task type and skill name are required'); return }
    setSkillsBusy('add'); setSkillsNotice(null)
    try {
      await upsertAnalyticsSkill({ task_type: skillForm.task_type.trim(), skill_name: skillForm.skill_name.trim(), required_tools: skillForm.required_tools.split(',').map(s => s.trim()).filter(Boolean) })
      setSkillForm({ task_type: '', skill_name: '', required_tools: '' })
      setSkillsNotice(`Saved: ${skillForm.task_type}`)
      await loadSkills()
    } catch (e) { setSkillsNotice(e instanceof Error ? e.message : 'Save failed') }
    finally { setSkillsBusy(null) }
  }

  const handleDeleteSkill = async (taskType: string) => {
    setSkillsBusy(`del:${taskType}`); setSkillsNotice(null)
    try { await deleteAnalyticsSkill(taskType); setSkillsNotice(`Deleted: ${taskType}`); await loadSkills() }
    catch (e) { setSkillsNotice(e instanceof Error ? e.message : 'Delete failed') }
    finally { setSkillsBusy(null) }
  }

  useEffect(() => { if (activeTab === 'skills' && skills.length === 0 && !loadingSkills) loadSkills() }, [activeTab, skills.length, loadingSkills, loadSkills])

  // ── Connectors ─────────────────────────────────────────────────────────────
  const [connectors, setConnectors] = useState<ConnectorStatus[]>([])
  const [loadingConnectors, setLoadingConnectors] = useState(false)
  const [connectorsError, setConnectorsError] = useState<string | null>(null)

  const loadConnectors = useCallback(async () => {
    setLoadingConnectors(true); setConnectorsError(null)
    try { setConnectors(await listConnectors()) }
    catch (e) { setConnectorsError(e instanceof Error ? e.message : 'Failed to load') }
    finally { setLoadingConnectors(false) }
  }, [])

  useEffect(() => { if (activeTab === 'connectors' && connectors.length === 0 && !loadingConnectors) loadConnectors() }, [activeTab, connectors.length, loadingConnectors, loadConnectors])

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className="dr-history-stack">
      <header>
        <p className="eyebrow">Conf</p>
        <h1 className="section-title dr-dashboard-hero-title">Settings</h1>
        <p className="dr-history-summary">Agent preferences, tools, integrations, and learned skills.</p>
      </header>

      {/* Tab bar */}
      <div className="flex gap-1 overflow-x-auto border-b border-[color:var(--border)] pb-0 scrollbar-none">
        {TABS.map(t => (
          <button key={t.id} type="button" onClick={() => setActiveTab(t.id)}
            className={`px-4 py-2 text-sm font-medium rounded-t-lg border border-b-0 whitespace-nowrap transition-colors ${activeTab === t.id ? 'border-[color:var(--border)] bg-[color:var(--surface)] text-[color:var(--text)]' : 'border-transparent text-muted hover:text-[color:var(--text)]'}`}
          >{t.label}</button>
        ))}
      </div>

      {/* ── General ─────────────────────────────────────────────────────────── */}
      {activeTab === 'general' && (
        <>
          {loadingSettings && <p className="text-muted text-sm">Loading…</p>}
          {!settings && settingsError && <p className="text-[color:var(--danger)] text-sm">{settingsError}</p>}
          {settings && (
            <form onSubmit={handleSaveSettings} className="space-y-5 panel p-6">
              <div>
                <FieldLabel htmlFor="display-name">Display name</FieldLabel>
                <TextInput id="display-name" value={settings.display_name ?? ''} onChange={v => setSettings({ ...settings, display_name: v || null })} placeholder="e.g. Jason" />
                <p className="text-xs text-muted mt-1">Shown in the dashboard greeting.</p>
              </div>
              <div>
                <FieldLabel htmlFor="budget">Monthly Budget (USD)</FieldLabel>
                <TextInput id="budget" type="number" value={settings.max_monthly_cost} onChange={v => setSettings({ ...settings, max_monthly_cost: parseFloat(v) })} />
              </div>
              <div>
                <FieldLabel htmlFor="model">Preferred Model</FieldLabel>
                <TextInput id="model" value={settings.preferred_model ?? ''} onChange={v => setSettings({ ...settings, preferred_model: v || null })} placeholder="e.g. deepseek/deepseek-chat" />
                <p className="text-xs text-muted mt-1">Leave blank for automatic routing.</p>
              </div>
              <div>
                <FieldLabel htmlFor="tz">Timezone</FieldLabel>
                <TextInput id="tz" value={settings.timezone} onChange={v => setSettings({ ...settings, timezone: v })} placeholder="America/New_York" />
                <p className="text-xs text-muted mt-1">IANA timezone name.</p>
              </div>

              <div className="pt-2 border-t border-[color:var(--border)] space-y-3">
                <p className="text-xs uppercase tracking-widest text-muted">Persona</p>
                <Toggle id="persona-enabled" checked={settings.agent_persona_enabled} onChange={v => setSettings({ ...settings, agent_persona_enabled: v })} label="Enable persona profile injection" />
                <div>
                  <FieldLabel htmlFor="persona-path">Persona Folder</FieldLabel>
                  <TextInput id="persona-path" value={settings.agent_persona_path} onChange={v => setSettings({ ...settings, agent_persona_path: v })} />
                  <p className="text-xs text-muted mt-1">Relative (e.g. data/persona) or absolute path.</p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <button type="button" onClick={async () => { setPreviewLoading(true); setPreviewError(null); try { setPersonaPreview((await getPersonaPreview()).preview || '') } catch (e) { setPreviewError(e instanceof Error ? e.message : 'Failed') } finally { setPreviewLoading(false) } }} disabled={previewLoading} className="btn-ghost px-3 py-1.5 rounded text-xs disabled:opacity-50">{previewLoading ? 'Loading…' : 'Preview resolved persona'}</button>
                  {previewError && <span className="text-[color:var(--danger)] text-xs">{previewError}</span>}
                </div>
                <textarea value={personaPreview} readOnly rows={5} className="w-full bg-[color:var(--bg-elev)] rounded-lg px-3 py-2 text-xs border border-[color:var(--border)] focus:outline-none" placeholder="Click preview to load the resolved persona prompt" />
              </div>

              <div className="pt-2 border-t border-[color:var(--border)] space-y-3">
                <p className="text-xs uppercase tracking-widest text-muted">Behaviour</p>
                <Toggle id="notifications" checked={settings.enable_notifications} onChange={v => setSettings({ ...settings, enable_notifications: v })} label="Enable notifications" />
                <Toggle id="autosave" checked={settings.auto_save_results} onChange={v => setSettings({ ...settings, auto_save_results: v })} label="Auto-save results" />
                <Toggle id="thinking-stream" checked={settings.agent_show_thinking_while_streaming} onChange={v => setSettings({ ...settings, agent_show_thinking_while_streaming: v })} label="Show planning stream in agent chat" description="When enabled, status and thinking before each reply appear in the transcript." />
              </div>

              {autostart !== null && (
                <div className="pt-2 border-t border-[color:var(--border)]">
                  <Toggle id="autostart" checked={autostart} onChange={async v => { setAutostartState(v); await setAutostart(v) }} label="Launch on login" description="Desktop only." />
                </div>
              )}

              <div className="flex items-center gap-3 pt-2">
                <button type="submit" disabled={savingSettings} className="btn-accent px-4 py-2 rounded-lg text-sm font-medium disabled:opacity-50">{savingSettings ? 'Saving…' : 'Save Settings'}</button>
                {savedSettings && <span className="text-[color:var(--success)] text-sm">Saved!</span>}
                {saveError && <span className="text-[color:var(--danger)] text-sm">{saveError}</span>}
              </div>
            </form>
          )}
        </>
      )}

      {/* ── Tools ───────────────────────────────────────────────────────────── */}
      {activeTab === 'tools' && (
        <div className="space-y-3">
          {loadingTools && <p className="text-muted text-sm">Loading tools…</p>}
          {!loadingTools && (
            <>
              <p className="text-sm text-muted">{tools.length} available · {enabledTools.size} enabled by default. Enabled tools are always offered to the agent; optional tools can still be requested per-run.</p>
              {toolsNotice && <p className="text-xs text-muted">{toolsNotice}</p>}
              {tools.map((tool, i) => (
                <SectionCard key={`${tool.name}-${i}`}>
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-sm font-medium">{tool.name || 'Unnamed tool'}</p>
                      {tool.description && <p className="text-xs text-muted mt-1 leading-relaxed">{tool.description}</p>}
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <span className={`text-[10px] uppercase tracking-widest px-2 py-1 rounded border ${enabledTools.has(tool.name) ? 'border-[color:var(--success)] text-[color:var(--success)]' : 'border-[color:var(--border)] text-muted'}`}>
                        {enabledTools.has(tool.name) ? 'enabled' : 'optional'}
                      </span>
                      <button type="button" disabled={!tool.name || toolsBusy === tool.name} onClick={() => void toggleTool(tool.name, !enabledTools.has(tool.name))} className="dr-btn-ghost px-2 py-1 rounded text-xs disabled:opacity-50">
                        {enabledTools.has(tool.name) ? 'Disable' : 'Enable'}
                      </button>
                    </div>
                  </div>
                </SectionCard>
              ))}
            </>
          )}
        </div>
      )}

      {/* ── MCP Servers ─────────────────────────────────────────────────────── */}
      {activeTab === 'mcp' && (
        <div className="space-y-4">
          {/* Stats */}
          <div className="grid grid-cols-3 gap-3">
            {[['Healthy', mcpHealth.healthyCount], ['Total', mcpHealth.total || mcpServers.length], ['Configured', mcpServers.length]].map(([label, val]) => (
              <SectionCard key={String(label)}>
                <p className="text-xs uppercase tracking-widest text-muted">{label}</p>
                <p className="text-2xl font-semibold mt-1">{val}</p>
              </SectionCard>
            ))}
          </div>

          {/* Add form */}
          <SectionCard>
            <p className="text-xs uppercase tracking-widest text-muted">Add MCP Server</p>
            <div className="grid sm:grid-cols-2 gap-2">
              <TextInput value={mcpForm.name} onChange={v => setMcpForm(p => ({ ...p, name: v }))} placeholder="Server name" />
              <select value={mcpForm.transport} onChange={e => setMcpForm(p => ({ ...p, transport: e.target.value }))} className="bg-[color:var(--bg-elev)] border border-[color:var(--border)] rounded-lg px-3 py-2 text-sm">
                <option value="http_json">http_json</option>
                <option value="sse">sse</option>
                <option value="stdio">stdio</option>
              </select>
            </div>
            {mcpForm.transport === 'stdio' ? (
              <div className="grid sm:grid-cols-2 gap-2">
                <TextInput value={mcpForm.command} onChange={v => setMcpForm(p => ({ ...p, command: v }))} placeholder="command (e.g. npx)" />
                <TextInput value={mcpForm.args} onChange={v => setMcpForm(p => ({ ...p, args: v }))} placeholder="args, comma-separated" />
              </div>
            ) : (
              <TextInput value={mcpForm.url} onChange={v => setMcpForm(p => ({ ...p, url: v }))} placeholder="Server URL" />
            )}
            <button type="button" onClick={handleAddMcp} disabled={mcpBusy === 'add'} className="dr-btn-accent px-3 py-1.5 rounded text-xs disabled:opacity-50">{mcpBusy === 'add' ? 'Adding…' : 'Add Server'}</button>
            {mcpNotice && <p className="text-xs text-muted">{mcpNotice}</p>}
          </SectionCard>

          {/* Server list */}
          {loadingMcp && <p className="text-muted text-sm">Loading…</p>}
          {!loadingMcp && mcpServers.length === 0 && <p className="text-sm text-muted">No MCP servers configured.</p>}
          {mcpServers.map((sv, i) => {
            const name = String(sv.name ?? `server-${i + 1}`)
            const status = String(sv.status ?? 'unknown')
            return (
              <SectionCard key={name}>
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm font-medium">{name}</p>
                    <p className="text-xs text-muted mt-0.5">{String(sv.transport ?? '—')} {sv.url ? `· ${sv.url}` : ''}</p>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <span className={`text-[10px] uppercase tracking-widest ${status === 'healthy' ? 'text-[color:var(--success)]' : 'text-muted'}`}>{status}</span>
                    <button type="button" onClick={() => void handleDeleteMcp(name)} disabled={mcpBusy === `del:${name}`} className="dr-btn-ghost px-2 py-1 rounded text-xs text-[color:var(--danger)] disabled:opacity-50">Remove</button>
                  </div>
                </div>
              </SectionCard>
            )
          })}
        </div>
      )}

      {/* ── Skills ──────────────────────────────────────────────────────────── */}
      {activeTab === 'skills' && (
        <div className="space-y-4">
          {/* Stats */}
          <div className="grid grid-cols-2 gap-3">
            {[['Tracked skills', skills.length], ['Growth areas', growthAreas.length]].map(([label, val]) => (
              <SectionCard key={String(label)}>
                <p className="text-xs uppercase tracking-widest text-muted">{label}</p>
                <p className="text-2xl font-semibold mt-1">{val}</p>
              </SectionCard>
            ))}
          </div>

          {/* Add form */}
          <SectionCard>
            <p className="text-xs uppercase tracking-widest text-muted">Add or Update Skill</p>
            <div className="grid sm:grid-cols-2 gap-2">
              <TextInput value={skillForm.task_type} onChange={v => setSkillForm(p => ({ ...p, task_type: v }))} placeholder="Task type (e.g. coding)" />
              <TextInput value={skillForm.skill_name} onChange={v => setSkillForm(p => ({ ...p, skill_name: v }))} placeholder="Skill name" />
            </div>
            <TextInput value={skillForm.required_tools} onChange={v => setSkillForm(p => ({ ...p, required_tools: v }))} placeholder="Required tools (comma-separated, optional)" />
            <button type="button" onClick={handleAddSkill} disabled={skillsBusy === 'add'} className="dr-btn-accent px-3 py-1.5 rounded text-xs disabled:opacity-50">{skillsBusy === 'add' ? 'Saving…' : 'Save Skill'}</button>
            {skillsNotice && <p className="text-xs text-muted">{skillsNotice}</p>}
          </SectionCard>

          {/* Skills table */}
          {loadingSkills && <p className="text-muted text-sm">Loading…</p>}
          {!loadingSkills && skills.length === 0 && <p className="text-sm text-muted">No skills tracked yet. Skills are learned automatically or added above.</p>}
          {skills.length > 0 && (
            <div className="panel panel-soft rounded-lg overflow-hidden">
              <div className="grid grid-cols-[1.5fr_0.7fr_0.7fr_auto] gap-3 px-4 py-2 text-[10px] uppercase tracking-widest text-muted border-b border-[color:var(--border)]">
                <span>Skill</span><span className="text-right">Success</span><span className="text-right">Uses</span><span />
              </div>
              {skills.map((skill, i) => {
                const name = String(skill.skill ?? skill.name ?? `Skill ${i + 1}`)
                const taskType = String(skill.task_type ?? skill.taskType ?? name)
                const success = skill.success_rate ?? skill.success ?? skill.win_rate
                const uses = skill.count ?? skill.uses ?? skill.total ?? '—'
                return (
                  <div key={taskType} className="grid grid-cols-[1.5fr_0.7fr_0.7fr_auto] gap-3 px-4 py-2.5 text-sm border-b last:border-b-0 border-[color:var(--border)]/50 items-center">
                    <span className="truncate font-medium" title={name}>{name}</span>
                    <span className="text-right text-muted">{success == null ? '—' : String(success)}</span>
                    <span className="text-right text-muted">{String(uses)}</span>
                    <button type="button" onClick={() => void handleDeleteSkill(taskType)} disabled={skillsBusy === `del:${taskType}`} className="dr-btn-ghost px-2 py-0.5 rounded text-[10px] text-[color:var(--danger)] disabled:opacity-50">Delete</button>
                  </div>
                )
              })}
            </div>
          )}

          {growthAreas.length > 0 && (
            <SectionCard>
              <p className="text-xs uppercase tracking-widest text-muted">Top Growth Areas</p>
              <div className="flex flex-wrap gap-2 mt-1">
                {growthAreas.map(a => <span key={a} className="dr-chip">{a}</span>)}
              </div>
            </SectionCard>
          )}
        </div>
      )}

      {/* ── Connectors ──────────────────────────────────────────────────────── */}
      {activeTab === 'connectors' && (
        <div className="space-y-4">
          <p className="text-sm text-muted">Connect external services. Tokens are stored locally and only sent to the service&apos;s own API.</p>
          {loadingConnectors && <p className="text-muted text-sm">Loading…</p>}
          {connectorsError && <p className="text-[color:var(--danger)] text-sm">{connectorsError}</p>}
          {!loadingConnectors && !connectorsError && connectors.map(c => (
            <ConnectorCard key={c.id} connector={c} onUpdate={u => setConnectors(prev => prev.map(x => x.id === u.id ? u : x))} />
          ))}
        </div>
      )}
    </div>
  )
}
