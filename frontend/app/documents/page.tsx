'use client'

import { useEffect, useRef, useState, useCallback } from 'react'
import PageHeader from '@/components/PageHeader'
import { getDocuments, uploadDocument, deleteDocument } from '@/lib/api'

type Doc = {
  id: string
  filename: string
  file_type: string
  file_size: number
  chunk_count: number
  created_at: string
}

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export default function DocumentsPage() {
  const [docs, setDocs] = useState<Doc[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadMsg, setUploadMsg] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await getDocuments()
      setDocs(data.documents)
      setTotal(data.total)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load documents')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    setUploadMsg(null)
    setError(null)
    try {
      const result = await uploadDocument(file)
      setUploadMsg(`Ingested "${result.filename}" — ${result.chunk_count} chunks`)
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Upload failed')
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  async function handleDelete(id: string, filename: string) {
    if (!confirm(`Delete "${filename}"? This cannot be undone.`)) return
    try {
      await deleteDocument(id)
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Delete failed')
    }
  }

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <PageHeader
        eyebrow="Knowledge base"
        title="Documents"
        description="Upload PDFs, DOCX, or text files. The agent searches them automatically when answering questions."
      />

      {/* Upload area */}
      <div className="panel rounded-xl border-dashed p-6 text-center space-y-3">
        <p className="text-muted text-sm">PDF, DOCX, TXT, MD — up to 20 MB</p>
        <label className="inline-block cursor-pointer">
          <input
            ref={fileRef}
            type="file"
            accept=".pdf,.docx,.txt,.md,.rst,.csv,.json,.yaml,.yml"
            className="hidden"
            onChange={handleUpload}
            disabled={uploading}
          />
          <span className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
            uploading
              ? 'bg-[color:var(--surface-soft)] text-muted cursor-not-allowed border border-[color:var(--border)]'
              : 'btn-accent cursor-pointer'
          }`}>
            {uploading ? 'Ingesting…' : 'Choose file to upload'}
          </span>
        </label>
        {uploadMsg && <p className="text-[color:var(--success)] text-sm">{uploadMsg}</p>}
        {error && <p className="text-[color:var(--danger)] text-sm">{error}</p>}
      </div>

      {/* Document list */}
      <div className="space-y-2">
        <div className="flex items-center justify-between text-xs text-muted px-1">
          <span>{total} document{total !== 1 ? 's' : ''}</span>
          <button onClick={load} className="hover:text-[color:var(--text)] transition-colors">Refresh</button>
        </div>

        {loading ? (
          <p className="text-muted text-sm py-4 text-center">Loading…</p>
        ) : docs.length === 0 ? (
          <p className="text-muted text-sm py-4 text-center">No documents yet. Upload one above.</p>
        ) : (
          docs.map(doc => (
            <div key={doc.id} className="panel flex items-center gap-3 rounded-lg px-4 py-3">
              <span className="text-xs bg-[color:var(--surface-soft)] text-muted rounded px-2 py-0.5 uppercase font-mono border border-[color:var(--border)]">
                {doc.file_type}
              </span>
              <div className="flex-1 min-w-0">
                <p className="text-sm truncate">{doc.filename}</p>
                <p className="text-xs text-muted">
                  {doc.chunk_count} chunks · {formatBytes(doc.file_size)} · {new Date(doc.created_at).toLocaleDateString()}
                </p>
              </div>
              <button
                onClick={() => handleDelete(doc.id, doc.filename)}
                className="text-xs text-muted hover:text-[color:var(--danger)] transition-colors shrink-0"
              >
                Delete
              </button>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
