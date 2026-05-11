'use client'

import { useState, useEffect, useCallback } from 'react'
import {
  getSettings,
  updateSettings,
  getPersonaPreview,
  listConnectors,
  saveConnector,
  clearConnectorToken,
  testConnector,
  type ConnectorStatus,
} from '@/lib/api'

// ── Autostart (Tauri desktop only) ───────────────────────────────────────────

async function getAutostartEnabled(): Promise<boolean | null> {
  if (typeof window === 'undefined' || !('__TAURI__' in window)) return null
  try {
    const { isEnabled } = await import('@tauri-apps/plugin-autostart')
    return isEnabled()
  } catch { return null }
}

async function setAutostart(enabled: boolean) {
  if (typeof window === 'undefined' || !('__TAURI__' in window)) return
  try {
    const { enable, disable } = await import('@tauri-apps/plugin-autostart')
    if (enabled) await enable()
    else await disable()
  } catch { /* not in Tauri */ }
}

// ── Types ─────────────────────────────────────────────────────────────────────

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
    try {
      const updated = await saveConnector(connector.id, { token: token.trim() || undefined, enabled: true })
      onUpdate(updated)
      setToken('')
      setExpanded(false)
      flash('Saved and enabled.')
    } catch (e) { flash(e instanceof Error ? e.message : 'Save failed') }
    finally { setSaving(false) }
  }

  const handleToggle = async () => {
    setSaving(true)
    try {
      const updated = await saveConnector(connector.id, { enabled: !connector.enabled })
      onUpdate(updated)
    } catch (e) { flash(e instanceof Error ? e.message : 'Toggle failed') }
    finally { setSaving(false) }
  }

  const handleClear = async () => {
    setClearing(true)
    setTestResult(null)
    try {
      const updated = await clearConnectorToken(connector.id)
      onUpdate(updated)
      setExpanded(true)
      flash('Token removed.')
    } catch (e) { flash(e instanceof Error ? e.message : 'Clear failed') }
    finally { setClearing(false) }
  }

  const handleTest = async () => {
    setTesting(true)
    setTestResult(null)
    try { setTestResult(await testConnector(connector.id)) }
    catch (e) { setTestResult({ ok: false, detail: e instanceof Error ? e.message : 'Test failed' }) }
    finally { setTesting(false) }
  }

  return (
    <div className={`panel p-5 space-y-4 transition-all ${connector.enabled ? 'border-[color:var(--accent)]/30' : ''}`}>
      <div className="flex items-start gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="section-title dr-title-16">{connector.name}</h3>
            {connector.configured ? (
              <span className={`text-[10px] uppercase tracking-widest px-2 py-0.5 rounded border font-semibold ${connector.enabled ? 'border-[color:var(--success)]/50 text-[color:var(--success)] bg-[color:var(--success)]/10' : 'border-[color:var(--border)] text-muted'}`}>
                {connector.enabled ? 'Enabled' : 'Disabled'}
              </span>
            ) : (
              <span className="text-[10px] uppercase tracking-widest px-2 py-0.5 rounded border border-[color:var(--border)] text-muted">Not configured</span>
            )}
          </div>
          <p className="text-sm text-muted mt-1">{connector.description}</p>
          {connector.configured && connector.token_preview && (
            <p className="text-xs font-mono text-muted mt-1">{connector.token_label}: {connector.token_preview}</p>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {connector.configured && (
            <button
              type="button"
              onClick={handleToggle}
              disabled={saving}
              title={connector.enabled ? 'Disable connector' : 'Enable connector'}
              className={`relative inline-flex h-6 w-11 items-center rounded-full border transition-colors disabled:opacity-50 ${connector.enabled ? 'bg-[color:var(--accent)] border-[color:var(--accent)]' : 'bg-[color:var(--surface-soft)] border-[color:var(--border)]'}`}
            >
              <span className={`inline-block h-4 w-4 rounded-full bg-white shadow transition-transform ${connector.enabled ? 'translate-x-6' : 'translate-x-1'}`} />
            </button>
          )}
          <button type="button" onClick={() => setExpanded(e => !e)} className="dr-btn-ghost px-2.5 py-1 text-xs rounded-lg">
            {expanded ? 'Collapse' : 'Configure'}
          </button>
        </div>
      </div>

      {connector.configured && !expanded && (
        <div className="flex flex-wrap gap-1.5">
          {connector.actions.map(a => <span key={a} className="dr-chip dr-chip-tool">{a}</span>)}
        </div>
      )}

      {expanded && (
        <div className="space-y-3 border-t border-[color:var(--border)] pt-4">
          <div className="space-y-1">
            <label className="text-xs text-muted uppercase tracking-widest">{connector.token_label}</label>
            <div className="relative">
              <input
                type={showToken ? 'text' : 'password'}
                value={token}
                onChange={e => setToken(e.target.value)}
                placeholder={connector.configured ? 'Enter new token to replace existing' : 'Paste token here'}
                className="w-full bg-[color:var(--bg-elev)] border border-[color:var(--border)] rounded-lg px-3 py-2 text-sm font-mono pr-16 focus:outline-none focus:border-[color:var(--accent)]"
              />
              <button type="button" onClick={() => setShowToken(s => !s)} className="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-muted px-1 py-0.5 hover:text-[color:var(--text)]">
                {showToken ? 'hide' : 'show'}
              </button>
            </div>
            <a href={connector.token_help} target="_blank" rel="noopener noreferrer" className="text-xs text-[color:var(--accent-2)] hover:underline">
              How to get a token ↗
            </a>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <button type="button" onClick={handleSave} disabled={saving || (!token.trim() && !connector.configured)} className="dr-btn-accent px-3 py-1.5 rounded-lg text-xs disabled:opacity-50">
              {saving ? 'Saving…' : connector.configured ? 'Update token' : 'Save & enable'}
            </button>
            <button type="button" onClick={handleTest} disabled={testing || !connector.configured} className="dr-btn-ghost px-3 py-1.5 rounded-lg text-xs disabled:opacity-50">
              {testing ? 'Testing…' : 'Test connection'}
            </button>
            {connector.configured && (
              <button type="button" onClick={handleClear} disabled={clearing} className="dr-btn-ghost px-3 py-1.5 rounded-lg text-xs text-[color:var(--danger)] disabled:opacity-50 ml-auto">
                {clearing ? 'Removing…' : 'Remove token'}
              </button>
            )}
          </div>
          {testResult && (
            <p className={`text-xs px-3 py-2 rounded-lg border ${testResult.ok ? 'text-[color:var(--success)] border-[color:var(--success)]/30 bg-[color:var(--success)]/10' : 'text-[color:var(--danger)] border-[color:var(--danger)]/30 bg-[color:var(--danger)]/10'}`}>
              {testResult.ok ? '✓' : '✗'} {testResult.detail}
            </p>
          )}
        </div>
      )}
      {notice && <p className="text-xs text-muted border-t border-[color:var(--border)] pt-3">{notice}</p>}
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

type Tab = 'general' | 'connectors'

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState<Tab>('general')

  // Read ?tab= from URL on mount for deep linking (e.g. from action menu)
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    if (params.get('tab') === 'connectors') setActiveTab('connectors')
  }, [])

  // ── General tab state ──────────────────────────────────────────────────────
  const [settings, setSettings] = useState<SettingsData | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [autostart, setAutostartState] = useState<boolean | null>(null)
  const [personaPreview, setPersonaPreview] = useState('')
  const [previewLoading, setPreviewLoading] = useState(false)
  const [previewError, setPreviewError] = useState<string | null>(null)

  // ── Connectors tab state ───────────────────────────────────────────────────
  const [connectors, setConnectors] = useState<ConnectorStatus[]>([])
  const [connectorsLoading, setConnectorsLoading] = useState(false)
  const [connectorsError, setConnectorsError] = useState<string | null>(null)

  const loadConnectors = useCallback(async () => {
    setConnectorsLoading(true)
    setConnectorsError(null)
    try { setConnectors(await listConnectors()) }
    catch (e) { setConnectorsError(e instanceof Error ? e.message : 'Failed to load') }
    finally { setConnectorsLoading(false) }
  }, [])

  useEffect(() => { getAutostartEnabled().then(setAutostartState) }, [])

  useEffect(() => {
    getSettings()
      .then((data: Record<string, unknown>) => {
        setSettings({
          display_name: (data.display_name as string | null) ?? null,
          preferred_model: (data.preferred_model as string | null) ?? null,
          max_monthly_cost: typeof data.max_monthly_cost === 'number' ? data.max_monthly_cost : 30,
          enable_notifications: data.enable_notifications !== false,
          auto_save_results: data.auto_save_results !== false,
          context_window_target_percent: typeof data.context_window_target_percent === 'number' ? data.context_window_target_percent : 0.75,
          default_tools: Array.isArray(data.default_tools) ? (data.default_tools as string[]) : null,
          timezone: typeof data.timezone === 'string' ? data.timezone : 'UTC',
          agent_persona_enabled: data.agent_persona_enabled !== false,
          agent_persona_path: typeof data.agent_persona_path === 'string' ? data.agent_persona_path : 'data/persona',
          agent_show_thinking_while_streaming: data.agent_show_thinking_while_streaming !== false,
          metadata: (data.metadata as Record<string, unknown>) && typeof data.metadata === 'object' ? (data.metadata as Record<string, unknown>) : {},
        })
      })
      .catch(err => setLoadError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (activeTab === 'connectors' && connectors.length === 0 && !connectorsLoading) loadConnectors()
  }, [activeTab, connectors.length, connectorsLoading, loadConnectors])

  async function refreshPersonaPreview() {
    setPreviewLoading(true)
    setPreviewError(null)
    try { setPersonaPreview((await getPersonaPreview()).preview || '') }
    catch (err) { setPreviewError(err instanceof Error ? err.message : 'Preview failed') }
    finally { setPreviewLoading(false) }
  }

  async function handleSave(e: React.FormEvent) {
    e.preventDefault()
    if (!settings) return
    setSaving(true)
    setSaveError(null)
    try {
      const payload = { ...settings, display_name: settings.display_name?.trim() || null }
      await updateSettings(payload)
      setSettings(payload)
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch (err) { setSaveError(err instanceof Error ? err.message : 'Save failed') }
    finally { setSaving(false) }
  }

  const tabs: { id: Tab; label: string }[] = [
    { id: 'general', label: 'General' },
    { id: 'connectors', label: 'Connectors' },
  ]

  return (
    <div className="dr-history-stack">
      <header>
        <p className="eyebrow">Conf</p>
        <h1 className="section-title dr-dashboard-hero-title">Settings</h1>
        <p className="dr-history-summary">Agent preferences, persona, and third-party integrations.</p>
      </header>

      {/* Tab bar */}
      <div className="flex gap-1 border-b border-[color:var(--border)] pb-0">
        {tabs.map(t => (
          <button
            key={t.id}
            type="button"
            onClick={() => setActiveTab(t.id)}
            className={`px-4 py-2 text-sm font-medium rounded-t-lg border border-b-0 transition-colors ${
              activeTab === t.id
                ? 'border-[color:var(--border)] bg-[color:var(--surface)] text-[color:var(--text)]'
                : 'border-transparent text-muted hover:text-[color:var(--text)]'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* ── General tab ───────────────────────────────────────────────────── */}
      {activeTab === 'general' && (
        <>
          {loading && <p className="text-muted text-sm">Loading settings…</p>}
          {!settings && loadError && <p className="text-[color:var(--danger)] text-sm">{loadError}</p>}
          {settings && (
            <form onSubmit={handleSave} className="space-y-5 panel p-6">
              <div>
                <label htmlFor="display-name" className="block text-sm text-muted mb-1">Display name</label>
                <input id="display-name" type="text" placeholder="e.g. Jason" value={settings.display_name ?? ''} onChange={e => setSettings({ ...settings, display_name: e.target.value || null })} className="w-full bg-[color:var(--bg-elev)] rounded-lg px-3 py-2 text-sm border border-[color:var(--border)] focus:outline-none focus:border-[color:var(--accent)]" />
                <p className="text-xs text-muted mt-1">Shown on the dashboard greeting. Leave blank for generic greeting.</p>
              </div>

              <div>
                <label htmlFor="max-monthly-cost" className="block text-sm text-muted mb-1">Monthly Budget (USD)</label>
                <input id="max-monthly-cost" type="number" step="0.01" min="0" value={settings.max_monthly_cost} onChange={e => setSettings({ ...settings, max_monthly_cost: parseFloat(e.target.value) })} className="w-full bg-[color:var(--bg-elev)] rounded-lg px-3 py-2 text-sm border border-[color:var(--border)] focus:outline-none focus:border-[color:var(--accent)]" />
              </div>

              <div>
                <label htmlFor="preferred-model" className="block text-sm text-muted mb-1">Preferred Model</label>
                <input id="preferred-model" type="text" placeholder="e.g. deepseek/deepseek-chat" value={settings.preferred_model ?? ''} onChange={e => setSettings({ ...settings, preferred_model: e.target.value || null })} className="w-full bg-[color:var(--bg-elev)] rounded-lg px-3 py-2 text-sm border border-[color:var(--border)] focus:outline-none focus:border-[color:var(--accent)]" />
                <p className="text-xs text-muted mt-1">Leave blank to use automatic model routing.</p>
              </div>

              <div>
                <label htmlFor="timezone" className="block text-sm text-muted mb-1">Timezone</label>
                <input id="timezone" type="text" value={settings.timezone} onChange={e => setSettings({ ...settings, timezone: e.target.value })} className="w-full bg-[color:var(--bg-elev)] rounded-lg px-3 py-2 text-sm border border-[color:var(--border)] focus:outline-none focus:border-[color:var(--accent)]" />
                <p className="text-xs text-muted mt-1">IANA name (e.g. America/New_York).</p>
              </div>

              <div className="pt-2 border-t border-[color:var(--border)] space-y-3">
                <div className="flex items-center gap-3">
                  <input type="checkbox" id="persona-enabled" checked={settings.agent_persona_enabled} onChange={e => setSettings({ ...settings, agent_persona_enabled: e.target.checked })} className="w-4 h-4 accent-[color:var(--accent)]" />
                  <label htmlFor="persona-enabled" className="text-sm">Enable persona profile injection</label>
                </div>
                <div>
                  <label htmlFor="persona-path" className="block text-sm text-muted mb-1">Persona Folder</label>
                  <input id="persona-path" type="text" value={settings.agent_persona_path} onChange={e => setSettings({ ...settings, agent_persona_path: e.target.value })} className="w-full bg-[color:var(--bg-elev)] rounded-lg px-3 py-2 text-sm border border-[color:var(--border)] focus:outline-none focus:border-[color:var(--accent)]" />
                  <p className="text-xs text-muted mt-1">Relative (e.g. data/persona) or absolute path.</p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <button type="button" onClick={refreshPersonaPreview} disabled={previewLoading} className="btn-ghost px-3 py-1.5 rounded text-xs font-medium disabled:opacity-50">
                    {previewLoading ? 'Loading…' : 'Preview resolved persona'}
                  </button>
                  {previewError && <span className="text-[color:var(--danger)] text-xs">{previewError}</span>}
                </div>
                <textarea id="persona-preview" value={personaPreview} readOnly rows={6} className="w-full bg-[color:var(--bg-elev)] rounded-lg px-3 py-2 text-xs border border-[color:var(--border)] focus:outline-none" placeholder="Click preview to load the resolved persona prompt" />
              </div>

              <div className="pt-2 border-t border-[color:var(--border)] space-y-3">
                <div className="flex items-center gap-3">
                  <input type="checkbox" id="notifications" checked={settings.enable_notifications} onChange={e => setSettings({ ...settings, enable_notifications: e.target.checked })} className="w-4 h-4 accent-[color:var(--accent)]" />
                  <label htmlFor="notifications" className="text-sm">Enable notifications</label>
                </div>
                <div className="flex items-center gap-3">
                  <input type="checkbox" id="autosave" checked={settings.auto_save_results} onChange={e => setSettings({ ...settings, auto_save_results: e.target.checked })} className="w-4 h-4 accent-[color:var(--accent)]" />
                  <label htmlFor="autosave" className="text-sm">Auto-save results</label>
                </div>
                <div className="flex items-start gap-3">
                  <input type="checkbox" id="agent-show-thinking-stream" checked={settings.agent_show_thinking_while_streaming} onChange={e => setSettings({ ...settings, agent_show_thinking_while_streaming: e.target.checked })} className="w-4 h-4 accent-[color:var(--accent)] mt-0.5 shrink-0" />
                  <div>
                    <label htmlFor="agent-show-thinking-stream" className="text-sm cursor-pointer">Show planning stream in agent chat</label>
                    <p className="text-xs text-muted mt-1 leading-relaxed">When enabled, status and thinking before each reply appear in the transcript.</p>
                  </div>
                </div>
              </div>

              {autostart !== null && (
                <div className="flex items-center gap-3 pt-2 border-t border-[color:var(--border)]">
                  <input type="checkbox" id="autostart" checked={autostart} onChange={async e => { setAutostartState(e.target.checked); await setAutostart(e.target.checked) }} className="w-4 h-4 accent-[color:var(--accent)]" />
                  <label htmlFor="autostart" className="text-sm">Launch on login <span className="text-xs text-muted">(desktop only)</span></label>
                </div>
              )}

              <div className="flex items-center gap-3 pt-2">
                <button type="submit" disabled={saving} className="btn-accent px-4 py-2 rounded-lg text-sm font-medium disabled:opacity-50">
                  {saving ? 'Saving…' : 'Save Settings'}
                </button>
                {saved && <span className="text-[color:var(--success)] text-sm">Saved!</span>}
                {saveError && <span className="text-[color:var(--danger)] text-sm">{saveError}</span>}
              </div>
            </form>
          )}
        </>
      )}

      {/* ── Connectors tab ────────────────────────────────────────────────── */}
      {activeTab === 'connectors' && (
        <div className="space-y-4">
          <p className="text-sm text-muted">
            Connect external services so the agent can read and write on your behalf.
            Tokens are stored locally and never sent anywhere except the service&apos;s own API.
          </p>
          {connectorsLoading && <p className="text-muted text-sm">Loading connectors…</p>}
          {connectorsError && <p className="text-[color:var(--danger)] text-sm">{connectorsError}</p>}
          {!connectorsLoading && !connectorsError && connectors.map(c => (
            <ConnectorCard key={c.id} connector={c} onUpdate={updated => setConnectors(prev => prev.map(x => x.id === updated.id ? updated : x))} />
          ))}
        </div>
      )}
    </div>
  )
}
