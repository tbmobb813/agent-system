'use client'

import { useState, useEffect } from 'react'
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
  const [error, setError] = useState<string | null>(null)
  const [autostart, setAutostartState] = useState<boolean | null>(null)
  const [personaPreview, setPersonaPreview] = useState('')
  const [previewLoading, setPreviewLoading] = useState(false)

  useEffect(() => {
    getAutostartEnabled().then(setAutostartState)
  }, [])

  useEffect(() => {
    getSettings()
      .then(setSettings)
      .catch(err => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  async function refreshPersonaPreview() {
    setPreviewLoading(true)
    setError(null)
    try {
      const payload = await getPersonaPreview()
      setPersonaPreview(payload.preview || '')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Preview failed')
    } finally {
      setPreviewLoading(false)
    }
  }

  async function handleSave(e: React.FormEvent) {
    e.preventDefault()
    if (!settings) return
    setSaving(true)
    setError(null)
    try {
      await updateSettings(settings)
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <p className="text-gray-400">Loading settings…</p>
  if (!settings && error) return <p className="text-red-400">Error: {error}</p>
  if (!settings) return null

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Settings</h1>
      <form onSubmit={handleSave} className="max-w-xl space-y-5">

        <div>
          <label htmlFor="max-monthly-cost" className="block text-sm text-gray-400 mb-1">Monthly Budget (USD)</label>
          <input
            id="max-monthly-cost"
            type="number"
            step="0.01"
            min="0"
            value={settings.max_monthly_cost}
            onChange={e => setSettings({ ...settings, max_monthly_cost: parseFloat(e.target.value) })}
            className="w-full bg-gray-800 rounded-lg px-3 py-2 text-sm border border-gray-700 focus:outline-none focus:border-indigo-500"
          />
        </div>

        <div>
          <label htmlFor="preferred-model" className="block text-sm text-gray-400 mb-1">Preferred Model</label>
          <input
            id="preferred-model"
            type="text"
            placeholder="e.g. deepseek/deepseek-chat"
            value={settings.preferred_model ?? ''}
            onChange={e => setSettings({ ...settings, preferred_model: e.target.value || null })}
            className="w-full bg-gray-800 rounded-lg px-3 py-2 text-sm border border-gray-700 focus:outline-none focus:border-indigo-500"
          />
          <p className="text-xs text-gray-500 mt-1">Leave blank to use automatic model routing.</p>
        </div>

        <div>
          <label htmlFor="timezone" className="block text-sm text-gray-400 mb-1">Timezone</label>
          <input
            id="timezone"
            type="text"
            value={settings.timezone}
            onChange={e => setSettings({ ...settings, timezone: e.target.value })}
            className="w-full bg-gray-800 rounded-lg px-3 py-2 text-sm border border-gray-700 focus:outline-none focus:border-indigo-500"
          />
        </div>

        <div className="pt-2 border-t border-gray-800">
          <div className="flex items-center gap-3 mb-3">
            <input
              type="checkbox"
              id="persona-enabled"
              checked={settings.agent_persona_enabled}
              onChange={e => setSettings({ ...settings, agent_persona_enabled: e.target.checked })}
              className="w-4 h-4 accent-indigo-500"
            />
            <label htmlFor="persona-enabled" className="text-sm text-gray-300">
              Enable persona profile injection
            </label>
          </div>

          <label htmlFor="persona-path" className="block text-sm text-gray-400 mb-1">Persona Folder</label>
          <input
            id="persona-path"
            type="text"
            value={settings.agent_persona_path}
            onChange={e => setSettings({ ...settings, agent_persona_path: e.target.value })}
            className="w-full bg-gray-800 rounded-lg px-3 py-2 text-sm border border-gray-700 focus:outline-none focus:border-indigo-500"
          />
          <p className="text-xs text-gray-500 mt-1">
            Relative example: data/persona. Absolute paths are also supported.
          </p>

          <div className="mt-3">
            <button
              type="button"
              onClick={refreshPersonaPreview}
              disabled={previewLoading}
              className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 rounded text-xs font-medium disabled:opacity-50 transition-colors"
            >
              {previewLoading ? 'Loading preview…' : 'Preview resolved persona block'}
            </button>
          </div>

          <label htmlFor="persona-preview" className="block text-sm text-gray-400 mt-3 mb-1">Persona Preview</label>
          <textarea
            id="persona-preview"
            value={personaPreview}
            readOnly
            rows={8}
            className="w-full bg-gray-900 rounded-lg px-3 py-2 text-xs border border-gray-700 focus:outline-none"
            placeholder="Click preview to load the resolved persona prompt block"
          />
        </div>

        <div className="flex items-center gap-3">
          <input
            type="checkbox"
            id="notifications"
            checked={settings.enable_notifications}
            onChange={e => setSettings({ ...settings, enable_notifications: e.target.checked })}
            className="w-4 h-4 accent-indigo-500"
          />
          <label htmlFor="notifications" className="text-sm text-gray-300">
            Enable notifications
          </label>
        </div>

        <div className="flex items-center gap-3">
          <input
            type="checkbox"
            id="autosave"
            checked={settings.auto_save_results}
            onChange={e => setSettings({ ...settings, auto_save_results: e.target.checked })}
            className="w-4 h-4 accent-indigo-500"
          />
          <label htmlFor="autosave" className="text-sm text-gray-300">
            Auto-save results
          </label>
        </div>

        {autostart !== null && (
          <div className="flex items-center gap-3 pt-2 border-t border-gray-800">
            <input
              type="checkbox"
              id="autostart"
              checked={autostart}
              onChange={async e => {
                setAutostartState(e.target.checked)
                await setAutostart(e.target.checked)
              }}
              className="w-4 h-4 accent-indigo-500"
            />
            <label htmlFor="autostart" className="text-sm text-gray-300">
              Launch on login <span className="text-xs text-gray-500">(desktop only)</span>
            </label>
          </div>
        )}

        <div className="flex items-center gap-3 pt-2">
          <button
            type="submit"
            disabled={saving}
            className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 rounded-lg text-sm font-medium disabled:opacity-50 transition-colors"
          >
            {saving ? 'Saving…' : 'Save Settings'}
          </button>
          {saved && <span className="text-green-400 text-sm">Saved!</span>}
          {error && <span className="text-red-400 text-sm">{error}</span>}
        </div>
      </form>
    </div>
  )
}
