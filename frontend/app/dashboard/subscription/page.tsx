'use client'

import { CreditCard } from 'lucide-react'
import { AppShell } from '@/components/layout/app-shell'
import { billing } from '@/lib/api'
import { useApi, fmtDate } from '@/lib/use-api'
import { Badge, Button, humanise } from '@/components/ui/primitives'
import { Empty, ErrorState, SkeletonRows } from '@/components/ui/feedback'
import { Card } from '@/components/ui/surfaces'
import { cn } from '@/lib/utils'

export default function SubscriptionPage() {
  return (
    <AppShell eyebrow="Subscription" roles={['admin']}>
      <Subscription />
    </AppShell>
  )
}

const STATUS_TONE: Record<string, 'verified' | 'warning' | 'critical' | 'info'> = {
  active: 'verified', trialing: 'info', past_due: 'warning', ended: 'critical', cancelled: 'critical',
}
const STATUS_LABEL: Record<string, string> = { trialing: 'Free trial', ended: 'Trial ended', past_due: 'Payment due' }

function Subscription() {
  const q = useApi(() => billing.subscription(), [])
  if (q.error) return <ErrorState title="Your plan could not be loaded" message={q.error} onRetry={q.refresh} />
  const d = q.data
  if (!d) return <SkeletonRows rows={6} />
  if (!d.plan) {
    return <Empty title="No metered plan" body={`This company is not on a metered plan. ${d.seats_used} staff accounts and ${d.ai_used.toLocaleString()} AI-analysed complaints this month.`} className="m-8" />
  }

  const name = String(d.plan.name)
  const code = String(d.plan.code)
  const price = d.plan.monthly_price as number | null
  const dateLabel = d.status === 'trialing' ? 'Trial ends' : 'Current period ends'
  const date = d.status === 'trialing' ? d.trial_ends_at : d.current_period_end

  return (
    <div className="flex max-w-[860px] flex-col gap-6">
      <div>
        <p className="eyebrow mb-1">Administrator</p>
        <h1 className="display text-h2">Subscription</h1>
      </div>

      {d.notice && (
        <div role="status" className="rounded-[var(--radius-lg)] border border-warning/40 bg-warning-dim px-5 py-4 text-[14.5px] text-espresso">
          <strong className="font-semibold">AI analysis is paused.</strong> {d.notice} Your customers can still file complaints,
          and your rules still route and escalate every one.
        </div>
      )}

      <Card radius="xl">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-3">
              <CreditCard size={18} className="text-taupe" aria-hidden />
              <h2 className="font-display text-[26px] leading-tight text-espresso">{name}</h2>
              <Badge tone={STATUS_TONE[d.status] ?? 'neutral'} dot>{STATUS_LABEL[d.status] ?? humanise(d.status)}</Badge>
            </div>
            <p className="mt-2 text-[14.5px] text-taupe-2">
              {price === null ? 'Custom agreement' : `PKR ${price.toLocaleString('en-PK')} a month`}{d.billing_cycle === 'annual' ? ', billed yearly' : ''}
              {date ? ` · ${dateLabel} ${fmtDate(date, false)}` : ''}
            </p>
          </div>
          <Button href={`/pricing?plan=${encodeURIComponent(code)}#request`} variant="secondary">Change plan</Button>
        </div>

        <div className="mt-7 grid gap-6 sm:grid-cols-2">
          <Meter label="Staff accounts" used={d.seats_used} limit={d.seats_limit ?? null} />
          <Meter label="AI-analysed complaints this month" used={d.ai_used} limit={d.ai_limit ?? null} />
        </div>
      </Card>

      <p className="text-[13.5px] leading-relaxed text-taupe-2">
        Reaching the complaint allowance never stops your customers: complaints are still taken, routed and escalated by your rules.
        Only adding staff beyond your plan is refused. To change plan or arrange payment, choose Change plan and we will contact you.
      </p>
    </div>
  )
}

function Meter({ label, used, limit }: { label: string; used: number; limit: number | null }) {
  const share = limit ? Math.min(100, Math.round((used / limit) * 100)) : 0
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-[13.5px] text-taupe-2">{label}</span>
        <span className="font-mono text-[14px] text-espresso">{used.toLocaleString()}{limit !== null ? ` / ${limit.toLocaleString()}` : ''}</span>
      </div>
      {limit !== null && (
        <div role="meter" aria-label={label} aria-valuemin={0} aria-valuemax={limit} aria-valuenow={used} className="mt-2 h-2 w-full overflow-hidden rounded-full bg-sand/60">
          <div className={cn('h-full rounded-full', share >= 100 ? 'bg-critical' : share >= 80 ? 'bg-warning' : 'bg-verified')} style={{ width: `${share}%` }} />
        </div>
      )}
    </div>
  )
}
