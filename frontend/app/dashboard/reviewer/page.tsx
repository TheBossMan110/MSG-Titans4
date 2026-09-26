'use client'

import Link from 'next/link'
import { ArrowRight, ClipboardCheck, GitCompare, History, Inbox, ScrollText, ShieldAlert, Siren, TriangleAlert, Waypoints } from 'lucide-react'
import type { ReactNode } from 'react'
import { AppShell } from '@/components/layout/app-shell'
import { useAuth } from '@/lib/auth-context'
import { review, type Brief } from '@/lib/api'
import { useApi, fmtRelative } from '@/lib/use-api'
import { Badge, Button, humanise, priorityTone } from '@/components/ui/primitives'
import { Stat } from '@/components/ui/data'
import { Empty, ErrorState, SkeletonRows } from '@/components/ui/feedback'
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
  policy: 'The policies contradict each other, a rule conflicts, or no policy supports the decision.',
  escalation: 'Whether or how far to escalate is not clear from the rules.',
  adversarial: 'Prompt injection, manipulation or a sensitive complaint. Handled as data; a person confirms.',
  validation: 'The AI did not answer, no rule matched, or the response guard blocked the reply.',
  ambiguous: 'The complaint can be read more than one way.',
}

/**
 * The reviewer is the quality-control desk between the two pipelines and the
 * agent. Nothing here trusts the AI by default: each case says why a person
 * is needed, and every decision -- with the original recommendation beside it
 * -- stays in the audit trail.
 */
function ReviewerDashboard() {
  const { user } = useAuth()
  const q = useApi(() => review.overview(), [], true, { live: true })
  const d = q.data

  return (
    <div className="flex flex-col gap-8">
      <section className="mesh-banner grain relative overflow-hidden rounded-[var(--radius-xl)] px-6 py-8 text-ink-on-dark md:px-10 md:py-10">
        <div className="relative z-[1] flex flex-wrap items-end justify-between gap-6">
          <div className="animate-rise">
            <p className="eyebrow mb-3 text-sand-2">Reviewer dashboard</p>
            <h1 className="display text-h1 text-ink-on-dark">{user?.full_name}</h1>
            <p className="mt-3 max-w-[58ch] text-[15.5px] text-ink-on-dark/80">
              Cases the system will not settle alone. Compare the AI with the rules, check the policy, then approve, modify, reclassify, reassign or escalate.
            </p>
          </div>
          <Button href="/dashboard/review" variant="onDark" icon={<Inbox size={15} aria-hidden />}>Open the review queue</Button>
        </div>
      </section>

      {q.error ? <ErrorState message={q.error} onRetry={q.refresh} /> : (
        <>
          <DashSection id="review-overview" title="Review overview" icon={<ClipboardCheck size={15} aria-hidden />}>
            <div className="grid grid-cols-2 gap-x-6 gap-y-5 sm:grid-cols-3 xl:grid-cols-6">
              <Stat label="Waiting for review" value={d?.open} size="lg" tone={d?.open ? 'warning' : 'neutral'} />
              <Stat label="Nobody has claimed" value={d?.unclaimed} />
              <Stat label="Claimed by me" value={d?.claimed_by_me} />
              <Stat label="My decisions today" value={d?.totals.today} />
              <Stat label="My decisions in total" value={d?.totals.actions} />
              <Stat label="Of which overrides" value={d?.totals.overrides} tone={d?.totals.overrides ? 'rule' : 'neutral'} />
            </div>
          </DashSection>

          <div className="grid gap-6 xl:grid-cols-2">
            {(d?.groups ?? []).map((g) => (
              <DashSection key={g.key} id={g.key} title={g.label} icon={GROUP_ICON[g.key]}
                aside={<Badge tone={g.count ? 'warning' : 'verified'}>{g.count} waiting</Badge>}>
                <p className="mb-3 text-[13.5px] leading-relaxed text-taupe-2">{GROUP_HELP[g.key]}</p>
                {!g.items.length ? <Empty title="Nothing waiting" body="No case in the queue for this reason." /> : (
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

          <div className="grid gap-6 xl:grid-cols-2">
            <DashSection id="my-queue" title="Claimed by me" icon={<Inbox size={15} aria-hidden />}>
              {!d ? <SkeletonRows rows={3} /> : !d.my_queue.length ? (
                <Empty title="Nothing claimed" body="Claim a case from the review queue to work on it here." />
              ) : <CaseList rows={d.my_queue} />}
            </DashSection>
            <DashSection id="history" title="My review history" icon={<History size={15} aria-hidden />}>
              {!d ? <SkeletonRows rows={4} /> : !d.history.length ? (
                <Empty title="No decisions yet" body="Your approvals, overrides and comments appear here, each with the original recommendation kept in the audit trail." />
              ) : (
                <ul className="divide-y divide-line-soft">
                  {d.history.map((h, i) => (
                    <li key={`${h.public_ref}-${h.at}-${i}`}>
                      <Link href={`/dashboard/complaints/${encodeURIComponent(h.public_ref)}`} className="flex items-center gap-3 py-2.5 hover:bg-white/50">
                        <Badge tone={h.is_override ? 'rule' : 'neutral'}>{humanise(h.action)}{h.is_override ? ' · override' : ''}</Badge>
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-[14px] text-espresso">{h.title}</span>
                          <span className="block text-[12.5px] text-taupe-2"><span className="font-mono">{h.public_ref}</span> · {fmtRelative(h.at)}{h.note ? ` · “${h.note.slice(0, 60)}”` : ''}</span>
                        </span>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </DashSection>
          </div>
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
