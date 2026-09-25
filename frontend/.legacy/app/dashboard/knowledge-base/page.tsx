'use client'
import { useState, useEffect } from 'react'
import Link from 'next/link'
import { RefreshCw, Search, Upload, ExternalLink, CheckCircle, XCircle, AlertTriangle } from 'lucide-react'
import {
  DashboardShell, AuthGuard, StatCard, Spinner, ErrorState, Empty, DropZone,
} from '@/components/ui'
import { knowledge } from '@/lib/api'
import type { KnowledgeDocument, DocumentCoverage, SearchResult, ValidationIssue } from '@/lib/api'

type ViewMode = 'documents' | 'search' | 'upload'

export default function KnowledgeBasePage() {
  return (
    <AuthGuard allowedRoles={['manager', 'admin', 'evaluator']}>
      <KBContent />
    </AuthGuard>
  )
}

function KBContent() {
  const [docs, setDocs] = useState<KnowledgeDocument[]>([])
  const [coverage, setCoverage] = useState<DocumentCoverage | null>(null)
  const [issues, setIssues] = useState<ValidationIssue[]>([])
  const [searchResults, setSearchResults] = useState<SearchResult[]>([])
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const [searching, setSearching] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [view, setView] = useState<ViewMode>('documents')
  const [uploadResults, setUploadResults] = useState<{ filename: string; success: boolean; error?: string }[]>([])

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const [d, c, i] = await Promise.all([
        knowledge.list(),
        knowledge.coverage(),
        knowledge.validationIssues(),
      ])
      setDocs(d)
      setCoverage(c)
      setIssues(i)
    } catch (e: unknown) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  const search = async () => {
    if (!query.trim()) return
    setSearching(true)
    try {
      const results = await knowledge.search(query.trim())
      setSearchResults(results)
    } catch (e: unknown) {
      setError((e as Error).message)
    } finally {
      setSearching(false)
    }
  }

  const handleFiles = async (files: File[]) => {
    setUploading(true)
    try {
      const res = await knowledge.upload(files)
      setUploadResults(res.results)
      // Reload docs
      await load()
    } catch (e: unknown) {
      setError((e as Error).message)
    } finally {
      setUploading(false)
    }
  }

  useEffect(() => { load() }, [])

  return (
    <DashboardShell>
      <div className="page-header">
        <div>
          <h1 className="page-title">Knowledge Base</h1>
          <p className="page-subtitle">Manage documents that inform the AI pipeline's understanding</p>
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          {(['documents', 'search', 'upload'] as ViewMode[]).map((v) => (
            <button
              key={v}
              className={`btn ${view === v ? 'btn-orange' : 'btn-ghost'} btn-sm`}
              onClick={() => setView(v)}
              id={`kb-tab-${v}`}
            >
              {v.charAt(0).toUpperCase() + v.slice(1)}
            </button>
          ))}
          <button className="btn btn-ghost btn-sm" onClick={load} disabled={loading}>
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {coverage && (
        <div className="stats-grid" style={{ marginBottom: 20 }}>
          <StatCard label="Total Documents" value={coverage.total_documents} icon={<ExternalLink size={18} />} />
          <StatCard label="Active Documents" value={coverage.active_documents} accent="var(--verified)" />
          <StatCard label="Total Chunks" value={coverage.total_chunks.toLocaleString()} sub="Indexed text blocks" />
          <StatCard
            label="Validation Issues"
            value={issues.filter((i) => i.severity === 'ERROR').length}
            accent={issues.some((i) => i.severity === 'ERROR') ? 'var(--critical)' : undefined}
            sub={`${issues.filter((i) => i.severity === 'WARNING').length} warnings`}
          />
        </div>
      )}

      {error && <ErrorState error={error} retry={load} />}

      {/* Documents view */}
      {view === 'documents' && (
        loading ? (
          <div style={{ display: 'flex', justifyContent: 'center', padding: '60px 0' }}><Spinner size={28} /></div>
        ) : docs.length === 0 ? (
          <div className="table-wrap"><Empty title="No documents" body="Upload documents to populate the knowledge base." action={{ label: 'Upload Documents', onClick: () => setView('upload') }} /></div>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Title</th>
                  <th>Category</th>
                  <th>Status</th>
                  <th>Versions</th>
                  <th>Active Version</th>
                  <th>Updated</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {docs.map((doc) => (
                  <tr key={doc.id}>
                    <td>
                      <span style={{ fontWeight: 600, fontSize: 13 }}>{doc.title}</span>
                      {doc.file_type && <span style={{ fontSize: 11, color: 'var(--text-4)', marginLeft: 8 }}>.{doc.file_type}</span>}
                    </td>
                    <td style={{ fontSize: 12, color: 'var(--text-3)' }}>{doc.category ?? '—'}</td>
                    <td>
                      <span className={`badge ${doc.status === 'ACTIVE' ? 'badge-verified' : doc.status === 'DRAFT' ? 'badge-mismatch' : 'badge-neutral'}`}>
                        {doc.status}
                      </span>
                    </td>
                    <td style={{ fontSize: 12, fontFamily: 'DM Mono, monospace' }}>{doc.version_count}</td>
                    <td style={{ fontSize: 12, color: 'var(--text-3)' }}>{doc.active_version ?? '—'}</td>
                    <td style={{ fontSize: 12, color: 'var(--text-3)', fontFamily: 'DM Mono, monospace' }}>
                      {doc.updated_at ? new Date(doc.updated_at).toLocaleDateString() : '—'}
                    </td>
                    <td>
                      <Link href={`/dashboard/knowledge-base/${doc.id}`} className="btn btn-ghost btn-sm">View →</Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}

      {/* Search view */}
      {view === 'search' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div className="card" style={{ padding: '20px' }}>
            <div style={{ display: 'flex', gap: 10 }}>
              <input
                id="kb-search-input"
                className="input"
                placeholder="Search knowledge base…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && search()}
                style={{ flex: 1 }}
              />
              <button className="btn btn-orange" onClick={search} disabled={searching || !query.trim()}>
                {searching ? <Spinner size={14} color="#fff" /> : <Search size={14} />}
                Search
              </button>
            </div>
          </div>

          {searchResults.length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {searchResults.map((r) => (
                <div key={r.chunk_key} className="card" style={{ padding: '18px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                    <div>
                      <span style={{ fontWeight: 700, fontSize: 14 }}>{r.document_title}</span>
                      {r.section_heading && <span style={{ fontSize: 12, color: 'var(--text-3)', marginLeft: 10 }}>§ {r.section_heading}</span>}
                    </div>
                    <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                      <span className={`badge ${r.version_status === 'ACTIVE' ? 'badge-verified' : 'badge-neutral'}`}>{r.version_status}</span>
                      {r.score != null && (
                        <span style={{ fontSize: 11, color: 'var(--text-4)', fontFamily: 'DM Mono, monospace' }}>
                          score: {r.score.toFixed(3)}
                        </span>
                      )}
                    </div>
                  </div>
                  <p style={{ fontSize: 13, color: 'var(--text-2)', lineHeight: 1.6 }}>{r.content_snippet}</p>
                  <div style={{ marginTop: 10, display: 'flex', gap: 8 }}>
                    <span style={{ fontSize: 11, color: 'var(--text-4)', fontFamily: 'DM Mono, monospace' }}>
                      {r.version_label} · {r.chunk_key}
                    </span>
                    <Link
                      href={`/dashboard/knowledge-base/trace/${encodeURIComponent(r.chunk_key)}`}
                      className="btn btn-ghost btn-sm"
                      style={{ fontSize: 11 }}
                    >
                      <ExternalLink size={10} /> Trace Source
                    </Link>
                  </div>
                </div>
              ))}
            </div>
          )}

          {!searching && searchResults.length === 0 && query && (
            <Empty title="No results" body={`No matches for "${query}"`} />
          )}
        </div>
      )}

      {/* Upload view */}
      {view === 'upload' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16, maxWidth: 600 }}>
          <div className="card" style={{ padding: '24px' }}>
            <h3 style={{ fontSize: 15, fontWeight: 700, marginBottom: 12 }}>Upload Documents</h3>
            <DropZone
              onFiles={handleFiles}
              accept=".pdf,.txt,.md,.docx"
              label="Drop PDF, TXT, Markdown or DOCX files here"
            />
            {uploading && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 16, color: 'var(--text-3)', justifyContent: 'center' }}>
                <Spinner /> Uploading…
              </div>
            )}
          </div>

          {uploadResults.length > 0 && (
            <div className="card" style={{ padding: '20px' }}>
              <h3 style={{ fontSize: 14, fontWeight: 700, marginBottom: 12 }}>Upload Results</h3>
              {uploadResults.map((r) => (
                <div key={r.filename} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 0', borderBottom: '1px solid var(--border)' }}>
                  <span style={{ fontSize: 13 }}>{r.filename}</span>
                  {r.success ? (
                    <span className="badge badge-verified"><CheckCircle size={10} /> Uploaded</span>
                  ) : (
                    <span className="badge badge-critical"><XCircle size={10} /> {r.error ?? 'Failed'}</span>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Validation issues */}
      {issues.length > 0 && view === 'documents' && (
        <div className="card" style={{ padding: '20px', marginTop: 16 }}>
          <h3 style={{ fontSize: 14, fontWeight: 700, marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
            <AlertTriangle size={14} color="var(--mismatch)" />
            Validation Issues ({issues.length})
          </h3>
          {issues.slice(0, 5).map((issue, i) => (
            <div key={i} style={{ padding: '8px 0', borderBottom: '1px solid var(--border)', display: 'flex', gap: 10, alignItems: 'flex-start' }}>
              <span className={`badge ${issue.severity === 'ERROR' ? 'badge-critical' : issue.severity === 'WARNING' ? 'badge-mismatch' : 'badge-neutral'}`}>{issue.severity}</span>
              <div>
                <p style={{ fontSize: 13, color: 'var(--text-2)' }}>{issue.description}</p>
                <p style={{ fontSize: 11, color: 'var(--text-4)', marginTop: 2 }}>
                  {issue.issue_type} · doc: {issue.document_id.slice(0, 8)}…
                </p>
              </div>
            </div>
          ))}
        </div>
      )}
    </DashboardShell>
  )
}
