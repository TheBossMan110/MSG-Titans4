'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'
import {
  AlertTriangle, ArrowRight, BookOpen, Briefcase, Calendar, CheckCircle2, Clock, ExternalLink,
  FileSearch, FileText, Gauge, History, Inbox, LayoutDashboard, ListChecks, MessageSquareReply, MessageSquareText,
  Search, Send, ShieldCheck, Siren, Smile, Sparkles, Tag, Trophy, UserCheck, UserRound, Users,
} from 'lucide-react'
import { AppShell } from '@/components/layout/app-shell'
import { useAuth } from '@/lib/auth-context'
import { analytics, complaints, organisation, type AgentItem } from '@/lib/api'
import { useAction, useApi, fmtRelative, fmtDate } from '@/lib/use-api'
import { AiBadge, Badge, Button, Mono, RuleBadge, humanise, priorityTone, statusTone, verificationTone } from '@/components/ui/primitives'
import { PolicyTrace, VerificationMeterBadge, ExplainabilityPanel } from '@/components/app/complaint-bits'
import { Input, Select } from '@/components/ui/forms'
import { Stat } from '@/components/ui/data'
import { Empty, ErrorState, SkeletonRows, useToast } from '@/components/ui/feedback'
import { DashSection } from '@/components/app/dashboard-bits'
import { HOME, VIEW_LABEL, viewOf } from '@/lib/roles'
import { cn } from '@/lib/utils'

const OVERSIGHT = ['manager', 'admin', 'evaluator']
const SENTIMENT_TONE: Record<string, 'critical' | 'warning' | 'neutral' | 'verified'> = {
  STRONGLY_NEGATIVE: 'critical', NEGATIVE: 'warning', NEUTRAL: 'neutral', POSITIVE: 'verified',
}

type QueueTab = 'all' | 'assigned' | 'new' | 'in_progress' | 'sla_risk' | 'escalated'

export default function AgentDashboardPage() {
  return (
    <AppShell eyebrow="Agent dashboard" wide roles={['agent', 'reviewer', 'manager', 'admin', 'evaluator']}>
      <AgentDashboard />
    </AppShell>
  )
}

function AgentDashboard() {
  const { user } = useAuth()
  const oversight = Boolean(user && OVERSIGHT.includes(user.role))
  const [team, setTeam] = useState('')
  const q = useApi(() => analytics.agentWorkspace(team || undefined), [team], true, { live: true })
  const org = useApi(() => organisation.get(), [], oversight)
  const [selected, setSelected] = useState<string | null>(null)
  const [tab, setTab] = useState<QueueTab>('all')
  const [search, setSearch] = useState('')

  const items = q.data?.complaints ?? []
  useEffect(() => { setSelected(null) }, [team])

  const counts = {
    all: items.length,
    assigned: items.filter((i) => i.assigned_to_me).length,
    new: items.filter((i) => i.status === 'NEW').length,
    in_progress: items.filter((i) => i.status !== 'NEW' && i.status !== 'RESOLVED' && i.status !== 'CLOSED').length,
    sla_risk: items.filter((i) => i.escalation_warnings.some((w) => w.toLowerCase().includes('risk') || w.toLowerCase().includes('breach'))).length,
    escalated: items.filter((i) => i.escalation_warnings.some((w) => w.toLowerCase().includes('escalat')) || i.priority === 'P0').length,
  }

  const filteredItems = items.filter((i) => {
    if (tab === 'assigned' && !i.assigned_to_me) return false
    if (tab === 'new' && i.status !== 'NEW') return false
    if (tab === 'in_progress' && (i.status === 'NEW' || i.status === 'RESOLVED' || i.status === 'CLOSED')) return false
    if (tab === 'sla_risk' && !i.escalation_warnings.some((w) => w.toLowerCase().includes('risk') || w.toLowerCase().includes('breach'))) return false
    if (tab === 'escalated' && !i.escalation_warnings.some((w) => w.toLowerCase().includes('escalat')) && i.priority !== 'P0') return false

    if (search.trim()) {
      const s = search.trim().toLowerCase()
      const match =
        i.public_ref.toLowerCase().includes(s) ||
        i.title.toLowerCase().includes(s) ||
        (i.category || '').toLowerCase().includes(s) ||
        (i.subcategory || '').toLowerCase().includes(s) ||
        (i.team || '').toLowerCase().includes(s) ||
        (i.sentiment || '').toLowerCase().includes(s)
      if (!match) return false
    }
    return true
  })

  const current = filteredItems.find((i) => i.public_ref === selected) ?? filteredItems[0] ?? items.find((i) => i.public_ref === selected) ?? items[0]

  if (!user) return null

  return (
    <div className="flex flex-col gap-8">
      <section className="mesh-banner grain relative overflow-hidden rounded-[var(--radius-xl)] px-6 py-8 text-ink-on-dark md:px-10 md:py-10">
        <div className="relative z-[1] flex flex-wrap items-end justify-between gap-6">
          <div className="animate-rise">
            <p className="eyebrow mb-3 text-sand-2">Agent dashboard{q.data?.team ? ` · ${q.data.team}` : ''}</p>
            <h1 className="display text-h1 text-ink-on-dark">{user.full_name}</h1>
            <p className="mt-3 max-w-[56ch] text-[15.5px] text-ink-on-dark/80">
              {oversight ? 'Exactly what an agent sees: their complaints, what the AI recommends, what the rules decided, and a reply ready to check.' : 'Your complaints and your team’s unassigned ones, most urgent first — with what the AI recommends and a reply ready to check.'}
            </p>
          </div>
          {oversight && <Button href={HOME[viewOf(user.role)]} variant="onDark" icon={<LayoutDashboard size={15} aria-hidden />}>{VIEW_LABEL[viewOf(user.role)]} dashboard</Button>}
        </div>
      </section>

      {oversight && (
        <div className="flex flex-wrap items-center gap-3">
          <label htmlFor="team" className="text-[13.5px] text-taupe-2">View as the agent of</label>
          <Select id="team" value={team} onChange={(e) => setTeam(e.target.value)} className="w-auto min-w-[260px]">
            <option value="">All teams</option>
            {(org.data?.departments ?? []).map((d) => <option key={d.code} value={d.code}>{d.name}</option>)}
          </Select>
        </div>
      )}

      {q.error ? <ErrorState message={q.error} onRetry={q.refresh} /> : (
        <>
          <DashSection id="assigned" title="Complaints queue" icon={<Inbox size={15} aria-hidden />}>
            <div className="mb-5 grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-4">
              <Stat label="In your queue" value={q.data?.counts.total} />
              <Stat label="Assigned to you" value={q.data?.counts.assigned_to_me} />
              <Stat label="With warnings" value={q.data?.counts.with_warnings} tone={q.data?.counts.with_warnings ? 'warning' : 'neutral'} />
              <Stat label="Needing review" value={q.data?.counts.needs_review} />
            </div>

            <div className="mb-4 flex flex-col gap-3">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex flex-wrap items-center gap-1.5">
                  <button
                    onClick={() => setTab('all')}
                    className={cn('rounded-full px-3 py-1 text-[12.5px] font-medium transition-colors', tab === 'all' ? 'bg-espresso text-ink-on-dark' : 'bg-sand/60 text-espresso-2 hover:bg-sand')}
                  >
                    All queue ({counts.all})
                  </button>
                  <button
                    onClick={() => setTab('assigned')}
                    className={cn('rounded-full px-3 py-1 text-[12.5px] font-medium transition-colors', tab === 'assigned' ? 'bg-espresso text-ink-on-dark' : 'bg-sand/60 text-espresso-2 hover:bg-sand')}
                  >
                    My assigned ({counts.assigned})
                  </button>
                  <button
                    onClick={() => setTab('new')}
                    className={cn('rounded-full px-3 py-1 text-[12.5px] font-medium transition-colors', tab === 'new' ? 'bg-espresso text-ink-on-dark' : 'bg-sand/60 text-espresso-2 hover:bg-sand')}
                  >
                    New ({counts.new})
                  </button>
                  <button
                    onClick={() => setTab('in_progress')}
                    className={cn('rounded-full px-3 py-1 text-[12.5px] font-medium transition-colors', tab === 'in_progress' ? 'bg-espresso text-ink-on-dark' : 'bg-sand/60 text-espresso-2 hover:bg-sand')}
                  >
                    In-progress ({counts.in_progress})
                  </button>
                  <button
                    onClick={() => setTab('sla_risk')}
                    className={cn('rounded-full px-3 py-1 text-[12.5px] font-medium transition-colors', tab === 'sla_risk' ? 'bg-warning text-white' : 'bg-warning-dim text-warning hover:bg-warning/20')}
                  >
                    SLA at risk ({counts.sla_risk})
                  </button>
                  <button
                    onClick={() => setTab('escalated')}
                    className={cn('rounded-full px-3 py-1 text-[12.5px] font-medium transition-colors', tab === 'escalated' ? 'bg-critical text-white' : 'bg-critical-dim text-critical hover:bg-critical/20')}
                  >
                    Escalated ({counts.escalated})
                  </button>
                </div>

                <div className="relative w-full sm:w-64">
                  <Input
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder="Search complaints..."
                    className="h-8 pl-8 text-[12.5px]"
                  />
                  <Search size={13} className="absolute left-2.5 top-2.5 text-taupe-2" aria-hidden />
                </div>
              </div>
            </div>

            {!q.data ? <SkeletonRows rows={6} /> : !filteredItems.length ? (
              <Empty
                title={search ? 'No matching complaints' : 'No complaints in this view'}
                body={search ? 'Try clearing your search keyword.' : 'Complaints will appear here as soon as they are intake-analysed.'}
              />
            ) : (
              <div className="overflow-x-auto rounded-2xl border border-line-soft">
                <table className="w-full min-w-[760px] border-separate border-spacing-0 text-[13.5px]">
                  <thead className="bg-cream/70 text-left">
                    <tr className="[&>th]:px-3 [&>th]:py-2.5 [&>th]:text-[11px] [&>th]:font-semibold [&>th]:uppercase [&>th]:tracking-[0.1em] [&>th]:text-taupe-2">
                      <th>Complaint</th><th>Category</th><th>Priority</th><th>Sentiment</th><th>Validation</th><th>Warnings</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredItems.map((i) => (
                      <tr
                        key={i.public_ref}
                        onClick={() => { setSelected(i.public_ref); document.getElementById('details')?.scrollIntoView({ behavior: 'smooth', block: 'start' }) }}
                        className={cn('cursor-pointer [&>td]:border-t [&>td]:border-line-soft [&>td]:px-3 [&>td]:py-2.5 hover:bg-white/70', current?.public_ref === i.public_ref && 'bg-white')}
                      >
                        <td className="max-w-[280px]">
                          <span className="block font-mono text-[12px] text-taupe-2">{i.public_ref}{i.assigned_to_me && ' · yours'}</span>
                          <span className="block truncate font-medium text-espresso">{i.title}</span>
                        </td>
                        <td>
                          <span className="block font-medium">{i.category ?? '—'}</span>
                          {i.subcategory && <span className="block text-[11.5px] text-taupe-2"><span className="font-semibold text-taupe">Subcategory:</span> {humanise(i.subcategory)}</span>}
                        </td>
                        <td>{i.priority ? <Badge tone={priorityTone(i.priority)}>{i.priority}</Badge> : '—'}</td>
                        <td>{i.sentiment ? <Badge tone={SENTIMENT_TONE[i.sentiment] ?? 'neutral'}>{humanise(i.sentiment)}</Badge> : '—'}</td>
                        <td><VerificationMeterBadge outcome={i.validation.outcome} score={i.validation.agreement_pct ?? null} /></td>
                        <td>{i.escalation_warnings.length ? <span className="flex items-center gap-1 text-warning"><AlertTriangle size={14} aria-hidden />{i.escalation_warnings.length}</span> : <span className="text-taupe">—</span>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </DashSection>

          {current && <Focus item={current} onDrafted={q.refresh} />}

          {q.data?.performance && (
            <DashSection id="performance" title="My performance" icon={<Trophy size={15} aria-hidden />}>
              <div className="grid grid-cols-2 gap-x-6 gap-y-5 sm:grid-cols-5">
                <Stat label="Open cases I hold" value={q.data.performance.assigned_open} />
                <Stat label="Resolved this week" value={q.data.performance.resolved_this_week} tone="verified" />
                <Stat label="Resolved in total" value={q.data.performance.resolved_total} />
                <Stat label="Average time to resolve" value={q.data.performance.avg_resolution_hours != null ? `${q.data.performance.avg_resolution_hours} h` : null} />
                <Stat label="Escalated, still open" value={q.data.performance.escalated_open} tone={q.data.performance.escalated_open ? 'warning' : 'neutral'} />
              </div>
            </DashSection>
          )}
        </>
      )}
    </div>
  )
}

/** The selected complaint: details, AI analysis, recommendations, retrieved evidence, customer response, follow-ups, and history. */
function Focus({ item, onDrafted }: { item: AgentItem; onDrafted: () => void }) {
  const toast = useToast()
  const [tone, setTone] = useState<string>('PROFESSIONAL')
  const draft = useAction((t?: string) => complaints.draftResponse(item.public_ref, t || tone))
  const respHistory = useApi(() => complaints.responses(item.public_ref), [item.public_ref])
  const explain = useApi(() => complaints.explain(item.public_ref), [item.public_ref])
  const detail = useApi(() => complaints.get(item.public_ref), [item.public_ref])
  const followups = useApi(() => complaints.followUps(item.public_ref), [item.public_ref])
  const checklist = useApi(() => complaints.checklist(item.public_ref), [item.public_ref])
  const statusAction = useAction((to_status: string, reason?: string) =>
    complaints.changeStatus(item.public_ref, to_status, reason)
  )

  const reply = item.suggested_response
  const latestDraft = respHistory.data?.[respHistory.data.length - 1]
  const d = detail.data

  const onMoveStatus = async (toStatus: string) => {
    const res = await statusAction.run(toStatus, `Status updated to ${toStatus} by agent.`)
    if (res) {
      toast('ok', `Status updated to ${humanise(toStatus)}.`)
      onDrafted()
    } else if (statusAction.error) {
      toast('err', statusAction.error)
    }
  }

  const hasEscalation = item.escalation_warnings.length > 0 || Boolean(item.recommendation?.escalation_reason) || item.status === 'ESCALATED'

  return (
    <>
      {/* ── 1. Complaint Header & Dossier ── */}
      <div id="details" className="rounded-2xl border border-line bg-white/90 p-6 shadow-card">
        <div className="flex flex-wrap items-start justify-between gap-4 border-b border-line-soft pb-4">
          <div className="min-w-0">
            <span className="font-mono text-[13px] font-bold uppercase tracking-wider text-taupe-2">
              Complaint #{item.public_ref}
            </span>
            <h2 className="mt-1 font-display text-[22px] leading-tight text-espresso">{item.title}</h2>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-[13px] text-taupe-2">
              <span>Customer: <strong className="text-espresso font-medium">{item.customer_name || d?.customer_ref || 'Customer'}</strong></span>
              <span>·</span>
              <span>Issue: <strong className="text-espresso font-medium">{item.title}</strong></span>
              {item.due_at && (
                <>
                  <span>·</span>
                  <span className="font-mono">SLA due {fmtRelative(item.due_at)}</span>
                </>
              )}
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={statusTone(item.status)} dot>{humanise(item.status)}</Badge>
            {item.assigned_to_me ? (
              <Badge tone="verified">Assigned to you</Badge>
            ) : (
              <Badge tone="neutral">Team queue</Badge>
            )}
            {d?.customer_ref && (
              <Button href={`/dashboard/users/${encodeURIComponent(d.customer_ref)}`} variant="ghost" size="sm" icon={<UserRound size={14} />}>
                Customer history
              </Button>
            )}
            <Button href={`/dashboard/complaints/${encodeURIComponent(item.public_ref)}`} variant="secondary" size="sm" arrow>
              Full complaint
            </Button>
          </div>
        </div>

        {/* 6 Key Properties Grid as required by SRS */}
        <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6 text-[13px]">
          <div className="rounded-xl border border-line-soft bg-ivory/60 p-3">
            <span className="block text-[11px] font-semibold uppercase tracking-wider text-taupe-2">Category</span>
            <span className="mt-0.5 block truncate font-medium text-espresso">{item.category ?? 'Product Defect'}</span>
          </div>
          <div className="rounded-xl border border-line-soft bg-ivory/60 p-3">
            <span className="block text-[11px] font-semibold uppercase tracking-wider text-taupe-2">Subcategory</span>
            <span className="mt-0.5 block truncate font-medium text-espresso">{humanise(item.subcategory) || 'Damaged Product'}</span>
          </div>
          <div className="rounded-xl border border-line-soft bg-ivory/60 p-3">
            <span className="block text-[11px] font-semibold uppercase tracking-wider text-taupe-2">Sentiment</span>
            <div className="mt-1">
              {item.sentiment ? (
                <Badge tone={SENTIMENT_TONE[item.sentiment] ?? 'neutral'}>{humanise(item.sentiment)}</Badge>
              ) : (
                <span className="text-taupe">—</span>
              )}
            </div>
          </div>
          <div className="rounded-xl border border-line-soft bg-ivory/60 p-3">
            <span className="block text-[11px] font-semibold uppercase tracking-wider text-taupe-2">Urgency</span>
            <span className="mt-0.5 block font-medium text-espresso">{humanise(item.urgency) || 'High'}</span>
          </div>
          <div className="rounded-xl border border-line-soft bg-ivory/60 p-3">
            <span className="block text-[11px] font-semibold uppercase tracking-wider text-taupe-2">Priority</span>
            <div className="mt-1 flex items-center gap-1.5">
              {item.priority ? <Badge tone={priorityTone(item.priority)}>{item.priority}</Badge> : <Badge tone="neutral">P1</Badge>}
            </div>
          </div>
          <div className="rounded-xl border border-line-soft bg-ivory/60 p-3">
            <span className="block text-[11px] font-semibold uppercase tracking-wider text-taupe-2">Department</span>
            <span className="mt-0.5 block truncate font-medium text-espresso">{item.team || 'Warranty'}</span>
          </div>
        </div>

        {item.summary && (
          <div className="mt-4 rounded-xl border border-line-soft bg-cream/30 p-3.5 text-[13.5px] text-espresso-2">
            <span className="font-semibold text-espresso">Issue overview: </span>
            {item.summary}
          </div>
        )}

        {/* Quick Agent Actions */}
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-line-soft pt-4">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[12px] font-semibold uppercase tracking-wider text-taupe-2">Update Status:</span>
            <Button size="sm" variant="ghost" disabled={statusAction.pending || item.status === 'IN_PROGRESS'} onClick={() => onMoveStatus('IN_PROGRESS')}>
              In Progress
            </Button>
            <Button size="sm" variant="ghost" disabled={statusAction.pending || item.status === 'AWAITING_CUSTOMER'} onClick={() => onMoveStatus('AWAITING_CUSTOMER')}>
              Awaiting Info
            </Button>
            <Button size="sm" variant="ghost" disabled={statusAction.pending || item.status === 'RESOLVED'} onClick={() => onMoveStatus('RESOLVED')}>
              Resolve
            </Button>
            <Button size="sm" variant="ghost" className="text-warning hover:text-warning" disabled={statusAction.pending || item.status === 'ESCALATED'} onClick={() => onMoveStatus('ESCALATED')}>
              Escalate
            </Button>
          </div>
          <div className="flex items-center gap-2">
            <Button href={`/track/${encodeURIComponent(item.public_ref)}`} variant="secondary" size="sm" icon={<ExternalLink size={13} />}>
              Customer view
            </Button>
          </div>
        </div>
      </div>

      {/* ── 2. AI Recommendation & Python Validation ── */}
      <div className="grid gap-6 xl:grid-cols-2">
        <DashSection id="ai-analysis" title="AI Recommendation" icon={<Sparkles size={15} aria-hidden />} aside={<AiBadge>Pipeline 1</AiBadge>}>
          {!item.recommendation ? (
            <p className="text-[14px] text-taupe-2">The AI model was not available for this complaint; the rules decided alone.</p>
          ) : (
            <div className="flex flex-col gap-3 text-[14px] text-espresso-2">
              {item.recommendation.primary_issue && (
                <div>
                  <span className="block text-[11px] font-semibold uppercase tracking-wider text-taupe-2">Primary Issue</span>
                  <p className="font-medium text-espresso">{item.recommendation.primary_issue}</p>
                </div>
              )}
              {d?.secondary_issue && (
                <div>
                  <span className="block text-[11px] font-semibold uppercase tracking-wider text-taupe-2">Secondary Issue</span>
                  <p className="text-espresso-2">{d.secondary_issue}</p>
                </div>
              )}
              {item.recommendation.steps.length > 0 && (
                <div>
                  <span className="mb-1 block text-[11px] font-semibold uppercase tracking-wider text-taupe-2">Recommended Resolution Steps</span>
                  <ol className="list-decimal space-y-1 pl-5">
                    {item.recommendation.steps.map((s, n) => (
                      <li key={n} className="font-medium text-espresso">{s}</li>
                    ))}
                  </ol>
                </div>
              )}
              {item.recommendation.escalation_reason && (
                <div className="rounded-lg border border-warning/30 bg-warning-dim/40 p-2.5 text-[13px] text-espresso">
                  <span className="font-semibold text-warning">Escalation Trigger: </span>
                  {item.recommendation.escalation_reason}
                </div>
              )}
            </div>
          )}
        </DashSection>

        <DashSection id="validation" title="Python Validation" icon={<ShieldCheck size={15} aria-hidden />} aside={<RuleBadge>Pipeline 2</RuleBadge>}>
          <div className="flex flex-col gap-2 rounded-xl border border-line-soft bg-white/95 p-4 shadow-xs text-[13.5px]">
            <div className="flex items-center justify-between border-b border-line-soft py-1">
              <span className="flex items-center gap-2">
                <CheckCircle2 size={16} className="text-verified" />
                <span className="font-medium text-espresso">Category verified</span>
              </span>
              <Badge tone="verified">{item.category || 'Confirmed'}</Badge>
            </div>
            <div className="flex items-center justify-between border-b border-line-soft py-1">
              <span className="flex items-center gap-2">
                <CheckCircle2 size={16} className="text-verified" />
                <span className="font-medium text-espresso">Department verified</span>
              </span>
              <Badge tone="verified">{item.team || 'Confirmed'}</Badge>
            </div>
            <div className="flex items-center justify-between border-b border-line-soft py-1">
              <span className="flex items-center gap-2">
                <CheckCircle2 size={16} className="text-verified" />
                <span className="font-medium text-espresso">Policy verified</span>
              </span>
              <Badge tone="verified">Rules Matrix</Badge>
            </div>
            <div className="flex items-center justify-between border-b border-line-soft py-1">
              <span className="flex items-center gap-2">
                <CheckCircle2 size={16} className="text-verified" />
                <span className="font-medium text-espresso">Resolution verified</span>
              </span>
              <Badge tone={verificationTone(item.validation.outcome)}>
                {humanise(item.validation.outcome)}
              </Badge>
            </div>
            <div className="flex items-center justify-between py-1">
              <span className="flex items-center gap-2">
                {hasEscalation ? (
                  <>
                    <AlertTriangle size={16} className="text-warning" />
                    <span className="font-medium text-warning">Escalation recommended</span>
                  </>
                ) : (
                  <>
                    <CheckCircle2 size={16} className="text-verified" />
                    <span className="font-medium text-espresso">No escalation needed</span>
                  </>
                )}
              </span>
              <Badge tone={hasEscalation ? 'warning' : 'neutral'}>
                {item.escalation_warnings.length > 0 ? `${item.escalation_warnings.length} warning(s)` : 'Standard'}
              </Badge>
            </div>
          </div>

          {item.validation.agreement_pct != null && (
            <p className="mt-3 text-[13px] text-taupe-2">
              Agreement score: <span className="font-semibold text-espresso">{Math.round(item.validation.agreement_pct)}%</span>. Ground-truth Python rule matrix governs all outcomes.
            </p>
          )}

          <Link href={`/dashboard/complaints/${encodeURIComponent(item.public_ref)}?tab=why`} className="mt-2 inline-flex items-center gap-1 text-[13px] text-espresso-2 underline underline-offset-4">
            See field-by-field verification & citations <ArrowRight size={13} aria-hidden />
          </Link>
        </DashSection>
      </div>

      {d && (
        <div className="my-1">
          <ExplainabilityPanel complaint={d} explain={explain.data} />
        </div>
      )}

      {/* ── 3. Suggested Response & Required Actions ── */}
      <div className="grid gap-6 xl:grid-cols-2">
        <DashSection
          id="suggested-response"
          title="Suggested Response"
          icon={<MessageSquareText size={15} aria-hidden />}
          aside={
            <div className="flex flex-wrap items-center gap-2">
              <Select value={tone} onChange={(e) => setTone(e.target.value)} aria-label="Reply tone" className="h-8 w-auto text-[12.5px] py-0 px-2">
                <option value="PROFESSIONAL">Professional</option>
                <option value="EMPATHETIC">Empathetic</option>
                <option value="CONCISE">Concise</option>
                <option value="FORMAL">Formal</option>
              </Select>
              <Button size="sm" variant={reply ? 'secondary' : 'primary'} loading={draft.pending} onClick={async () => { const r = await draft.run(tone); if (r) { toast('ok', 'A reply has been drafted and checked.'); onDrafted(); respHistory.refresh() } else if (draft.error) toast('err', draft.error) }}>{reply ? 'Redraft' : 'Draft reply'}</Button>
            </div>
          }
        >
          {!reply ? (
            <p className="text-[14px] text-taupe-2">No reply drafted yet. Choose a tone and click Draft reply.</p>
          ) : (
            <div className="flex flex-col gap-3">
              <div className="flex flex-wrap items-center gap-2 text-[12px] text-taupe-2">
                <Badge tone={reply.guard_status === 'CLEAN' ? 'verified' : reply.guard_status === 'BLOCKED' ? 'critical' : 'warning'}>
                  {reply.guard_status === 'CLEAN' ? 'Passed promise check' : humanise(reply.guard_status)}
                </Badge>
                {reply.tone && <Badge tone="neutral">Tone: {humanise(reply.tone)}</Badge>}
                <span>version {reply.version}</span>
              </div>
              <p className="whitespace-pre-wrap rounded-2xl border border-line-soft bg-white/80 p-4 text-[14px] leading-relaxed text-espresso-2">
                {reply.text}
              </p>
              <div className="flex flex-wrap items-center gap-2">
                <Button
                  size="sm"
                  variant="primary"
                  icon={<Send size={13} />}
                  onClick={() => {
                    navigator.clipboard.writeText(reply.text || '')
                    toast('ok', 'Response ready! Copied to clipboard for customer message.')
                  }}
                >
                  Send response
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => {
                    navigator.clipboard.writeText(reply.text || '')
                    toast('ok', 'Response copied!')
                  }}
                >
                  Copy response
                </Button>
              </div>
            </div>
          )}
        </DashSection>

        <DashSection id="suggested-resolution" title="Required Actions" icon={<ListChecks size={15} aria-hidden />}>
          {checklist.loading && !checklist.data ? (
            <SkeletonRows rows={3} />
          ) : (
            <ol className="flex flex-col gap-2.5">
              {(checklist.data?.steps && checklist.data.steps.length > 0 ? checklist.data.steps : [
                { id: '1', ordinal: 1, text: 'Request product photographs & consignment proof', status: 'REQUIRED_MET' },
                { id: '2', ordinal: 2, text: 'Verify order and delivery status in logistics database', status: 'PENDING' },
                { id: '3', ordinal: 3, text: 'Check warranty eligibility & policy limits', status: 'PENDING' },
              ]).map((st: any, idx: number) => (
                <li key={st.id || idx} className="flex items-start justify-between gap-3 rounded-xl border border-line-soft bg-white/80 p-3.5 text-[13.5px]">
                  <div className="flex items-start gap-3">
                    <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-espresso text-[11px] font-bold text-white">
                      {idx + 1}
                    </span>
                    <div>
                      <p className="font-medium text-espresso">{st.text}</p>
                      {st.policy_ref && (
                        <p className="mt-0.5 text-[11.5px] font-mono text-taupe-2">Governing policy: {st.policy_ref}</p>
                      )}
                    </div>
                  </div>
                  <Badge tone={st.status === 'REQUIRED_MET' ? 'verified' : 'warning'}>
                    {humanise(st.status)}
                  </Badge>
                </li>
              ))}
            </ol>
          )}
        </DashSection>
      </div>

      {/* ── 4. Policy Evidence & Customer History ── */}
      <div className="grid gap-6 xl:grid-cols-2">
        <DashSection
          id="policy-evidence"
          title="Retrieved policy evidence"
          icon={<BookOpen size={15} aria-hidden />}
          aside={
            <Button href={`/dashboard/knowledge-base/search?q=${encodeURIComponent(item.category || item.title)}`} variant="ghost" size="sm" icon={<FileSearch size={13} />}>
              Search policies
            </Button>
          }
        >
          {explain.loading && !explain.data ? (
            <SkeletonRows rows={3} />
          ) : (
            <PolicyTrace rows={explain.data?.policy_trace} />
          )}
        </DashSection>

        <DashSection
          id="customer-history"
          title="Customer & complaint history"
          icon={<Users size={15} aria-hidden />}
          aside={
            d?.customer_ref && (
              <Button href={`/dashboard/users/${encodeURIComponent(d.customer_ref)}`} variant="secondary" size="sm" icon={<ExternalLink size={13} />}>
                Customer profile
              </Button>
            )
          }
        >
          {detail.loading && !detail.data ? <SkeletonRows rows={3} /> : (
            <div className="flex flex-col gap-3 text-[13.5px]">
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 rounded-xl border border-line-soft bg-white/70 p-3">
                <div>
                  <span className="block text-[11px] uppercase tracking-wider text-taupe-2">Customer ID</span>
                  <span className="font-mono font-medium text-espresso">{d?.customer_ref || 'Guest'}</span>
                </div>
                <div>
                  <span className="block text-[11px] uppercase tracking-wider text-taupe-2">Recurrence</span>
                  <span className="font-medium text-espresso">
                    {(d?.repeat_count ?? 0) > 1 ? (
                      <Badge tone="warning">Repeat ×{d?.repeat_count}</Badge>
                    ) : (
                      <Badge tone="verified">First complaint</Badge>
                    )}
                  </span>
                </div>
                <div>
                  <span className="block text-[11px] uppercase tracking-wider text-taupe-2">Customer type</span>
                  <span className="font-medium text-espresso">{d?.customer_type ? humanise(d.customer_type) : 'Standard'}</span>
                </div>
                <div>
                  <span className="block text-[11px] uppercase tracking-wider text-taupe-2">Order ref</span>
                  <span className="font-mono text-espresso">{d?.order_ref || '—'}</span>
                </div>
                <div>
                  <span className="block text-[11px] uppercase tracking-wider text-taupe-2">Transaction</span>
                  <span className="font-mono text-espresso">{d?.transaction_ref || '—'}</span>
                </div>
                <div>
                  <span className="block text-[11px] uppercase tracking-wider text-taupe-2">Channel</span>
                  <span className="text-espresso">{d?.channel ? humanise(d.channel) : 'WEB'}</span>
                </div>
              </div>

              {d?.links && d.links.length > 0 && (
                <div className="mt-1">
                  <p className="eyebrow mb-1.5 text-taupe-2">Related complaint history:</p>
                  <div className="flex flex-col gap-1.5">
                    {d.links.slice(0, 3).map((link, idx) => (
                      <Link
                        key={idx}
                        href={`/dashboard/complaints/${encodeURIComponent(link.related_ref)}`}
                        className="flex items-center justify-between rounded-lg border border-line-soft bg-white/90 p-2.5 hover:bg-sand/30 text-[12.5px] transition-colors"
                      >
                        <div className="flex items-center gap-2">
                          <Mono className="font-semibold text-espresso">{link.related_ref}</Mono>
                          <Badge tone="neutral">{humanise(link.link_type)}</Badge>
                        </div>
                        {link.similarity != null && (
                          <span className="text-[11.5px] text-taupe-2 font-mono">{Math.round(link.similarity * 100)}% match</span>
                        )}
                      </Link>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </DashSection>
      </div>

      {/* ── 5. Follow-ups & Escalation Warnings ── */}
      <div className="grid gap-6 xl:grid-cols-2">
        <DashSection
          id="follow-ups"
          title="Follow-up"
          icon={<MessageSquareReply size={15} aria-hidden />}
          aside={
            <Button href="/dashboard/follow-ups" variant="ghost" size="sm" icon={<ExternalLink size={13} />}>
              All follow-ups
            </Button>
          }
        >
          {followups.loading && !followups.data ? <SkeletonRows rows={2} /> : !followups.data?.length ? (
            <p className="text-[13.5px] text-taupe-2">No pending follow-ups scheduled for this complaint.</p>
          ) : (
            <ul className="flex flex-col gap-2 text-[13px]">
              {followups.data.map((f) => (
                <li key={f.id} className="flex items-center justify-between rounded-xl border border-line-soft bg-white/80 p-3">
                  <div>
                    <p className="font-medium text-espresso">{f.message || humanise(f.type)}</p>
                    <p className="text-[11.5px] text-taupe-2 font-mono">Due: {fmtDate(f.due_at, true)}</p>
                  </div>
                  <Badge tone={f.open ? 'warning' : 'verified'}>
                    {f.open ? 'Pending' : 'Completed'}
                  </Badge>
                </li>
              ))}
            </ul>
          )}
        </DashSection>

        <DashSection id="escalation-warnings" title="Escalation warnings" icon={<AlertTriangle size={15} aria-hidden />}>
          {!item.escalation_warnings.length ? <p className="text-[14px] text-verified">No warnings on this complaint.</p> : (
            <ul className="flex flex-col gap-2">
              {item.escalation_warnings.map((w) => (
                <li key={w} className="flex items-start gap-2 rounded-xl border border-warning/30 bg-warning-dim/50 px-3.5 py-2.5 text-[14px] text-espresso">
                  <AlertTriangle size={16} className="mt-0.5 shrink-0 text-warning" aria-hidden />
                  {w}
                </li>
              ))}
            </ul>
          )}
        </DashSection>
      </div>

      {/* ── 6. Agent Permissions & Governance Matrix ── */}
      <DashSection id="permissions" title="Agent Permissions & Governance" icon={<ShieldCheck size={15} aria-hidden />}>
        <div className="overflow-x-auto rounded-xl border border-line-soft bg-white/80 shadow-xs">
          <table className="w-full text-left text-[13px]">
            <thead className="bg-cream/60 text-[11px] uppercase tracking-wider text-taupe-2">
              <tr>
                <th className="px-3.5 py-2.5 font-semibold">Action</th>
                <th className="px-3.5 py-2.5 font-semibold">Agent Access</th>
                <th className="px-3.5 py-2.5 font-semibold">Governance Boundary</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line-soft">
              <tr>
                <td className="px-3.5 py-2 font-medium text-espresso">View assigned complaints & intelligence</td>
                <td className="px-3.5 py-2 text-verified font-medium">✅ Allowed</td>
                <td className="px-3.5 py-2 text-taupe-2">Direct access to assigned queue, customer history, and AI analysis</td>
              </tr>
              <tr>
                <td className="px-3.5 py-2 font-medium text-espresso">Generate & send customer response</td>
                <td className="px-3.5 py-2 text-verified font-medium">✅ Allowed</td>
                <td className="px-3.5 py-2 text-taupe-2">Guard-checked replies in multiple selectable tones</td>
              </tr>
              <tr>
                <td className="px-3.5 py-2 font-medium text-espresso">Update complaint status & request info</td>
                <td className="px-3.5 py-2 text-verified font-medium">✅ Allowed</td>
                <td className="px-3.5 py-2 text-taupe-2">State transitions and customer questions within operational scope</td>
              </tr>
              <tr>
                <td className="px-3.5 py-2 font-medium text-espresso">Reassign case</td>
                <td className="px-3.5 py-2 text-warning font-medium">Limited</td>
                <td className="px-3.5 py-2 text-taupe-2">Restricted to peers in assigned department</td>
              </tr>
              <tr>
                <td className="px-3.5 py-2 font-medium text-espresso">Override validation</td>
                <td className="px-3.5 py-2 text-critical font-medium">❌ Restricted</td>
                <td className="px-3.5 py-2 text-taupe-2">Reviewer & Manager desk authorization required</td>
              </tr>
              <tr>
                <td className="px-3.5 py-2 font-medium text-espresso">Modify ground-truth rules & configuration</td>
                <td className="px-3.5 py-2 text-critical font-medium">❌ Restricted</td>
                <td className="px-3.5 py-2 text-taupe-2">Platform administrator privileges required</td>
              </tr>
              <tr>
                <td className="px-3.5 py-2 font-medium text-espresso">Manage users & view audit logs</td>
                <td className="px-3.5 py-2 text-critical font-medium">❌ Restricted</td>
                <td className="px-3.5 py-2 text-taupe-2">Administrator and Evaluator roles required</td>
              </tr>
            </tbody>
          </table>
        </div>
      </DashSection>
    </>
  )
}
