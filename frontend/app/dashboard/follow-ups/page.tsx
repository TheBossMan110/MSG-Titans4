'use client'

import Link from 'next/link'
import { AppShell } from '@/components/layout/app-shell'
import { review } from '@/lib/api'
import { useApi, fmtDate, fmtMinutes } from '@/lib/use-api'
import { Badge, Button, humanise, priorityTone } from '@/components/ui/primitives'
import { Table, Th, Td, Tr, Stat } from '@/components/ui/data'
import { Empty, ErrorState, SkeletonRows } from '@/components/ui/feedback'

export default function FollowUpsPage() {
  return (
    <AppShell eyebrow="Follow-ups" roles={['agent', 'reviewer', 'manager', 'admin', 'evaluator']}>
      <Due />
    </AppShell>
  )
}

function Due() {
  const q = useApi(() => review.dueFollowUps(200))
  const rows = q.data ?? []
  const overdue = rows.filter((r) => (r.overdue_minutes ?? 0) > 0).length
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div><p className="eyebrow mb-1">Commitments</p><h1 className="display text-h2">Follow-ups due</h1></div>
        <Button variant="secondary" size="sm" onClick={q.refresh}>Refresh</Button>
      </div>
      <div className="grid gap-6 rounded-[var(--radius-xl)] border border-line bg-ivory p-6 sm:grid-cols-3">
        <Stat label="Due now" value={q.data ? rows.length : undefined} />
        <Stat label="Overdue" value={q.data ? overdue : undefined} tone={overdue ? 'critical' : 'neutral'} />
        <Stat label="Oldest overdue" value={q.data ? (overdue ? fmtMinutes(Math.max(...rows.map((r) => r.overdue_minutes ?? 0))) : '—') : undefined} />
      </div>
      {q.error ? <ErrorState message={q.error} onRetry={q.refresh} /> : q.loading && !q.data ? <SkeletonRows rows={6} /> : !rows.length ? <Empty title="Nothing due" body="Every promised follow-up is done or not yet due." /> : (
        <Table>
          <thead><tr><Th>Complaint</Th><Th>Priority</Th><Th>Type</Th><Th>Message</Th><Th>Due</Th><Th align="right">Overdue</Th><Th /></tr></thead>
          <tbody>
            {rows.map((f) => (
              <Tr key={f.id}>
                <Td mono><Link href={`/dashboard/complaints/${f.public_ref}`} className="underline decoration-line underline-offset-4">{f.public_ref}</Link></Td>
                <Td>{f.priority ? <Badge tone={priorityTone(f.priority)}>{f.priority}</Badge> : '—'}</Td>
                <Td>{humanise(f.type)}</Td>
                <Td className="max-w-[420px] text-[13px] text-espresso-2">{f.message ?? '—'}</Td>
                <Td className="whitespace-nowrap">{fmtDate(f.due_at)}</Td>
                <Td align="right">{(f.overdue_minutes ?? 0) > 0 ? <Badge tone="critical">{fmtMinutes(f.overdue_minutes)}</Badge> : <Badge tone="warning">due</Badge>}</Td>
                <Td align="right"><Button href={`/dashboard/complaints/${f.public_ref}`} size="sm" variant="ghost">Open</Button></Td>
              </Tr>
            ))}
          </tbody>
        </Table>
      )}
    </div>
  )
}
