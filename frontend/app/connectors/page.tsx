'use client'

import { useEffect, useState, useCallback } from 'react'
import {
  listConnectors,
  saveConnector,
  clearConnectorToken,
  testConnector,
  type ConnectorStatus,
} from '@/lib/api'

// ── Icons ─────────────────────────────────────────────────────────────────────

function IconGitHub() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" />
    </svg>
  )
}

function ConnectorIcon({ id }: { id: string }) {
  if (id === 'github') return <IconGitHub />
  return <span className="text-lg">🔌</span>
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

  const flash = (msg: string) => {
    setNotice(msg)
    setTimeout(() => setNotice(null), 3500)
  }

  const handleSave = async () => {
    if (!token.trim() && !connector.configured) return
    setSaving(true)
    try {
      const updated = await saveConnector(connector.id, {
        token: token.trim() || undefined,
        enabled: true,
      })
      onUpdate(updated)
      setToken('')
      setExpanded(false)
      flash('Saved and enabled.')
    } catch (e) {
      flash(e instanceof Error ? e.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  const handleToggle = async () => {
    setSaving(true)
    try {
      const updated = await saveConnector(connector.id, { enabled: !connector.enabled })
      onUpdate(updated)
    } catch (e) {
      flash(e instanceof Error ? e.message : 'Toggle failed')
    } finally {
      setSaving(false)
    }
  }

  const handleClear = async () => {
    setClearing(true)
    setTestResult(null)
    try {
      const updated = await clearConnectorToken(connector.id)
      onUpdate(updated)
      setExpanded(true)
      flash('Token removed.')
    } catch (e) {
      flash(e instanceof Error ? e.message : 'Clear failed')
    } finally {
      setClearing(false)
    }
  }

  const handleTest = async () => {
    setTesting(true)
    setTestResult(null)
    try {
      const result = await testConnector(connector.id)
      setTestResult(result)
    } catch (e) {
      setTestResult({ ok: false, detail: e instanceof Error ? e.message : 'Test failed' })
    } finally {
      setTesting(false)
    }
  }

  return (
    <div className={`panel p-5 space-y-4 transition-all ${connector.enabled ? 'border-[color:var(--accent)]/30' : ''}`}>
      {/* Header */}
      <div className="flex items-start gap-3">
        <div className={`mt-0.5 ${connector.configured ? 'text-[color:var(--accent)]' : 'text-muted'}`}>
          <ConnectorIcon id={connector.id} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="section-title dr-title-16">{connector.name}</h3>
            {connector.configured ? (
              <span className={`text-[10px] uppercase tracking-widest px-2 py-0.5 rounded border font-semibold ${
                connector.enabled
                  ? 'border-[color:var(--success)]/50 text-[color:var(--success)] bg-[color:var(--success)]/10'
                  : 'border-[color:var(--border)] text-muted'
              }`}>
                {connector.enabled ? 'Enabled' : 'Disabled'}
              </span>
            ) : (
              <span className="text-[10px] uppercase tracking-widest px-2 py-0.5 rounded border border-[color:var(--border)] text-muted">
                Not configured
              </span>
            )}
          </div>
          <p className="text-sm text-muted mt-1">{connector.description}</p>
          {connector.configured && connector.token_preview && (
            <p className="text-xs font-mono text-muted mt-1">{connector.token_label}: {connector.token_preview}</p>
          )}
        </div>
        {/* Actions */}
        <div className="flex items-center gap-2 shrink-0">
          {connector.configured && (
            <button
              type="button"
              onClick={handleToggle}
              disabled={saving}
              title={connector.enabled ? 'Disable connector' : 'Enable connector'}
              className={`relative inline-flex h-6 w-11 items-center rounded-full border transition-colors disabled:opacity-50 ${
                connector.enabled
                  ? 'bg-[color:var(--accent)] border-[color:var(--accent)]'
                  : 'bg-[color:var(--surface-soft)] border-[color:var(--border)]'
              }`}
            >
              <span className={`inline-block h-4 w-4 rounded-full bg-white shadow transition-transform ${
                connector.enabled ? 'translate-x-6' : 'translate-x-1'
              }`} />
            </button>
          )}
          <button
            type="button"
            onClick={() => setExpanded(e => !e)}
            className="dr-btn-ghost px-2.5 py-1 text-xs rounded-lg"
          >
            {expanded ? 'Collapse' : 'Configure'}
          </button>
        </div>
      </div>

      {/* Actions list */}
      {connector.configured && !expanded && (
        <div className="flex flex-wrap gap-1.5">
          {connector.actions.map(a => (
            <span key={a} className="dr-chip dr-chip-tool">{a}</span>
          ))}
        </div>
      )}

      {/* Expanded config */}
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
              <button
                type="button"
                onClick={() => setShowToken(s => !s)}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-muted px-1 py-0.5 hover:text-[color:var(--text)]"
              >
                {showToken ? 'hide' : 'show'}
              </button>
            </div>
            <a
              href={connector.token_help}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-[color:var(--accent-2)] hover:underline"
            >
              How to get a token ↗
            </a>
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            <button
              type="button"
              onClick={handleSave}
              disabled={saving || (!token.trim() && !connector.configured)}
              className="dr-btn-accent px-3 py-1.5 rounded-lg text-xs disabled:opacity-50"
            >
              {saving ? 'Saving…' : connector.configured ? 'Update token' : 'Save & enable'}
            </button>
            <button
              type="button"
              onClick={handleTest}
              disabled={testing || !connector.configured}
              className="dr-btn-ghost px-3 py-1.5 rounded-lg text-xs disabled:opacity-50"
            >
              {testing ? 'Testing…' : 'Test connection'}
            </button>
            {connector.configured && (
              <button
                type="button"
                onClick={handleClear}
                disabled={clearing}
                className="dr-btn-ghost px-3 py-1.5 rounded-lg text-xs text-[color:var(--danger)] disabled:opacity-50 ml-auto"
              >
                {clearing ? 'Removing…' : 'Remove token'}
              </button>
            )}
          </div>

          {testResult && (
            <p className={`text-xs px-3 py-2 rounded-lg border ${
              testResult.ok
                ? 'text-[color:var(--success)] border-[color:var(--success)]/30 bg-[color:var(--success)]/10'
                : 'text-[color:var(--danger)] border-[color:var(--danger)]/30 bg-[color:var(--danger)]/10'
            }`}>
              {testResult.ok ? '✓' : '✗'} {testResult.detail}
            </p>
          )}
        </div>
      )}

      {notice && (
        <p className="text-xs text-muted border-t border-[color:var(--border)] pt-3">{notice}</p>
      )}
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function ConnectorsPage() {
  const [connectors, setConnectors] = useState<ConnectorStatus[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      setError(null)
      const data = await listConnectors()
      setConnectors(data)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load connectors')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const updateConnector = useCallback((updated: ConnectorStatus) => {
    setConnectors(prev => prev.map(c => c.id === updated.id ? updated : c))
  }, [])

  const configuredCount = connectors.filter(c => c.configured).length
  const enabledCount = connectors.filter(c => c.enabled).length

  return (
    <div className="dr-history-stack">
      <header>
        <p className="eyebrow">Integrations</p>
        <h1 className="section-title dr-dashboard-hero-title">Connectors</h1>
        <p className="dr-history-summary">
          Connect external services so the agent can read and write on your behalf.
          Tokens are stored locally and never sent anywhere except the service&apos;s own API.
        </p>
        {!loading && connectors.length > 0 && (
          <div className="dr-dashboard-pill-row mt-4">
            <span className="dr-pill-stat">
              <span className={`dr-pill-stat-dot ${enabledCount > 0 ? 'dr-pill-tone-ok' : 'dr-pill-tone-muted'}`} />
              <span className="dr-pill-stat-label">{enabledCount} active</span>
            </span>
            <span className="dr-pill-stat">
              <span className="dr-pill-stat-dot dr-pill-tone-muted" />
              <span className="dr-pill-stat-label">{configuredCount} configured</span>
            </span>
            <span className="dr-pill-stat">
              <span className="dr-pill-stat-dot dr-pill-tone-running" />
              <span className="dr-pill-stat-label">{connectors.length} available</span>
            </span>
          </div>
        )}
      </header>

      {loading && (
        <div className="panel p-8 text-center text-muted text-sm">Loading connectors…</div>
      )}

      {error && (
        <div className="panel p-5 text-sm text-[color:var(--danger)]">
          Failed to load connectors: {error}
        </div>
      )}

      {!loading && !error && (
        <div className="space-y-4">
          {connectors.map(c => (
            <ConnectorCard key={c.id} connector={c} onUpdate={updateConnector} />
          ))}
        </div>
      )}
    </div>
  )
}
