'use client'

import { useState, useEffect, useCallback, useRef } from 'react'
import {
  listMemories,
  searchMemories,
  saveMemory,
  deleteMemory,
  getAnalyticsSkills,
  type Memory,
} from '@/lib/api'

// ── Helpers ───────────────────────────────────────────────────────────────────

const CATEGORIES = ['', 'fact', 'preference', 'insight', 'observation', 'task']

const CATEGORY_COLORS: Record<string, string> = {
  fact: 'border-[color:var(--accent)]/50 text-[color:var(--accent)] bg-[color:var(--accent)]/10',
  preference: 'border-purple-400/50 text-purple-400 bg-purple-400/10',
  insight: 'border-[color:var(--success)]/50 text-[color:var(--success)] bg-[color:var(--success)]/10',
  observation: 'border-yellow-400/50 text-yellow-400 bg-yellow-400/10',
  task: 'border-[color:var(--accent-2)]/50 text-[color:var(--accent-2)] bg-[color:var(--accent-2)]/10',
}

function categoryColor(cat: string): string {
  return CATEGORY_COLORS[cat] ?? 'border-(--border) text-muted'
}

function fmtDatetime(iso: string | null | undefined): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}

// ── Shared primitives ─────────────────────────────────────────────────────────

const INPUT_CLASS = 'w-full bg-[color:var(--bg-elev)] border border-(--border) rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[color:var(--accent)]'

function SectionCard({ children }: { children: React.ReactNode }) {
  return <div className="panel p-5 space-y-4">{children}</div>
}

// ── Types ─────────────────────────────────────────────────────────────────────

type Tab = 'memories' | 'skills'
type SkillRow = Record<string, unknown>

// ── Page ──────────────────────────────────────────────────────────────────────

export default function MemoryPage() {
  const [activeTab, setActiveTab] = useState<Tab>('memories')

  // ── Memories state ────────────────────────────────────────────────────────
  const [memories, setMemories] = useState<Memory[]>([])
  const [loadingMem, setLoadingMem] = useState(true)
  const [memError, setMemError] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [filterCat, setFilterCat] = useState('')
  const [busy, setBusy] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  // add memory form
  const [newContent, setNewContent] = useState('')
  const [newCat, setNewCat] = useState('fact')
  const [saving, setSaving] = useState(false)

  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const flash = (msg: string) => { setNotice(msg); setTimeout(() => setNotice(null), 4000) }

  const loadMemories = useCallback(async (q?: string, cat?: string) => {
    setLoadingMem(true); setMemError(null)
    try {
      if (q && q.trim()) {
        const res = await searchMemories(q.trim(), 20)
        setMemories(res.results)
      } else {
        const res = await listMemories(40, cat || undefined)
        setMemories(res.memories)
      }
    } catch (e) { setMemError(e instanceof Error ? e.message : 'Failed to load') }
    finally { setLoadingMem(false) }
  }, [])

  useEffect(() => { void loadMemories() }, [loadMemories])

  useEffect(() => () => { if (searchTimer.current) clearTimeout(searchTimer.current) }, [])

  // debounce search input
  const handleQueryChange = (val: string) => {
    setQuery(val)
    if (searchTimer.current) clearTimeout(searchTimer.current)
    searchTimer.current = setTimeout(() => void loadMemories(val, filterCat), 350)
  }

  const handleCatChange = (cat: string) => {
    setFilterCat(cat)
    void loadMemories(query, cat)
  }

  const handleDelete = async (id: string) => {
    setBusy(id)
    try { await deleteMemory(id); flash('Deleted'); setMemories(prev => prev.filter(m => m.id !== id)) }
    catch (e) { flash(e instanceof Error ? e.message : 'Delete failed') }
    finally { setBusy(null) }
  }

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!newContent.trim()) return
    setSaving(true)
    try {
      await saveMemory(newContent.trim(), newCat)
      setNewContent('')
      flash('Memory saved')
      await loadMemories(query, filterCat)
    } catch (e) { flash(e instanceof Error ? e.message : 'Save failed') }
    finally { setSaving(false) }
  }

  // ── Skills state ──────────────────────────────────────────────────────────
  const [skills, setSkills] = useState<SkillRow[]>([])
  const [growthAreas, setGrowthAreas] = useState<string[]>([])
  const [loadingSkills, setLoadingSkills] = useState(false)
  const [skillsError, setSkillsError] = useState<string | null>(null)

  const loadSkills = useCallback(async () => {
    setLoadingSkills(true); setSkillsError(null)
    try {
      const d = await getAnalyticsSkills() as { skills?: unknown; growth_areas?: unknown }
      setSkills(Array.isArray(d.skills) ? d.skills as SkillRow[] : [])
      setGrowthAreas(Array.isArray(d.growth_areas) ? d.growth_areas.map(String) : [])
    } catch (e) { setSkillsError(e instanceof Error ? e.message : 'Failed to load') }
    finally { setLoadingSkills(false) }
  }, [])

  useEffect(() => { if (activeTab === 'skills' && skills.length === 0 && !loadingSkills) void loadSkills() }, [activeTab, skills.length, loadingSkills, loadSkills])

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="dr-history-stack">
      <header>
        <p className="eyebrow">Learning</p>
        <h1 className="section-title dr-dashboard-hero-title">Memory</h1>
        <p className="dr-history-summary">
          Browse and search what the agent knows about you — facts, preferences, insights, and learned skills.
        </p>
      </header>

      {/* Tab bar */}
      <div className="flex gap-1 border-b border-[color:var(--border)] pb-0">
        {(['memories', 'skills'] as Tab[]).map(t => (
          <button
            key={t}
            type="button"
            onClick={() => setActiveTab(t)}
            className={`px-4 py-2 text-sm font-medium rounded-t-lg border border-b-0 capitalize whitespace-nowrap transition-colors ${activeTab === t ? 'border-(--border) bg-[color:var(--surface)] text-[color:var(--text)]' : 'border-transparent text-muted hover:text-[color:var(--text)]'}`}
          >
            {t}
          </button>
        ))}
      </div>

      {/* ── Memories tab ──────────────────────────────────────────────────────── */}
      {activeTab === 'memories' && (
        <div className="space-y-4">
          {/* Stats */}
          <div className="grid grid-cols-2 gap-3">
            <SectionCard>
              <p className="text-xs uppercase tracking-widest text-muted">Loaded</p>
              <p className="text-2xl font-semibold mt-1">{memories.length}</p>
            </SectionCard>
            <SectionCard>
              <p className="text-xs uppercase tracking-widest text-muted">Category filter</p>
              <select
                value={filterCat}
                onChange={e => handleCatChange(e.target.value)}
                className="mt-1 w-full bg-[color:var(--bg-elev)] border border-(--border) rounded-lg px-3 py-1.5 text-sm capitalize"
              >
                {CATEGORIES.map(c => <option key={c} value={c}>{c || 'All categories'}</option>)}
              </select>
            </SectionCard>
          </div>

          {/* Search */}
          <div className="relative">
            <input
              type="search"
              value={query}
              onChange={e => handleQueryChange(e.target.value)}
              placeholder="Search memories…"
              className={INPUT_CLASS}
            />
            {loadingMem && (
              <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-muted">searching…</span>
            )}
          </div>

          {/* Add memory */}
          <SectionCard>
            <p className="text-xs uppercase tracking-widest text-muted">Add Memory</p>
            <form onSubmit={handleSave} className="space-y-2">
              <textarea
                rows={2}
                value={newContent}
                onChange={e => setNewContent(e.target.value)}
                placeholder="e.g. User prefers concise bullet-point responses"
                className={INPUT_CLASS}
              />
              <div className="flex items-center gap-2">
                <select
                  value={newCat}
                  onChange={e => setNewCat(e.target.value)}
                  className="bg-[color:var(--bg-elev)] border border-(--border) rounded-lg px-3 py-2 text-sm"
                >
                  {CATEGORIES.filter(Boolean).map(c => <option key={c} value={c}>{c}</option>)}
                </select>
                <button type="submit" disabled={saving || !newContent.trim()} className="dr-btn-accent px-3 py-2 rounded-lg text-xs disabled:opacity-50">
                  {saving ? 'Saving…' : 'Save'}
                </button>
              </div>
            </form>
          </SectionCard>

          {notice && <p className="text-xs text-muted px-1">{notice}</p>}

          {/* Memory list */}
          {!loadingMem && memError && <p className="text-[color:var(--danger)] text-sm">{memError}</p>}
          {!loadingMem && !memError && memories.length === 0 && (
            <p className="text-sm text-muted">{query ? 'No results for that query.' : 'No memories yet — the agent builds these automatically during conversations.'}</p>
          )}

          {memories.length > 0 && (
            <div className="space-y-2">
              {memories.map(m => (
                <div key={m.id} className="panel p-4 flex items-start gap-3">
                  <div className="flex-1 min-w-0 space-y-1.5">
                    <p className="text-sm leading-relaxed">{m.content}</p>
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className={`text-[10px] uppercase tracking-widest px-2 py-0.5 rounded border font-semibold ${categoryColor(m.category)}`}>
                        {m.category}
                      </span>
                      <span className="text-xs text-muted">{fmtDatetime(m.created_at)}</span>
                      {(m.relevance_score != null || m.similarity != null) && (
                        <span className="text-xs text-muted">relevance {((m.relevance_score ?? m.similarity ?? 0) * 100).toFixed(0)}%</span>
                      )}
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => void handleDelete(m.id)}
                    disabled={busy === m.id}
                    className="dr-btn-ghost px-2 py-1 rounded text-xs text-[color:var(--danger)] shrink-0 disabled:opacity-50"
                  >
                    {busy === m.id ? '…' : 'Delete'}
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── Skills tab ────────────────────────────────────────────────────────── */}
      {activeTab === 'skills' && (
        <div className="space-y-4">
          {loadingSkills && <p className="text-muted text-sm">Loading…</p>}
          {!loadingSkills && skillsError && <p className="text-[color:var(--danger)] text-sm">{skillsError}</p>}

          {!loadingSkills && !skillsError && (
            <>
              {/* Stats */}
              <div className="grid grid-cols-2 gap-3">
                <SectionCard>
                  <p className="text-xs uppercase tracking-widest text-muted">Learned skills</p>
                  <p className="text-2xl font-semibold mt-1">{skills.length}</p>
                </SectionCard>
                <SectionCard>
                  <p className="text-xs uppercase tracking-widest text-muted">Growth areas</p>
                  <p className="text-2xl font-semibold mt-1">{growthAreas.length}</p>
                </SectionCard>
              </div>

              {skills.length === 0 && (
                <p className="text-sm text-muted">No skills tracked yet. Skills are learned automatically after the agent completes complex tasks.</p>
              )}

              {/* Skills table */}
              {skills.length > 0 && (
                <div className="panel panel-soft rounded-lg overflow-hidden">
                  <div className="grid grid-cols-[1.5fr_1fr_0.6fr_0.6fr] gap-3 px-4 py-2 text-[10px] uppercase tracking-widest text-muted border-b border-(--border)">
                    <span>Skill</span>
                    <span>Task type</span>
                    <span className="text-right">Success</span>
                    <span className="text-right">Uses</span>
                  </div>
                  {skills.map((skill, i) => {
                    const name = String(skill.skill_name ?? skill.skill ?? skill.name ?? `Skill ${i + 1}`)
                    const taskType = String(skill.task_type ?? skill.taskType ?? name)
                    const successRaw = skill.success_rate ?? skill.success ?? skill.win_rate
                    const success = successRaw == null ? null : typeof successRaw === 'number' ? successRaw : parseFloat(String(successRaw))
                    const uses = skill.total_uses ?? skill.count ?? skill.uses ?? skill.total ?? null
                    const level = String(skill.proficiency_level ?? '')

                    return (
                      <div key={`${taskType}-${i}`} className="grid grid-cols-[1.5fr_1fr_0.6fr_0.6fr] gap-3 px-4 py-3 text-sm border-b last:border-b-0 border-(--border)/50 items-center">
                        <div className="min-w-0">
                          <p className="font-medium truncate" title={name}>{name}</p>
                          {level && (
                            <span className={`text-[10px] uppercase tracking-widest ${level === 'expert' ? 'text-[color:var(--success)]' : level === 'competent' ? 'text-[color:var(--accent-2)]' : 'text-muted'}`}>
                              {level}
                            </span>
                          )}
                        </div>
                        <span className="text-xs text-muted truncate" title={taskType}>{taskType}</span>
                        <div className="text-right">
                          {success == null ? (
                            <span className="text-muted">—</span>
                          ) : (
                            <div className="space-y-0.5">
                              <span className={success >= 0.8 ? 'text-[color:var(--success)]' : success >= 0.5 ? 'text-[color:var(--accent-2)]' : 'text-[color:var(--danger)]'}>
                                {(success * 100).toFixed(0)}%
                              </span>
                              <div className="h-1 rounded-full bg-[color:var(--bg-elev)] overflow-hidden">
                                <div
                                  className={`h-full rounded-full transition-all ${success >= 0.8 ? 'bg-[color:var(--success)]' : success >= 0.5 ? 'bg-[color:var(--accent-2)]' : 'bg-[color:var(--danger)]'}`}
                                  style={{ width: `${Math.round(success * 100)}%` }}
                                />
                              </div>
                            </div>
                          )}
                        </div>
                        <span className="text-right text-muted">{uses == null ? '—' : String(uses)}</span>
                      </div>
                    )
                  })}
                </div>
              )}

              {growthAreas.length > 0 && (
                <SectionCard>
                  <p className="text-xs uppercase tracking-widest text-muted">Top growth areas</p>
                  <div className="flex flex-wrap gap-2 mt-1">
                    {growthAreas.map(a => <span key={a} className="dr-chip">{a}</span>)}
                  </div>
                </SectionCard>
              )}
            </>
          )}
        </div>
      )}
    </div>
  )
}
