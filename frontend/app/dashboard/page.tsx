'use client'

import Link from 'next/link'
import { useEffect, useState, type ReactNode } from 'react'
import { useRouter } from 'next/navigation'
import { AlertTriangle, ArrowRight, Headset, Scale, ShieldCheck, Siren, UserCheck } from 'lucide-react'
import { AppShell } from '@/components/layout/app-shell'
import { useAuth } from '@/lib/auth-context'
import { analytics } from '@/lib/api'
import { useApi, fmtRelative } from '@/lib/use-api'
import { Badge, Button, humanise, priorityTone } from '@/components/ui/primitives'
import { Card } from '@/components/ui/surfaces'
import { Stat, Ratio } from '@/components/ui/data'
import { Empty, ErrorState, SkeletonRows } from '@/components/ui/feedback'
import { Bars, Stacked } from '@/components/app/charts'
import { DashSection } from '@/components/app/dashboard-bits'

const OVERSIGHT = ['manager', 'admin', 'evaluator']
const WINDOWS: Array<[number, string]> = [[7, '7 days'], [30, '30 days'], [90, '90 days'], [365, '12 months']]

export default function AdminDashboardPage() {
  return (
    <AppShell eyebrow="Admin dashboard" wide>
      <AdminDashboard />
    </AppShell>
  )
}

function AdminDashboard() {
  const { user } = useAuth()
  const router = useRouter()
  const [days, setDays] = useState<number>(365)
  const q = useApi(() => analytics.dashboard(days), [days])

  // Customers have their own dashboard, agents and reviewers the agent one.
  useEffect(() => {
    if (!user) return
    if (user.role === 'customer') router.replace('/dashboard/my-complaints')
    else if (!OVERSIGHT.includes(user.role)) router.replace('/dashboard/agent')
  }, [user, router])
  if (!user || !OVERSIGHT.includes(user.role)) return null

  const d = q.data
  return (
    <div className="flex flex-col gap-8">
      <section className="mesh-banner grain relative overflow-hidden rounded-[var(--radius-xl)] px-6 py-8 text-ink-on-dark md:px-10 md:py-10">
        <div className="relative z-[1] flex flex-wrap items-end justify-between gap-6">
          <div className="animate-rise">
            <p className="eyebrow mb-3 text-sand-2">Admin dashboard · signed in as {user.role}</p>
            <h1 className="display text-h1 text-ink-on-dark">{user.full_name}</h1>
            <p className="mt-3 max-w-[56ch] text-[15.5px] text-ink-on-dark/80">The whole register at a glance: volume, where it goes, how urgent it is, and where a person is needed.</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button href="/dashboard/agent" variant="onDark" icon={<Headset size={15} aria-hidden />}>Agent dashboard</Button>
          </div>
        </div>
      </section>

      <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Time window">
        <span className="mr-1 text-[13px] text-taupe-2">Showing</span>
        {WINDOWS.map(([value, label]) => (
          <button key={label} type="button" onClick={() => setDays(value)} aria-pressed={days === value}
            className={days === value ? 'rounded-full bg-espresso px-3 py-1.5 text-[13px] text-ink-on-dark' : 'rounded-full border border-line bg-white/70 px-3 py-1.5 text-[13px] text-espresso-2 hover:bg-white'}>
            {label}
          </button>
        ))}
      </div>

      {q.error ? <ErrorState message={q.error} onRetry={q.refresh} /> : (
        <>
          <DashSection id="total" title="Total complaints" icon={<Scale size={15} aria-hidden />}>
            <div className="grid grid-cols-2 gap-x-6 gap-y-5 sm:grid-cols-4">
              <Stat label="Total" value={d?.volume.total} size="lg" />
              <Stat label="Open" value={d?.volume.open} />
              <Stat label="Resolved" value={d?.volume.resolved} tone="verified" />
              <Stat label="Failed analysis" value={d?.volume.failed} tone={d && d.volume.failed ? 'warning' : 'neutral'} />
            </div>
          </DashSection>

          <div className="grid gap-6 xl:grid-cols-2">
            <DashSection id="categories" title="Category distribution">
              {!d ? <SkeletonRows rows={6} /> : <Bars rows={(d.categories ?? []).filter((c) => c.count > 0).map((c) => ({ label: c.name, value: c.count, sub: c.pct != null ? `${Math.round(c.pct)}%` : undefined }))} />}
            </DashSection>
            <DashSection id="departments" title="Department distribution">
              {!d ? <SkeletonRows rows={6} /> : <Bars tone="taupe" rows={(d.departments ?? []).filter((x) => x.total > 0).map((x) => ({ label: x.name, value: x.total, sub: `${x.open} open` }))} />}
            </DashSection>
            <DashSection id="priorities" title="Priority levels">
              {!d ? <SkeletonRows rows={4} /> : (
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                  {['P0', 'P1', 'P2', 'P3'].map((p) => (
                    <Link key={p} href={`/dashboard/complaints?priority=${p}`} className="rounded-2xl border border-line-soft bg-white/70 p-4 transition-colors hover:bg-white">
                      <Badge tone={priorityTone(p)}>{p}</Badge>
                      <p className="mt-3 font-display text-[30px] leading-none text-espresso">{d.priorities?.[p] ?? 0}</p>
                      <p className="mt-1 text-[12.5px] text-taupe-2">{({ P0: 'Critical', P1: 'High', P2: 'Medium', P3: 'Low' } as Record<string, string>)[p]}</p>
                    </Link>
                  ))}
                </div>
              )}
            </DashSection>
            <DashSection id="escalations" title="Escalations" icon={<Siren size={15} aria-hidden />}>
              {!d ? <SkeletonRows rows={4} /> : (
                <div className="flex flex-col gap-5">
                  <Ratio numerator={d.escalation.rate?.count ?? 0} denominator={d.escalation.rate?.total ?? 0} label="Complaints escalated" tone="warning" />
                  <Bars tone="warning" rows={Object.entries(d.escalation.by_level ?? {}).filter(([k]) => k !== 'NONE').map(([k, v]) => ({ label: humanise(k), value: Number(v) }))} />
                  <Link href="/dashboard/escalations" className="text-[13.5px] text-espresso-2 underline underline-offset-4">Open the escalations list</Link>
                </div>
              )}
            </DashSection>
          </div>

          <DashSection id="resolution" title="Resolution status">
            {!d ? <SkeletonRows rows={3} /> : (
              <div className="flex flex-col gap-4">
                <Stacked parts={Object.entries(d.volume.by_status ?? {}).map(([k, v]) => ({ label: humanise(k), value: Number(v), tone: ['RESOLVED', 'CLOSED'].includes(k) ? 'verified' : k === 'MANUAL_REVIEW' ? 'warning' : k === 'FAILED' ? 'critical' : k === 'ESCALATED' ? 'warning' : 'taupe' }))} />
                <Ratio numerator={d.volume.resolved} denominator={d.volume.total} label="Resolved or closed" tone="verified" />
              </div>
            )}
          </DashSection>

          <div className="grid gap-6 xl:grid-cols-2">
            <DashSection id="sla-risks" title="SLA risks" icon={<AlertTriangle size={15} aria-hidden />} aside={d ? <Badge tone={d.sla.open_at_risk ? 'warning' : 'verified'}>{d.sla.open_at_risk} at risk</Badge> : null}>
              <ComplaintList rows={d?.sla_risks} empty="No open complaint is near its deadline." render={(r) => <span className={r.breached ? 'text-critical' : 'text-warning'}>{r.breached ? 'Breached' : 'Due'} {fmtRelative(String(r.due_at))}</span>} />
            </DashSection>
            <DashSection id="mismatches" title="GenAI / Python mismatches" icon={<ShieldCheck size={15} aria-hidden />}>
              {!d ? <SkeletonRows rows={4} /> : (
                <div className="flex flex-col gap-5">
                  <div className="grid grid-cols-3 gap-4">
                    <Stat label="Agreement" value={d.pipelines.mean_agreement_pct != null ? `${Math.round(d.pipelines.mean_agreement_pct)}%` : null} />
                    <Stat label="Rules corrected AI" value={d.pipelines.rules_corrected_the_model?.count ?? 0} tone="rule" />
                    <Stat label="Critical mismatches" value={d.pipelines.critical_mismatches} tone={d.pipelines.critical_mismatches ? 'critical' : 'neutral'} />
                  </div>
                  <ComplaintList rows={d.mismatches} empty="The AI and the rules agreed on every recent complaint." render={(r) => <span>{String(r.mismatched_fields)} field{Number(r.mismatched_fields) === 1 ? '' : 's'} differ{Number(r.critical) ? ` · ${String(r.critical)} critical` : ''}</span>} />
                </div>
              )}
            </DashSection>
          </div>

          <DashSection id="manual-review" title="Manual-review cases" icon={<UserCheck size={15} aria-hidden />} aside={d ? <Badge tone="warning">{d.review.open} waiting</Badge> : null}>
            <ComplaintList rows={d?.manual_review} empty="Nothing is waiting for a person." render={(r) => <span>{r.team ? `${String(r.team)} · ` : ''}waiting {fmtRelative(String(r.created_at))}</span>} />
            <Button href="/dashboard/review" variant="secondary" size="sm" className="mt-4" arrow>Open the review queue</Button>
          </DashSection>
        </>
      )}
    </div>
  )
}

function ComplaintList({ rows, empty, render }: { rows?: Array<Record<string, unknown>>; empty: string; render: (r: Record<string, unknown>) => ReactNode }) {
  if (!rows) return <SkeletonRows rows={4} />
  if (!rows.length) return <Empty title="All clear" body={empty} />
  return (
    <ul className="divide-y divide-line-soft">
      {rows.map((r) => (
        <li key={String(r.public_ref)}>
          <Link href={`/dashboard/complaints/${encodeURIComponent(String(r.public_ref))}`} className="flex items-center gap-3 py-2.5 hover:bg-white/50">
            {r.priority ? <Badge tone={priorityTone(String(r.priority))}>{String(r.priority)}</Badge> : null}
            <span className="min-w-0 flex-1">
              <span className="block truncate text-[14px] font-medium text-espresso">{String(r.title)}</span>
              <span className="block text-[12.5px] text-taupe-2"><span className="font-mono">{String(r.public_ref)}</span> · {render(r)}</span>
            </span>
            <ArrowRight size={15} className="shrink-0 text-taupe" aria-hidden />
          </Link>
        </li>
      ))}
    </ul>
  )
}

