'use client'

import { useState } from 'react'
import Link from 'next/link'
import { AppShell } from '@/components/layout/app-shell'
import { useAuth } from '@/lib/auth-context'
import { complaints, analytics, admin } from '@/lib/api'
import { useApi, fmtRelative } from '@/lib/use-api'
import { Badge, Button, Mono, humanise, escalationTone, priorityTone } from '@/components/ui/primitives'
import { Card, PanelHeader } from '@/components/ui/surfaces'
import { Table, Th, Td, Tr, Pagination, Ratio } from '@/components/ui/data'
import { Empty, ErrorState, SkeletonRows } from '@/components/ui/feedback'
import { StatusBadge, EscalationPanel } from '@/components/app/complaint-bits'
import { cn } from '@/lib/utils'

const LADDER = ['NONE', 'SUPERVISOR', 'DEPT_MANAGER', 'SPECIALIST', 'COMPLIANCE_REVIEW', 'CRITICAL_MGMT']

export default function EscalationsPage() {
  return (
    <AppShell eyebrow="Escalations" roles={['agent', 'reviewer', 'manager', 'admin', 'evaluator']} wide>
      <Board />
    </AppShell>
  )
}

/**
 * The command board: escalated complaints, the ladder they sit on, and one
 * selected complaint's escalation note. Reads the same complaint register as
 * everything else, filtered to ESCALATED, so there is no second truth.
 */
function Board() {
  const { user } = useAuth()
  const oversight = user && ['manager', 'admin', 'evaluator'].includes(user.role)
  const [page, setPage] = useState(1)
  const [selected, setSelected] = useState<string | null>(null)
  const q = useApi(() => complaints.list({ status: 'ESCALATED', page, size: 25 }), [page])
  const dash = useApi(() => analytics.dashboard(30), [], Boolean(oversight))
  const taxonomy = useApi(() => admin.taxonomy(), [], Boolean(oversight))
  const byLevel = dash.data?.escalation.by_level ?? {}
  const byTrigger = dash.data?.escalation.by_trigger ?? {}
  const rate = dash.data?.escalation.rate

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div><p className="eyebrow mb-1">Command board</p><h1 className="display text-h2">Escalations</h1></div>
        <Button href="/dashboard/complaints?status=ESCALATED" variant="secondary" size="sm">Open in the register</Button>
      </div>

      {oversight && (
        <div className="grid gap-6 lg:grid-cols-[1fr_1fr_1.2fr]">
          <Card>
            <PanelHeader title="The ladder" eyebrow="Last 30 days" />
            <ol className="flex flex-col-reverse gap-2">
              {LADDER.map((lvl, i) => {
                const n = byLevel[lvl] ?? 0
                const max = Math.max(1, ...Object.values(byLevel))
                const name = taxonomy.data?.escalation_levels?.find((e) => e.code === lvl)?.name
                return (
                  <li key={lvl} className="grid grid-cols-[150px_1fr_36px] items-center gap-3 text-[12.5px]">
                    <span className="flex flex-col"><Mono className="text-[11.5px]">{lvl}</Mono>{name && <span className="text-[11px] text-taupe-2">{name}</span>}</span>
                    <span className="h-5 overflow-hidden rounded-full bg-sand"><span className={cn('block h-full rounded-full', i === 5 ? 'bg-critical' : i >= 3 ? 'bg-warning' : 'bg-espresso')} style={{ width: `${(n / max) * 100}%` }} /></span>
                    <Mono className="text-right">{n}</Mono>
                  </li>
                )
              })}
            </ol>
          </Card>
          <Card>
            <PanelHeader title="Triggered by" />
            {dash.loading && !dash.data ? <SkeletonRows rows={3} /> : (
              <ul className="flex flex-col gap-2">{Object.entries(byTrigger).sort((a, b) => b[1] - a[1]).map(([k, v]) => <li key={k} className="flex items-center justify-between text-[13.5px]"><span>{humanise(k)}</span><Mono>{v}</Mono></li>)}{!Object.keys(byTrigger).length && <li className="text-[13.5px] text-taupe-2">No escalations in the window.</li>}</ul>
            )}
            {rate && <div className="mt-5"><Ratio numerator={rate.count ?? 0} denominator={rate.total ?? 0} label="Escalation rate" tone="warning" /></div>}
          </Card>
          <Card tone={selected ? 'ivory' : 'ghost'}>
            <PanelHeader title="Escalation note" eyebrow={selected ? <Mono>{selected}</Mono> : 'Select a row'} />
            {selected ? <EscalationPanel refId={selected} /> : <p className="text-[13.5px] text-taupe-2">Choose a complaint below to read its escalation reason and the note written for the specialist.</p>}
          </Card>
        </div>
      )}

      {q.error ? <ErrorState message={q.error} onRetry={q.refresh} /> : q.loading && !q.data ? <SkeletonRows rows={8} /> : !q.data!.items.length ? <Empty title="Nothing is escalated" body="No complaint currently sits above its department." /> : (
        <>
          <Table>
            <thead><tr><Th>Complaint</Th><Th>Title</Th><Th>Level</Th><Th>Department</Th><Th>Priority</Th><Th>Status</Th><Th align="right">Received</Th><Th /></tr></thead>
            <tbody>
              {q.data!.items.map((c) => (
                <Tr key={c.id} onClick={() => setSelected(c.public_ref)} className={cn(selected === c.public_ref && 'bg-sand/40')}>
                  <Td mono>{c.public_ref}</Td>
                  <Td className="max-w-[360px]"><span className="line-clamp-1">{c.title}</span></Td>
                  <Td><Badge tone={escalationTone(c.escalation_code)}>{humanise(c.escalation_code ?? 'NONE')}</Badge></Td>
                  <Td>{humanise(c.department)}</Td>
                  <Td>{c.priority_code ? <Badge tone={priorityTone(c.priority_code)}>{c.priority_code}</Badge> : '—'}</Td>
                  <Td><StatusBadge status={c.status} /></Td>
                  <Td align="right" className="whitespace-nowrap text-taupe-2">{fmtRelative(c.created_at)}</Td>
                  <Td align="right"><Link href={`/dashboard/complaints/${c.public_ref}`} onClick={(e) => e.stopPropagation()} className="text-[13px] underline decoration-line underline-offset-4">Open</Link></Td>
                </Tr>
              ))}
            </tbody>
          </Table>
          <Pagination page={page} size={25} total={q.data!.total} onPage={setPage} />
        </>
      )}
    </div>
  )
}
