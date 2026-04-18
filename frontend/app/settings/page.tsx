'use client'

import { useState, useEffect } from 'react'
import PageHeader from '@/components/PageHeader'
import { getSettings, updateSettings, getPersonaPreview } from '@/lib/api'

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

type SettingsData = {
  display_name: string | null
  preferred_model: string | null
  max_monthly_cost: number
  enable_notifications: boolean
  auto_save_results: boolean
  timezone: string
  agent_persona_enabled: boolean
  agent_persona_path: string
}

export default function SettingsPage() {
  const [settings, setSettings] = useState<SettingsData | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [previewError, setPreviewError] = useState<string | null>(null)
  const [autostart, setAutostartState] = useState<boolean | null>(null)
  const [personaPreview, setPersonaPreview] = useState('')
  const [previewLoading, setPreviewLoading] = useState(false)

  useEffect(() => {
    getAutostartEnabled().then(setAutostartState)
  }, [])

  useEffect(() => {
    getSettings()
      .then(setSettings)
      .catch(err => setLoadError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false))
  }, [])

  async function refreshPersonaPreview() {
    setPreviewLoading(true)
    setPreviewError(null)
    try {
      const payload = await getPersonaPreview()
      setPersonaPreview(payload.preview || '')
    } catch (err) {
      setPreviewError(err instanceof Error ? err.message : 'Preview failed')
    } finally {
      setPreviewLoading(false)
    }
  }

  async function handleSave(e: React.FormEvent) {
    e.preventDefault()
    if (!settings) return
    setSaving(true)
    setSaveError(null)
    try {
      const payload = {
        ...settings,
        display_name: settings.display_name?.trim() || null,
      }
      await updateSettings(payload)
      setSettings(payload)
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <p className="text-muted">Loading settings…</p>
  if (!settings && loadError) return <p className="text-[color:var(--danger)]">Error: {loadError}</p>
  if (!settings) return null

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Control deck"
        title="Settings"
        description="Tune budgets, routing preferences, and persona behavior for your agent."
      />

      <form onSubmit={handleSave} className="max-w-2xl space-y-5 panel p-6">

        <div>
          <label htmlFor="max-monthly-cost" className="block text-sm text-muted mb-1">Monthly Budget (USD)</label>
          <input
            id="max-monthly-cost"
            type="number"
            step="0.01"
            min="0"
            value={settings.max_monthly_cost}
            onChange={e => setSettings({ ...settings, max_monthly_cost: parseFloat(e.target.value) })}
            className="w-full bg-[color:var(--bg-elev)] rounded-lg px-3 py-2 text-sm border border-[color:var(--border)] focus:outline-none focus:border-[color:var(--accent)]"
          />
        </div>

        <div>
          <label htmlFor="preferred-model" className="block text-sm text-muted mb-1">Preferred Model</label>
          <input
            id="preferred-model"
            type="text"
            placeholder="e.g. deepseek/deepseek-chat"
            value={settings.preferred_model ?? ''}
            onChange={e => setSettings({ ...settings, preferred_model: e.target.value || null })}
            className="w-full bg-[color:var(--bg-elev)] rounded-lg px-3 py-2 text-sm border border-[color:var(--border)] focus:outline-none focus:border-[color:var(--accent)]"
          />
          <p className="text-xs text-muted mt-1">Leave blank to use automatic model routing.</p>
        </div>

        <div>
          <label htmlFor="timezone" className="block text-sm text-muted mb-1">Timezone</label>
          <input
            id="timezone"
            type="text"
            value={settings.timezone}
            onChange={e => setSettings({ ...settings, timezone: e.target.value })}
            className="w-full bg-[color:var(--bg-elev)] rounded-lg px-3 py-2 text-sm border border-[color:var(--border)] focus:outline-none focus:border-[color:var(--accent)]"
          />
          <p className="text-xs text-muted mt-1">IANA name (e.g. America/New_York). Used with the hour of day for your dashboard greeting.</p>
        </div>

        <div>
          <label htmlFor="display-name" className="block text-sm text-muted mb-1">Display name</label>
          <input
            id="display-name"
            type="text"
            placeholder="e.g. Jason"
            value={settings.display_name ?? ''}
            onChange={e => setSettings({ ...settings, display_name: e.target.value || null })}
            className="w-full bg-[color:var(--bg-elev)] rounded-lg px-3 py-2 text-sm border border-[color:var(--border)] focus:outline-none focus:border-[color:var(--accent)]"
          />
          <p className="text-xs text-muted mt-1">Shown on the dashboard (e.g. “Good evening, Jason”). Leave blank for a generic greeting.</p>
        </div>

        <div className="pt-2 border-t border-[color:var(--border)]">
          <div className="flex items-center gap-3 mb-3">
            <input
              type="checkbox"
              id="persona-enabled"
              checked={settings.agent_persona_enabled}
              onChange={e => setSettings({ ...settings, agent_persona_enabled: e.target.checked })}
              className="w-4 h-4 accent-[color:var(--accent)]"
            />
            <label htmlFor="persona-enabled" className="text-sm">
              Enable persona profile injection
            </label>
          </div>

          <label htmlFor="persona-path" className="block text-sm text-muted mb-1">Persona Folder</label>
          <input
            id="persona-path"
            type="text"
            value={settings.agent_persona_path}
            onChange={e => setSettings({ ...settings, agent_persona_path: e.target.value })}
            className="w-full bg-[color:var(--bg-elev)] rounded-lg px-3 py-2 text-sm border border-[color:var(--border)] focus:outline-none focus:border-[color:var(--accent)]"
          />
          <p className="text-xs text-muted mt-1">
            Relative example: data/persona. Absolute paths are also supported.
          </p>

          <div className="mt-3 flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={refreshPersonaPreview}
              disabled={previewLoading}
              className="btn-ghost px-3 py-1.5 rounded text-xs font-medium disabled:opacity-50"
            >
              {previewLoading ? 'Loading preview…' : 'Preview resolved persona block'}
            </button>
            {previewError && <span className="text-[color:var(--danger)] text-xs">{previewError}</span>}
          </div>

          <label htmlFor="persona-preview" className="block text-sm text-muted mt-3 mb-1">Persona Preview</label>
          <textarea
            id="persona-preview"
            value={personaPreview}
            readOnly
            rows={8}
            className="w-full bg-[color:var(--bg-elev)] rounded-lg px-3 py-2 text-xs border border-[color:var(--border)] focus:outline-none"
            placeholder="Click preview to load the resolved persona prompt block"
          />
        </div>

        <div className="flex items-center gap-3">
          <input
            type="checkbox"
            id="notifications"
            checked={settings.enable_notifications}
            onChange={e => setSettings({ ...settings, enable_notifications: e.target.checked })}
            className="w-4 h-4 accent-[color:var(--accent)]"
          />
          <label htmlFor="notifications" className="text-sm">
            Enable notifications
          </label>
        </div>

        <div className="flex items-center gap-3">
          <input
            type="checkbox"
            id="autosave"
            checked={settings.auto_save_results}
            onChange={e => setSettings({ ...settings, auto_save_results: e.target.checked })}
            className="w-4 h-4 accent-[color:var(--accent)]"
          />
          <label htmlFor="autosave" className="text-sm">
            Auto-save results
          </label>
        </div>

        {autostart !== null && (
          <div className="flex items-center gap-3 pt-2 border-t border-[color:var(--border)]">
            <input
              type="checkbox"
              id="autostart"
              checked={autostart}
              onChange={async e => {
                setAutostartState(e.target.checked)
                await setAutostart(e.target.checked)
              }}
              className="w-4 h-4 accent-[color:var(--accent)]"
            />
            <label htmlFor="autostart" className="text-sm">
              Launch on login <span className="text-xs text-muted">(desktop only)</span>
            </label>
          </div>
        )}

        <div className="flex items-center gap-3 pt-2">
          <button
            type="submit"
            disabled={saving}
            className="btn-accent px-4 py-2 rounded-lg text-sm font-medium disabled:opacity-50"
          >
            {saving ? 'Saving…' : 'Save Settings'}
          </button>
          {saved && <span className="text-[color:var(--success)] text-sm">Saved!</span>}
          {saveError && <span className="text-[color:var(--danger)] text-sm">{saveError}</span>}
        </div>
      </form>
    </div>
  )
}
