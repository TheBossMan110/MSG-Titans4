'use client'

import type { ReactNode } from 'react'
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

