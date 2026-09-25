'use client'
import { useState, useEffect } from 'react'
import Link from 'next/link'
import { RefreshCw, Eye, CheckCircle, XCircle, AlertTriangle } from 'lucide-react'
import {
  DashboardShell, AuthGuard, StatCard, StatusPill, PriorityBadge,
  Spinner, ErrorState, Empty,
} from '@/components/ui'
import { review } from '@/lib/api'
import type { ReviewQueueItem, ReviewStats } from '@/lib/api'

export default function ReviewQueuePage() {
  return (
    <AuthGuard allowedRoles={['reviewer', 'manager', 'admin']}>
      <ReviewContent />
    </AuthGuard>
  )
}

function ReviewContent() {
  const [queue, setQueue] = useState<ReviewQueueItem[]>([])
  const [stats, setStats] = useState<ReviewStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [claiming, setClaiming] = useState<string | null>(null)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const [q, s] = await Promise.all([review.queue(), review.stats()])
      setQueue(q)
      setStats(s)
    } catch (e: unknown) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const claim = async (ref: string) => {
    setClaiming(ref)
    try {
      await review.claim(ref)
      // Navigate to complaint detail
      window.location.href = `/dashboard/complaints/${ref}`
    } catch (e: unknown) {
      alert((e as Error).message)
    } finally {
      setClaiming(null)
    }
  }

  const REASON_LABELS: Record<string, { label: string; color: string }> = {
    GENAI_UNAVAILABLE: { label: 'AI Unavailable', color: 'var(--ai)' },
    GENAI_PYTHON_DISAGREEMENT: { label: 'Engine Disagreement', color: 'var(--mismatch)' },
    MANUAL_FLAG: { label: 'Manual Flag', color: 'var(--orange-2)' },
  }

  return (
    <DashboardShell>
      <div className="page-header">
        <div>
          <h1 className="page-title">Review Queue</h1>
          <p className="page-subtitle">Complaints requiring human reviewer attention</p>
        </div>
        <button className="btn btn-ghost btn-sm" onClick={load} disabled={loading}>
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
        </button>
      </div>

      {stats && (
        <div className="stats-grid" style={{ marginBottom: 20 }}>
          <StatCard
            label="Queue Depth"
            value={stats.queue_depth}
            accent={stats.queue_depth > 10 ? 'var(--critical)' : stats.queue_depth > 5 ? 'var(--mismatch)' : undefined}
            sub="Awaiting review"
          />
          <StatCard
            label="Override Rate"
            value={stats.override_rate != null ? `${Math.round(stats.override_rate * 100)}%` : 'Not measured'}
            sub="AI decisions overridden"
          />
          <StatCard
            label="Avg Review Time"
            value={stats.avg_review_time_minutes != null ? `${stats.avg_review_time_minutes.toFixed(0)}m` : 'Not measured'}
            sub="Per complaint"
          />
        </div>
      )}

      {error && <ErrorState error={error} retry={load} />}

      {loading ? (
        <div style={{ display: 'flex', justifyContent: 'center', padding: '60px 0' }}>
          <Spinner size={28} />
        </div>
      ) : queue.length === 0 ? (
        <div className="table-wrap">
          <Empty
            icon={<CheckCircle size={40} />}
            title="Review queue is empty"
            body="All complaints have been reviewed or are within acceptable confidence bounds."
          />
        </div>
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Ref</th>
                <th>Title</th>
                <th>Reason</th>
                <th>Priority</th>
                <th>Status</th>
                <th>In Queue Since</th>
                <th>Claimed By</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {queue.map((item) => {
                const reason = REASON_LABELS[item.reason] ?? { label: item.reason, color: 'var(--text-3)' }
                return (
                  <tr key={item.ref}>
                    <td>
                      <span style={{ fontFamily: 'DM Mono, monospace', fontSize: 12, color: 'var(--orange-2)' }}>
                        {item.complaint?.public_ref ?? item.ref}
                      </span>
                    </td>
                    <td style={{ maxWidth: 220 }}>
                      <span style={{ fontWeight: 500, fontSize: 13 }}>{item.title}</span>
                    </td>
                    <td>
                      <span className="badge badge-mismatch" style={{ color: reason.color, borderColor: reason.color + '44' }}>
                        {item.reason === 'GENAI_PYTHON_DISAGREEMENT' && <AlertTriangle size={10} />}
                        {reason.label}
                      </span>
                    </td>
                    <td><PriorityBadge priority={item.priority} /></td>
                    <td><StatusPill status={item.complaint?.status ?? 'IN_REVIEW'} /></td>
                    <td style={{ fontSize: 12, color: 'var(--text-3)', fontFamily: 'DM Mono, monospace' }}>
                      {new Date(item.queued_at).toLocaleDateString()}
                    </td>
                    <td style={{ fontSize: 12, color: 'var(--text-3)' }}>
                      {item.claimed_by ?? <span style={{ color: 'var(--text-4)' }}>Unclaimed</span>}
                    </td>
                    <td>
                      <button
                        className="btn btn-orange btn-sm"
                        onClick={() => claim(item.ref)}
                        disabled={!!item.claimed_by || claiming === item.ref}
                        id={`claim-${item.ref}`}
                      >
                        {claiming === item.ref ? <Spinner size={12} color="#fff" /> : <Eye size={12} />}
                        {item.claimed_by ? 'Claimed' : 'Claim & Review'}
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </DashboardShell>
  )
}
