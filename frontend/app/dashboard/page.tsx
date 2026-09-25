'use client'

import Link from 'next/link'
import { useEffect } from 'react'
import { FileSearch, FlaskConical, Inbox, Plus, ShieldCheck, Siren, UserCheck } from 'lucide-react'
import { useRouter } from 'next/navigation'
import { AppShell } from '@/components/layout/app-shell'
import { useAuth } from '@/lib/auth-context'
import { analytics, review, audit, system } from '@/lib/api'
import { useApi, fmtRelative, fmtMinutes } from '@/lib/use-api'
import { Badge, Button, Mono, humanise, priorityTone } from '@/components/ui/primitives'
import { Card, PanelHeader } from '@/components/ui/surfaces'
import { Stat, Ratio, Table, Th, Td, Tr } from '@/components/ui/data'
import { DegradedBanner, Empty, SkeletonRows } from '@/components/ui/feedback'
import { StatusBadge } from '@/components/app/complaint-bits'

export default function DashboardPage() {
  return (
    <AppShell eyebrow="Overview">
      <Overview />
    </AppShell>
  )
}

function Overview() {
  const { user } = useAuth()
  const router = useRouter()
  useEffect(() => { if (user?.role === 'customer') router.replace('/dashboard/my-complaints') }, [user, router])
  if (!user || user.role === 'customer') return null

  const oversight = ['manager', 'admin', 'evaluator'].includes(user.role)
  const hasQueue = ['agent', 'reviewer', 'manager', 'admin'].includes(user.role)
  const hour = new Date().getHours()
  const greeting = hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening'

  return (
    <div className="flex flex-col gap-8">
      <section className="mesh-banner grain relative overflow-hidden rounded-[var(--radius-xl)] px-6 py-9 text-ink-on-dark md:px-10 md:py-11">
        <div className="relative z-[1] flex flex-wrap items-end justify-between gap-8">
          <div className="animate-rise">
            <p className="eyebrow mb-3 text-sand-2">{greeting} · {user.role}</p>
            <h1 className="display text-h1 text-ink-on-dark">{user.full_name.split(' ')[0]}.</h1>
            <p className="mt-3 max-w-[52ch] text-[15.5px] text-ink-on-dark/80">
              The command centre: what arrived, what the rules corrected, and what is waiting on a person.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button href="/dashboard/complaints/new" variant="onDark" icon={<Plus size={15} aria-hidden />}>New complaint</Button>
            <Button href="/dashboard/review" className="border border-ink-on-dark/25 bg-transparent text-ink-on-dark hover:bg-ink-on-dark/10" icon={<UserCheck size={15} aria-hidden />}>Review queue</Button>
            {oversight && <Button href="/dashboard/rules/sandbox" className="border border-ink-on-dark/25 bg-transparent text-ink-on-dark hover:bg-ink-on-dark/10" icon={<FlaskConical size={15} aria-hidden />}>Rule sandbox</Button>}
          </div>
        </div>
      </section>
      <Health />
      {oversight && <Pulse />}
      <div className="grid gap-6 lg:grid-cols-2">
        {hasQueue && <MyQueue />}
        <ReviewDepth />
        <DueFollowUps />
        {oversight && <RecentActivity />}
      </div>
    </div>
  )
}

function Health() {
  const q = useApi(() => system.health())
  if (q.error) return <DegradedBanner>The API is not responding: {q.error}</DegradedBanner>
  if (q.data && !q.data.llm_configured) return <DegradedBanner>No GenAI provider is configured. The rule engine is carrying every decision alone; verification outcomes will read as incomplete until one is restored.</DegradedBanner>
  return null
}

function Pulse() {
  const q = useApi(() => analytics.dashboard(30))
  if (q.error) return null
  const d = q.data
  return (
    <section>
      <div className="mb-4 flex items-baseline justify-between"><p className="eyebrow">Last 30 days</p><Link href="/dashboard/analytics" className="text-[13px] text-taupe-2 underline decoration-line underline-offset-4">Full analytics</Link></div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card tone="glass" radius="xl" lift><Stat icon={<Inbox size={12} aria-hidden />} label="Complaints" value={d ? d.volume.total ?? 0 : undefined} evidence={d ? `${d.volume.open ?? 0} open · ${d.volume.resolved ?? 0} resolved` : undefined} /></Card>
        <Card tone="glass" radius="xl" lift><Stat icon={<Siren size={12} aria-hidden />} label="Escalation rate" value={d ? d.escalation.rate.pct ?? null : undefined} unit="%" evidence={d ? `${d.escalation.rate.count ?? 0} of ${d.escalation.rate.total ?? 0}` : undefined} tone="warning" /></Card>
        <Card tone="glass" radius="xl" lift><Stat icon={<ShieldCheck size={12} aria-hidden />} label="Rules corrected the AI" value={d ? d.pipelines.rules_corrected_the_model.pct ?? null : undefined} unit="%" evidence={d ? `${d.pipelines.rules_corrected_the_model.count ?? 0} of ${d.pipelines.rules_corrected_the_model.total ?? 0} contested · ${d.pipelines.degraded ?? 0} rules-only` : undefined} tone="rule" /></Card>
        <Card tone="glass" radius="xl" lift><Stat icon={<FileSearch size={12} aria-hidden />} label="Mean traceability" value={d ? d.traceability.mean_traceability_pct ?? null : undefined} unit="%" evidence={d ? `${d.traceability.unmeasured_traceability ?? 0} unmeasured` : undefined} tone="verified" /></Card>
      </div>
    </section>
  )
}

function MyQueue() {
  const q = useApi(() => analytics.myQueue())
  return (
    <Card>
      <PanelHeader title="My workload" eyebrow="Assigned to me" aside={<Button href="/dashboard/complaints" size="sm" variant="secondary">All complaints</Button>} />
      {q.loading && !q.data ? <SkeletonRows rows={4} /> : q.error ? <p className="text-[13.5px] text-taupe-2">{q.error}</p> : !q.data?.complaints.length ? <Empty title="Nothing assigned" body="Claim from the review queue, or wait for routing." /> : (
        <ul className="divide-y divide-line-soft">
          {q.data.complaints.slice(0, 8).map((c) => (
            <li key={c.public_ref} className="flex items-center gap-3 py-2.5">
              <Link href={`/dashboard/complaints/${c.public_ref}`} className="font-mono text-[12.5px] underline decoration-line underline-offset-4">{c.public_ref}</Link>
              <span className="flex-1 truncate text-[13.5px]">{c.title}</span>
              {c.priority && <Badge tone={priorityTone(c.priority)}>{c.priority}</Badge>}
              <StatusBadge status={c.status} />
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}

function ReviewDepth() {
  const q = useApi(() => review.stats())
  const depth = q.data?.depth ?? {}
  const total = Object.values(depth).reduce((a, b) => a + b, 0)
  const rate = q.data?.override_rate as { count?: number; total?: number; pct?: number | null } | undefined
  return (
    <Card>
      <PanelHeader title="Review queue" eyebrow="Human review" aside={<Button href="/dashboard/review" size="sm" variant="secondary">Open queue</Button>} />
      {q.loading && !q.data ? <SkeletonRows rows={3} /> : q.error ? <p className="text-[13.5px] text-taupe-2">{q.error}</p> : (
        <div className="flex flex-col gap-4">
          <div className="flex flex-wrap gap-2">{Object.entries(depth).map(([k, v]) => <Badge key={k}>{humanise(k)} <Mono className="ml-1">{v}</Mono></Badge>)}{total === 0 && <span className="text-[13.5px] text-taupe-2">The queue is empty.</span>}</div>
          {rate && typeof rate.total === 'number' && <Ratio numerator={rate.count ?? 0} denominator={rate.total} label="Override rate" tone="warning" />}
        </div>
      )}
    </Card>
  )
}

function DueFollowUps() {
  const q = useApi(() => review.dueFollowUps(8))
  return (
    <Card>
      <PanelHeader title="Follow-ups due" eyebrow="Commitments" aside={<Button href="/dashboard/follow-ups" size="sm" variant="secondary">All follow-ups</Button>} />
      {q.loading && !q.data ? <SkeletonRows rows={3} /> : q.error ? <p className="text-[13.5px] text-taupe-2">{q.error}</p> : !q.data?.length ? <Empty title="Nothing due" body="Every promised follow-up is either done or not yet due." /> : (
        <ul className="divide-y divide-line-soft">
          {q.data.map((f) => (
            <li key={f.id} className="flex items-center gap-3 py-2.5 text-[13.5px]">
              <Link href={`/dashboard/complaints/${f.public_ref}`} className="font-mono text-[12.5px] underline decoration-line underline-offset-4">{f.public_ref}</Link>
              <span className="flex-1 truncate">{humanise(f.type)}{f.message ? ` · ${f.message}` : ''}</span>
              <Badge tone={(f.overdue_minutes ?? 0) > 0 ? 'critical' : 'warning'}>{(f.overdue_minutes ?? 0) > 0 ? `overdue ${fmtMinutes(f.overdue_minutes)}` : `due ${fmtRelative(f.due_at)}`}</Badge>
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}

function RecentActivity() {
  const q = useApi(() => audit.list({ size: 8 }))
  return (
    <Card>
      <PanelHeader title="Recent activity" eyebrow="Audit trail" aside={<Button href="/dashboard/audit" size="sm" variant="secondary">Full trail</Button>} />
      {q.loading && !q.data ? <SkeletonRows rows={4} /> : q.error ? <p className="text-[13.5px] text-taupe-2">{q.error}</p> : !q.data?.items.length ? <Empty title="No activity yet" /> : (
        <Table dense>
          <thead><tr><Th>Action</Th><Th>Entity</Th><Th>Actor</Th><Th align="right">When</Th></tr></thead>
          <tbody>{q.data.items.map((r) => <Tr key={r.id}><Td mono>{r.action}</Td><Td mono className="text-taupe-2">{r.entity_type}:{r.entity_id.slice(0, 12)}</Td><Td>{r.actor ?? 'system'}</Td><Td align="right" className="text-taupe-2">{fmtRelative(r.at)}</Td></Tr>)}</tbody>
        </Table>
      )}
    </Card>
  )
}
