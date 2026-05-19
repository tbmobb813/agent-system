'use client'

import { useState, useEffect, useCallback } from 'react'
import {
  listSchedules,
  createSchedule,
  deleteSchedule,
  type Schedule,
} from '@/lib/api'

// ── Helpers ───────────────────────────────────────────────────────────────────

const CRON_PRESETS = [
  { label: 'Every hour', value: '0 * * * *' },
  { label: 'Daily 9am', value: '0 9 * * *' },
  { label: 'Daily midnight', value: '0 0 * * *' },
  { label: 'Weekdays 9am', value: '0 9 * * 1-5' },
  { label: 'Weekly Mon', value: '0 9 * * 1' },
  { label: 'Every 6h', value: '0 */6 * * *' },
  { label: 'Monthly 1st', value: '0 0 1 * *' },
]

const ROUTER_TIERS = ['', 'free', 'simple', 'balanced', 'coding', 'research', 'advanced', 'premium', 'agent']

const CRON_LABELS: Record<string, string> = Object.fromEntries(CRON_PRESETS.map(p => [p.value, p.label]))

function describeCron(expr: string): string {
  return CRON_LABELS[expr.trim()] ?? expr
}

function fmtDatetime(iso: string | null | undefined): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}

function fmtNextRun(iso: string): string {
  const ms = new Date(iso).getTime() - Date.now()
  if (ms < 0) return 'overdue'
  if (ms < 60_000) return 'in <1 min'
  if (ms < 3_600_000) return `in ${Math.floor(ms / 60_000)}m`
  if (ms < 86_400_000) return `in ${Math.floor(ms / 3_600_000)}h`
  return `in ${Math.floor(ms / 86_400_000)}d`
}

// ── Shared primitives (matches settings/page.tsx style) ───────────────────────

const INPUT_CLASS = 'w-full bg-[color:var(--bg-elev)] border border-(--border) rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[color:var(--accent)]'

function SectionCard({ children }: { children: React.ReactNode }) {
  return <div className="panel p-5 space-y-4">{children}</div>
}

function FieldLabel({ htmlFor, children }: { htmlFor?: string; children: React.ReactNode }) {
  return <label htmlFor={htmlFor} className="block text-xs uppercase tracking-widest text-muted mb-1">{children}</label>
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function SchedulesPage() {
  const [schedules, setSchedules] = useState<Schedule[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  // form state
  const [prompt, setPrompt] = useState('')
  const [cron, setCron] = useState('0 9 * * *')
  const [context, setContext] = useState('')
  const [routerTier, setRouterTier] = useState('')
  const [maxIter, setMaxIter] = useState(10)
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)

  const flash = (msg: string) => { setNotice(msg); setTimeout(() => setNotice(null), 4000) }

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try { setSchedules(await listSchedules()) }
    catch (e) { setError(e instanceof Error ? e.message : 'Failed to load') }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { void load() }, [load])

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!prompt.trim()) { setCreateError('Prompt is required'); return }
    setCreating(true); setCreateError(null)
    try {
      await createSchedule({
        cron: cron.trim(),
        prompt: prompt.trim(),
        context: context.trim() || undefined,
        router_tier: routerTier || undefined,
        max_iterations: maxIter,
      })
      setPrompt(''); setContext(''); setRouterTier(''); setMaxIter(10)
      flash('Schedule created')
      await load()
    } catch (e) { setCreateError(e instanceof Error ? e.message : 'Create failed') }
    finally { setCreating(false) }
  }

  const handleDelete = async (id: string, label: string) => {
    setBusy(id)
    try { await deleteSchedule(id); flash(`Deleted: ${label}`); await load() }
    catch (e) { flash(e instanceof Error ? e.message : 'Delete failed') }
    finally { setBusy(null) }
  }

  const activeCount = schedules.filter(s => s.enabled).length

  return (
    <div className="dr-history-stack">
      <header>
        <p className="eyebrow">Automation</p>
        <h1 className="section-title dr-dashboard-hero-title">Schedules</h1>
        <p className="dr-history-summary">
          Create cron-driven agent runs that execute unattended — daily reports, nightly backups, weekly audits.
        </p>
      </header>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-3">
        {[
          ['Total', schedules.length],
          ['Active', activeCount],
          ['Next run', schedules.length > 0
            ? fmtNextRun(schedules.slice().sort((a, b) => new Date(a.next_run_at).getTime() - new Date(b.next_run_at).getTime())[0].next_run_at)
            : '—'],
        ].map(([label, val]) => (
          <SectionCard key={String(label)}>
            <p className="text-xs uppercase tracking-widest text-muted">{label}</p>
            <p className="text-2xl font-semibold mt-1">{val}</p>
          </SectionCard>
        ))}
      </div>

      {/* Create form */}
      <SectionCard>
        <p className="text-xs uppercase tracking-widest text-muted">New Schedule</p>
        <form onSubmit={handleCreate} className="space-y-4">
          <div>
            <FieldLabel htmlFor="sched-prompt">Prompt</FieldLabel>
            <textarea
              id="sched-prompt"
              rows={3}
              value={prompt}
              onChange={e => setPrompt(e.target.value)}
              placeholder="e.g. Summarise today's costs and send a Telegram report"
              className={INPUT_CLASS}
            />
          </div>

          <div>
            <FieldLabel htmlFor="sched-cron">Cron expression</FieldLabel>
            <input
              id="sched-cron"
              type="text"
              value={cron}
              onChange={e => setCron(e.target.value)}
              placeholder="0 9 * * *"
              className={`${INPUT_CLASS} font-mono`}
            />
            <div className="flex flex-wrap gap-1.5 mt-2">
              {CRON_PRESETS.map(p => (
                <button
                  key={p.value}
                  type="button"
                  onClick={() => setCron(p.value)}
                  className={`dr-chip text-xs cursor-pointer transition-colors ${cron === p.value ? 'dr-chip-tool' : ''}`}
                >
                  {p.label}
                </button>
              ))}
            </div>
          </div>

          <div className="grid sm:grid-cols-2 gap-3">
            <div>
              <FieldLabel htmlFor="sched-tier">Router tier</FieldLabel>
              <select
                id="sched-tier"
                value={routerTier}
                onChange={e => setRouterTier(e.target.value)}
                className="w-full bg-[color:var(--bg-elev)] border border-(--border) rounded-lg px-3 py-2 text-sm"
              >
                {ROUTER_TIERS.map(t => (
                  <option key={t} value={t}>{t || 'Auto (recommended)'}</option>
                ))}
              </select>
            </div>
            <div>
              <FieldLabel htmlFor="sched-iter">Max iterations</FieldLabel>
              <input
                id="sched-iter"
                type="number"
                min={1}
                max={50}
                value={maxIter}
                onChange={e => setMaxIter(Math.max(1, Math.min(50, parseInt(e.target.value) || 10)))}
                className={INPUT_CLASS}
              />
            </div>
          </div>

          <div>
            <FieldLabel htmlFor="sched-ctx">Context (optional)</FieldLabel>
            <input
              id="sched-ctx"
              type="text"
              value={context}
              onChange={e => setContext(e.target.value)}
              placeholder="Extra context injected into the run"
              className={INPUT_CLASS}
            />
          </div>

          <div className="flex items-center gap-3">
            <button type="submit" disabled={creating} className="dr-btn-accent px-4 py-2 rounded-lg text-sm font-medium disabled:opacity-50">
              {creating ? 'Creating…' : 'Create schedule'}
            </button>
            {createError && <span className="text-[color:var(--danger)] text-xs">{createError}</span>}
          </div>
        </form>
      </SectionCard>

      {notice && (
        <p className="text-xs text-muted px-1">{notice}</p>
      )}

      {/* Schedule list */}
      {loading && <p className="text-muted text-sm">Loading…</p>}
      {!loading && error && <p className="text-[color:var(--danger)] text-sm">{error}</p>}
      {!loading && !error && schedules.length === 0 && (
        <p className="text-sm text-muted">No schedules yet. Create one above.</p>
      )}

      {schedules.length > 0 && (
        <div className="space-y-3">
          {schedules.map(s => (
            <div key={s.id} className="panel p-4 space-y-3">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-mono text-xs text-[color:var(--accent-2)]">{describeCron(s.cron_expr)}</span>
                    <span className={`text-[10px] uppercase tracking-widest px-2 py-0.5 rounded border font-semibold ${s.enabled ? 'border-[color:var(--success)]/50 text-[color:var(--success)] bg-[color:var(--success)]/10' : 'border-(--border) text-muted'}`}>
                      {s.enabled ? 'active' : 'paused'}
                    </span>
                    {s.router_tier && (
                      <span className="dr-chip dr-chip-tool text-[10px]">{s.router_tier}</span>
                    )}
                  </div>
                  <p className="text-sm mt-1 leading-relaxed line-clamp-2">{s.prompt}</p>
                  {s.context && <p className="text-xs text-muted mt-0.5 truncate">ctx: {s.context}</p>}
                </div>
                <button
                  type="button"
                  onClick={() => void handleDelete(s.id, describeCron(s.cron_expr))}
                  disabled={busy === s.id}
                  className="dr-btn-ghost px-2.5 py-1 rounded text-xs text-[color:var(--danger)] shrink-0 disabled:opacity-50"
                >
                  {busy === s.id ? '…' : 'Delete'}
                </button>
              </div>
              <div className="flex gap-4 text-xs text-muted border-t border-(--border) pt-2">
                <span>Next: <span className="text-[color:var(--text)]">{fmtNextRun(s.next_run_at)}</span> ({fmtDatetime(s.next_run_at)})</span>
                <span>Last: <span className="text-[color:var(--text)]">{fmtDatetime(s.last_run_at)}</span></span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
