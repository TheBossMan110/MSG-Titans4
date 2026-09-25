'use client'

import { use } from 'react'
import Link from 'next/link'
import { ArrowLeft, CalendarClock, Hash, LifeBuoy, ShieldCheck, Sparkles } from 'lucide-react'
import { complaints, type S } from '@/lib/api'
import { useApi, fmtDate, fmtRelative } from '@/lib/use-api'
import { AuthGuard } from '@/components/layout/auth-guard'
import { Badge, Button, Wordmark, humanise, statusTone } from '@/components/ui/primitives'
import { Card } from '@/components/ui/surfaces'
import { SlaMeter } from '@/components/ui/data'
import { ErrorState, Skeleton } from '@/components/ui/feedback'
import { EvidencePanel, MilestoneTimeline, QuestionsPanel, TeamCard } from '@/components/app/customer'

export default function TrackRefPage({ params }: { params: Promise<{ ref: string }> }) {
  const { ref } = use(params)
  return (
    <main className="mesh-hero min-h-dvh">
      <div className="container-x py-8 md:py-10">
        <div className="mb-10 flex items-center justify-between gap-4">
          <Link href="/"><Wordmark /></Link>
          <div className="flex gap-2">
            <Button href="/dashboard/my-complaints" variant="secondary" size="sm" icon={<ArrowLeft size={14} aria-hidden />}>My complaints</Button>
          </div>
        </div>
        <AuthGuard>
          <Tracking refId={decodeURIComponent(ref)} />
        </AuthGuard>
      </div>
    </main>
  )
}

function Tracking({ refId }: { refId: string }) {
  const q = useApi(() => complaints.status(refId), [refId])

  if (q.loading && !q.data) {
    return (
      <div className="flex flex-col gap-6">
        <Skeleton className="h-10 w-72" />
        <Skeleton className="h-40 w-full" />
        <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]"><Skeleton className="h-72" /><Skeleton className="h-72" /></div>
      </div>
    )
  }
  if (q.error) {
    return (
      <div className="mx-auto max-w-[640px]">
        <ErrorState title="We could not show that complaint" message={q.error} onRetry={q.refresh} />
        <Button href="/track" variant="secondary" className="mt-4">Try another reference</Button>
      </div>
    )
  }
  const s = q.data!
  const setStatus = (next: S['ComplaintStatusOut']) => q.setData(next)
  const done = s.status === 'RESOLVED' || s.status === 'CLOSED'

  return (
    <div className="flex flex-col gap-6">
      {/* hero */}
      <section className="glass relative overflow-hidden rounded-[var(--radius-xl)] p-6 md:p-9">
        <span aria-hidden className="pointer-events-none absolute -right-24 -top-24 size-72 rounded-full bg-ai-2/25 blur-3xl" />
        <div className="relative grid gap-8 lg:grid-cols-[1.5fr_1fr] lg:items-end">
          <div className="min-w-0 animate-rise">
            <p className="eyebrow mb-3 flex items-center gap-2"><Hash size={12} aria-hidden /> Complaint {s.public_ref}</p>
            <h1 className="display text-h2">{s.title}</h1>
            <div className="mt-4 flex flex-wrap items-center gap-2">
              <Badge tone={statusTone(s.status)} dot pulse={s.action_needed}>{s.action_needed ? 'Waiting for you' : humanise(s.status)}</Badge>
              {s.category_name && <Badge tone="neutral">{s.category_name}</Badge>}
              {s.escalated && <Badge tone="warning">A specialist is involved</Badge>}
              <span className="text-[13px] text-taupe">Updated {fmtRelative(s.last_updated)}</span>
            </div>
          </div>
          <div className="rounded-2xl border border-white/70 bg-white/70 p-5">
            {done ? (
              <div className="flex items-center gap-3">
                <span className="inline-flex size-10 items-center justify-center rounded-full bg-verified text-white"><ShieldCheck size={18} aria-hidden /></span>
                <div><p className="font-medium text-espresso">Resolved</p><p className="text-[13px] text-taupe">Confirmed against company policy.</p></div>
              </div>
            ) : (
              <SlaMeter start={s.submitted_at} due={s.target_resolution_at} label="We aim to resolve this by" />
            )}
          </div>
        </div>
        <div className="relative mt-9 border-t border-line-soft pt-7">
          <MilestoneTimeline milestones={s.milestones ?? []} orientation="horizontal" />
        </div>
      </section>

      <div className="grid gap-6 lg:grid-cols-[1.45fr_1fr]">
        <div className="flex flex-col gap-6">
          <QuestionsPanel refId={s.public_ref} status={s} onUpdated={setStatus} />
          <EvidencePanel refId={s.public_ref} evidence={s.evidence ?? []} onUploaded={() => void q.refresh()} />
        </div>

        <aside className="flex flex-col gap-6">
          <TeamCard department={s.department} publicRef={s.public_ref} />
          <Card tone="glass" radius="xl">
            <p className="eyebrow mb-2 flex items-center gap-1.5"><Sparkles size={12} className="text-ai" aria-hidden /> What we understood</p>
            {s.summary ? (
              <p className="font-display text-[18px] leading-relaxed text-espresso">{s.summary}</p>
            ) : (
              <p className="text-[14px] text-taupe">We are still reading your complaint. The summary appears here once it has been checked.</p>
            )}
            <dl className="mt-5 grid grid-cols-[max-content_1fr] gap-x-5 gap-y-2 border-t border-line-soft pt-4 text-[13.5px]">
              <dt className="text-taupe">Submitted</dt><dd className="text-espresso-2">{fmtDate(s.submitted_at)}</dd>
              <dt className="text-taupe">Reference</dt><dd className="font-mono text-espresso-2">{s.public_ref}</dd>
              <dt className="text-taupe">Files attached</dt><dd className="text-espresso-2">{s.evidence?.length ?? 0}</dd>
            </dl>
          </Card>

          <Card tone="rule" radius="xl">
            <p className="mb-2 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-rule">
              <ShieldCheck size={13} aria-hidden /> How your complaint is handled
            </p>
            <p className="text-[14px] leading-relaxed text-rule">
              An AI model reads it and suggests what should happen. Nothing it suggests reaches you
              until the company&rsquo;s own rules have confirmed it — and where the two disagree,
              a person looks at it.
            </p>
          </Card>

          <Card tone="glass" radius="xl">
            <p className="eyebrow mb-3 flex items-center gap-1.5"><LifeBuoy size={12} aria-hidden /> Need help?</p>
            <ul className="flex flex-col gap-2.5 text-[14px] text-espresso-2">
              <li className="flex gap-2"><CalendarClock size={16} className="mt-0.5 shrink-0 text-taupe" aria-hidden />Quote <span className="font-mono">{s.public_ref}</span> in any message so we find it at once.</li>
              <li className="flex gap-2"><ShieldCheck size={16} className="mt-0.5 shrink-0 text-taupe" aria-hidden />We will never ask for your password or card number.</li>
            </ul>
            <Button href="/dashboard/complaints/new" variant="secondary" size="sm" className="mt-4">Raise a different issue</Button>
          </Card>
        </aside>
      </div>
    </div>
  )
}
