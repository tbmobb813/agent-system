'use client'

import { useState, useEffect, useCallback } from 'react'
import Link from 'next/link'
import { listProjects, createProject, updateProject, deleteProject, type Project } from '@/lib/api'

const PRESET_COLORS = [
  '#2be3c6', '#59a7ff', '#ff6a76', '#ffba49', '#2fd67d',
  '#9d7dff', '#ff4fd8', '#54f2ff', '#f4a524', '#b0b2cf',
]

function ColorDot({ color, size = 12 }: { color: string; size?: number }) {
  return <span style={{ width: size, height: size, borderRadius: '50%', background: color, display: 'inline-block', flexShrink: 0 }} />
}

function ProjectFormModal({
  initial,
  onSave,
  onClose,
}: {
  initial?: Project
  onSave: (p: Project) => void
  onClose: () => void
}) {
  const [name, setName] = useState(initial?.name ?? '')
  const [description, setDescription] = useState(initial?.description ?? '')
  const [color, setColor] = useState(initial?.color ?? PRESET_COLORS[0])
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim()) return
    setSaving(true); setError(null)
    try {
      const result = initial
        ? await updateProject(initial.id, { name: name.trim(), description: description.trim() || undefined, color })
        : await createProject({ name: name.trim(), description: description.trim() || undefined, color })
      onSave(result)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm">
      <div className="bg-[color:var(--bg)] border border-[color:var(--border)] rounded-xl shadow-2xl w-full max-w-md p-6 space-y-4">
        <h3 className="section-title dr-title-16">{initial ? 'Edit project' : 'New project'}</h3>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs uppercase tracking-widest text-muted mb-1">Name</label>
            <input
              autoFocus
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="e.g. Research, Work, Personal"
              className="w-full bg-[color:var(--bg-elev)] border border-[color:var(--border)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[color:var(--accent)]"
            />
          </div>
          <div>
            <label className="block text-xs uppercase tracking-widest text-muted mb-1">Description <span className="normal-case tracking-normal">(optional)</span></label>
            <input
              value={description}
              onChange={e => setDescription(e.target.value)}
              placeholder="What goes in here?"
              className="w-full bg-[color:var(--bg-elev)] border border-[color:var(--border)] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[color:var(--accent)]"
            />
          </div>
          <div>
            <label className="block text-xs uppercase tracking-widest text-muted mb-2">Color</label>
            <div className="flex gap-2 flex-wrap">
              {PRESET_COLORS.map(c => (
                <button
                  key={c}
                  type="button"
                  onClick={() => setColor(c)}
                  style={{ background: c }}
                  className={`w-7 h-7 rounded-full transition-transform ${color === c ? 'scale-125 ring-2 ring-white/40 ring-offset-1 ring-offset-[color:var(--bg)]' : 'hover:scale-110'}`}
                />
              ))}
            </div>
          </div>
          {error && <p className="text-xs text-[color:var(--danger)]">{error}</p>}
          <div className="flex gap-2 justify-end pt-1">
            <button type="button" onClick={onClose} className="dr-btn-ghost px-3 py-1.5 rounded-lg text-sm">Cancel</button>
            <button type="submit" disabled={saving || !name.trim()} className="dr-btn-accent px-3 py-1.5 rounded-lg text-sm disabled:opacity-50">
              {saving ? 'Saving…' : initial ? 'Save changes' : 'Create'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

function ProjectCard({ project, onEdit, onDelete }: { project: Project; onEdit: () => void; onDelete: () => void }) {
  const [confirming, setConfirming] = useState(false)
  const [deleting, setDeleting] = useState(false)

  const handleDelete = async () => {
    setDeleting(true)
    try { await deleteProject(project.id); onDelete() }
    catch { setDeleting(false); setConfirming(false) }
  }

  return (
    <div className="panel p-5 flex flex-col gap-3 hover:border-[color:var(--accent)]/40 transition-colors">
      <div className="flex items-start gap-3">
        <ColorDot color={project.color} size={14} />
        <div className="flex-1 min-w-0">
          <Link href={`/projects/${project.id}`} className="text-sm font-semibold hover:text-[color:var(--accent)] transition-colors block truncate">
            {project.name}
          </Link>
          {project.description && <p className="text-xs text-muted mt-0.5 truncate">{project.description}</p>}
        </div>
      </div>
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs text-muted">{project.task_count} {project.task_count === 1 ? 'task' : 'tasks'}</span>
        <div className="flex items-center gap-1">
          <button type="button" onClick={onEdit} className="dr-btn-ghost px-2 py-0.5 rounded text-xs">Edit</button>
          {confirming ? (
            <span className="flex items-center gap-1">
              <button type="button" onClick={handleDelete} disabled={deleting} className="px-2 py-0.5 rounded text-xs text-[color:var(--danger)] border border-[color:var(--danger)]/40 hover:bg-[color:var(--danger)]/10 disabled:opacity-50">
                {deleting ? '…' : 'Confirm'}
              </button>
              <button type="button" onClick={() => setConfirming(false)} className="dr-btn-ghost px-2 py-0.5 rounded text-xs">Cancel</button>
            </span>
          ) : (
            <button type="button" onClick={() => setConfirming(true)} className="dr-btn-ghost px-2 py-0.5 rounded text-xs text-[color:var(--danger)]">Delete</button>
          )}
        </div>
      </div>
    </div>
  )
}

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState<Project | null>(null)

  const load = useCallback(async () => {
    try { const d = await listProjects(); setProjects(d.projects) }
    catch (e) { setError(e instanceof Error ? e.message : 'Failed to load') }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])

  const handleSaved = (p: Project) => {
    setProjects(prev => {
      const idx = prev.findIndex(x => x.id === p.id)
      return idx >= 0 ? prev.map(x => x.id === p.id ? p : x) : [p, ...prev]
    })
    setShowForm(false)
    setEditing(null)
  }

  return (
    <div className="dr-history-stack">
      <header>
        <p className="eyebrow">Workspace</p>
        <h1 className="section-title dr-dashboard-hero-title">Projects</h1>
        <p className="dr-history-summary">Group related tasks into folders to keep your work organised.</p>
      </header>

      <div className="flex items-center justify-between gap-3">
        <p className="text-sm text-muted">{projects.length} {projects.length === 1 ? 'project' : 'projects'}</p>
        <button type="button" onClick={() => setShowForm(true)} className="dr-btn-accent px-3 py-1.5 rounded-lg text-sm">
          + New project
        </button>
      </div>

      {loading && <p className="text-muted text-sm">Loading…</p>}
      {error && <p className="text-[color:var(--danger)] text-sm">{error}</p>}

      {!loading && projects.length === 0 && (
        <div className="panel p-10 text-center space-y-3">
          <p className="text-2xl">📁</p>
          <p className="text-sm text-muted">No projects yet. Create one to start grouping your tasks.</p>
          <button type="button" onClick={() => setShowForm(true)} className="dr-btn-accent px-4 py-2 rounded-lg text-sm mx-auto">
            Create your first project
          </button>
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {projects.map(p => (
          <ProjectCard
            key={p.id}
            project={p}
            onEdit={() => setEditing(p)}
            onDelete={() => setProjects(prev => prev.filter(x => x.id !== p.id))}
          />
        ))}
      </div>

      {(showForm || editing) && (
        <ProjectFormModal
          initial={editing ?? undefined}
          onSave={handleSaved}
          onClose={() => { setShowForm(false); setEditing(null) }}
        />
      )}
    </div>
  )
}
