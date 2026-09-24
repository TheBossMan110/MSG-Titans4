'use client'
import { useState, useEffect } from 'react'
import Link from 'next/link'
import { RefreshCw, AlertTriangle, CheckCircle, Shield, Zap } from 'lucide-react'
import {
  DashboardShell, AuthGuard, StatCard, PercentBar, TwoEnginePanel,
  VerificationBadge, PriorityBadge, Spinner, ErrorState, Empty,
} from '@/components/ui'
import { analytics, complaints as complaintsApi } from '@/lib/api'
import type { PipelineData, ComplaintSummary } from '@/lib/api'

export default function ValidationPage() {
  return (
    <AuthGuard allowedRoles={['reviewer', 'manager', 'admin', 'evaluator']}>
      <ValidationContent />
    </AuthGuard>
  )
}

function ValidationContent() {
  const [pipeline, setPipeline] = useState<PipelineData | null>(null)
  const [mismatches, setMismatches] = useState<ComplaintSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const [p, m] = await Promise.all([
        analytics.pipelines(),
        complaintsApi.list({ verification_outcome: 'MISMATCH', per_page: 20 }),
      ])
      setPipeline(p)
      setMismatches(m.items)
    } catch (e: unknown) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  return (
    <DashboardShell>
      <div className="page-header">
        <div>
          <h1 className="page-title">Validation</h1>
          <p className="page-subtitle">AI Engine vs Python Ground-Truth comparison and mismatch tracking</p>
        </div>
        <button className="btn btn-ghost btn-sm" onClick={load} disabled={loading}>
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
        </button>
      </div>

      {/* Legend */}
      <div style={{ display: 'flex', gap: 16, marginBottom: 20, flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 14px', background: 'var(--ai-dim)', border: '1px solid var(--ai-border)', borderRadius: 'var(--r-md)', fontSize: 13 }}>
          <Zap size={14} color="#a5b4fc" /> <span style={{ color: '#a5b4fc', fontWeight: 600 }}>AI Engine</span> — Indigo
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 14px', background: 'var(--py-dim)', border: '1px solid var(--py-border)', borderRadius: 'var(--r-md)', fontSize: 13 }}>
          <Shield size={14} color="#67e8f9" /> <span style={{ color: '#67e8f9', fontWeight: 600 }}>Python Verifier</span> — Cyan
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 14px', background: 'var(--verified-dim)', border: '1px solid var(--verified-border)', borderRadius: 'var(--r-md)', fontSize: 13 }}>
          <CheckCircle size={14} color="var(--verified)" /> Agreement
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 14px', background: 'var(--mismatch-dim)', border: '1px solid var(--mismatch-border)', borderRadius: 'var(--r-md)', fontSize: 13 }}>
          <AlertTriangle size={14} color="var(--mismatch)" /> Mismatch → Review Queue
        </div>
      </div>

      {error && <ErrorState error={error} retry={load} />}

      {loading ? (
        <div style={{ display: 'flex', justifyContent: 'center', padding: '60px 0' }}><Spinner size={28} /></div>
      ) : (
        <>
          {/* Pipeline stats */}
          {pipeline && (
            <>
              <div className="stats-grid" style={{ marginBottom: 20 }}>
                <StatCard
                  label="Overall Agreement"
                  value={pipeline.agreement_rate != null ? `${Math.round(pipeline.agreement_rate * 100)}%` : 'Not measured'}
                  accent={pipeline.agreement_rate != null ? (pipeline.agreement_rate > 0.85 ? 'var(--verified)' : pipeline.agreement_rate > 0.7 ? 'var(--mismatch)' : 'var(--critical)') : undefined}
                  sub={`${pipeline.agreement_count} agreed / ${pipeline.total} total`}
                />
                <StatCard
                  label="Mismatches"
                  value={pipeline.mismatch_count.toLocaleString()}
                  accent={pipeline.mismatch_count > 0 ? 'var(--mismatch)' : undefined}
                  sub="Routed to human review"
                />
                <StatCard
                  label="Total Processed"
                  value={pipeline.total.toLocaleString()}
                  sub="Through dual pipeline"
                />
              </div>

              {/* Per-field agreement */}
              <div className="card" style={{ padding: '20px', marginBottom: 20 }}>
                <h3 style={{ fontSize: 14, fontWeight: 700, marginBottom: 14 }}>Agreement by Field</h3>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 14 }}>
                  {pipeline.by_field.map((f) => (
                    <div key={f.field}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12.5, marginBottom: 6 }}>
                        <span style={{ color: 'var(--text-2)', fontWeight: 600, textTransform: 'capitalize' }}>{f.field}</span>
                        <span style={{ color: 'var(--text-3)', fontFamily: 'DM Mono, monospace' }}>
                          {f.agreement_rate != null ? `${Math.round(f.agreement_rate * 100)}%` : 'Not measured'}
                        </span>
                      </div>
                      <PercentBar
                        value={f.agreement_rate != null ? Math.round(f.agreement_rate * 100) : null}
                        color={f.agreement_rate != null
                          ? (f.agreement_rate > 0.85 ? 'var(--verified)' : f.agreement_rate > 0.7 ? 'var(--mismatch)' : 'var(--critical)')
                          : 'var(--text-4)'
                        }
                      />
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}

          {/* Mismatch list */}
          <div>
            <h3 style={{ fontSize: 14, fontWeight: 700, marginBottom: 12 }}>
              Recent Mismatches ({mismatches.length})
            </h3>
            {mismatches.length === 0 ? (
              <div className="table-wrap">
                <Empty
                  icon={<CheckCircle size={40} />}
                  title="No mismatches"
                  body="All processed complaints have verified agreement between AI and Python engines."
                />
              </div>
            ) : (
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Ref</th>
                      <th>Title</th>
                      <th>Priority</th>
                      <th>Verification</th>
                      <th>Category</th>
                      <th>Updated</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {mismatches.map((c) => (
                      <tr key={c.id}>
                        <td>
                          <span style={{ fontFamily: 'DM Mono, monospace', fontSize: 12, color: 'var(--orange-2)' }}>
                            {c.public_ref ?? c.ref}
                          </span>
                        </td>
                        <td style={{ maxWidth: 220, fontSize: 13 }}>{c.title}</td>
                        <td><PriorityBadge priority={c.priority} /></td>
                        <td><VerificationBadge outcome={c.verification_outcome} /></td>
                        <td style={{ fontSize: 12, color: 'var(--text-3)' }}>{c.category ?? '—'}</td>
                        <td style={{ fontSize: 12, color: 'var(--text-3)', fontFamily: 'DM Mono, monospace' }}>
                          {new Date(c.updated_at).toLocaleDateString()}
                        </td>
                        <td>
                          <Link href={`/dashboard/complaints/${c.ref}`} className="btn btn-ghost btn-sm">
                            View →
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}
    </DashboardShell>
  )
}
