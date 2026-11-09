'use client'

import Link from 'next/link'
import type { ReactNode } from 'react'
import { ArrowRight } from 'lucide-react'
import type { Brief } from '@/lib/api'
import { fmtRelative } from '@/lib/use-api'
import { Badge, escalationTone, humanise, priorityTone } from '@/components/ui/primitives'
import { Empty, SkeletonRows } from '@/components/ui/feedback'
import { Card } from '@/components/ui/surfaces'

/** The sections, in the order the SRS lists what administrators see. The sidebar links to each. */
export const ADMIN_SECTIONS: Array<[string, string]> = [
  ['total', 'Total complaints'],
  ['categories', 'Category distribution'],
  ['departments', 'Department distribution'],
  ['priorities', 'Priority levels'],
  ['escalations', 'Escalations'],
  ['resolution', 'Resolution status'],
  ['sla-risks', 'SLA risks'],
  ['mismatches', 'GenAI / Python mismatches'],
  ['manual-review', 'Manual-review cases'],
  ['people', 'Users & sign-ins'],
]

/** The agent dashboard's sections, in the order the SRS lists what agents see. */
export const AGENT_SECTIONS: Array<[string, string]> = [
  ['assigned', 'Assigned complaints'],
  ['category', 'Complaint category'],
  ['priority', 'Priority'],
  ['sentiment', 'Sentiment'],
  ['recommendation', 'GenAI recommendation'],
  ['validation', 'Validation status'],
  ['suggested-response', 'Suggested response'],
  ['escalation-warnings', 'Escalation warnings'],
  ['performance', 'My performance'],
]

/** The reviewer's desk: the queue grouped by why a person is needed, then their own decisions. */
export const REVIEWER_SECTIONS: Array<[string, string]> = [
  ['review-overview', 'Review overview'],
  ['latest', 'Latest complaints'],
  ['disagreement', 'AI and rules disagree'],
  ['policy', 'Policy conflicts'],
  ['escalation', 'Escalation questions'],
  ['adversarial', 'Adversarial cases'],
  ['validation', 'Validation failures'],
  ['ambiguous', 'Ambiguous complaints'],
  ['my-queue', 'Claimed by me'],
  ['history', 'My review history'],
]

/** The manager's view of the operation. */
export const MANAGER_SECTIONS: Array<[string, string]> = [
  ['today', 'Today'],
  ['latest', 'Latest complaints'],
  ['teams', 'Team performance'],
  ['agents', 'Agent workload'],
  ['sla', 'SLA monitoring'],
  ['critical', 'Critical cases'],
  ['escalations', 'Escalations'],
  ['review-status', 'Review status'],
]

/** The customer dashboard's sections, in the order the SRS lists what users see. */
export const USER_SECTIONS: Array<[string, string]> = [
  ['complaint-id', 'Complaint ID'],
  ['status', 'Status'],
  ['submitted', 'Submitted date'],
  ['department', 'Department'],
  ['latest-update', 'Latest update'],
  ['resolution', 'Resolution status'],
]

/**
 * The newest complaints this person may see, in any state, with who has each.
 * Refreshes itself with the page, so a new complaint and every change to it
 * appear without anybody reloading.
 */
export function LatestComplaints({ rows }: { rows: Brief[] | undefined }) {
  if (!rows) return <SkeletonRows rows={5} />
  if (!rows.length) return <Empty title="No complaints yet" body="New complaints appear here the moment they arrive." />
  return (
    <ul className="divide-y divide-line-soft">
      {rows.map((r) => (
        <li key={r.public_ref}>
          <Link href={`/dashboard/complaints/${encodeURIComponent(r.public_ref)}`} className="flex flex-wrap items-center gap-3 py-2.5 hover:bg-white/50">
            {r.priority ? <Badge tone={priorityTone(r.priority)}>{r.priority}</Badge> : null}
            <span className="min-w-[200px] flex-1">
              <span className="block truncate text-[14px] font-medium text-espresso">{r.title}</span>
              <span className="block text-[12.5px] text-taupe-2">
                <span className="font-mono">{r.public_ref}</span> · {r.team ?? 'Being routed'} · {r.assignee ?? 'Not assigned yet'} · {fmtRelative(r.created_at)}
              </span>
            </span>
            {r.escalation && r.escalation !== 'NONE' ? <Badge tone={escalationTone(r.escalation)}>{humanise(r.escalation)}</Badge> : null}
            <Badge tone="neutral">{humanise(r.status)}</Badge>
            <ArrowRight size={15} className="shrink-0 text-taupe" aria-hidden />
          </Link>
        </li>
      ))}
    </ul>
  )
}

/** A dashboard section the sidebar can jump to. */
export function DashSection({ id, title, icon, aside, children }: { id: string; title: string; icon?: ReactNode; aside?: ReactNode; children: ReactNode }) {
  return (
    <Card id={id} tone="glass" radius="xl" className="scroll-mt-24 min-w-0 transition-shadow duration-500 data-[flash=true]:ring-2 data-[flash=true]:ring-espresso/40">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <h2 className="flex items-center gap-2 font-display text-[22px] leading-tight text-espresso">{icon}{title}</h2>
        {aside}
      </div>
      {children}
    </Card>
  )
}

