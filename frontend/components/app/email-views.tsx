'use client'

import Link from 'next/link'
import { useState } from 'react'
import { ArrowDownLeft, ArrowUpRight, Mail } from 'lucide-react'
import { mail, type S } from '@/lib/api'
import { useApi, fmtDate, fmtRelative } from '@/lib/use-api'
import { Badge, humanise } from '@/components/ui/primitives'
import { Card } from '@/components/ui/surfaces'
import { Pagination } from '@/components/ui/data'
import { Empty, ErrorState, SkeletonRows } from '@/components/ui/feedback'
import { cn } from '@/lib/utils'

const STATUS_TONE: Record<string, 'verified' | 'warning' | 'critical' | 'neutral'> = {
  REPLIED: 'verified', SENT: 'verified', PROCESSED: 'neutral', RECEIVED: 'neutral',
  NOT_SENT: 'warning', IGNORED: 'neutral', FAILED: 'critical',
}
const STATUS_LABEL: Record<string, string> = {
  REPLIED: 'Answered', SENT: 'Sent', PROCESSED: 'Handled, reply not sent', RECEIVED: 'Received',
  NOT_SENT: 'Written, not sent', IGNORED: 'Ignored (automatic mail)', FAILED: 'Failed',
}
const INTENT_LABEL: Record<string, string> = {
  COMPLAINT: 'New complaint', FOLLOW_UP: 'Follow-up', STATUS: 'Status question', QUESTION: 'Question', OTHER: 'Other', REPLY: 'Our reply',
}

/** The mailbox as a two-pane reader: messages on the left, the open one on the right. */
export function Mailbox({ staff, refreshKey = 0 }: { staff: boolean; refreshKey?: number }) {
  const [page, setPage] = useState(1)
  const [direction, setDirection] = useState<'' | 'IN' | 'OUT'>(staff ? 'IN' : '')
  const q = useApi(() => mail.messages({ page, size: 20, direction: direction || undefined }), [page, direction, refreshKey])
  const [open, setOpen] = useState<string | null>(null)
  const items = q.data?.items ?? []
  const current = open ?? items[0]?.id ?? null

  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,420px)_1fr]">
      <div className="flex min-w-0 flex-col gap-3">
        <div className="flex gap-1.5" role="tablist" aria-label="Which emails">
          {([['IN', 'Received'], ['OUT', 'Sent'], ['', 'All']] as Array<['' | 'IN' | 'OUT', string]>).map(([value, label]) => (
            <button key={label} role="tab" aria-selected={direction === value} onClick={() => { setDirection(value); setPage(1); setOpen(null) }}
              className={cn('rounded-full px-3 py-1.5 text-[13px]', direction === value ? 'bg-espresso text-ink-on-dark' : 'border border-line bg-white/70 text-espresso-2 hover:bg-white')}>{label}</button>
          ))}
        </div>
        {q.error ? <ErrorState message={q.error} onRetry={q.refresh} /> : !q.data ? <SkeletonRows rows={6} /> : !items.length ? (
          <Empty title="No emails yet" body={staff ? 'Emails sent to the support address appear here once the mailbox is connected — or use “Simulate an email”.' : 'When you email support, your messages and our replies appear here.'} />
        ) : (
          <ul className="flex flex-col gap-1.5">
            {items.map((m) => (
              <li key={m.id}>
                <button type="button" onClick={() => setOpen(m.id)}
                  className={cn('flex w-full items-start gap-3 rounded-2xl border px-3.5 py-3 text-left transition-colors', current === m.id ? 'border-espresso/25 bg-white shadow-sm' : 'border-transparent hover:bg-white/70')}>
                  <span className={cn('mt-0.5 inline-flex size-8 shrink-0 items-center justify-center rounded-full', m.direction === 'IN' ? 'bg-sand text-espresso-2' : 'bg-espresso text-ink-on-dark')}>
                    {m.direction === 'IN' ? <ArrowDownLeft size={15} aria-hidden /> : <ArrowUpRight size={15} aria-hidden />}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center justify-between gap-2">
                      <span className="truncate text-[13.5px] font-medium text-espresso">{m.direction === 'IN' ? (m.from_name || m.from_address) : `To ${m.to_address}`}</span>
                      <span className="shrink-0 text-[11.5px] text-taupe-2">{fmtRelative(m.created_at)}</span>
                    </span>
                    <span className="block truncate text-[13.5px] text-espresso-2">{m.subject || '(no subject)'}</span>
                    <span className="mt-1 flex flex-wrap gap-1.5">
                      {m.intent && <Badge>{INTENT_LABEL[m.intent] ?? humanise(m.intent)}</Badge>}
                      <Badge tone={STATUS_TONE[m.status] ?? 'neutral'}>{STATUS_LABEL[m.status] ?? humanise(m.status)}</Badge>
                      {m.complaint_ref && <Badge tone="ink">{m.complaint_ref}</Badge>}
                    </span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
        {q.data && q.data.total > 20 && <Pagination page={page} size={20} total={q.data.total} onPage={setPage} />}
      </div>
      <div className="min-w-0">{current ? <MessageView id={current} staff={staff} /> : null}</div>
    </div>
  )
}

export function MessageView({ id, staff }: { id: string; staff: boolean }) {
  const q = useApi(() => mail.message(id), [id])
  if (q.error) return <ErrorState message={q.error} onRetry={q.refresh} />
  if (!q.data) return <SkeletonRows rows={8} />
  const m = q.data
  const all = [m, ...(m.thread ?? [])].sort((a, b) => String(a.created_at).localeCompare(String(b.created_at)))
  return (
    <Card tone="glass" radius="xl" className="flex flex-col gap-4">
      <div>
        <p className="eyebrow mb-1 flex items-center gap-1.5"><Mail size={12} aria-hidden /> {m.direction === 'IN' ? 'Received' : 'Sent'} {fmtDate(m.created_at)}</p>
        <h2 className="font-display text-[22px] leading-tight text-espresso">{m.subject || '(no subject)'}</h2>
        <p className="mt-1 text-[13px] text-taupe-2">From {m.from_name ? `${m.from_name} <${m.from_address}>` : m.from_address} · to {m.to_address}</p>
        {m.complaint_ref && (
          <Link href={staff ? `/dashboard/complaints/${m.complaint_ref}` : `/track/${m.complaint_ref}`} className="mt-2 inline-block text-[13.5px] text-espresso-2 underline underline-offset-4">
            Complaint {m.complaint_ref}
          </Link>
        )}
        {m.error && staff && <p className="mt-2 rounded-lg bg-warning-dim px-3 py-2 text-[12.5px] text-espresso">{m.error}</p>}
      </div>
      <ol className="flex flex-col gap-3">
        {all.map((e) => <ThreadItem key={e.id} e={e} focus={e.id === m.id} full={e.id === m.id ? m : null} />)}
      </ol>
    </Card>
  )
}

function ThreadItem({ e, focus, full }: { e: S['EmailOut']; focus: boolean; full: S['EmailDetail'] | null }) {
  const detail = useApi(() => mail.message(e.id), [e.id], !full)
  const d = full ?? detail.data
  return (
    <li className={cn('rounded-2xl border p-4', e.direction === 'IN' ? 'border-line-soft bg-white/80' : 'border-espresso/15 bg-cream/60', focus && 'ring-1 ring-espresso/20')}>
      <p className="mb-2 flex flex-wrap items-center justify-between gap-2 text-[12.5px] text-taupe-2">
        <span className="font-medium text-espresso">{e.direction === 'IN' ? (e.from_name || e.from_address) : 'Our reply'}</span>
        <span>{fmtDate(e.created_at)} · {STATUS_LABEL[e.status] ?? humanise(e.status)}</span>
      </p>
      {!d ? <SkeletonRows rows={3} /> : d.body_html ? (
        // The reply exactly as the customer receives it. Sandboxed: no script runs.
        <iframe title={`Email: ${e.subject}`} srcDoc={d.body_html} sandbox="" className="h-[620px] w-full rounded-xl border border-line-soft bg-white" />
      ) : (
        <p className="whitespace-pre-wrap text-[14px] leading-relaxed text-espresso-2">{d.body_text || '(empty)'}</p>
      )}
    </li>
  )
}
