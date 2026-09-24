'use client'
import { use, useEffect, useState } from 'react'
import Link from 'next/link'
import { ArrowLeft, AlertTriangle } from 'lucide-react'
import { DashboardShell, AuthGuard, PercentBar, Spinner, ErrorState, KvRow } from '@/components/ui'
import { benchmark } from '@/lib/api'
import type { BenchmarkRunDetail } from '@/lib/api'

export default function BenchmarkRunPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params)
  return (
    <AuthGuard allowedRoles={['admin', 'evaluator']}>
      <RunDetail id={id} />
    </AuthGuard>
  )
}

function RunDetail({ id }: { id: string }) {
  const [run, setRun] = useState<BenchmarkRunDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    benchmark.runDetail(id)
      .then(setRun)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [id])

  if (loading) return (
    <DashboardShell>
      <div style={{ display: 'flex', justifyContent: 'center', padding: '80px 0' }}><Spinner size={28} /></div>
    </DashboardShell>
  )

  if (error) return (
    <DashboardShell>
      <Link href="/dashboard/benchmark" className="btn btn-ghost btn-sm" style={{ marginBottom: 16 }}>
        <ArrowLeft size={14} /> Benchmark
      </Link>
      <ErrorState error={error} />
    </DashboardShell>
  )

  if (!run) return null

  return (
    <DashboardShell>
      <Link href="/dashboard/benchmark" className="btn btn-ghost btn-sm" style={{ marginBottom: 16 }}>
        <ArrowLeft size={14} /> Benchmark
      </Link>

      <h1 className="page-title" style={{ marginBottom: 4 }}>Run: {run.dataset_tag}</h1>
      <p className="page-subtitle" style={{ marginBottom: 20 }}>{new Date(run.started_at).toLocaleString()}</p>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 20 }}>
        <div className="card" style={{ padding: '20px' }}>
          <h3 style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 12 }}>
            Summary
          </h3>
          <KvRow label="Status" value={
            <span className={`badge ${run.status === 'COMPLETED' ? 'badge-verified' : run.status === 'FAILED' ? 'badge-critical' : 'badge-mismatch'}`}>
              {run.status}
            </span>
          } />
          <KvRow label="Dataset" value={run.dataset_tag} mono />
          <KvRow label="Started" value={new Date(run.started_at).toLocaleString()} />
          {run.completed_at && <KvRow label="Completed" value={new Date(run.completed_at).toLocaleString()} />}
          <KvRow label="Overall Accuracy" value={
            run.overall_accuracy != null
              ? <span style={{ color: run.overall_accuracy > 0.85 ? 'var(--verified)' : 'var(--mismatch)', fontWeight: 700 }}>
                  {(run.overall_accuracy * 100).toFixed(2)}%
                </span>
              : 'Not measured'
          } />
          <KvRow label="Guard Compliance" value={
            run.guard_compliance != null ? `${(run.guard_compliance * 100).toFixed(2)}%` : 'Not measured'
          } />
        </div>

        <div className="card" style={{ padding: '20px' }}>
          <h3 style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 12 }}>
            Accuracy by Field
          </h3>
          {run.per_field.length === 0 ? (
            <p style={{ fontSize: 13, color: 'var(--text-4)' }}>No per-field data available</p>
          ) : (
            run.per_field.map((f) => (
              <div key={f.field} style={{ marginBottom: 10 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12.5, marginBottom: 4 }}>
                  <span style={{ color: 'var(--text-2)', textTransform: 'capitalize' }}>{f.field}</span>
                  <span style={{ color: 'var(--text-3)', fontFamily: 'DM Mono, monospace' }}>
                    {f.accuracy != null ? `${(f.accuracy * 100).toFixed(1)}%` : 'Not measured'}
                  </span>
                </div>
                <PercentBar
                  value={f.accuracy != null ? Math.round(f.accuracy * 100) : null}
                  color={f.accuracy != null
                    ? (f.accuracy > 0.85 ? 'var(--verified)' : f.accuracy > 0.7 ? 'var(--mismatch)' : 'var(--critical)')
                    : 'var(--text-4)'}
                />
              </div>
            ))
          )}
        </div>
      </div>

      {/* Failures */}
      {run.failures.length > 0 && (
        <div className="card card-mismatch" style={{ padding: '20px' }}>
          <h3 style={{ fontSize: 14, fontWeight: 700, marginBottom: 14, display: 'flex', alignItems: 'center', gap: 8 }}>
            <AlertTriangle size={14} color="var(--mismatch)" />
            Failures ({run.failures.length})
          </h3>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Ref</th>
                  <th>Field</th>
                  <th>Expected</th>
                  <th>Got</th>
                  <th>Description</th>
                </tr>
              </thead>
              <tbody>
                {run.failures.map((f, i) => (
                  <tr key={i}>
                    <td>
                      <Link href={`/dashboard/complaints/${f.ref}`} style={{ color: 'var(--orange-2)', fontFamily: 'DM Mono, monospace', fontSize: 12 }}>
                        {f.ref}
                      </Link>
                    </td>
                    <td style={{ fontSize: 12, textTransform: 'capitalize' }}>{f.field}</td>
                    <td style={{ fontSize: 12, fontFamily: 'DM Mono, monospace', color: 'var(--verified)' }}>{f.expected}</td>
                    <td style={{ fontSize: 12, fontFamily: 'DM Mono, monospace', color: 'var(--critical)' }}>{f.got}</td>
                    <td style={{ fontSize: 12, color: 'var(--text-3)', maxWidth: 200 }}>{f.description ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </DashboardShell>
  )
}
