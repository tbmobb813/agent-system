'use client'

import { useState, useEffect } from 'react'
import { getSettings, updateSettings } from '@/lib/api'

type SettingsData = {
  preferred_model: string | null
  max_monthly_cost: number
  enable_notifications: boolean
  auto_save_results: boolean
  timezone: string
}

export default function SettingsPage() {
  const [settings, setSettings] = useState<SettingsData | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getSettings()
      .then(setSettings)
      .catch(err => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

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
          <label className="block text-sm text-gray-400 mb-1">Monthly Budget (USD)</label>
          <input
            type="number"
            step="0.01"
            min="0"
            value={settings.max_monthly_cost}
            onChange={e => setSettings({ ...settings, max_monthly_cost: parseFloat(e.target.value) })}
            className="w-full bg-gray-800 rounded-lg px-3 py-2 text-sm border border-gray-700 focus:outline-none focus:border-indigo-500"
          />
        </div>

        <div>
          <label className="block text-sm text-gray-400 mb-1">Preferred Model</label>
          <input
            type="text"
            placeholder="e.g. deepseek/deepseek-chat"
            value={settings.preferred_model ?? ''}
            onChange={e => setSettings({ ...settings, preferred_model: e.target.value || null })}
            className="w-full bg-gray-800 rounded-lg px-3 py-2 text-sm border border-gray-700 focus:outline-none focus:border-indigo-500"
          />
          <p className="text-xs text-gray-500 mt-1">Leave blank to use automatic model routing.</p>
        </div>

        <div>
          <label className="block text-sm text-gray-400 mb-1">Timezone</label>
          <input
            type="text"
            value={settings.timezone}
            onChange={e => setSettings({ ...settings, timezone: e.target.value })}
            className="w-full bg-gray-800 rounded-lg px-3 py-2 text-sm border border-gray-700 focus:outline-none focus:border-indigo-500"
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
