'use client'
import { useState, useEffect } from 'react'
import Link from 'next/link'
import {
  MessageSquare, CheckCircle, AlertTriangle, TrendingUp, Clock,
  Shield, Zap, Activity, ChevronRight, RefreshCw, Users,
} from 'lucide-react'
import { DashboardShell, StatCard, AuthGuard, StatusPill, PriorityBadge, VerificationBadge, Spinner, ErrorState, ArchKey } from '@/components/ui'
import { analytics, complaints as complaintsApi, review, system } from '@/lib/api'
import type { AnalyticsDashboard, ComplaintSummary, ReviewStats, SystemHealth } from '@/lib/api'
import { useAuth } from '@/lib/auth-context'

export default function DashboardPage() {
  return (
    <AuthGuard>
      <DashboardContent />
    </AuthGuard>
  )
}

function DashboardContent() {
  const { user } = useAuth()
  const [dash, setDash] = useState<AnalyticsDashboard | null>(null)
  const [recent, setRecent] = useState<ComplaintSummary[]>([])
  const [reviewStats, setReviewStats] = useState<ReviewStats | null>(null)
  const [health, setHealth] = useState<SystemHealth | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const [d, c, h] = await Promise.all([
        analytics.dashboard().catch(() => null),
        complaintsApi.list({ per_page: 8 }).catch(() => null),
        system.health().catch(() => null),
      ])
      setDash(d)
      setRecent(c?.items ?? [])
      setHealth(h)

      // Review stats only for appropriate roles
      if (user?.role && ['reviewer', 'manager', 'admin'].includes(user.role)) {
        const rs = await review.stats().catch(() => null)
        setReviewStats(rs)
      }
    } catch (e: unknown) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  return (
    <DashboardShell>
      {/* Header */}
      <div className="page-header">
        <div>
          <h1 className="page-title">
            Welcome back, {user?.display_name ?? user?.email?.split('@')[0]}
          </h1>
          <p className="page-subtitle">
            <span style={{ textTransform: 'capitalize', color: 'var(--orange-2)', fontWeight: 600 }}>{user?.role}</span>
            {user?.department && <> · {user.department}</>}
            {' '}· {new Date().toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long' })}
          </p>
        </div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          {/* Health indicator */}
          {health && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 7, padding: '6px 14px', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--r-md)', fontSize: 12 }}>
              <span className={`dot dot-pulse ${health.status === 'OK' ? 'dot-verified' : health.status === 'DEGRADED' ? 'dot-mismatch' : 'dot-critical'}`} />
              <span style={{ color: 'var(--text-2)' }}>
                {health.status === 'OK' ? 'All Systems' : health.status}
              </span>
            </div>
          )}
          <button className="btn btn-ghost btn-sm" onClick={load} disabled={loading} title="Refresh">
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          </button>
          {user?.role === 'customer' && (
            <Link href="/dashboard/complaints/new" className="btn btn-orange btn-sm">
              <MessageSquare size={14} /> Submit Complaint
            </Link>
          )}
        </div>
      </div>

      {/* Architecture key */}
      <ArchKey />

      {loading && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '40px 0', color: 'var(--text-3)', justifyContent: 'center' }}>
          <Spinner /> Loading dashboard…
        </div>
      )}

      {error && <div style={{ marginTop: 20 }}><ErrorState error={error} retry={load} /></div>}

      {!loading && !error && (
        <>
          {/* Stats grid */}
          {dash && (
            <div className="stats-grid" style={{ marginTop: 20 }}>
              <StatCard
                label="Total Complaints"
                value={dash.total_complaints.toLocaleString()}
                icon={<MessageSquare size={18} />}
                sub={<><CheckCircle size={11} /> {dash.resolved_count} resolved</>}
              />
              <StatCard
                label="Pipeline Agreement"
                value={dash.pipeline_agreement_rate != null ? `${Math.round(dash.pipeline_agreement_rate * 100)}%` : 'Not measured'}
                accent={dash.pipeline_agreement_rate != null
                  ? (dash.pipeline_agreement_rate > 0.85 ? 'var(--verified)' : dash.pipeline_agreement_rate > 0.7 ? 'var(--mismatch)' : 'var(--critical)')
                  : undefined}
                icon={<Shield size={18} />}
                sub={<><Zap size={11} style={{ color: '#a5b4fc' }} /> AI vs Python match rate</>}
              />
              <StatCard
                label="Escalated"
                value={dash.escalated_count.toLocaleString()}
                accent={dash.escalated_count > 0 ? 'var(--critical)' : undefined}
                icon={<AlertTriangle size={18} />}
                sub={<>Requires immediate action</>}
              />
              <StatCard
                label="Avg Resolution"
                value={dash.avg_resolution_hours != null ? `${dash.avg_resolution_hours.toFixed(1)}h` : 'Not measured'}
                icon={<Clock size={18} />}
                sub={<>Across all resolved cases</>}
              />
              {reviewStats && (
                <StatCard
                  label="Review Queue"
                  value={reviewStats.queue_depth.toLocaleString()}
                  accent={reviewStats.queue_depth > 5 ? 'var(--mismatch)' : undefined}
                  icon={<Users size={18} />}
                  sub={<>Override rate: {reviewStats.override_rate != null ? `${Math.round(reviewStats.override_rate * 100)}%` : 'Not measured'}</>}
                />
              )}
            </div>
          )}

          {/* By Priority + By Status */}
          {dash && (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 20 }}>
              {/* By Priority */}
              <div className="card" style={{ padding: '20px' }}>
                <h3 style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 14 }}>
                  By Priority
                </h3>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {(['P0', 'P1', 'P2', 'P3'] as const).map((p) => {
                    const count = dash.by_priority[p] ?? 0
                    const max = Math.max(...Object.values(dash.by_priority), 1)
                    const colors: Record<string, string> = { P0: 'var(--critical)', P1: 'var(--mismatch)', P2: 'var(--ai)', P3: 'var(--text-3)' }
                    return (
                      <div key={p} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <PriorityBadge priority={p} />
                        <div style={{ flex: 1, height: 6, background: 'var(--surface-3)', borderRadius: 99 }}>
                          <div style={{ width: `${(count / max) * 100}%`, height: '100%', background: colors[p], borderRadius: 99, transition: 'width 0.8s ease' }} />
                        </div>
                        <span style={{ fontSize: 12, fontFamily: 'DM Mono, monospace', color: 'var(--text-2)', minWidth: 28, textAlign: 'right' }}>{count}</span>
                      </div>
                    )
                  })}
                </div>
              </div>

              {/* System health */}
              {health && (
                <div className="card" style={{ padding: '20px' }}>
                  <h3 style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 14 }}>
                    System Health
                  </h3>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                    {[
                      { label: 'Database', status: health.database, color: health.database === 'OK' ? 'var(--verified)' : 'var(--critical)' },
                      { label: 'AI Provider', status: health.genai_provider, color: health.genai_provider === 'OK' ? 'var(--ai)' : health.genai_provider === 'UNAVAILABLE' ? 'var(--mismatch)' : 'var(--critical)' },
                      { label: 'Rule Engine', status: health.rule_engine, color: health.rule_engine === 'OK' ? 'var(--py)' : 'var(--critical)' },
                    ].map((s) => (
                      <div key={s.label} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 12px', background: 'var(--surface-2)', borderRadius: 'var(--r-sm)' }}>
                        <span style={{ fontSize: 13, color: 'var(--text-2)' }}>{s.label}</span>
                        <span style={{ fontSize: 11, fontWeight: 700, color: s.color, display: 'flex', alignItems: 'center', gap: 5 }}>
                          <span style={{ width: 7, height: 7, borderRadius: '50%', background: s.color }} />
                          {s.status}
                        </span>
                      </div>
                    ))}
                    {health.degraded_reason && (
                      <p style={{ fontSize: 12, color: 'var(--mismatch)', marginTop: 6 }}>{health.degraded_reason}</p>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Recent complaints */}
          <div className="table-wrap">
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '16px 16px 0' }}>
              <h3 style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                Recent Complaints
              </h3>
              <Link href="/dashboard/complaints" className="btn btn-ghost btn-sm">
                View all <ChevronRight size={12} />
              </Link>
            </div>
            <table className="table" style={{ marginTop: 8 }}>
              <thead>
                <tr>
                  <th>Ref</th>
                  <th>Title</th>
                  <th>Status</th>
                  <th>Priority</th>
                  <th>Verification</th>
                  <th>Updated</th>
                </tr>
              </thead>
              <tbody>
                {recent.length === 0 ? (
                  <tr>
                    <td colSpan={6} style={{ textAlign: 'center', padding: '40px', color: 'var(--text-4)' }}>
                      No complaints found
                    </td>
                  </tr>
                ) : (
                  recent.map((c) => (
                    <tr key={c.id} onClick={() => window.location.href = `/dashboard/complaints/${c.ref}`}>
                      <td>
                        <span style={{ fontFamily: 'DM Mono, monospace', fontSize: 12, color: 'var(--orange-2)' }}>
                          {c.public_ref ?? c.ref}
                        </span>
                      </td>
                      <td style={{ maxWidth: 240 }}>
                        <span style={{ fontWeight: 500, fontSize: 13, overflow: 'hidden', display: '-webkit-box', WebkitLineClamp: 1, WebkitBoxOrient: 'vertical' }}>
                          {c.title}
                        </span>
                        {c.category && <span style={{ fontSize: 11, color: 'var(--text-4)', display: 'block' }}>{c.category}</span>}
                      </td>
                      <td><StatusPill status={c.status} /></td>
                      <td><PriorityBadge priority={c.priority} /></td>
                      <td><VerificationBadge outcome={c.verification_outcome} /></td>
                      <td style={{ fontSize: 12, color: 'var(--text-3)', fontFamily: 'DM Mono, monospace' }}>
                        {new Date(c.updated_at).toLocaleDateString()}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Quick links */}
          <div style={{ display: 'flex', gap: 10, marginTop: 20, flexWrap: 'wrap' }}>
            {[
              { href: '/dashboard/complaints', label: 'All Complaints', icon: <MessageSquare size={14} /> },
              { href: '/dashboard/analytics', label: 'Analytics', icon: <TrendingUp size={14} />, roles: ['manager', 'admin', 'evaluator'] },
              { href: '/dashboard/review', label: 'Review Queue', icon: <Activity size={14} />, roles: ['reviewer', 'manager', 'admin'] },
              { href: '/dashboard/knowledge-base', label: 'Knowledge Base', icon: <Shield size={14} />, roles: ['manager', 'admin', 'evaluator'] },
              { href: '/dashboard/benchmark', label: 'Benchmark', icon: <Zap size={14} />, roles: ['admin', 'evaluator'] },
            ].filter((l) => !l.roles || (user?.role && l.roles.includes(user.role))).map((l) => (
              <Link key={l.href} href={l.href} className="btn btn-ghost btn-sm">
                {l.icon} {l.label}
              </Link>
            ))}
          </div>
        </>
      )}
    </DashboardShell>
  )
}
