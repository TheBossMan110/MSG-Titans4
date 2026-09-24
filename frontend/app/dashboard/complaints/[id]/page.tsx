'use client'
import { use, useState, useEffect } from 'react'
import Link from 'next/link'
import {
  ArrowLeft, RefreshCw, Zap, Shield, CheckCircle, AlertTriangle,
  AlertCircle, Clock, ChevronDown, ExternalLink, Play, User,
  MessageSquare, FileText, Activity,
} from 'lucide-react'
import {
  DashboardShell, AuthGuard, StatusPill, PriorityBadge, VerificationBadge,
  Confidence, TwoEnginePanel, ChecklistItem, TimelineEvent, SlaBadge,
  KvRow, RuleAccordion, Spinner, ErrorState,
} from '@/components/ui'
import { complaints as complaintsApi, review, ApiError } from '@/lib/api'
import type {
  ComplaintDetail, ExplainResult, ChecklistStep, FollowUp,
  EscalationNote, LifecycleEvent, SlaInfo, ReviewHistoryItem, ComplaintStatus,
} from '@/lib/api'
import { useAuth } from '@/lib/auth-context'

export default function ComplaintDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params)
  return (
    <AuthGuard>
      <ComplaintDetail id={id} />
    </AuthGuard>
  )
}

type Tab = 'overview' | 'pipeline' | 'checklist' | 'history' | 'escalation'

function ComplaintDetail({ id }: { id: string }) {
  const { user } = useAuth()
  const [complaint, setComplaint] = useState<ComplaintDetail | null>(null)
  const [explain, setExplain] = useState<ExplainResult | null>(null)
  const [checklist, setChecklist] = useState<ChecklistStep[]>([])
  const [followUps, setFollowUps] = useState<FollowUp[]>([])
  const [escalation, setEscalation] = useState<EscalationNote | null>(null)
  const [lifecycle, setLifecycle] = useState<{ events: LifecycleEvent[]; available_actions: ComplaintStatus[] } | null>(null)
  const [sla, setSla] = useState<SlaInfo | null>(null)
  const [reviewHistory, setReviewHistory] = useState<ReviewHistoryItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState<Tab>('overview')
  const [actionLoading, setActionLoading] = useState(false)
  const [actionNote, setActionNote] = useState('')
  const [confirmNote, setConfirmNote] = useState('')

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const c = await complaintsApi.get(id)
      setComplaint(c)

      // Load secondary data in parallel (all gracefully failing)
      const [exp, chk, fu, esc, lc, rh] = await Promise.allSettled([
        complaintsApi.explain(id),
        complaintsApi.checklist(id),
        complaintsApi.followUps(id),
        complaintsApi.escalation(id),
        complaintsApi.lifecycle(id),
        user?.role && ['reviewer', 'manager', 'admin'].includes(user.role)
          ? review.history(id)
          : Promise.resolve([]),
      ])

      if (exp.status === 'fulfilled') setExplain(exp.value)
      if (chk.status === 'fulfilled') setChecklist(chk.value)
      if (fu.status === 'fulfilled') setFollowUps(fu.value)
      if (esc.status === 'fulfilled') setEscalation(esc.value)
      if (lc.status === 'fulfilled') setLifecycle(lc.value)
      if (rh.status === 'fulfilled') setReviewHistory(rh.value)

      // SLA (reviewer+)
      if (user?.role && ['reviewer', 'manager', 'admin'].includes(user.role)) {
        const slaData = await review.sla(id).catch(() => null)
        setSla(slaData)
      }
    } catch (e: unknown) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [id])

  const updateStatus = async (newStatus: ComplaintStatus) => {
    if (!complaint) return
    setActionLoading(true)
    try {
      const updated = await complaintsApi.updateStatus(id, newStatus, confirmNote || undefined)
      setComplaint(updated)
      setConfirmNote('')
      // Reload lifecycle
      const lc = await complaintsApi.lifecycle(id).catch(() => null)
      if (lc) setLifecycle(lc)
    } catch (e: unknown) {
      alert((e as Error).message)
    } finally {
      setActionLoading(false)
    }
  }

  const reanalyse = async () => {
    setActionLoading(true)
    try {
      const updated = await complaintsApi.reanalyse(id)
      setComplaint(updated)
    } catch (e: unknown) {
      alert((e as Error).message)
    } finally {
      setActionLoading(false)
    }
  }

  const confirmStep = async (step_id: string) => {
    try {
      const updated = await complaintsApi.confirmStep(id, step_id)
      setChecklist((prev) => prev.map((s) => s.step_id === step_id ? updated : s))
    } catch (e: unknown) {
      alert((e as Error).message)
    }
  }

  const completeFollowUp = async (fu_id: string) => {
    try {
      const updated = await complaintsApi.completeFollowUp(id, fu_id)
      setFollowUps((prev) => prev.map((f) => f.id === fu_id ? updated : f))
    } catch (e: unknown) {
      alert((e as Error).message)
    }
  }

  if (loading) return (
    <DashboardShell>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, justifyContent: 'center', padding: '80px 0' }}>
        <Spinner size={28} /> Loading complaint…
      </div>
    </DashboardShell>
  )

  if (error) return (
    <DashboardShell>
      <Link href="/dashboard/complaints" className="btn btn-ghost btn-sm" style={{ marginBottom: 16 }}>
        <ArrowLeft size={14} /> All Complaints
      </Link>
      <ErrorState error={error} retry={load} />
    </DashboardShell>
  )

  if (!complaint) return null

  const isAgent = user?.role && ['agent', 'reviewer', 'manager', 'admin'].includes(user.role)
  const isReviewer = user?.role && ['reviewer', 'manager', 'admin'].includes(user.role)
  const verificationColor =
    complaint.verification_outcome === 'VERIFIED' ? 'var(--verified)' :
    complaint.verification_outcome === 'MISMATCH' ? 'var(--mismatch)' :
    complaint.verification_outcome === 'CRITICAL' ? 'var(--critical)' :
    'var(--text-3)'

  const engineFields = complaint.pipeline_ai || complaint.pipeline_python ? [
    { label: 'Category', ai: complaint.pipeline_ai?.category, python: complaint.pipeline_python?.category },
    { label: 'Urgency', ai: complaint.pipeline_ai?.urgency, python: complaint.pipeline_python?.urgency },
    { label: 'Priority', ai: complaint.pipeline_ai?.priority, python: complaint.pipeline_python?.priority },
    { label: 'Department', ai: complaint.pipeline_ai?.department, python: complaint.pipeline_python?.department },
    { label: 'Escalation', ai: complaint.pipeline_ai?.escalation_required != null ? String(complaint.pipeline_ai.escalation_required) : null, python: complaint.pipeline_python?.escalation_required != null ? String(complaint.pipeline_python.escalation_required) : null },
    { label: 'Confidence', ai: complaint.pipeline_ai?.confidence != null ? `${Math.round(complaint.pipeline_ai.confidence * 100)}%` : null, python: null },
  ] : []

  return (
    <DashboardShell>
      {/* Breadcrumb */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 20, flexWrap: 'wrap' }}>
        <Link href="/dashboard/complaints" className="btn btn-ghost btn-sm">
          <ArrowLeft size={14} /> Complaints
        </Link>
        <span style={{ color: 'var(--text-4)', fontSize: 12 }}>/</span>
        <span style={{ fontFamily: 'DM Mono, monospace', fontSize: 13, color: 'var(--orange-2)' }}>
          {complaint.public_ref ?? complaint.ref}
        </span>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          {isAgent && (
            <button className="btn btn-ghost btn-sm" onClick={reanalyse} disabled={actionLoading} title="Re-run analysis pipeline">
              <Play size={13} /> Re-analyse
            </button>
          )}
          <button className="btn btn-ghost btn-sm" onClick={load} disabled={loading}>
            <RefreshCw size={13} />
          </button>
        </div>
      </div>

      {/* Header */}
      <div style={{
        background: 'var(--surface)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--r-xl)',
        padding: '24px',
        marginBottom: 20,
        borderLeft: `4px solid ${verificationColor}`,
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 16, flexWrap: 'wrap' }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <h1 style={{ fontSize: 'clamp(18px, 2.5vw, 24px)', fontWeight: 800, letterSpacing: '-0.02em', marginBottom: 10 }}>
              {complaint.title}
            </h1>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
              <StatusPill status={complaint.status} />
              <PriorityBadge priority={complaint.priority} />
              <VerificationBadge outcome={complaint.verification_outcome} />
              {sla && <SlaBadge breached={sla.breached} minutesRemaining={sla.minutes_remaining} risk={sla.risk_level} />}
              {complaint.escalation_required && (
                <span className="badge badge-critical">
                  <AlertCircle size={10} /> Escalated
                </span>
              )}
            </div>
          </div>
          {/* Action buttons */}
          {isAgent && lifecycle?.available_actions && lifecycle.available_actions.length > 0 && (
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {lifecycle.available_actions.slice(0, 3).map((action) => (
                <button
                  key={action}
                  className={`btn btn-sm ${action === 'RESOLVED' ? 'btn-py' : action === 'ESCALATED' ? 'btn-ghost' : 'btn-ghost'}`}
                  style={action === 'ESCALATED' ? { borderColor: 'var(--critical-border)', color: '#f87171' } : undefined}
                  onClick={() => updateStatus(action)}
                  disabled={actionLoading}
                >
                  {action.replace(/_/g, ' ')}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 4, borderBottom: '1px solid var(--border)', marginBottom: 20 }}>
        {([
          { id: 'overview', label: 'Overview', icon: <FileText size={13} /> },
          { id: 'pipeline', label: 'Dual-Engine Pipeline', icon: <Zap size={13} /> },
          { id: 'checklist', label: `Checklist (${checklist.length})`, icon: <CheckCircle size={13} /> },
          { id: 'history', label: 'History', icon: <Activity size={13} /> },
          ...(complaint.escalation_required ? [{ id: 'escalation' as Tab, label: 'Escalation', icon: <AlertTriangle size={13} /> }] : []),
        ] as { id: Tab; label: string; icon: React.ReactNode }[]).map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              padding: '10px 16px', background: 'none', border: 'none', cursor: 'pointer',
              fontSize: 13.5, fontWeight: tab === t.id ? 700 : 500,
              color: tab === t.id ? 'var(--orange-2)' : 'var(--text-3)',
              borderBottom: `2px solid ${tab === t.id ? 'var(--orange)' : 'transparent'}`,
              transition: 'color 0.15s',
            }}
          >
            {t.icon}
            {t.label}
          </button>
        ))}
      </div>

      {/* ── OVERVIEW TAB ── */}
      {tab === 'overview' && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: 16 }}>
          <div>
            {/* Description */}
            <div className="card" style={{ padding: '20px', marginBottom: 16 }}>
              <h3 style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 12 }}>
                Description
              </h3>
              <p style={{ fontSize: 14, color: 'var(--text-2)', lineHeight: 1.7, whiteSpace: 'pre-wrap' }}>
                {complaint.description}
              </p>
            </div>

            {/* AI summary */}
            {complaint.summary && (
              <div className="card card-ai" style={{ padding: '20px', marginBottom: 16 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                  <Zap size={14} color="#a5b4fc" />
                  <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#a5b4fc' }}>
                    AI Summary
                  </span>
                </div>
                <p style={{ fontSize: 14, color: 'var(--text-2)', lineHeight: 1.7 }}>{complaint.summary}</p>
              </div>
            )}

            {/* Entities */}
            {complaint.entities && Object.keys(complaint.entities).length > 0 && (
              <div className="card" style={{ padding: '20px', marginBottom: 16 }}>
                <h3 style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 12 }}>
                  Extracted Entities
                </h3>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {Object.entries(complaint.entities).map(([type, values]) => (
                    <div key={type} style={{ display: 'flex', gap: 8, alignItems: 'baseline' }}>
                      <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-4)', minWidth: 100, textTransform: 'capitalize' }}>{type}:</span>
                      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                        {values.map((v) => <span key={v} className="badge badge-neutral">{v}</span>)}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Follow-ups */}
            {followUps.length > 0 && (
              <div className="card" style={{ padding: '20px' }}>
                <h3 style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 12 }}>
                  Follow-Ups
                </h3>
                {followUps.map((fu) => (
                  <div key={fu.id} style={{
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    padding: '10px 0', borderBottom: '1px solid var(--border)', gap: 12,
                  }}>
                    <div>
                      <span style={{ fontSize: 13.5, fontWeight: 500, color: fu.completed ? 'var(--text-4)' : 'var(--text)', textDecoration: fu.completed ? 'line-through' : 'none' }}>
                        {fu.type}
                      </span>
                      {fu.description && <p style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 2 }}>{fu.description}</p>}
                      <p style={{ fontSize: 11, color: fu.minutes_late ? 'var(--critical)' : 'var(--text-4)', marginTop: 2 }}>
                        Due: {new Date(fu.due_at).toLocaleString()}
                        {fu.minutes_late != null && fu.minutes_late > 0 && ` (${fu.minutes_late}m late)`}
                      </p>
                    </div>
                    {!fu.completed && isAgent && (
                      <button className="btn btn-sm btn-ghost" onClick={() => completeFollowUp(fu.id)}>Mark Done</button>
                    )}
                    {fu.completed && <CheckCircle size={16} color="var(--verified)" />}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Right sidebar */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {/* Details */}
            <div className="card" style={{ padding: '18px' }}>
              <h3 style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 12 }}>
                Details
              </h3>
              <KvRow label="Ref" value={<span style={{ fontFamily: 'DM Mono, monospace', fontSize: 12, color: 'var(--orange-2)' }}>{complaint.public_ref ?? complaint.ref}</span>} />
              <KvRow label="Category" value={complaint.category} />
              <KvRow label="Department" value={complaint.department} />
              <KvRow label="Urgency" value={complaint.urgency} />
              <KvRow label="Channel" value={complaint.channel} />
              <KvRow label="Created" value={new Date(complaint.created_at).toLocaleString()} />
              {complaint.order_ref && <KvRow label="Order Ref" value={complaint.order_ref} mono />}
              {complaint.product && <KvRow label="Product" value={complaint.product} />}
              {complaint.amount != null && <KvRow label="Amount" value={`£${complaint.amount.toFixed(2)}`} />}
            </div>

            {/* Customer (hidden payload for customer role) */}
            {isAgent && (
              <div className="card" style={{ padding: '18px' }}>
                <h3 style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 12 }}>
                  <User size={12} style={{ display: 'inline', marginRight: 6 }} />
                  Customer
                </h3>
                <KvRow label="Name" value={complaint.customer_name} />
                <KvRow label="Email" value={complaint.customer_email} />
                <KvRow label="Type" value={complaint.customer_type} />
              </div>
            )}

            {/* Reconciled result */}
            {complaint.reconciled && (
              <div className={`card ${complaint.verification_outcome === 'VERIFIED' ? 'card-verified' : complaint.verification_outcome === 'MISMATCH' ? 'card-mismatch' : 'card-critical'}`} style={{ padding: '18px' }}>
                <h3 style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 12 }}>
                  Reconciled Outcome
                </h3>
                <KvRow label="Source" value={
                  <span className={`badge ${complaint.reconciled.source === 'AGREEMENT' ? 'badge-verified' : complaint.reconciled.source === 'PYTHON' ? 'badge-py' : 'badge-ai'}`}>
                    {complaint.reconciled.source}
                  </span>
                } />
                <KvRow label="Agreement" value={complaint.reconciled.agreement_score != null ? `${Math.round(complaint.reconciled.agreement_score * 100)}%` : 'Not measured'} />
                <KvRow label="Escalation" value={complaint.reconciled.escalation_required ? <span style={{ color: 'var(--critical)' }}>Required</span> : 'No'} />
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── PIPELINE TAB ── */}
      {tab === 'pipeline' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {engineFields.length > 0 ? (
            <TwoEnginePanel fields={engineFields} />
          ) : (
            <div style={{ padding: '40px 0', textAlign: 'center', color: 'var(--text-3)' }}>
              Pipeline results not yet available
            </div>
          )}

          {/* Disagreements */}
          {complaint.reconciled?.disagreements && complaint.reconciled.disagreements.length > 0 && (
            <div className="card card-mismatch" style={{ padding: '20px' }}>
              <h3 style={{ fontSize: 13, fontWeight: 700, color: 'var(--mismatch)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 14 }}>
                <AlertTriangle size={13} style={{ display: 'inline', marginRight: 6 }} />
                Disagreements ({complaint.reconciled.disagreements.length})
              </h3>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {complaint.reconciled.disagreements.map((d, i) => (
                  <div key={i} style={{ display: 'grid', gridTemplateColumns: '120px 1fr 24px 1fr 80px', gap: 8, alignItems: 'center', padding: '8px 12px', background: 'var(--surface)', borderRadius: 'var(--r-sm)', fontSize: 12 }}>
                    <span style={{ fontWeight: 700, color: 'var(--text-2)' }}>{d.field}</span>
                    <span style={{ color: '#a5b4fc', fontFamily: 'DM Mono, monospace' }}>{d.ai_value}</span>
                    <span style={{ color: 'var(--text-4)', textAlign: 'center' }}>vs</span>
                    <span style={{ color: '#67e8f9', fontFamily: 'DM Mono, monospace' }}>{d.python_value}</span>
                    <span className={`badge ${d.winner === 'PYTHON' ? 'badge-py' : 'badge-ai'}`}>{d.winner} wins</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Explain result */}
          {explain && (
            <>
              {explain.rules_fired.length > 0 && (
                <div className="card" style={{ padding: '20px' }}>
                  <h3 style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 14 }}>
                    <Shield size={13} style={{ display: 'inline', marginRight: 6 }} />
                    Rules Fired ({explain.rules_fired.length})
                  </h3>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                    {explain.rules_fired.map((r) => <RuleAccordion key={r.rule_id} rule={r} />)}
                  </div>
                </div>
              )}

              {(explain.genai_reasoning || explain.python_reasoning) && (
                <div className="pipeline-split">
                  {explain.genai_reasoning && (
                    <div className="engine-block engine-block-ai">
                      <div className="engine-label engine-label-ai"><Zap size={12} /> AI Reasoning</div>
                      <p style={{ fontSize: 13, color: 'var(--text-2)', lineHeight: 1.7 }}>{explain.genai_reasoning}</p>
                    </div>
                  )}
                  {explain.python_reasoning && (
                    <div className="engine-block engine-block-py">
                      <div className="engine-label engine-label-py"><Shield size={12} /> Python Reasoning</div>
                      <p style={{ fontSize: 13, color: 'var(--text-2)', lineHeight: 1.7 }}>{explain.python_reasoning}</p>
                    </div>
                  )}
                </div>
              )}

              {explain.reconciliation_notes && (
                <div className="card" style={{ padding: '16px 20px' }}>
                  <p style={{ fontSize: 12, color: 'var(--text-3)', fontStyle: 'italic' }}>{explain.reconciliation_notes}</p>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* ── CHECKLIST TAB ── */}
      {tab === 'checklist' && (
        <div className="table-wrap">
          {checklist.length === 0 ? (
            <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-3)' }}>
              No checklist steps generated yet
            </div>
          ) : (
            <>
              <div style={{ padding: '16px', borderBottom: '1px solid var(--border)' }}>
                <span style={{ fontSize: 13, color: 'var(--text-3)' }}>
                  {checklist.filter((s) => s.confirmed).length} / {checklist.length} confirmed
                  {checklist.some((s) => s.type === 'RULE_REQUIRED' && !s.confirmed) && (
                    <span className="badge badge-critical" style={{ marginLeft: 10 }}>Required steps pending</span>
                  )}
                </span>
              </div>
              {checklist.map((step) => (
                <ChecklistItem
                  key={step.step_id}
                  step={step}
                  onConfirm={confirmStep}
                  disabled={!isAgent}
                />
              ))}
            </>
          )}
        </div>
      )}

      {/* ── HISTORY TAB ── */}
      {tab === 'history' && (
        <div className="card" style={{ padding: '20px' }}>
          {lifecycle?.events.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-3)' }}>No events yet</div>
          ) : (
            <div>
              {(lifecycle?.events ?? []).map((ev, i) => (
                <TimelineEvent
                  key={ev.id}
                  event={ev}
                  last={i === (lifecycle?.events.length ?? 0) - 1}
                />
              ))}

              {/* Review history */}
              {reviewHistory.length > 0 && (
                <>
                  <div className="divider" />
                  <h3 style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 14 }}>
                    Review History
                  </h3>
                  {reviewHistory.map((rh) => (
                    <div key={rh.id} style={{ padding: '10px 0', borderBottom: '1px solid var(--border)' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                        <span style={{ fontSize: 13.5, fontWeight: 600 }}>{rh.action}</span>
                        <span style={{ fontSize: 11, color: 'var(--text-4)', fontFamily: 'DM Mono, monospace' }}>{new Date(rh.created_at).toLocaleString()}</span>
                      </div>
                      <p style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 2 }}>{rh.reviewer_email}</p>
                      {rh.note && <p style={{ fontSize: 12, color: 'var(--text-2)', marginTop: 4 }}>{rh.note}</p>}
                    </div>
                  ))}
                </>
              )}
            </div>
          )}
        </div>
      )}

      {/* ── ESCALATION TAB ── */}
      {tab === 'escalation' && escalation && (
        <div className="card card-critical" style={{ padding: '24px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20 }}>
            <AlertCircle size={22} color="var(--critical)" />
            <h2 style={{ fontSize: 20, fontWeight: 800 }}>Escalation Details</h2>
          </div>
          <KvRow label="Level" value={escalation.level} />
          <KvRow label="Handler" value={escalation.handler} />
          <KvRow label="Escalated At" value={escalation.escalated_at ? new Date(escalation.escalated_at).toLocaleString() : undefined} />
          {escalation.note_available && escalation.note && (
            <div style={{ marginTop: 16, padding: '14px 16px', background: 'var(--surface)', borderRadius: 'var(--r-md)', border: '1px solid var(--border)' }}>
              <p style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-3)', marginBottom: 6 }}>Escalation Note</p>
              <p style={{ fontSize: 14, color: 'var(--text-2)', lineHeight: 1.7 }}>{escalation.note}</p>
            </div>
          )}
          {!escalation.note_available && (
            <p style={{ fontSize: 13, color: 'var(--text-4)', marginTop: 12 }}>Escalation note not available at this access level.</p>
          )}
        </div>
      )}
    </DashboardShell>
  )
}
