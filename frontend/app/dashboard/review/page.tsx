'use client'

import { useState } from 'react'
import Link from 'next/link'
import { AppShell } from '@/components/layout/app-shell'
import { useAuth } from '@/lib/auth-context'
import { review } from '@/lib/api'
import { useApi, useAction, fmtRelative } from '@/lib/use-api'
import { Badge, Button, Mono, humanise, priorityTone } from '@/components/ui/primitives'
import { Select, Checkbox } from '@/components/ui/forms'
import { Table, Th, Td, Tr, Pagination, Ratio } from '@/components/ui/data'
import { Empty, ErrorState, SkeletonRows, useToast } from '@/components/ui/feedback'
import { StatusBadge, OutcomeBadge, EscalationBadge } from '@/components/app/complaint-bits'

export default function ReviewPage() {
  return (
    <AppShell eyebrow="Review queue" roles={['agent', 'reviewer', 'manager', 'admin', 'evaluator']} wide>
      <Queue />
    </AppShell>
  )
}

function Queue() {
  const { user } = useAuth()
  const toast = useToast()
  const [page, setPage] = useState(1)
  const [status, setStatus] = useState('')
  const [mine, setMine] = useState(false)
  const [breached, setBreached] = useState(false)
  const q = useApi(() => review.queue({ page, size: 25, status: status || undefined, assigned_to_me: mine || undefined, breached_only: breached || undefined }), [page, status, mine, breached])
  const stats = useApi(() => review.stats())
  const sweep = useAction(() => review.sweep())
  const isReviewer = user && ['reviewer', 'manager', 'admin'].includes(user.role)
  const canSweep = user && ['manager', 'admin'].includes(user.role)
  const depth = stats.data?.depth ?? {}
  const rate = stats.data?.override_rate as { count?: number; total?: number } | undefined

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div><p className="eyebrow mb-1">Human review</p><h1 className="display text-h2">Queue</h1></div>
        {canSweep && <Button variant="secondary" size="sm" loading={sweep.pending} onClick={async () => { const r = await sweep.run(); if (r) { toast(r.breached?.length ? 'warn' : 'ok', `Swept ${r.checked}: ${r.breached?.length ?? 0} breached, ${r.at_risk?.length ?? 0} at risk, ${r.no_policy ?? 0} without a policy.`); q.refresh() } else if (sweep.error) toast('err', sweep.error) }}>Run SLA sweep</Button>}
      </div>

      <div className="grid gap-4 rounded-[var(--radius-xl)] border border-line bg-ivory p-5 md:grid-cols-[1fr_320px]">
        <div><p className="eyebrow mb-2">Depth by status</p><div className="flex flex-wrap gap-2">{Object.entries(depth).map(([k, v]) => <Badge key={k}>{humanise(k)} <Mono className="ml-1">{v}</Mono></Badge>)}{!Object.keys(depth).length && <span className="text-[13.5px] text-taupe-2">Empty.</span>}</div></div>
        {rate && typeof rate.total === 'number' && <Ratio numerator={rate.count ?? 0} denominator={rate.total} label="Override rate (all time)" tone="warning" />}
      </div>

      <div className="flex flex-wrap items-center gap-4">
        <Select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1) }} aria-label="Queue status" className="w-auto"><option value="">Open items</option>{['PENDING', 'CLAIMED', 'IN_REVIEW', 'RESOLVED', 'DISMISSED', 'CLOSED'].map((s) => <option key={s} value={s}>{humanise(s)}</option>)}</Select>
        <Checkbox label="Assigned to me" checked={mine} onChange={(e) => { setMine(e.target.checked); setPage(1) }} />
        <Checkbox label="SLA breached only" checked={breached} onChange={(e) => { setBreached(e.target.checked); setPage(1) }} />
      </div>

      {q.error ? <ErrorState message={q.error} onRetry={q.refresh} /> : q.loading && !q.data ? <SkeletonRows rows={8} /> : !q.data!.items.length ? <Empty title="Nothing waiting" body="Every complaint that needed a person has one." /> : (
        <>
          <Table>
            <thead><tr><Th>Complaint</Th><Th>Title</Th><Th>Why</Th><Th>Priority</Th><Th>Escalation</Th><Th>Verification</Th><Th>Status</Th><Th>Assigned</Th><Th>SLA</Th><Th align="right">Queued</Th><Th /></tr></thead>
            <tbody>
              {q.data!.items.map((r) => (
                <Tr key={r.id}>
                  <Td mono><Link href={`/dashboard/review/${r.public_ref}`} className="underline decoration-line underline-offset-4">{r.public_ref}</Link></Td>
                  <Td className="max-w-[260px]"><span className="line-clamp-1">{r.title}</span></Td>
                  <Td><span className="flex max-w-[260px] flex-wrap gap-1">{(r.reasons ?? []).slice(0, 3).map((x) => <Badge key={x}><Mono className="text-[11px]">{x}</Mono></Badge>)}{(r.reasons?.length ?? 0) > 3 && <span className="text-[12px] text-taupe-2">+{r.reasons!.length - 3}</span>}</span></Td>
                  <Td>{r.priority_code ? <Badge tone={priorityTone(r.priority_code)}>{r.priority_code}</Badge> : '—'}</Td>
                  <Td><EscalationBadge code={r.escalation_code} /></Td>
                  <Td><OutcomeBadge outcome={r.verification_outcome} /></Td>
                  <Td><StatusBadge status={r.status} /></Td>
                  <Td className="text-[12.5px] text-taupe-2">{r.assigned_to ? (r.assigned_to === user?.id ? 'me' : r.assigned_to.slice(0, 8)) : '—'}</Td>
                  <Td>{r.sla_breached ? <Badge tone="critical">breached</Badge> : r.sla_at_risk ? <Badge tone="warning">at risk</Badge> : <Badge tone="verified">ok</Badge>}</Td>
                  <Td align="right" className="whitespace-nowrap text-taupe-2">{fmtRelative(r.created_at)}</Td>
                  <Td align="right"><Button href={`/dashboard/review/${r.public_ref}`} size="sm" variant={isReviewer ? 'primary' : 'ghost'}>{isReviewer ? 'Review' : 'Open'}</Button></Td>
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
