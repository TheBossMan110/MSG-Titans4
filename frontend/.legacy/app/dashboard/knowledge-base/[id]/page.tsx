'use client'
import { use, useEffect, useState } from 'react'
import Link from 'next/link'
import { ArrowLeft, CheckCircle, XCircle, RefreshCw } from 'lucide-react'
import { DashboardShell, AuthGuard, KvRow, Spinner, ErrorState } from '@/components/ui'
import { knowledge } from '@/lib/api'
import type { KnowledgeDocument, DocumentVersion } from '@/lib/api'

export default function DocumentDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params)
  return (
    <AuthGuard allowedRoles={['manager', 'admin', 'evaluator']}>
      <DocDetail id={id} />
    </AuthGuard>
  )
}

function DocDetail({ id }: { id: string }) {
  const [doc, setDoc] = useState<(KnowledgeDocument & { versions: DocumentVersion[] }) | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [acting, setActing] = useState<string | null>(null)

  const load = async () => {
    setLoading(true)
    setError(null)
    try { setDoc(await knowledge.get(id)) }
    catch (e: unknown) { setError((e as Error).message) }
    finally { setLoading(false) }
  }

  const activate = async (version_id: string) => {
    setActing(version_id)
    try { await knowledge.activate(version_id); await load() }
    catch (e: unknown) { alert((e as Error).message) }
    finally { setActing(null) }
  }

  const deactivate = async (version_id: string) => {
    setActing(version_id)
    try { await knowledge.deactivate(version_id); await load() }
    catch (e: unknown) { alert((e as Error).message) }
    finally { setActing(null) }
  }

  useEffect(() => { load() }, [id])

  return (
    <DashboardShell>
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 20 }}>
        <Link href="/dashboard/knowledge-base" className="btn btn-ghost btn-sm">
          <ArrowLeft size={14} /> Knowledge Base
        </Link>
        <button className="btn btn-ghost btn-sm" onClick={load} disabled={loading}>
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
        </button>
      </div>

      {loading ? (
        <div style={{ display: 'flex', justifyContent: 'center', padding: '80px 0' }}><Spinner size={28} /></div>
      ) : error ? (
        <ErrorState error={error} retry={load} />
      ) : !doc ? null : (
        <>
          <h1 className="page-title" style={{ marginBottom: 4 }}>{doc.title}</h1>
          <p className="page-subtitle" style={{ marginBottom: 20 }}>
            {doc.category} · {doc.file_type} · {doc.version_count} version{doc.version_count !== 1 ? 's' : ''}
          </p>

          <div style={{ display: 'grid', gridTemplateColumns: '280px 1fr', gap: 16 }}>
            {/* Meta */}
            <div className="card" style={{ padding: '18px' }}>
              <h3 style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 12 }}>
                Document Details
              </h3>
              <KvRow label="Status" value={
                <span className={`badge ${doc.status === 'ACTIVE' ? 'badge-verified' : doc.status === 'DRAFT' ? 'badge-mismatch' : 'badge-neutral'}`}>
                  {doc.status}
                </span>
              } />
              <KvRow label="Category" value={doc.category} />
              <KvRow label="File Type" value={doc.file_type} />
              <KvRow label="Active Version" value={doc.active_version ?? '—'} mono />
              <KvRow label="Created" value={new Date(doc.created_at).toLocaleString()} />
              {doc.updated_at && <KvRow label="Updated" value={new Date(doc.updated_at).toLocaleString()} />}
            </div>

            {/* Versions */}
            <div>
              <h3 style={{ fontSize: 14, fontWeight: 700, marginBottom: 12 }}>Versions</h3>
              {doc.versions.length === 0 ? (
                <p style={{ color: 'var(--text-4)', fontSize: 13 }}>No versions found.</p>
              ) : (
                doc.versions.map((v) => (
                  <div key={v.id} className={`card ${v.status === 'ACTIVE' ? 'card-verified' : ''}`} style={{ padding: '16px', marginBottom: 10 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                      <div>
                        <span style={{ fontFamily: 'DM Mono, monospace', fontWeight: 700, color: 'var(--text)', marginRight: 8 }}>{v.version_label}</span>
                        <span className={`badge ${v.status === 'ACTIVE' ? 'badge-verified' : v.status === 'DRAFT' ? 'badge-mismatch' : 'badge-neutral'}`}>{v.status}</span>
                      </div>
                      <div style={{ display: 'flex', gap: 8 }}>
                        {v.status !== 'ACTIVE' && (
                          <button
                            className="btn btn-py btn-sm"
                            onClick={() => activate(v.id)}
                            disabled={acting === v.id}
                            id={`activate-${v.id}`}
                          >
                            {acting === v.id ? <Spinner size={12} /> : <CheckCircle size={12} />}
                            Activate
                          </button>
                        )}
                        {v.status === 'ACTIVE' && (
                          <button
                            className="btn btn-ghost btn-sm"
                            onClick={() => deactivate(v.id)}
                            disabled={acting === v.id}
                            id={`deactivate-${v.id}`}
                          >
                            {acting === v.id ? <Spinner size={12} /> : <XCircle size={12} />}
                            Deactivate
                          </button>
                        )}
                        <Link href={`/dashboard/knowledge-base/version/${v.id}`} className="btn btn-ghost btn-sm">
                          View Chunks →
                        </Link>
                      </div>
                    </div>
                    <div style={{ display: 'flex', gap: 16, fontSize: 12, color: 'var(--text-3)' }}>
                      <span>{v.chunk_count} chunks</span>
                      <span>{v.section_count} sections</span>
                      <span>{new Date(v.created_at).toLocaleDateString()}</span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </>
      )}
    </DashboardShell>
  )
}
