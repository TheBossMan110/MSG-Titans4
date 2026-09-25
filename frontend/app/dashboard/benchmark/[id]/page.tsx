'use client'

import { use } from 'react'
import Link from 'next/link'
import { AppShell } from '@/components/layout/app-shell'
import { benchmark } from '@/lib/api'
import { useApi } from '@/lib/use-api'
import { Badge, Button, Mono, humanise } from '@/components/ui/primitives'
import { Card, PanelHeader } from '@/components/ui/surfaces'
import { KV, Table, Th, Td, Tr, Stat } from '@/components/ui/data'
import { Empty, ErrorState, Loading } from '@/components/ui/feedback'
import { Bars } from '@/components/app/charts'

export default function RunPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params)
  return (
    <AppShell eyebrow="Benchmark / Run" roles={['manager', 'admin', 'evaluator']} wide>
      <Run id={id} />
    </AppShell>
  )
}

/**
 * The metrics dictionary is rendered as it comes: every numeric leaf becomes
 * a figure, every nested object a group. This page does not decide what the
 * runner measures; it shows what it measured.
 */
function Run({ id }: { id: string }) {
  const q = useApi(() => benchmark.runDetail(id), [id])
  if (q.loading && !q.data) return <Loading label="Opening the run" />
  if (q.error) return <ErrorState message={q.error} onRetry={q.refresh} />
  const r = q.data!
  const m = (r.metrics ?? {}) as Record<string, unknown>
  const groups = Object.entries(m).filter(([, v]) => v && typeof v === 'object' && !Array.isArray(v)) as Array<[string, Record<string, unknown>]>
  const leaves = Object.entries(m).filter(([, v]) => typeof v === 'number' || typeof v === 'string' || v === null) as Array<[string, number | string | null]>
  const failures = r.rule_failures ?? []
  const byField = failures.reduce<Record<string, number>>((acc, f) => { acc[f.field] = (acc[f.field] ?? 0) + 1; return acc }, {})

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="eyebrow mb-2"><Link href="/dashboard/benchmark" className="underline decoration-line underline-offset-4">Benchmark</Link> / <Mono>{r.id.slice(0, 8)}</Mono></p>
          <h1 className="display text-h2">{r.label}</h1>
          <div className="mt-3 flex flex-wrap gap-2"><Badge tone={r.status === 'COMPLETED' || r.status === 'DONE' ? 'verified' : r.status === 'FAILED' ? 'critical' : 'warning'} dot>{humanise(r.status)}</Badge><Badge><Mono>{r.dataset_tag}</Mono></Badge></div>
        </div>
        <Button href={`/dashboard/benchmark/datasets/${encodeURIComponent(r.dataset_tag)}`} variant="secondary" size="sm">Dataset</Button>
      </div>

      <Card tone="cream"><KV rows={[['Ruleset', <Mono key="r">{r.ruleset_version}</Mono>], ['Prompt version', <Mono key="p">{r.prompt_version}</Mono>], ['Provider · model', <Mono key="m">{r.provider} · {r.model}</Mono>]]} className="sm:grid-cols-[max-content_1fr_max-content_1fr_max-content_1fr]" /></Card>

      {leaves.length > 0 && <div className="grid gap-x-8 gap-y-6 rounded-[var(--radius-xl)] border border-line bg-ivory p-6 sm:grid-cols-2 lg:grid-cols-4">{leaves.map(([k, v]) => <Stat key={k} label={humanise(k)} value={typeof v === 'number' ? Number.isInteger(v) ? v : v <= 1 && /pct|rate|acc|score|agree/i.test(k) ? Math.round(v * 1000) / 10 : Math.round(v * 100) / 100 : v} unit={typeof v === 'number' && /pct|rate|acc|score|agree/i.test(k) ? '%' : undefined} />)}</div>}

      {groups.length > 0 && (
        <div className="grid gap-6 lg:grid-cols-2">
          {groups.map(([name, obj]) => (
            <Card key={name}>
              <PanelHeader title={humanise(name)} />
              <MetricGroup obj={obj} />
            </Card>
          ))}
        </div>
      )}
      {!leaves.length && !groups.length && <Empty title="No metrics recorded" body={r.status === 'FAILED' ? 'The run failed before scoring.' : 'The run has not finished scoring.'} />}

      <section>
        <PanelHeader title="Where the rules were wrong" eyebrow={`${failures.length} rule failures against the labels`} />
        {!failures.length ? <Empty title="No rule failures recorded" /> : (
          <div className="grid gap-6 lg:grid-cols-[280px_1fr]">
            <Card padding="sm" className="self-start"><p className="eyebrow mb-2 px-1">By field</p><Bars rows={Object.entries(byField).sort((a, b) => b[1] - a[1]).map(([k, v]) => ({ label: humanise(k), value: v }))} tone="critical" /></Card>
            <Table dense>
              <thead><tr><Th>Complaint</Th><Th>Field</Th><Th>Expected</Th><Th>Rules</Th><Th>GenAI</Th><Th>Explanation</Th></tr></thead>
              <tbody>{failures.slice(0, 300).map((f, i) => <Tr key={i}><Td mono><Link href={`/dashboard/complaints/${f.public_ref}`} className="underline decoration-line underline-offset-4">{f.public_ref}</Link></Td><Td>{humanise(f.field)}</Td><Td><span className="ink rounded px-1.5 py-0.5 font-mono text-[11.5px]">{f.expected ?? '—'}</span></Td><Td mono className="text-critical">{f.python ?? '—'}</Td><Td><span className="pencil rounded px-1.5 py-0.5 font-mono text-[11.5px]">{f.genai ?? '—'}</span></Td><Td className="max-w-[320px] text-[12.5px] text-taupe-2">{f.explanation ?? ''}</Td></Tr>)}</tbody>
            </Table>
          </div>
        )}
      </section>
    </div>
  )
}

function MetricGroup({ obj }: { obj: Record<string, unknown> }) {
  const entries = Object.entries(obj)
  const numeric = entries.filter(([, v]) => typeof v === 'number') as Array<[string, number]>
  const nested = entries.filter(([, v]) => v && typeof v === 'object' && !Array.isArray(v)) as Array<[string, Record<string, unknown>]>
  const other = entries.filter(([, v]) => !(typeof v === 'number') && !(v && typeof v === 'object' && !Array.isArray(v)))
  const pctLike = numeric.every(([k, v]) => v >= 0 && v <= 1) || numeric.every(([k]) => /pct|rate|acc|score/i.test(k))
  return (
    <div className="flex flex-col gap-4">
      {numeric.length > 0 && <Bars rows={numeric.map(([k, v]) => ({ label: humanise(k), value: pctLike ? Math.round((v <= 1 ? v * 100 : v) * 10) / 10 : v }))} max={pctLike ? 100 : undefined} tone={pctLike ? 'verified' : 'espresso'} />}
      {other.length > 0 && <KV rows={other.map(([k, v]) => [humanise(k), Array.isArray(v) ? v.join(', ') : String(v)])} />}
      {nested.map(([k, v]) => <div key={k} className="border-t border-line-soft pt-3"><p className="eyebrow mb-2">{humanise(k)}</p><MetricGroup obj={v} /></div>)}
    </div>
  )
}
