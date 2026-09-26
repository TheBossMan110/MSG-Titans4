'use client'

import { useState } from 'react'
import Link from 'next/link'
import {
  AlertTriangle, ArrowDown, ArrowRight, CheckCircle2, ChevronRight, ClipboardCheck,
  CornerDownRight, ExternalLink, FileSearch, FileText, Filter, GitCompare, History,
  Inbox, Info, LayoutDashboard, ListChecks, Lock, Mail, MessageSquareReply,
  RefreshCw, RotateCcw, Scale, ScrollText, ShieldAlert, ShieldCheck, Siren,
  Sparkles, TriangleAlert, UserCheck, UserRound, Users, Waypoints, XCircle,
} from 'lucide-react'
import type { ReactNode } from 'react'
import { AppShell } from '@/components/layout/app-shell'
import { useAuth } from '@/lib/auth-context'
import { review, type Brief, type S } from '@/lib/api'
import { useApi, fmtRelative, fmtDate } from '@/lib/use-api'
import { Badge, Button, Mono, humanise, priorityTone, statusTone, verificationTone } from '@/components/ui/primitives'
import { Stat } from '@/components/ui/data'
import { Card, PanelHeader } from '@/components/ui/surfaces'
import { Empty, ErrorState, SkeletonRows, useToast } from '@/components/ui/feedback'
import { DashSection } from '@/components/app/dashboard-bits'

export default function ReviewerDashboardPage() {
  return (
    <AppShell eyebrow="Reviewer dashboard" roles={['reviewer', 'manager', 'admin', 'evaluator']} wide>
      <ReviewerDashboard />
    </AppShell>
  )
}

const GROUP_ICON: Record<string, ReactNode> = {
  disagreement: <GitCompare size={15} aria-hidden />,
  policy: <ScrollText size={15} aria-hidden />,
  escalation: <Siren size={15} aria-hidden />,
  adversarial: <ShieldAlert size={15} aria-hidden />,
  validation: <TriangleAlert size={15} aria-hidden />,
  ambiguous: <Waypoints size={15} aria-hidden />,
}

const GROUP_HELP: Record<string, string> = {
  disagreement: 'The AI and the rule engine reached different answers. Decide which is right, or correct both.',
  policy: 'The policies contradict each other, a rule conflicts, or no active policy citation supports the decision.',
  escalation: 'Whether or how far to escalate is not clear from the rules, or requires human-in-the-loop review.',
  adversarial: 'Prompt injection, adversarial data or a sensitive complaint. Handled as raw data; a reviewer decides.',
  validation: 'The AI did not answer, no rule matched, or the response guard blocked the draft reply.',
  ambiguous: 'The complaint text can be read more than one way and cannot be safely automated.',
}

function reasonBadge(r: string) {
  const norm = r.toUpperCase()
  if (norm.includes('DISAGREE') || norm.includes('AI') || norm === 'GENAI_PYTHON_DISAGREEMENT') {
    return <Badge tone="critical"><GitCompare size={12} className="mr-1 inline" />AI ≠ Python</Badge>
  }
  if (norm.includes('CONTRADICTION') || norm.includes('CONFLICT') || norm === 'POLICY_CONTRADICTION') {
    return <Badge tone="warning"><Scale size={12} className="mr-1 inline" />Policy Conflict</Badge>
  }
  if (norm.includes('SUPPORT_MISSING') || norm.includes('EVIDENCE') || norm === 'POLICY_SUPPORT_MISSING') {
    return <Badge tone="warning"><ScrollText size={12} className="mr-1 inline" />Missing Evidence</Badge>
  }
  if (norm.includes('ESCALAT') || norm === 'ESCALATION_UNCLEAR') {
    return <Badge tone="warning"><Siren size={12} className="mr-1 inline" />Escalation Issue</Badge>
  }
  if (norm.includes('SENSITIVE') || norm.includes('INJECTION') || norm.includes('ADVERSARIAL')) {
    return <Badge tone="critical"><ShieldAlert size={12} className="mr-1 inline" />Safety Case</Badge>
  }
  if (norm.includes('GUARD') || norm.includes('UNMATCHED') || norm.includes('UNAVAILABLE')) {
    return <Badge tone="neutral"><TriangleAlert size={12} className="mr-1 inline" />Validation Failure</Badge>
  }
  return <Badge tone="neutral">{humanise(r)}</Badge>
}

/**
 * Reviewer Dashboard (SRS Requirements & Decision-Review Layer)
 * Quality-control desk between AI + Python pipelines and operational support agents.
 */
function ReviewerDashboard() {
  const { user } = useAuth()
  const q = useApi(() => review.overview(), [], true, { live: true })
  const queueData = useApi(() => review.queue({ page: 1, size: 50 }), [], true, { live: true })
  const [filterReason, setFilterReason] = useState<string>('all')

  const d = q.data
  const qItems = queueData.data?.items ?? []

  const filteredQueue = qItems.filter((item) => {
    if (filterReason === 'all') return true
    if (filterReason === 'mine') return item.assigned_to === user?.id
    if (filterReason === 'disagreement') return (item.reasons ?? []).some((r) => r.includes('DISAGREE'))
    if (filterReason === 'policy') return (item.reasons ?? []).some((r) => r.includes('POLICY') || r.includes('CONFLICT'))
    if (filterReason === 'escalation') return (item.reasons ?? []).some((r) => r.includes('ESCALAT'))
    if (filterReason === 'adversarial') return (item.reasons ?? []).some((r) => r.includes('SENSITIVE') || r.includes('INJECTION'))
    if (filterReason === 'validation') return (item.reasons ?? []).some((r) => r.includes('GUARD') || r.includes('UNMATCH') || r.includes('UNAVAIL'))
    return true
  })

  return (
    <div className="flex flex-col gap-8">
      {/* ── Top Mesh Banner ── */}
      <section className="mesh-banner grain relative overflow-hidden rounded-[var(--radius-xl)] px-6 py-8 text-ink-on-dark md:px-10 md:py-10">
        <div className="relative z-[1] flex flex-wrap items-end justify-between gap-6">
          <div className="animate-rise">
            <p className="eyebrow mb-3 text-sand-2">Reviewer Dashboard · Quality Control Desk</p>
            <h1 className="display text-h1 text-ink-on-dark">{user?.full_name}</h1>
            <p className="mt-3 max-w-[62ch] text-[15.5px] leading-relaxed text-ink-on-dark/80">
              The decision-review layer between AI + Python validation and operational support.
              Never trusts AI alone: compare GenAI with deterministic Python rules, verify policy citations,
              and record all decisions with immutable audit trail preservation.
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            <Button href="/dashboard/review" variant="onDark" icon={<Inbox size={15} aria-hidden />}>
              Full Review Queue
            </Button>
            <Button href="/dashboard/audit" variant="secondary" icon={<FileText size={15} aria-hidden />}>
              Audit Trail
            </Button>
          </div>
        </div>
      </section>

      {q.error ? <ErrorState message={q.error} onRetry={q.refresh} /> : (
        <>
          {/* ── 1. Review Overview ── */}
          <DashSection id="review-overview" title="Review Overview" icon={<ClipboardCheck size={15} aria-hidden />}>
            <div className="grid grid-cols-2 gap-x-6 gap-y-5 sm:grid-cols-3 xl:grid-cols-6">
              <Stat label="Waiting for review" value={d?.open} size="lg" tone={d?.open ? 'warning' : 'neutral'} />
              <Stat label="Nobody has claimed" value={d?.unclaimed} />
              <Stat label="Claimed by me" value={d?.claimed_by_me} />
              <Stat label="My decisions today" value={d?.totals.today} />
              <Stat label="My decisions in total" value={d?.totals.actions} />
              <Stat label="Of which overrides" value={d?.totals.overrides} tone={d?.totals.overrides ? 'rule' : 'neutral'} />
            </div>
          </DashSection>

          {/* ── 2. Audit-Preserving Override Architecture (Very Important SRS Requirement) ── */}
          <DashSection
            id="audit"
            title="Audit-Preserving Reviewer Override Pipeline"
            icon={<Scale size={15} aria-hidden />}
            aside={<Badge tone="verified">SRS Compliance Guaranteed</Badge>}
          >
            <div className="rounded-2xl border border-line-soft bg-sand/30 p-5 md:p-6">
              <p className="text-[14px] leading-relaxed text-espresso-2">
                When a reviewer overrides an AI recommendation or rule outcome, the system preserves the complete decision lineage.
                <strong className="text-espresso"> The original AI recommendation and the reviewer decision remain permanently stored in the audit trail.</strong>
              </p>

              <div className="mt-5 grid grid-cols-1 items-center gap-4 md:grid-cols-[1fr_auto_1fr_auto_1fr]">
                {/* Step 1: AI Original */}
                <div className="flex flex-col gap-2 rounded-xl border border-line bg-white/90 p-4 shadow-xs">
                  <div className="flex items-center justify-between">
                    <span className="eyebrow text-[11px] text-ai">Step 1</span>
                    <Badge tone="neutral">Immutable</Badge>
                  </div>
                  <h4 className="font-display font-semibold text-espresso">AI Original Decision</h4>
                  <p className="text-[12.5px] text-taupe-2">
                    Raw LLM response, extracted classification, prompt version, and confidence are saved to <Mono className="text-[11px]">genai_runs</Mono>.
                  </p>
                </div>

                <div className="hidden text-taupe md:block">
                  <ArrowRight size={22} className="mx-auto" />
                </div>
                <div className="text-taupe md:hidden">
                  <ArrowDown size={20} className="mx-auto" />
                </div>

                {/* Step 2: Reviewer Decision */}
                <div className="flex flex-col gap-2 rounded-xl border-2 border-ai/40 bg-ai-wash/40 p-4 shadow-xs">
                  <div className="flex items-center justify-between">
                    <span className="eyebrow text-[11px] text-ai">Step 2</span>
                    <Badge tone="rule">Reviewer Action</Badge>
                  </div>
                  <h4 className="font-display font-semibold text-espresso">Reviewer Decision</h4>
                  <p className="text-[12.5px] text-taupe-2">
                    Reviewer override reason, actor provenance, and before/after diff snapshot are logged to <Mono className="text-[11px]">review_actions</Mono>.
                  </p>
                </div>

                <div className="hidden text-taupe md:block">
                  <ArrowRight size={22} className="mx-auto" />
                </div>
                <div className="text-taupe md:hidden">
                  <ArrowDown size={20} className="mx-auto" />
                </div>

                {/* Step 3: Final Decision */}
                <div className="flex flex-col gap-2 rounded-xl border border-line bg-white/90 p-4 shadow-xs">
                  <div className="flex items-center justify-between">
                    <span className="eyebrow text-[11px] text-verified">Step 3</span>
                    <Badge tone="verified">Reconciled</Badge>
                  </div>
                  <h4 className="font-display font-semibold text-espresso">Final Decision</h4>
                  <p className="text-[12.5px] text-taupe-2">
                    Active complaint state updated with floor verification, visible to agents with full audit trail history.
                  </p>
                </div>
              </div>

              <div className="mt-4 flex flex-wrap items-center justify-between gap-3 pt-3 border-t border-line-soft">
                <span className="text-[12.5px] text-taupe-2">
                  SRS 1.8 #17 & FR lxiii: No hardcoded decisions or silent overwrites. Complete transparency in legal and compliance audits.
                </span>
                <Button href="/dashboard/audit" size="sm" variant="ghost" icon={<ExternalLink size={13} aria-hidden />}>
                  Inspect Audit Trail Logs
                </Button>
              </div>
            </div>
          </DashSection>

          {/* ── 3. Manual Review Queue ── */}
          <DashSection
            id="review-queue"
            title="Manual Review Queue"
            icon={<Inbox size={15} aria-hidden />}
            aside={<Mono className="text-[12px]">{filteredQueue.length} cases waiting</Mono>}
          >
            {/* Filter pills */}
            <div className="mb-4 flex flex-wrap items-center gap-2">
              <span className="text-[12.5px] font-medium text-taupe-2 mr-1">Filter by reason:</span>
              {[
                { id: 'all', label: 'All Cases' },
                { id: 'disagreement', label: 'AI ≠ Python' },
                { id: 'policy', label: 'Policy Conflict' },
                { id: 'escalation', label: 'Escalation Issue' },
                { id: 'adversarial', label: 'Safety Case' },
                { id: 'validation', label: 'Validation Failure' },
                { id: 'mine', label: 'Claimed by me' },
              ].map((pill) => (
                <button
                  key={pill.id}
                  onClick={() => setFilterReason(pill.id)}
                  className={`rounded-full px-3 py-1 text-[12px] font-medium transition-all ${
                    filterReason === pill.id
                      ? 'bg-espresso text-white shadow-xs'
                      : 'border border-line bg-white/70 text-espresso-2 hover:bg-white'
                  }`}
                >
                  {pill.label}
                </button>
              ))}
            </div>

            {/* Table */}
            {queueData.loading && !queueData.data ? (
              <SkeletonRows rows={6} />
            ) : !filteredQueue.length ? (
              <Empty
                title="Queue clean"
                body={filterReason === 'all' ? 'No complaints currently require manual human review.' : 'No cases matching this filter.'}
              />
            ) : (
              <div className="overflow-x-auto rounded-xl border border-line-soft bg-white/90">
                <table className="w-full text-left text-[13.5px]">
                  <thead>
                    <tr className="border-b border-line-soft bg-sand/20 text-[11.5px] uppercase tracking-wider text-taupe-2">
                      <th className="px-4 py-3 font-semibold">Complaint</th>
                      <th className="px-4 py-3 font-semibold">Issue Title</th>
                      <th className="px-4 py-3 font-semibold">Priority</th>
                      <th className="px-4 py-3 font-semibold">Review Reason</th>
                      <th className="px-4 py-3 font-semibold">SLA Status</th>
                      <th className="px-4 py-3 font-semibold">Assignment</th>
                      <th className="px-4 py-3 text-right font-semibold">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line-soft">
                    {filteredQueue.map((item) => {
                      const pri = item.priority_code || 'P3'
                      const isMe = item.assigned_to === user?.id
                      return (
                        <tr key={item.id} className="transition-colors hover:bg-sand/30">
                          <td className="px-4 py-3 font-mono font-medium text-espresso">
                            <Link href={`/dashboard/review/${encodeURIComponent(item.public_ref)}`} className="underline decoration-line underline-offset-4 hover:text-ai">
                              {item.public_ref}
                            </Link>
                          </td>
                          <td className="max-w-[280px] px-4 py-3">
                            <span className="block truncate font-medium text-espresso">{item.title}</span>
                            <span className="text-[11.5px] text-taupe-2">Waiting {fmtRelative(item.created_at)}</span>
                          </td>
                          <td className="px-4 py-3">
                            <Badge tone={priorityTone(pri)} pulse={pri === 'P0'}>
                              {pri}
                            </Badge>
                          </td>
                          <td className="px-4 py-3">
                            <div className="flex flex-wrap gap-1">
                              {(item.reasons?.length ? item.reasons : ['GENAI_PYTHON_DISAGREEMENT']).map((r, i) => (
                                <span key={i}>{reasonBadge(r)}</span>
                              ))}
                            </div>
                          </td>
                          <td className="px-4 py-3">
                            {item.sla_breached ? (
                              <Badge tone="critical">Breached</Badge>
                            ) : item.sla_at_risk ? (
                              <Badge tone="warning">At Risk</Badge>
                            ) : (
                              <Badge tone="verified">On Track</Badge>
                            )}
                          </td>
                          <td className="px-4 py-3 text-[12.5px] text-taupe-2">
                            {isMe ? (
                              <Badge tone="verified">Claimed by you</Badge>
                            ) : item.assigned_to ? (
                              <span>Claimed</span>
                            ) : (
                              <span className="text-sand-3 font-medium">Unassigned</span>
                            )}
                          </td>
                          <td className="px-4 py-3 text-right">
                            <Button href={`/dashboard/review/${encodeURIComponent(item.public_ref)}`} size="sm" variant="primary">
                              Review
                            </Button>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </DashSection>

          {/* ── 4. Themed Review Workspaces (Anchor Links from Nav) ── */}
          <div className="grid gap-6 xl:grid-cols-2">
            {(d?.groups ?? []).map((g) => (
              <DashSection
                key={g.key}
                id={g.key}
                title={g.label}
                icon={GROUP_ICON[g.key]}
                aside={<Badge tone={g.count ? 'warning' : 'verified'}>{g.count} waiting</Badge>}
              >
                <p className="mb-3 text-[13.5px] leading-relaxed text-taupe-2">{GROUP_HELP[g.key]}</p>
                {!g.items.length ? (
                  <Empty title="Nothing waiting" body="No case in the queue for this category." />
                ) : (
                  <CaseList rows={g.items} />
                )}
                {g.count > g.items.length && (
                  <Link href="/dashboard/review" className="mt-3 inline-flex items-center gap-1.5 text-[13px] text-espresso-2 underline underline-offset-4">
                    {g.count - g.items.length} more in the queue <ArrowRight size={13} aria-hidden />
                  </Link>
                )}
              </DashSection>
            ))}
            {!d && Array.from({ length: 4 }).map((_, i) => <SkeletonRows key={i} rows={4} />)}
          </div>

          {/* ── 5. Claimed by Me & History ── */}
          <div className="grid gap-6 xl:grid-cols-2">
            <DashSection id="my-queue" title="Claimed by Me" icon={<Inbox size={15} aria-hidden />}>
              {!d ? (
                <SkeletonRows rows={3} />
              ) : !d.my_queue.length ? (
                <Empty title="Nothing claimed" body="Claim an item from the review queue above to work on it here." />
              ) : (
                <CaseList rows={d.my_queue} />
              )}
            </DashSection>

            <DashSection id="history" title="My Review History" icon={<History size={15} aria-hidden />}>
              {!d ? (
                <SkeletonRows rows={4} />
              ) : !d.history.length ? (
                <Empty title="No decisions yet" body="Your approvals, overrides and comments appear here, each with the original recommendation kept in the audit trail." />
              ) : (
                <ul className="divide-y divide-line-soft">
                  {d.history.map((h, i) => (
                    <li key={`${h.public_ref}-${h.at}-${i}`}>
                      <Link href={`/dashboard/complaints/${encodeURIComponent(h.public_ref)}`} className="flex items-center gap-3 py-2.5 hover:bg-white/50">
                        <Badge tone={h.is_override ? 'rule' : 'neutral'}>
                          {humanise(h.action)}
                          {h.is_override ? ' · override' : ''}
                        </Badge>
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-[14px] text-espresso">{h.title}</span>
                          <span className="block text-[12.5px] text-taupe-2">
                            <span className="font-mono">{h.public_ref}</span> · {fmtRelative(h.at)}
                            {h.note ? ` · “${h.note.slice(0, 60)}”` : ''}
                          </span>
                        </span>
                        <ChevronRight size={14} className="text-taupe" aria-hidden />
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </DashSection>
          </div>

          {/* ── 6. Reviewer Permissions & Governance Table ── */}
          <DashSection id="permissions" title="Reviewer Permissions & System Boundaries" icon={<ShieldCheck size={15} aria-hidden />}>
            <div className="rounded-xl border border-line-soft bg-white/90 p-5">
              <p className="mb-4 text-[13.5px] text-taupe-2">
                The Reviewer is authorized to inspect, approve, override, or reclassify complaint decisions, but cannot modify ground-truth rules, upload official policies, manage platform users, or alter system configuration.
              </p>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {[
                  { action: 'View review queue', ok: true },
                  { action: 'Compare GenAI vs Python', ok: true },
                  { action: 'View policy evidence', ok: true },
                  { action: 'Approve decisions', ok: true },
                  { action: 'Reject decisions', ok: true },
                  { action: 'Modify recommendation', ok: true },
                  { action: 'Reclassify complaint', ok: true },
                  { action: 'Reassign to team/agent', ok: true },
                  { action: 'Escalate case', ok: true },
                  { action: 'Regenerate customer response', ok: true },
                  { action: 'Add review comments', ok: true },
                  { action: 'Override AI recommendation', ok: true },
                  { action: 'Modify ground-truth rules', ok: false },
                  { action: 'Modify/upload policies', ok: false },
                  { action: 'Manage users', ok: false },
                  { action: 'System configuration', ok: false },
                ].map((perm, idx) => (
                  <div
                    key={idx}
                    className={`flex items-center justify-between rounded-lg border p-2.5 text-[13px] ${
                      perm.ok
                        ? 'border-verified/20 bg-verified-wash/30 text-espresso'
                        : 'border-critical/20 bg-critical-wash/20 text-taupe-2'
                    }`}
                  >
                    <span className="font-medium">{perm.action}</span>
                    {perm.ok ? (
                      <span className="flex items-center text-[12px] font-semibold text-verified">
                        <CheckCircle2 size={15} className="mr-1" /> Allowed
                      </span>
                    ) : (
                      <span className="flex items-center text-[12px] font-semibold text-critical">
                        <XCircle size={15} className="mr-1" /> Prohibited
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </DashSection>
        </>
      )}
    </div>
  )
}

function CaseList({ rows }: { rows: Brief[] }) {
  return (
    <ul className="divide-y divide-line-soft">
      {rows.map((r) => (
        <li key={r.public_ref}>
          <Link href={`/dashboard/review/${encodeURIComponent(r.public_ref)}`} className="flex items-center gap-3 py-2.5 hover:bg-white/50">
            {r.priority ? <Badge tone={priorityTone(r.priority)}>{r.priority}</Badge> : null}
            <span className="min-w-0 flex-1">
              <span className="block truncate text-[14px] font-medium text-espresso">{r.title}</span>
              <span className="block text-[12.5px] text-taupe-2">
                <span className="font-mono">{r.public_ref}</span> · waiting {fmtRelative(r.waiting_since ?? r.created_at)}
                {r.claimed_by_me ? ' · claimed by you' : r.queue_status === 'IN_REVIEW' ? ' · being reviewed' : ''}
              </span>
            </span>
            <ArrowRight size={15} className="shrink-0 text-taupe" aria-hidden />
          </Link>
        </li>
      ))}
    </ul>
  )
}
