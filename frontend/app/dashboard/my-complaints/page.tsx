'use client'
import { useState, useEffect } from 'react'
import Link from 'next/link'
import { RefreshCw, MessageSquare, Plus } from 'lucide-react'
import { DashboardShell, AuthGuard, StatusPill, PriorityBadge, Empty, Spinner, ErrorState } from '@/components/ui'
import { complaints as complaintsApi } from '@/lib/api'
import type { ComplaintSummary } from '@/lib/api'

export default function MyComplaintsPage() {
  return (
    <AuthGuard allowedRoles={['customer']}>
      <MyComplaintsContent />
    </AuthGuard>
  )
}

function MyComplaintsContent() {
  const [items, setItems] = useState<ComplaintSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await complaintsApi.mine()
      setItems(data)
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
          <h1 className="page-title">My Complaints</h1>
          <p className="page-subtitle">{items.length} complaint{items.length !== 1 ? 's' : ''} submitted</p>
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          <button className="btn btn-ghost btn-sm" onClick={load} disabled={loading}>
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          </button>
          <Link href="/dashboard/complaints/new" className="btn btn-orange btn-sm">
            <Plus size={14} /> New Complaint
          </Link>
        </div>
      </div>

      {error && <ErrorState error={error} retry={load} />}

      {loading ? (
        <div style={{ display: 'flex', justifyContent: 'center', padding: '60px 0' }}><Spinner size={28} /></div>
      ) : items.length === 0 ? (
        <div className="table-wrap">
          <Empty
            icon={<MessageSquare size={40} />}
            title="No complaints submitted yet"
            body="If you have an issue, submit a complaint and we'll route it to the right team."
            action={{ label: 'Submit a Complaint', onClick: () => window.location.href = '/dashboard/complaints/new' }}
          />
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {items.map((c) => (
            <Link key={c.id} href={`/dashboard/complaints/${c.ref}`} style={{ display: 'block' }}>
              <div className="card" style={{ padding: '18px 20px', cursor: 'pointer' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 16 }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
                      <span style={{ fontFamily: 'DM Mono, monospace', fontSize: 12, color: 'var(--orange-2)' }}>
                        {c.public_ref}
                      </span>
                      <StatusPill status={c.status} />
                    </div>
                    <h3 style={{ fontSize: 15, fontWeight: 600, marginBottom: 4 }}>{c.title}</h3>
                    <p style={{ fontSize: 12, color: 'var(--text-3)' }}>
                      {c.category && `${c.category} · `}
                      Submitted {new Date(c.created_at).toLocaleDateString()}
                    </p>
                  </div>
                  <div style={{ display: 'flex', gap: 8, flexDirection: 'column', alignItems: 'flex-end' }}>
                    <PriorityBadge priority={c.priority} />
                    {c.status === 'AWAITING_CUSTOMER' && (
                      <span className="badge badge-mismatch">Action Required</span>
                    )}
                  </div>
                </div>

                {/* Status timeline indicator */}
                <div style={{ marginTop: 14, display: 'flex', gap: 0, alignItems: 'center' }}>
                  {['SUBMITTED', 'ANALYZING', 'ASSIGNED', 'IN_PROGRESS', 'RESOLVED'].map((s, i, arr) => {
                    const statuses = ['SUBMITTED', 'ANALYZING', 'ANALYZED', 'ASSIGNED', 'IN_PROGRESS', 'AWAITING_CUSTOMER', 'RESOLVED', 'CLOSED']
                    const currentIdx = statuses.indexOf(c.status)
                    const stepIdx = statuses.indexOf(s)
                    const done = currentIdx >= stepIdx
                    const isLast = i === arr.length - 1
                    return (
                      <div key={s} style={{ display: 'flex', alignItems: 'center', flex: isLast ? 0 : 1 }}>
                        <div style={{
                          width: 10, height: 10, borderRadius: '50%', flexShrink: 0,
                          background: done ? 'var(--orange)' : 'var(--surface-3)',
                          border: `2px solid ${done ? 'var(--orange)' : 'var(--border)'}`,
                        }} title={s} />
                        {!isLast && (
                          <div style={{ flex: 1, height: 2, background: done ? 'var(--orange)' : 'var(--border)', margin: '0 2px' }} />
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </DashboardShell>
  )
}
