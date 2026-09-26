'use client'

import { use } from 'react'
import Link from 'next/link'
import { AppShell } from '@/components/layout/app-shell'
import { useAuth } from '@/lib/auth-context'
import { complaints, review, admin } from '@/lib/api'
import { useApi, useAction } from '@/lib/use-api'
import { Badge, Button, Mono, humanise } from '@/components/ui/primitives'
import { Card, PanelHeader, PencilInk } from '@/components/ui/surfaces'
import { ErrorState, Loading, useToast } from '@/components/ui/feedback'
import {
  StatusBadge, OutcomeBadge, PriorityBadge, UrgencyBadge, EscalationBadge, VerificationCard, ComparisonTable, RuleHits,
  ReviewHistoryPanel, SlaPanel, ReviewActionForm,
} from '@/components/app/complaint-bits'

export default function ReviewItemPage({ params }: { params: Promise<{ ref: string }> }) {
  const { ref } = use(params)
  const refId = decodeURIComponent(ref)
  return (
    <AppShell eyebrow={<span>Review / <Mono>{refId}</Mono></span>} roles={['reviewer', 'manager', 'admin', 'evaluator']} wide>
      <ReviewItem refId={refId} />
    </AppShell>
  )
}

/**
 * The reviewer's desk: the complaint, both opinions side by side, the reasons
 * it was queued, and the action form. Claiming is explicit so two reviewers
 * do not work the same item.
 */
function ReviewItem({ refId }: { refId: string }) {
  const { user } = useAuth()
  const toast = useToast()
  const c = useApi(() => complaints.get(refId), [refId])
  const explain = useApi(() => complaints.explain(refId), [refId])
  const oversight = user && ['manager', 'admin', 'evaluator'].includes(user.role)
  const isReviewer = user && ['reviewer', 'manager', 'admin'].includes(user.role)
  const taxonomy = useApi(() => admin.taxonomy(), [], Boolean(oversight))
  const claim = useAction(() => review.claim(refId))

  if (c.loading && !c.data) return <Loading label="Opening for review" />
  if (c.error) return <ErrorState message={c.error} onRetry={c.refresh} />
  const d = c.data!
  const v = d.verification
  const contested = (explain.data?.comparisons ?? []).filter((r) => r.status !== 'MATCH' && r.status !== 'AGREED')

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="mb-2 flex flex-wrap items-center gap-2"><Mono className="text-[13px] text-taupe-2">{d.public_ref}</Mono><StatusBadge status={d.status} /><OutcomeBadge outcome={d.verification_outcome} /></div>
          <h1 className="display text-h2">{d.title}</h1>
          <div className="mt-3 flex flex-wrap items-center gap-2">{d.category && <Badge tone="ink">{humanise(d.category)}</Badge>}{d.department && <Badge tone="info">{humanise(d.department)}</Badge>}<UrgencyBadge u={d.urgency} /><PriorityBadge code={d.priority_code} /><EscalationBadge code={d.escalation_code} /></div>
        </div>
        <div className="flex gap-2">
          {isReviewer && <Button loading={claim.pending} onClick={async () => { const r = await claim.run(); if (r) toast('ok', `Claimed ${r.public_ref}.`); else if (claim.error) toast('err', claim.error) }}>Claim</Button>}
          <Button href={`/dashboard/complaints/${d.public_ref}`} variant="secondary">Full record</Button>
        </div>
      </header>

      {v?.review_reasons && v.review_reasons.length > 0 && (
        <Card tone="sand"><p className="eyebrow mb-2">Why this needs a person</p><div className="flex flex-wrap gap-1.5">{v.review_reasons.map((r) => <Badge key={r}><Mono>{r}</Mono></Badge>)}</div></Card>
      )}

      <div className="grid gap-6 lg:grid-cols-[1.3fr_1fr]">
        <div className="flex flex-col gap-6">
          <Card><PanelHeader title="The complaint" /><p className="whitespace-pre-wrap font-display text-[16.5px] leading-relaxed">{d.description_raw}</p></Card>
          {contested.length > 0 && (
            <section>
              <PanelHeader title="Where they disagreed" eyebrow="Pencil against ink" />
              <div className="flex flex-col gap-3">{contested.map((r) => <PencilInk key={r.field} pencilLabel={`AI · ${humanise(r.field)}`} inkLabel={`Rules · ${r.reason_code ?? humanise(r.status)}`} pencil={r.genai_value ?? '—'} ink={<>{r.python_value ?? '—'}{r.explanation && <span className="mt-1 block text-[12.5px] font-normal text-sand-2">{r.explanation}</span>}</>} />)}</div>
            </section>
          )}
          <section><PanelHeader title="All fields" /><ComparisonTable rows={explain.data?.comparisons} /></section>
          <section><PanelHeader title="Rules that fired" /><RuleHits hits={explain.data?.rule_hits} floor={explain.data?.escalation_floor} /></section>
        </div>
        <div className="flex flex-col gap-6">
          <VerificationCard v={v} />
          <Card><PanelHeader title="Decide" eyebrow={isReviewer ? 'Recorded with before/after' : 'Read only for your role'} /><ReviewActionForm refId={refId} taxonomy={taxonomy.data} onDone={(r) => { toast('ok', `${humanise(r.action)} recorded${r.queue_closed ? '; queue item closed' : ''}${r.escalation_raised ? '; escalation raised' : ''}.`); c.refresh(); explain.refresh() }} /></Card>
          <section><PanelHeader title="SLA" /><SlaPanel refId={refId} /></section>
          <section><PanelHeader title="History" /><ReviewHistoryPanel refId={refId} /></section>
          <p className="text-[12.5px] text-taupe-2"><Link href="/dashboard/review" className="underline decoration-line underline-offset-4">Back to the queue</Link></p>
        </div>
      </div>
    </div>
  )
}
