'use client'

import { useState } from 'react'
import { AppShell } from '@/components/layout/app-shell'
import { analytics } from '@/lib/api'
import { useApi, pct } from '@/lib/use-api'
import { Badge, Button, Mono, humanise } from '@/components/ui/primitives'
import { Card, PanelHeader } from '@/components/ui/surfaces'
import { Stat, Ratio } from '@/components/ui/data'
import { ErrorState, SkeletonRows } from '@/components/ui/feedback'
import { Bars, Columns, Stacked } from '@/components/app/charts'
import { cn } from '@/lib/utils'

const WINDOWS = [7, 30, 90, 365]

export default function AnalyticsPage() {
  return (
    <AppShell eyebrow="Analytics" roles={['manager', 'admin', 'evaluator']} wide>
      <Story />
    </AppShell>
  )
}

/**
 * The analytics story, in the order a manager asks the questions: how much,
 * what kind, who has it, how well did the two pipelines agree, how traceable
 * was it, what did the guard stop, how did people respond. Every figure shows
 * its denominator; every null reads as not measured.
 */
function Story() {
  const [days, setDays] = useState(30)
  const dash = useApi(() => analytics.dashboard(days), [days])
  const volume = useApi(() => analytics.volume(days), [days])
  const cats = useApi(() => analytics.categories(days), [days])
  const depts = useApi(() => analytics.departments(days), [days])
  const pipes = useApi(() => analytics.pipelines(days), [days])
  const risingTrends = useApi(() => analytics.trends(days <= 7 ? 'DAY' : days <= 30 ? 'WEEK' : 'MONTH'), [days])
  const d = dash.data

  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div><p className="eyebrow mb-1">Insight</p><h1 className="display text-h2">Analytics</h1></div>
        <div className="flex items-center gap-1 rounded-full border border-line bg-ivory p-1">{WINDOWS.map((w) => <button key={w} onClick={() => setDays(w)} className={cn('rounded-full px-3 py-1 text-[13px] transition-colors', days === w ? 'bg-espresso text-ink-on-dark' : 'text-espresso-2 hover:bg-sand/60')}>{w}d</button>)}</div>
      </div>

      {dash.error ? <ErrorState message={dash.error} onRetry={dash.refresh} /> : (
        <>
          <section className="grid gap-x-8 gap-y-6 rounded-[var(--radius-xl)] border border-line bg-ivory p-6 sm:grid-cols-2 lg:grid-cols-4">
            <Stat label="Complaints" value={d ? d.volume.total ?? 0 : undefined} evidence={d ? `${d.volume.open ?? 0} open · ${d.volume.resolved ?? 0} resolved · ${d.volume.failed ?? 0} failed` : undefined} />
            <Stat label="Escalation rate" value={d ? d.escalation.rate.pct ?? null : undefined} unit="%" tone="warning" evidence={d ? `${d.escalation.rate.count ?? 0} of ${d.escalation.rate.total ?? 0}` : undefined} />
            <Stat label="Decisions with GenAI" value={d ? d.pipelines.with_genai ?? 0 : undefined} evidence={d ? `${d.pipelines.degraded ?? 0} degraded (rules alone) of ${d.pipelines.decisions ?? 0}` : undefined} />
            <Stat label="SLA open at risk" value={d ? d.sla.open_at_risk ?? 0 : undefined} tone={d && (d.sla.open_at_risk ?? 0) > 0 ? 'warning' : 'neutral'} />
          </section>

          {risingTrends.data && risingTrends.data.length > 0 && (
            <Card tone="cream">
              <PanelHeader
                title="Rising Trends & Recurring Issues"
                eyebrow="Material changes over consecutive periods (categories, products, repeat failures, escalations)"
              />
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {risingTrends.data.map((t, idx) => (
                  <div
                    key={`${t.metric}-${t.dimension}-${t.dimension_value}-${idx}`}
                    className="flex flex-col justify-between rounded-[var(--radius-md)] border border-line bg-ivory p-3.5 shadow-sm"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <span className="text-[11px] font-semibold uppercase tracking-wider text-taupe-2">
                        {t.dimension === 'ALL' ? humanise(t.metric) : `${t.dimension}: ${t.dimension_value}`}
                      </span>
                      {t.anomaly ? (
                        <Badge tone="critical">Anomaly</Badge>
                      ) : (
                        <Badge tone="warning">Rising</Badge>
                      )}
                    </div>
                    <div className="mt-2 flex items-baseline justify-between">
                      <span className="font-mono text-[20px] font-medium text-ink">
                        {t.value}
                      </span>
                      <span className="text-[12px] text-taupe-2">
                        was {t.previous_value}{' '}
                        {t.delta_pct != null ? (
                          <span className="font-semibold text-critical">
                            (+{t.delta_pct}%)
                          </span>
                        ) : (
                          <span className="font-semibold text-warning">(new)</span>
                        )}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          )}

          <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
            <Card>
              <PanelHeader title="Volume" eyebrow="By day" />
              {volume.loading && !volume.data ? <SkeletonRows rows={3} /> : volume.error ? <p className="text-[13px] text-taupe-2">{volume.error}</p> : volume.data?.series?.length ? <Columns points={volume.data.series.map((p) => ({ label: p.date, value: p.count }))} height={140} /> : <Stacked parts={Object.entries(volume.data?.by_status ?? {}).map(([k, v]) => ({ label: humanise(k), value: v, tone: k === 'RESOLVED' || k === 'CLOSED' ? 'verified' : k === 'FAILED' ? 'critical' : k === 'ESCALATED' || k === 'MANUAL_REVIEW' ? 'warning' : 'espresso' }))} />}
              {volume.data?.by_status && volume.data.series?.length ? <div className="mt-5"><Stacked parts={Object.entries(volume.data.by_status).map(([k, v]) => ({ label: humanise(k), value: v, tone: k === 'RESOLVED' || k === 'CLOSED' ? 'verified' : k === 'FAILED' ? 'critical' : k === 'ESCALATED' || k === 'MANUAL_REVIEW' ? 'warning' : 'espresso' }))} /></div> : null}
            </Card>
            <Card>
              <PanelHeader title="Categories" eyebrow="Unclassified shown, not dropped" />
              {cats.loading && !cats.data ? <SkeletonRows rows={5} /> : <Bars rows={(cats.data ?? []).map((c) => ({ label: c.name, value: c.count, sub: c.pct != null ? `${c.pct}%` : undefined }))} />}
            </Card>
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <Card>
              <PanelHeader title="Products & Services" eyebrow="Breakdown across complaints" />
              {!d ? <SkeletonRows rows={5} /> : <Bars rows={(d.products ?? []).slice(0, 8).map((p: any) => ({ label: p.product, value: p.count, sub: p.pct != null ? `${p.pct}%` : undefined }))} />}
            </Card>
            <Card>
              <PanelHeader title="Customer Sentiment" eyebrow="Emotion indicator distribution" />
              {!d ? <SkeletonRows rows={4} /> : (
                <>
                  <Stacked parts={Object.entries(d.sentiment ?? {}).map(([k, v]) => ({
                    label: humanise(k),
                    value: v as number,
                    tone: k === 'POSITIVE' ? 'verified' : k === 'NEUTRAL' ? 'taupe' : k === 'STRONGLY_NEGATIVE' ? 'critical' : 'warning'
                  }))} />
                  {d.sentiment && (
                    <div className="mt-5">
                      <Bars rows={Object.entries(d.sentiment).map(([k, v]) => ({ label: humanise(k), value: v as number }))} tone="taupe" />
                    </div>
                  )}
                </>
              )}
            </Card>
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <Card>
              <PanelHeader title="Urgency distribution" eyebrow="Triage assessment" />
              {!d ? <SkeletonRows rows={4} /> : (
                <Bars rows={Object.entries(d.urgency ?? {}).map(([k, v]) => ({
                  label: humanise(k),
                  value: v as number,
                }))} tone="warning" />
              )}
            </Card>
            <Card>
              <PanelHeader title="Repeat complaints" eyebrow="Recurrence and history" />
              {!d ? <SkeletonRows rows={4} /> : (
                <>
                  <div className="grid grid-cols-2 gap-4 mb-4">
                    <Stat label="Repeat rate" value={d.repeat_complaints?.repeat_rate_pct ?? null} unit="%" tone={(d.repeat_complaints?.repeat_rate_pct ?? 0) > 15 ? 'warning' : 'neutral'} evidence={`${d.repeat_complaints?.repeated_complaints ?? 0} repeat complaints`} />
                    <Stat label="Total complaints" value={d.repeat_complaints?.total_complaints ?? 0} />
                  </div>
                  {d.repeat_complaints?.top_categories?.length ? (
                    <div>
                      <p className="eyebrow mb-2">Top recurring categories</p>
                      <Bars rows={d.repeat_complaints.top_categories.map((c: any) => ({ label: c.name, value: c.count }))} tone="taupe" />
                    </div>
                  ) : null}
                </>
              )}
            </Card>
          </div>

          <Card>
            <PanelHeader title="Resolution time" eyebrow="Overall and by priority (hours to resolve)" />
            {!d ? <SkeletonRows rows={3} /> : (
              <>
                <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4 mb-6">
                  <Stat label="Average resolution" value={d.resolution_time?.overall?.avg_hours ?? null} unit=" hrs" evidence={d.resolution_time?.overall?.count ? `${d.resolution_time.overall.count} resolved cases` : 'No resolved cases'} />
                  <Stat label="Median resolution" value={d.resolution_time?.overall?.median_hours ?? null} unit=" hrs" />
                  <Stat label="Fastest resolution" value={d.resolution_time?.overall?.min_hours ?? null} unit=" hrs" tone="verified" />
                  <Stat label="Longest resolution" value={d.resolution_time?.overall?.max_hours ?? null} unit=" hrs" tone="warning" />
                </div>
                {d.resolution_time?.by_priority && Object.keys(d.resolution_time.by_priority).length > 0 && (
                  <div>
                    <p className="eyebrow mb-2">Average hours by priority</p>
                    <div className="grid gap-3 sm:grid-cols-2 md:grid-cols-4">
                      {Object.entries(d.resolution_time.by_priority).map(([prio, stats]: [string, any]) => (
                        <div key={prio} className="rounded-[var(--radius-md)] border border-line bg-cream/40 p-3">
                          <p className="text-[12px] font-semibold text-espresso">{prio}</p>
                          <p className="mt-1 font-mono text-[18px] font-medium text-ink">{stats?.avg_hours != null ? `${stats.avg_hours}h` : '—'}</p>
                          <p className="text-[11px] text-taupe-2">{stats?.count ?? 0} cases · med {stats?.median_hours != null ? `${stats.median_hours}h` : '—'}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}
          </Card>

          <div className="grid gap-6 lg:grid-cols-2">
            <Card>
              <PanelHeader title="Department load" eyebrow="Total and open" />
              {depts.loading && !depts.data ? <SkeletonRows rows={5} /> : (
                <ul className="flex flex-col gap-2">
                  {(depts.data ?? []).map((x) => { const max = Math.max(1, ...(depts.data ?? []).map((y) => y.total)); return (
                    <li key={x.code} className="grid grid-cols-[minmax(120px,200px)_1fr_90px] items-center gap-3 text-[13px]">
                      <span className="truncate" title={x.name}>{x.name}</span>
                      <span className="relative h-4 overflow-hidden rounded-full bg-sand"><span className="absolute inset-y-0 left-0 rounded-full bg-taupe" style={{ width: `${(x.total / max) * 100}%` }} /><span className="absolute inset-y-0 left-0 rounded-full bg-espresso" style={{ width: `${(x.open / max) * 100}%` }} /></span>
                      <span className="text-right font-mono text-[12px] tnum">{x.open} / {x.total}</span>
                    </li>
                  ) })}
                  {!depts.data?.length && <li className="text-[13.5px] text-taupe-2">No routed complaints in the window.</li>}
                </ul>
              )}
            </Card>
            <Card>
              <PanelHeader title="Escalation ladder" />
              <Bars rows={Object.entries(d?.escalation.by_level ?? {}).map(([k, v]) => ({ label: k, value: v }))} tone="warning" />
              {d && Object.keys(d.escalation.by_trigger ?? {}).length > 0 && <div className="mt-5"><p className="eyebrow mb-2">Triggered by</p><Bars rows={Object.entries(d.escalation.by_trigger ?? {}).map(([k, v]) => ({ label: humanise(k), value: v }))} tone="taupe" /></div>}
            </Card>
          </div>

          <Card tone="cream">
            <PanelHeader title="Pipeline agreement" eyebrow="The model against the rules · deliberately not called accuracy" aside={<Button href="/dashboard/benchmark" size="sm" variant="secondary">Accuracy lives in the benchmark</Button>} />
            {pipes.loading && !pipes.data ? <SkeletonRows rows={3} /> : pipes.error ? <p className="text-[13px] text-taupe-2">{pipes.error}</p> : pipes.data && (
              <div className="grid gap-6 md:grid-cols-[1fr_1fr_1.2fr]">
                <Stat label="Mean agreement" value={pipes.data.mean_agreement_pct ?? null} unit="%" evidence={`${pipes.data.with_genai ?? 0} contested decisions`} />
                <div className="flex flex-col justify-end"><Ratio numerator={pipes.data.rules_corrected_the_model.count ?? 0} denominator={pipes.data.rules_corrected_the_model.total ?? 0} label="Rules corrected the model" tone="warning" /><p className="mt-2 text-[12.5px] text-taupe-2">{pipes.data.critical_mismatches ?? 0} critical mismatches</p></div>
                <div><p className="eyebrow mb-2">By outcome</p><Bars rows={Object.entries(pipes.data.by_outcome ?? {}).map(([k, v]) => ({ label: humanise(k), value: v }))} tone="taupe" /></div>
              </div>
            )}
          </Card>

          <div className="grid gap-6 lg:grid-cols-3">
            <Card>
              <PanelHeader title="Traceability" eyebrow="Citations that resolved" />
              <div className="flex flex-col gap-4">
                <Stat label="Mean traceability" value={d ? d.traceability.mean_traceability_pct ?? null : undefined} unit="%" evidence={d ? `${d.traceability.unmeasured_traceability ?? 0} decisions unmeasured` : undefined} tone="verified" />
                <Stat label="Mean compliance" value={d ? d.traceability.mean_compliance_pct ?? null : undefined} unit="%" evidence={d ? `${d.traceability.unmeasured_compliance ?? 0} decisions unmeasured` : undefined} tone="verified" />
              </div>
            </Card>
            <Card>
              <PanelHeader title="Security guard" eyebrow="What was stopped" />
              <Stat label="Injection-flagged complaints" value={d ? d.guard.injection_flagged_complaints ?? 0 : undefined} tone="critical" />
              <div className="mt-4"><p className="eyebrow mb-2">Injection events</p><Bars rows={Object.entries(d?.guard.injection_events ?? {}).map(([k, v]) => ({ label: humanise(k), value: v }))} tone="critical" /></div>
              <div className="mt-4"><p className="eyebrow mb-2">Response flags</p><Bars rows={Object.entries(d?.guard.response_flags ?? {}).map(([k, v]) => ({ label: humanise(k), value: v }))} tone="warning" /></div>
            </Card>
            <Card>
              <PanelHeader title="Human review" />
              {d && <div className="flex flex-col gap-4"><Ratio numerator={d.review.override_rate.count ?? 0} denominator={d.review.override_rate.total ?? 0} label="Override rate" tone="warning" /><div><p className="eyebrow mb-2">Queue depth</p><div className="flex flex-wrap gap-1.5">{Object.entries(d.review.queue_depth ?? {}).map(([k, v]) => <Badge key={k}>{humanise(k)} <Mono className="ml-1">{v}</Mono></Badge>)}{!Object.keys(d.review.queue_depth ?? {}).length && <span className="text-[13px] text-taupe-2">empty</span>}</div></div><div><p className="eyebrow mb-2">By action</p><Bars rows={Object.entries(d.review.by_action ?? {}).map(([k, v]) => ({ label: humanise(k), value: v }))} tone="taupe" /></div></div>}
            </Card>
          </div>

          <Card>
            <PanelHeader title="SLA compliance" eyebrow="By event type" />
            {d && Object.keys(d.sla.by_type ?? {}).length ? (
              <div className="grid gap-6 md:grid-cols-2">
                {Object.entries(d.sla.by_type ?? {}).map(([k, v]) => (
                  <div key={k}><Ratio numerator={v.compliance.count ?? 0} denominator={v.compliance.total ?? 0} label={`${humanise(k)} · compliance ${pct(v.compliance.pct, 1)}`} tone={(v.compliance.pct ?? 100) < 80 ? 'critical' : 'verified'} /><p className="mt-1.5 text-[12.5px] text-taupe-2">{v.met ?? 0} met · {v.breached ?? 0} breached · {v.at_risk ?? 0} at risk · {v.settled ?? 0} settled</p></div>
                ))}
              </div>
            ) : <p className="text-[13.5px] text-taupe-2">No SLA events in the window.</p>}
          </Card>

          {d && <p className="text-[12px] text-taupe-2">Generated {new Date(d.generated_at).toLocaleString()} · window {d.window_days ?? days} days</p>}
        </>
      )}
    </div>
  )
}
