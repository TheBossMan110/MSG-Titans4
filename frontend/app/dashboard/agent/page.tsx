'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'
import { AlertTriangle, ArrowRight, Gauge, LayoutDashboard, MessageSquareText, ShieldCheck, Sparkles, Tag, Smile, Inbox, Trophy } from 'lucide-react'
import { AppShell } from '@/components/layout/app-shell'
import { useAuth } from '@/lib/auth-context'
import { analytics, complaints, organisation, type AgentItem } from '@/lib/api'
import { useAction, useApi, fmtRelative } from '@/lib/use-api'
import { AiBadge, Badge, Button, RuleBadge, humanise, priorityTone, verificationTone } from '@/components/ui/primitives'
import { Select } from '@/components/ui/forms'
import { Stat } from '@/components/ui/data'
import { Empty, ErrorState, SkeletonRows, useToast } from '@/components/ui/feedback'
import { DashSection } from '@/components/app/dashboard-bits'
import { HOME, VIEW_LABEL, viewOf } from '@/lib/roles'
import { cn } from '@/lib/utils'

const OVERSIGHT = ['manager', 'admin', 'evaluator']
const SENTIMENT_TONE: Record<string, 'critical' | 'warning' | 'neutral' | 'verified'> = {
  STRONGLY_NEGATIVE: 'critical', NEGATIVE: 'warning', NEUTRAL: 'neutral', POSITIVE: 'verified',
}

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
  const items = q.data?.complaints ?? []
  const current = items.find((i) => i.public_ref === selected) ?? items[0]
  useEffect(() => { setSelected(null) }, [team])
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
          <DashSection id="assigned" title="Assigned complaints" icon={<Inbox size={15} aria-hidden />}>
            <div className="mb-5 grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-4">
              <Stat label="In your queue" value={q.data?.counts.total} />
              <Stat label="Assigned to you" value={q.data?.counts.assigned_to_me} />
              <Stat label="With warnings" value={q.data?.counts.with_warnings} tone={q.data?.counts.with_warnings ? 'warning' : 'neutral'} />
              <Stat label="Needing review" value={q.data?.counts.needs_review} />
            </div>
            {!q.data ? <SkeletonRows rows={6} /> : !items.length ? <Empty title="Nothing in your queue" body="New complaints for your team appear here as soon as they are analysed." /> : (
              <div className="overflow-x-auto rounded-2xl border border-line-soft">
                <table className="w-full min-w-[760px] border-separate border-spacing-0 text-[13.5px]">
                  <thead className="bg-cream/70 text-left">
                    <tr className="[&>th]:px-3 [&>th]:py-2.5 [&>th]:text-[11px] [&>th]:font-semibold [&>th]:uppercase [&>th]:tracking-[0.1em] [&>th]:text-taupe-2">
                      <th>Complaint</th><th>Category</th><th>Priority</th><th>Sentiment</th><th>Validation</th><th>Warnings</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((i) => (
                      <tr key={i.public_ref} onClick={() => { setSelected(i.public_ref); document.getElementById('category')?.scrollIntoView({ behavior: 'smooth', block: 'start' }) }}
                        className={cn('cursor-pointer [&>td]:border-t [&>td]:border-line-soft [&>td]:px-3 [&>td]:py-2.5 hover:bg-white/70', current?.public_ref === i.public_ref && 'bg-white')}>
                        <td className="max-w-[280px]"><span className="block font-mono text-[12px] text-taupe-2">{i.public_ref}{i.assigned_to_me && ' · yours'}</span><span className="block truncate font-medium text-espresso">{i.title}</span></td>
                        <td>{i.category ?? '—'}</td>
                        <td>{i.priority ? <Badge tone={priorityTone(i.priority)}>{i.priority}</Badge> : '—'}</td>
                        <td>{i.sentiment ? <Badge tone={SENTIMENT_TONE[i.sentiment] ?? 'neutral'}>{humanise(i.sentiment)}</Badge> : '—'}</td>
                        <td>{i.validation.outcome ? <Badge tone={verificationTone(i.validation.outcome)}>{humanise(i.validation.outcome)}</Badge> : '—'}</td>
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

/** The selected complaint, one section per thing the SRS says an agent sees. */
function Focus({ item, onDrafted }: { item: AgentItem; onDrafted: () => void }) {
  const toast = useToast()
  const draft = useAction(() => complaints.draftResponse(item.public_ref))
  const reply = item.suggested_response
  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-line bg-white/70 px-5 py-4">
        <div className="min-w-0">
          <p className="font-mono text-[12.5px] text-taupe-2">{item.public_ref} · {humanise(item.status)}{item.due_at ? ` · due ${fmtRelative(item.due_at)}` : ''}</p>
          <p className="truncate text-[16px] font-medium text-espresso">{item.title}</p>
        </div>
        <Button href={`/dashboard/complaints/${encodeURIComponent(item.public_ref)}`} variant="secondary" size="sm" arrow>Open complaint</Button>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <DashSection id="category" title="Complaint category" icon={<Tag size={15} aria-hidden />}>
          <p className="text-[18px] font-medium text-espresso">{item.category ?? 'Not classified'}</p>
          {item.team && <p className="mt-1 text-[13px] text-taupe-2">Handled by {item.team}</p>}
        </DashSection>
        <DashSection id="priority" title="Priority" icon={<Gauge size={15} aria-hidden />}>
          <div className="flex items-center gap-2">{item.priority ? <Badge tone={priorityTone(item.priority)}>{item.priority}</Badge> : '—'}{item.urgency && <span className="text-[14px] text-espresso-2">{humanise(item.urgency)} urgency</span>}</div>
        </DashSection>
        <DashSection id="sentiment" title="Sentiment" icon={<Smile size={15} aria-hidden />}>
          {item.sentiment ? <Badge tone={SENTIMENT_TONE[item.sentiment] ?? 'neutral'}>{humanise(item.sentiment)}</Badge> : <p className="text-taupe-2">Not measured</p>}
          <p className="mt-2 text-[13px] text-taupe-2">How the customer sounds — set the tone of your reply by it.</p>
        </DashSection>
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <DashSection id="recommendation" title="GenAI recommendation" icon={<Sparkles size={15} aria-hidden />} aside={<AiBadge>AI</AiBadge>}>
          {!item.recommendation ? <p className="text-[14px] text-taupe-2">The AI was not available for this complaint; the rules decided alone.</p> : (
            <div className="flex flex-col gap-3 text-[14px] text-espresso-2">
              {item.summary && <p className="leading-relaxed">{item.summary}</p>}
              {item.recommendation.primary_issue && <p><span className="text-taupe-2">Main issue: </span>{item.recommendation.primary_issue}</p>}
              {item.recommendation.steps.length > 0 && (
                <ol className="list-decimal space-y-1 pl-5">{item.recommendation.steps.map((s, n) => <li key={n}>{s}</li>)}</ol>
              )}
              {item.recommendation.escalation_reason && <p className="text-[13px] text-taupe-2">Why escalate: {item.recommendation.escalation_reason}</p>}
            </div>
          )}
        </DashSection>
        <DashSection id="validation" title="Validation status" icon={<ShieldCheck size={15} aria-hidden />} aside={<RuleBadge>rules</RuleBadge>}>
          <div className="flex flex-wrap items-center gap-2">
            {item.validation.outcome ? <Badge tone={verificationTone(item.validation.outcome)}>{humanise(item.validation.outcome)}</Badge> : '—'}
            {item.validation.requires_review && <Badge tone="warning">Needs a person to review</Badge>}
          </div>
          {item.validation.agreement_pct != null && <p className="mt-3 text-[14px] text-espresso-2">The AI and the rules agreed on {Math.round(item.validation.agreement_pct)}% of the fields. Where they differed, the rules’ answer is the one in force.</p>}
          <Link href={`/dashboard/complaints/${encodeURIComponent(item.public_ref)}`} className="mt-3 inline-flex items-center gap-1 text-[13.5px] text-espresso-2 underline underline-offset-4">See field by field <ArrowRight size={13} aria-hidden /></Link>
        </DashSection>
      </div>

      <DashSection id="suggested-response" title="Suggested response" icon={<MessageSquareText size={15} aria-hidden />}
        aside={<Button size="sm" variant={reply ? 'secondary' : 'primary'} loading={draft.pending} onClick={async () => { const r = await draft.run(); if (r) { toast('ok', 'A reply has been drafted and checked.'); onDrafted() } else if (draft.error) toast('err', draft.error) }}>{reply ? 'Redraft' : 'Draft a reply'}</Button>}>
        {!reply ? <p className="text-[14px] text-taupe-2">No reply drafted yet. The draft is written from what the rules confirmed, then checked so it never promises what policy does not allow.</p> : (
          <div className="flex flex-col gap-3">
            <div className="flex flex-wrap items-center gap-2 text-[12.5px] text-taupe-2"><Badge tone={reply.guard_status === 'CLEAN' ? 'verified' : reply.guard_status === 'BLOCKED' ? 'critical' : 'warning'}>{reply.guard_status === 'CLEAN' ? 'Passed the promise check' : humanise(reply.guard_status)}</Badge> version {reply.version}</div>
            <p className="whitespace-pre-wrap rounded-2xl border border-line-soft bg-white/80 p-4 text-[14.5px] leading-relaxed text-espresso-2">{reply.text}</p>
          </div>
        )}
      </DashSection>

      <DashSection id="escalation-warnings" title="Escalation warnings" icon={<AlertTriangle size={15} aria-hidden />}>
        {!item.escalation_warnings.length ? <p className="text-[14px] text-verified">No warnings on this complaint.</p> : (
          <ul className="flex flex-col gap-2">
            {item.escalation_warnings.map((w) => (
              <li key={w} className="flex items-start gap-2 rounded-xl border border-warning/30 bg-warning-dim/50 px-3.5 py-2.5 text-[14px] text-espresso"><AlertTriangle size={16} className="mt-0.5 shrink-0 text-warning" aria-hidden />{w}</li>
            ))}
          </ul>
        )}
      </DashSection>
    </>
  )
}
