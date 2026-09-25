'use client'

import { useState } from 'react'
import Link from 'next/link'
import { AppShell } from '@/components/layout/app-shell'
import { admin, analytics, complaints, type S } from '@/lib/api'
import { useApi, useAction } from '@/lib/use-api'
import { Badge, Button, Mono, humanise } from '@/components/ui/primitives'
import { Card, PanelHeader, PencilInk } from '@/components/ui/surfaces'
import { Stat } from '@/components/ui/data'
import { ErrorState, SkeletonRows } from '@/components/ui/feedback'
import { Bars } from '@/components/app/charts'
import { ComplaintTable } from '@/components/app/complaint-bits'
import { cn } from '@/lib/utils'

export default function SecurityPage() {
  return (
    <AppShell eyebrow="Security" roles={['manager', 'admin', 'evaluator']} wide>
      <Security />
    </AppShell>
  )
}

/**
 * Two halves. Above: what the guard has actually stopped, from the analytics
 * dashboard. Below: the deliberate defects (SRS 1.8 #15), four faulty
 * artefacts run through the real detectors on demand, nothing persisted, so
 * an evaluator can watch a detector catch a known fault.
 */
function Security() {
  const dash = useApi(() => analytics.dashboard(90))
  const flagged = useApi(() => complaints.list({ size: 10, search: '' }), [])
  const g = dash.data?.guard
  return (
    <div className="flex flex-col gap-8">
      <div><p className="eyebrow mb-1">Trust</p><h1 className="display text-h2">Security</h1><p className="mt-3 max-w-[64ch] text-[14.5px] text-espresso-2">Prompt injection is detected before the model sees the text; the response guard blocks unsupported promises, exceeded ceilings, hallucinated citations and lowered escalations before anything is sent. Below that, the deliberate defects: known faults the detectors must catch.</p></div>

      {dash.error ? <ErrorState message={dash.error} onRetry={dash.refresh} /> : (
        <div className="grid gap-6 lg:grid-cols-3">
          <Card><Stat label="Injection-flagged complaints" value={g ? g.injection_flagged_complaints ?? 0 : undefined} tone="critical" evidence="last 90 days" /><div className="mt-5"><p className="eyebrow mb-2">By pattern</p>{dash.loading && !g ? <SkeletonRows rows={3} /> : <Bars rows={Object.entries(g?.injection_events ?? {}).map(([k, v]) => ({ label: humanise(k), value: v }))} tone="critical" />}</div></Card>
          <Card><PanelHeader title="Response guard" eyebrow="Flags raised before send" />{dash.loading && !g ? <SkeletonRows rows={3} /> : <Bars rows={Object.entries(g?.response_flags ?? {}).map(([k, v]) => ({ label: humanise(k), value: v }))} tone="warning" />}</Card>
          <Card tone="cream"><PanelHeader title="The rule" /><p className="text-[14px] leading-relaxed">Instructions inside a complaint are evidence, not orders. A flagged complaint is decided by the rule engine alone, the model's output is discarded, and the attempt is written to the audit trail. Nothing about the attempt changes a category, a refund or an escalation.</p><p className="mt-3 text-[12.5px] text-taupe-2">Filter the register by <Link href="/dashboard/complaints" className="underline decoration-line underline-offset-4">injection suspected</Link> to see every flagged case.</p></Card>
        </div>
      )}

      <Defects />

      {flagged.data && flagged.data.items.some((c) => c.injection_suspected) && (
        <section><PanelHeader title="Recently flagged" eyebrow="From the register" /><ComplaintTable items={flagged.data.items.filter((c) => c.injection_suspected)} /></section>
      )}
    </div>
  )
}

function Defects() {
  const specs = useApi(() => admin.defects())
  const [results, setResults] = useState<Record<string, S['DefectResultOut']>>({})
  const one = useAction((code: string) => admin.demonstrate(code))
  const all = useAction(() => admin.demonstrateAll())
  const [busy, setBusy] = useState<string | null>(null)

  const runOne = async (code: string) => { setBusy(code); const r = await one.run(code); setBusy(null); if (r) setResults((s) => ({ ...s, [code]: r })) }
  const runAll = async () => { const rs = await all.run(); if (rs) setResults(Object.fromEntries(rs.map((r) => [r.code, r]))) }
  const caught = Object.values(results).filter((r) => r.detected).length

  return (
    <section className="flex flex-col gap-4">
      <PanelHeader title="Deliberate defects" eyebrow="SRS 1.8 #15 · known faults, real detectors, nothing persisted" aside={<><span className="text-[13px] text-taupe-2">{Object.keys(results).length ? `${caught} of ${Object.keys(results).length} caught` : ''}</span><Button size="sm" loading={all.pending} onClick={runAll}>Demonstrate all</Button></>} />
      {(one.error || all.error) && <ErrorState message={one.error ?? all.error} />}
      {specs.error ? <ErrorState message={specs.error} onRetry={specs.refresh} /> : specs.loading && !specs.data ? <SkeletonRows rows={4} /> : (
        <div className="grid gap-4 lg:grid-cols-2">
          {(specs.data ?? []).map((d) => {
            const r = results[d.code]
            return (
              <Card key={d.code} className={cn(r && (r.detected ? 'border-verified/40' : 'border-critical/40'))}>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div><Mono className="text-[12px] text-taupe-2">{d.code}</Mono><h3 className="font-display text-[20px] leading-tight">{d.name}</h3></div>
                  <div className="flex items-center gap-2"><Badge tone={d.severity === 'CRITICAL' ? 'critical' : d.severity === 'HIGH' ? 'warning' : 'neutral'}>{d.severity}</Badge>{r ? <Badge tone={r.detected ? 'verified' : 'critical'} dot>{r.detected ? 'caught' : 'MISSED'}</Badge> : <Button size="sm" variant="secondary" loading={busy === d.code} onClick={() => runOne(d.code)}>Run</Button>}</div>
                </div>
                <dl className="mt-3 grid gap-x-4 gap-y-1 text-[13px] sm:grid-cols-[110px_1fr]"><dt className="text-taupe-2">Breaks</dt><dd>{d.breaks}</dd><dt className="text-taupe-2">Detected by</dt><dd><Mono>{d.detected_by}</Mono></dd><dt className="text-taupe-2">Why it matters</dt><dd>{d.why_it_matters}</dd></dl>
                {r && (
                  <div className="mt-4 flex flex-col gap-3 border-t border-line-soft pt-4">
                    <PencilInk pencilLabel="Faulty artefact" inkLabel={r.corrected_to ? 'Corrected to' : 'Detector verdict'} pencil={<span className="text-[14px]">{r.faulty_artefact}</span>} ink={<span className="text-[14px]">{r.corrected_to ?? r.explanation}</span>} />
                    {r.corrected_to && <p className="text-[13px] text-espresso-2">{r.explanation}</p>}
                    {(r.findings ?? []).length > 0 && <ul className="flex flex-col gap-1 text-[12.5px]">{r.findings!.map((f, i) => <li key={i} className="flex gap-2"><Badge tone={f.severity === 'CRITICAL' ? 'critical' : 'warning'}>{f.flag_type}</Badge><span>{f.explanation}{f.matched_text && <Mono className="ml-1 text-taupe-2">“{f.matched_text}”</Mono>}</span></li>)}</ul>}
                    <p className="text-[12px] text-taupe-2">Detector <Mono>{r.detector}</Mono></p>
                  </div>
                )}
              </Card>
            )
          })}
        </div>
      )}
    </section>
  )
}
