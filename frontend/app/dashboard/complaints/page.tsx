'use client'
import { useState, useEffect, useCallback } from 'react'
import Link from 'next/link'
import { MessageSquare, Plus, Filter, RefreshCw } from 'lucide-react'
import { DashboardShell, AuthGuard, StatusPill, PriorityBadge, VerificationBadge, SearchBar, FilterSelect, Pagination, SkeletonRows, ErrorState, Empty } from '@/components/ui'
import { complaints as complaintsApi } from '@/lib/api'
import type { ComplaintSummary, Paginated } from '@/lib/api'
import { useAuth } from '@/lib/auth-context'

const STATUS_OPTIONS = [
  { value: '', label: 'All Status' },
  { value: 'SUBMITTED', label: 'Submitted' },
  { value: 'ANALYZING', label: 'Analyzing' },
  { value: 'ANALYZED', label: 'Analyzed' },
  { value: 'ASSIGNED', label: 'Assigned' },
  { value: 'IN_PROGRESS', label: 'In Progress' },
  { value: 'AWAITING_CUSTOMER', label: 'Awaiting Customer' },
  { value: 'RESOLVED', label: 'Resolved' },
  { value: 'CLOSED', label: 'Closed' },
  { value: 'ESCALATED', label: 'Escalated' },
  { value: 'IN_REVIEW', label: 'In Review' },
]

const PRIORITY_OPTIONS = [
  { value: '', label: 'All Priority' },
  { value: 'P0', label: 'P0 - Critical' },
  { value: 'P1', label: 'P1 - High' },
  { value: 'P2', label: 'P2 - Medium' },
  { value: 'P3', label: 'P3 - Low' },
]

const VERIFICATION_OPTIONS = [
  { value: '', label: 'All Verification' },
  { value: 'VERIFIED', label: 'Verified' },
  { value: 'MISMATCH', label: 'Mismatch' },
  { value: 'CRITICAL', label: 'Critical' },
]

export default function ComplaintsPage() {
  return (
    <AuthGuard>
      <ComplaintsContent />
    </AuthGuard>
  )
}

function ComplaintsContent() {
  const { user } = useAuth()
  const [data, setData] = useState<Paginated<ComplaintSummary> | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [q, setQ] = useState('')
  const [status, setStatus] = useState('')
  const [priority, setPriority] = useState('')
  const [verification, setVerification] = useState('')
  const [page, setPage] = useState(1)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      // Customers see only their own complaints
      let result: Paginated<ComplaintSummary>
      if (user?.role === 'customer') {
        const mine = await complaintsApi.mine()
        result = { items: mine, total: mine.length, page: 1, per_page: mine.length, pages: 1 }
      } else {
        result = await complaintsApi.list({
          q: q || undefined,
          status: status || undefined,
          priority: priority || undefined,
          verification_outcome: verification || undefined,
          page,
          per_page: 20,
        })
      }
      setData(result)
    } catch (e: unknown) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }, [q, status, priority, verification, page, user?.role])

  useEffect(() => { setPage(1) }, [q, status, priority, verification])
  useEffect(() => { load() }, [load])

  return (
    <DashboardShell>
      <div className="page-header">
        <div>
          <h1 className="page-title">{user?.role === 'customer' ? 'My Complaints' : 'All Complaints'}</h1>
          <p className="page-subtitle">
            {data ? `${data.total.toLocaleString()} complaint${data.total !== 1 ? 's' : ''}` : 'Loading…'}
          </p>
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          <button className="btn btn-ghost btn-sm" onClick={load} title="Refresh">
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          </button>
          {user?.role === 'customer' && (
            <Link href="/dashboard/complaints/new" className="btn btn-orange btn-sm">
              <Plus size={14} /> Submit New
            </Link>
          )}
        </div>
      </div>

      {/* Filters */}
      {user?.role !== 'customer' && (
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 16, alignItems: 'center' }}>
          <SearchBar value={q} onChange={setQ} placeholder="Search complaints…" />
          <FilterSelect id="status-filter" label="Status" value={status} onChange={setStatus} options={STATUS_OPTIONS} />
          <FilterSelect id="priority-filter" label="Priority" value={priority} onChange={setPriority} options={PRIORITY_OPTIONS} />
          <FilterSelect id="verification-filter" label="Verification" value={verification} onChange={setVerification} options={VERIFICATION_OPTIONS} />
        </div>
      )}

      {error && <ErrorState error={error} retry={load} />}

      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>Ref</th>
              <th>Title</th>
              <th>Status</th>
              <th>Priority</th>
              {user?.role !== 'customer' && <th>Verification</th>}
              {user?.role !== 'customer' && <th>Category</th>}
              <th>Updated</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <SkeletonRows rows={8} cols={user?.role !== 'customer' ? 8 : 6} />
            ) : !data?.items.length ? (
              <tr>
                <td colSpan={8}>
                  <Empty
                    icon={<MessageSquare size={40} />}
                    title="No complaints found"
                    body={q || status || priority || verification ? 'Try adjusting your filters.' : 'No complaints yet.'}
                  />
                </td>
              </tr>
            ) : (
              data.items.map((c) => (
                <tr key={c.id} onClick={() => window.location.href = `/dashboard/complaints/${c.ref}`}>
                  <td>
                    <span style={{ fontFamily: 'DM Mono, monospace', fontSize: 12, color: 'var(--orange-2)' }}>
                      {c.public_ref ?? c.ref}
                    </span>
                  </td>
                  <td style={{ maxWidth: 260 }}>
                    <span style={{ fontWeight: 500, fontSize: 13 }}>{c.title}</span>
                    {c.department && <span style={{ fontSize: 11, color: 'var(--text-4)', display: 'block' }}>{c.department}</span>}
                  </td>
                  <td><StatusPill status={c.status} /></td>
                  <td><PriorityBadge priority={c.priority} /></td>
                  {user?.role !== 'customer' && (
                    <td><VerificationBadge outcome={c.verification_outcome} /></td>
                  )}
                  {user?.role !== 'customer' && (
                    <td style={{ fontSize: 12, color: 'var(--text-3)' }}>{c.category ?? '—'}</td>
                  )}
                  <td style={{ fontSize: 12, color: 'var(--text-3)', fontFamily: 'DM Mono, monospace' }}>
                    {new Date(c.updated_at).toLocaleDateString()}
                  </td>
                  <td>
                    <Link
                      href={`/dashboard/complaints/${c.ref}`}
                      className="btn btn-ghost btn-sm"
                      onClick={(e) => e.stopPropagation()}
                    >
                      View →
                    </Link>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
        {data && (
          <Pagination page={data.page} pages={data.pages} onPage={setPage} />
        )}
      </div>
    </DashboardShell>
  )
}
