'use client'

import { useState } from 'react'
import Link from 'next/link'
import { Building, Gauge, Scale, ShieldCheck, Target, Users } from 'lucide-react'
import { AppShell } from '@/components/layout/app-shell'
import { platform } from '@/lib/api'
import { useApi, fmtDate } from '@/lib/use-api'
import { Badge, humanise } from '@/components/ui/primitives'
import { Card, PanelHeader } from '@/components/ui/surfaces'
import { Stat } from '@/components/ui/data'
import { ErrorState, SkeletonRows } from '@/components/ui/feedback'
import { Bars, Stacked } from '@/components/app/charts'
import { cn } from '@/lib/utils'

const WINDOWS: Array<[number | undefined, string]> = [[7, '7 days'], [30, '30 days'], [90, '90 days'], [undefined, 'All time']]

// The aggregate blocks arrive as open dictionaries (the same ones each
// company's analytics return); these are the shapes this page reads.
type RatioOut = { count: number; total: number; pct: number | null }
interface Volume { total: number; open: number; resolved: number; failed: number; by_status?: Record<string, number> }
interface Agreement { decisions: number; with_genai: number; degraded: number; mean_agreement_pct: number | null; rules_corrected_the_model: RatioOut; critical_mismatches: number; by_outcome: Record<string, number> }
interface Safety { injection_events: Record<string, number>; injection_flagged_complaints: number; response_flags: Record<string, number> }
interface Ai { calls: number; answered: RatioOut; by_status: Record<string, number> }
interface Sla { by_type: Record<string, { compliance: RatioOut; at_risk?: number }>; open_at_risk: number }
interface Escalation { rate: RatioOut }
interface Resolution { overall?: { avg_hours?: number | null; median_hours?: number | null; count?: number } }
interface Traceability { mean_traceability_pct: number | null; mean_compliance_pct: number | null }

const OUTCOME_TONE: Record<string, 'verified' | 'info' | 'warning' | 'taupe' | 'critical' | 'sand'> = {
  VERIFIED: 'verified', VERIFIED_WITH_WARNING: 'info', CORRECTED_BY_RULES: 'warning',
  MANUAL_REVIEW_REQUIRED: 'taupe', BLOCKED: 'critical', INCOMPLETE: 'sand',
}
const PRIORITY_TONE: Record<string, 'critical' | 'warning' | 'espresso' | 'taupe' | 'sand'> = { P0: 'critical', P1: 'warning', P2: 'espresso', P3: 'taupe', UNSET: 'sand' }

const sum = (o?: Record<string, number>) => Object.values(o ?? {}).reduce((a, b) => a + b, 0)
const pct = (v: number | null | undefined) => (v == null ? null : Math.round(v * 10) / 10)

export default function PlatformPage() {
  return (
    <AppShell eyebrow="Platform / Overview" roles={['superadmin']} wide>
      <Overview />
    </AppShell>
  )
}

/**
 * The super administrator's home: the whole platform in totals. It answers
 * "how many companies, how much work, and how well is the system doing?" and
 * nothing about any one company's complaints, customers, people or emails --
 * the API refuses this role on every router that serves those.
 */
function Overview() {
  const [days, setDays] = useState<number | undefined>(undefined)
  const q = useApi(() => platform.overview(days), [days])
  if (q.error) return <ErrorState title="The platform overview could not be loaded" message={q.error} onRetry={q.refresh} />
  const d = q.data
  const volume = d?.complaints as unknown as Volume | undefined
  const agreement = d?.agreement as unknown as Agreement | undefined
  const safety = d?.safety as unknown as Safety | undefined
  const ai = d?.ai as unknown as Ai | undefined
  const sla = d?.sla as unknown as Sla | undefined
  const escalation = d?.escalation as unknown as Escalation | undefined
  const resolution = d?.resolution_time as unknown as Resolution | undefined
  const trace = d?.traceability as unknown as Traceability | undefined
  const bench = d?.benchmark

  return (
    <div className="flex min-w-0 flex-col gap-6">
      <section className="mesh-banner grain relative overflow-hidden rounded-[var(--radius-xl)] px-6 py-8 text-ink-on-dark md:px-10 md:py-10">
        <div className="relative z-[1] flex flex-wrap items-end justify-between gap-6">
          <div className="min-w-0">
            <p className="eyebrow mb-3 flex items-center gap-2 text-sand-2"><Building size={13} aria-hidden /> Super administrator</p>
            <h1 className="display text-h1 text-ink-on-dark">SupportNova Platform</h1>
            <p className="mt-3 max-w-[60ch] text-[15.5px] text-ink-on-dark/80">
              Every company on the platform, in totals: how much work there is and how well the system is doing.
              No company&apos;s complaints, people or emails are visible here, by design.
            </p>
          </div>
          <div className="flex flex-wrap gap-2" role="group" aria-label="Time window">
            {WINDOWS.map(([value, label]) => (
              <button key={label} type="button" onClick={() => setDays(value)} aria-pressed={days === value}
                className={cn('rounded-full px-3 py-1.5 text-[13px] transition-colors', days === value ? 'bg-ink-on-dark text-espresso' : 'border border-ink-on-dark/25 text-ink-on-dark hover:bg-ink-on-dark/10')}>
                {label}
              </button>
            ))}
          </div>
        </div>
      </section>

      <div className="grid grid-cols-2 gap-x-6 gap-y-5 rounded-[var(--radius-xl)] border border-line bg-ivory p-5 sm:grid-cols-3 lg:grid-cols-6 md:p-6">
        <Stat label="Companies" value={d?.companies.total} icon={<Building size={12} aria-hidden />}
          evidence={d ? `${d.companies.active} active · ${d.companies.suspended} suspended` : undefined} />
        <Stat label="Staff" value={d?.people.staff} icon={<Users size={12} aria-hidden />} evidence="across every company" />
        <Stat label="Customers" value={d?.people.customers} />
        <Stat label="Complaints" value={volume?.total} evidence={days ? `last ${days} days` : 'all time'} />
        <Stat label="Open" value={volume?.open} tone={volume && volume.open > 0 ? 'warning' : 'neutral'} />
        <Stat label="Resolved" value={volume?.resolved} tone="verified" />
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.25fr_1fr]">
        <Card tone="glass" radius="xl">
          <PanelHeader eyebrow="How well it works" title="System accuracy" icon={<Target size={15} aria-hidden />} />
          {!d ? <SkeletonRows rows={5} /> : (
            <div className="flex flex-col gap-6">
              <div className="grid gap-5 sm:grid-cols-3">
                <Stat label="AI agrees with the rules" value={pct(agreement?.mean_agreement_pct)} unit="%"
                  evidence={`across ${agreement?.with_genai ?? 0} complaints the AI answered`} />
                <Stat label="Rules corrected the AI" value={pct(agreement?.rules_corrected_the_model.pct)} unit="%" tone="warning"
                  evidence={`${agreement?.rules_corrected_the_model.count ?? 0} of ${agreement?.rules_corrected_the_model.total ?? 0}`} />
                <Stat label="Citations that resolve" value={pct(trace?.mean_traceability_pct)} unit="%" tone="verified"
                  evidence="to an active policy paragraph" />
              </div>
              <div>
                <p className="mb-2 text-[13px] font-medium text-taupe-2">Verification outcomes</p>
                <Stacked parts={Object.entries(agreement?.by_outcome ?? {}).map(([k, v]) => ({ label: humanise(k), value: v, tone: OUTCOME_TONE[k] ?? 'sand' }))} />
              </div>
              <div className="rounded-2xl border border-line-soft bg-white/60 p-4">
                <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
                  <p className="font-medium text-espresso">Measured accuracy against labelled data</p>
                  {bench && <span className="text-[12.5px] text-taupe-2">{bench.dataset_tag} · {bench.sample_size ?? 0} complaints · {fmtDate(bench.finished_at, false)}</span>}
                </div>
                {!bench ? (
                  <p className="text-[13.5px] text-taupe-2">No labelled dataset has been scored yet. A company runs one from its Benchmark page.</p>
                ) : (
                  <div className="grid gap-5 sm:grid-cols-3">
                    <Stat label="Rules (Pipeline 2)" value={pct(bench.python_accuracy_pct)} unit="%" />
                    <Stat label="GenAI (Pipeline 1)" value={pct(bench.genai_accuracy_pct)} unit="%" />
                    <Stat label="Required escalations caught" value={pct(bench.escalation_recall_pct)} unit="%" tone="verified" evidence="target 100%" />
                  </div>
                )}
              </div>
              <p className="text-[12.5px] text-taupe-2">
                Agreement measures the AI against the rules, not against truth; measured accuracy needs labels. Complaints
                analysed while no AI provider answered ({agreement?.degraded ?? 0}) are left out rather than counted as disagreements.
              </p>
            </div>
          )}
        </Card>

        <div className="flex flex-col gap-6">
          <Card tone="glass" radius="xl">
            <PanelHeader eyebrow="Safety" title="What the safeguards stopped" icon={<ShieldCheck size={15} aria-hidden />} />
            {!d ? <SkeletonRows rows={4} /> : (
              <div className="flex flex-col gap-5">
                <div className="grid grid-cols-2 gap-5">
                  <Stat label="Injection attempts" value={sum(safety?.injection_events)} tone="critical"
                    evidence={`${safety?.injection_flagged_complaints ?? 0} complaints flagged`} />
                  <Stat label="Replies stopped by the guard" value={sum(safety?.response_flags)} tone="warning" />
                </div>
                <Bars rows={Object.entries(safety?.injection_events ?? {}).map(([k, v]) => ({ label: humanise(k), value: v }))} tone="critical" />
              </div>
            )}
          </Card>
          <Card tone="glass" radius="xl">
            <PanelHeader eyebrow="Health" title="AI and service" icon={<Gauge size={15} aria-hidden />} />
            {!d ? <SkeletonRows rows={4} /> : (
              <div className="grid grid-cols-2 gap-5">
                <Stat label="AI calls answered" value={pct(ai?.answered.pct)} unit="%" tone="verified"
                  evidence={`${ai?.answered.count ?? 0} of ${ai?.calls ?? 0} calls; the rules decide when it fails`} />
                <Stat label="Escalation rate" value={pct(escalation?.rate.pct)} unit="%" evidence={`${escalation?.rate.count ?? 0} escalated`} />
                <Stat label="Average resolution" value={resolution?.overall?.avg_hours ?? null} unit=" hrs"
                  evidence={`${resolution?.overall?.count ?? 0} resolved`} />
                <Stat label="SLA clocks at risk" value={sla?.open_at_risk} tone={sla && sla.open_at_risk > 0 ? 'warning' : 'neutral'} />
              </div>
            )}
          </Card>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card tone="glass" radius="xl">
          <PanelHeader eyebrow="Workload" title="Complaints by company" icon={<Building size={15} aria-hidden />}
            aside={<Link href="/dashboard/companies" className="text-[13px] text-espresso underline decoration-line underline-offset-4">All companies</Link>} />
          {!d ? <SkeletonRows rows={5} /> : (
            <Bars rows={d.by_company.slice(0, 10).map((c) => ({
              label: c.is_active ? c.name : `${c.name} (suspended)`, value: c.complaints, sub: `${c.open_complaints} open`,
            }))} />
          )}
        </Card>
        <Card tone="glass" radius="xl">
          <PanelHeader eyebrow="Urgency" title="Priority mix" icon={<Scale size={15} aria-hidden />} />
          {!d ? <SkeletonRows rows={3} /> : (
            <div className="flex flex-col gap-4">
              <Stacked parts={['P0', 'P1', 'P2', 'P3', 'UNSET'].filter((k) => d.priorities[k]).map((k) => ({ label: k === 'UNSET' ? 'Not yet set' : k, value: d.priorities[k], tone: PRIORITY_TONE[k] }))} />
              <div className="flex flex-wrap gap-2">
                {Object.entries(sla?.by_type ?? {}).map(([name, s]) => (
                  <Badge key={name} tone={s.compliance.pct == null ? 'neutral' : s.compliance.pct >= 90 ? 'verified' : 'warning'}>
                    {humanise(name)} SLA met: {s.compliance.pct == null ? 'nothing settled' : `${pct(s.compliance.pct)}%`}
                  </Badge>
                ))}
              </div>
            </div>
          )}
        </Card>
      </div>
    </div>
  )
}
