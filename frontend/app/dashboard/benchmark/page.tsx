'use client'

import { useState } from 'react'
import Link from 'next/link'
import { AppShell } from '@/components/layout/app-shell'
import { useAuth } from '@/lib/auth-context'
import { benchmark } from '@/lib/api'
import { useApi, useAction, fmtDate, fmtRelative } from '@/lib/use-api'
import { Badge, Button, Mono, humanise } from '@/components/ui/primitives'
import { Card, PanelHeader } from '@/components/ui/surfaces'
import { Field, Input, Select, Checkbox } from '@/components/ui/forms'
import { Table, Th, Td, Tr, Ratio } from '@/components/ui/data'
import { Empty, ErrorState, SkeletonRows, useToast } from '@/components/ui/feedback'

export default function BenchmarkPage() {
  return (
    <AppShell eyebrow="Benchmark" roles={['manager', 'admin', 'evaluator']} wide>
      <Bench />
    </AppShell>
  )
}

/**
 * Accuracy lives here, and only here: labelled datasets scored against both
 * pipelines. The analytics page measures agreement between the pipelines;
 * this page measures each against the truth.
 */
function Bench() {
  const { user } = useAuth()
  const toast = useToast()
  const datasets = useApi(() => benchmark.datasets())
  const runs = useApi(() => benchmark.runs(50))
  const start = useAction((p: Parameters<typeof benchmark.run>[0]) => benchmark.run(p))
  const [form, setForm] = useState({ dataset_tag: '', label: '', limit: '', run_genai: true, workers: 4, resume: true })
  const operator = user && ['evaluator', 'admin'].includes(user.role)

  return (
    <div className="flex flex-col gap-6">
      <div><p className="eyebrow mb-1">Ground truth</p><h1 className="display text-h2">Benchmark</h1><p className="mt-3 max-w-[64ch] text-[14.5px] text-espresso-2">Labelled datasets, imported from CSV, scored against both pipelines. Every run records the ruleset, prompt version, provider and model it used, so a number can be reproduced or disputed.</p></div>

      <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
        <div className="flex flex-col gap-6">
          <section>
            <PanelHeader title="Datasets" aside={operator && <Button href="/dashboard/benchmark/datasets/new" size="sm" variant="secondary">Import a dataset</Button>} />
            {datasets.error ? <ErrorState message={datasets.error} onRetry={datasets.refresh} /> : datasets.loading && !datasets.data ? <SkeletonRows rows={3} /> : !datasets.data?.length ? <Empty title="No datasets" body="Import a labelled CSV to begin." /> : (
              <Table dense>
                <thead><tr><Th>Tag</Th><Th align="right">Total</Th><Th align="right">Labelled</Th><Th align="right">Analysed</Th><Th align="right">Pending</Th><Th /></tr></thead>
                <tbody>{datasets.data.map((d) => <Tr key={d.dataset_tag}><Td mono><Link href={`/dashboard/benchmark/datasets/${encodeURIComponent(d.dataset_tag)}`} className="underline decoration-line underline-offset-4">{d.dataset_tag}</Link></Td><Td align="right" mono>{d.total ?? 0}</Td><Td align="right" mono>{d.labelled ?? 0}{(d.unlabelled ?? 0) > 0 && <span className="text-taupe-2"> (+{d.unlabelled} unlabelled)</span>}</Td><Td align="right" mono>{d.analysed ?? 0}</Td><Td align="right" mono>{d.pending_analysis ?? 0}</Td><Td align="right">{operator && <Button size="sm" variant="ghost" onClick={() => setForm((f) => ({ ...f, dataset_tag: d.dataset_tag }))}>Use</Button>}</Td></Tr>)}</tbody>
              </Table>
            )}
          </section>

          <section>
            <PanelHeader title="Runs" aside={<Button size="sm" variant="ghost" onClick={runs.refresh}>Refresh</Button>} />
            {runs.error ? <ErrorState message={runs.error} onRetry={runs.refresh} /> : runs.loading && !runs.data ? <SkeletonRows rows={5} /> : !runs.data?.length ? <Empty title="No runs yet" /> : (
              <Table dense>
                <thead><tr><Th>Label</Th><Th>Dataset</Th><Th>Status</Th><Th align="right">Sample</Th><Th>Category</Th><Th>Escalation</Th><Th>Stamp</Th><Th align="right">Started</Th></tr></thead>
                <tbody>{runs.data.map((r) => { const m = r.metrics as Record<string, unknown> | undefined; return <Tr key={r.id}><Td><Link href={`/dashboard/benchmark/${r.id}`} className="underline decoration-line underline-offset-4">{r.label}</Link></Td><Td mono>{r.dataset_tag}</Td><Td><Badge tone={r.status === 'COMPLETED' || r.status === 'DONE' ? 'verified' : r.status === 'FAILED' ? 'critical' : 'warning'} dot>{humanise(r.status)}</Badge></Td><Td align="right" mono>{r.sample_size ?? '—'}</Td><Td mono>{metric(m, 'category')}</Td><Td mono>{metric(m, 'escalation')}</Td><Td className="text-[11.5px] text-taupe-2"><Mono>{r.ruleset_version}</Mono> · {r.prompt_version} · {r.provider}/{r.model}</Td><Td align="right" className="whitespace-nowrap text-taupe-2">{fmtRelative(r.started_at)}</Td></Tr> })}</tbody>
              </Table>
            )}
          </section>
        </div>

        <Card className="self-start">
          <PanelHeader title="Start a run" eyebrow={operator ? 'Evaluator or admin' : 'Read only for your role'} />
          <form className="flex flex-col gap-3" onSubmit={async (e) => { e.preventDefault(); const r = await start.run({ dataset_tag: form.dataset_tag, label: form.label || undefined, limit: form.limit ? Number(form.limit) : undefined, run_genai: form.run_genai, workers: form.workers, resume: form.resume }); if (r) { toast('ok', `Run ${r.label} ${humanise(r.status).toLowerCase()}.`); runs.refresh() } else if (start.error) toast('err', start.error) }}>
            <fieldset disabled={!operator} className="flex flex-col gap-3">
              <Field label="Dataset">{(id) => <Select id={id} value={form.dataset_tag} onChange={(e) => setForm((f) => ({ ...f, dataset_tag: e.target.value }))} required><option value="">Choose…</option>{(datasets.data ?? []).map((d) => <option key={d.dataset_tag} value={d.dataset_tag}>{d.dataset_tag} ({d.labelled ?? 0} labelled)</option>)}</Select>}</Field>
              <Field label="Label">{(id) => <Input id={id} value={form.label} onChange={(e) => setForm((f) => ({ ...f, label: e.target.value }))} placeholder="e.g. after rule ESC-0031 change" />}</Field>
              <div className="grid grid-cols-2 gap-2">
                <Field label="Limit" hint="Blank = all">{(id) => <Input id={id} type="number" min={1} value={form.limit} onChange={(e) => setForm((f) => ({ ...f, limit: e.target.value }))} />}</Field>
                <Field label="Workers">{(id) => <Input id={id} type="number" min={1} max={16} value={form.workers} onChange={(e) => setForm((f) => ({ ...f, workers: Number(e.target.value) }))} />}</Field>
              </div>
              <Checkbox label="Run GenAI (Pipeline 1) as well as the rules" checked={form.run_genai} onChange={(e) => setForm((f) => ({ ...f, run_genai: e.target.checked }))} />
              <Checkbox label="Resume: skip complaints already analysed" checked={form.resume} onChange={(e) => setForm((f) => ({ ...f, resume: e.target.checked }))} />
              {start.error && <p className="text-[13px] text-critical">{start.error}</p>}
              <Button type="submit" loading={start.pending} disabled={!form.dataset_tag}>Start</Button>
            </fieldset>
          </form>
          <p className="mt-4 text-[12px] text-taupe-2">A run with GenAI uses the free-tier provider and may pause on quota; the rules-only run is deterministic and fast.</p>
        </Card>
      </div>
      {datasets.data && datasets.data.length > 0 && <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{datasets.data.map((d) => <Card key={d.dataset_tag} padding="sm" radius="md"><Ratio numerator={d.analysed ?? 0} denominator={d.total ?? 0} label={`${d.dataset_tag} · analysed`} /></Card>)}</div>}
      <p className="text-[12px] text-taupe-2">Last refreshed {fmtDate(new Date().toISOString())}</p>
    </div>
  )
}

function metric(m: Record<string, unknown> | undefined, field: string): string {
  if (!m) return '—'
  const direct = m[field] ?? (m.fields as Record<string, unknown> | undefined)?.[field] ?? (m.accuracy as Record<string, unknown> | undefined)?.[field]
  if (direct == null) return '—'
  if (typeof direct === 'number') return `${(direct <= 1 ? direct * 100 : direct).toFixed(1)}%`
  if (typeof direct === 'object') { const o = direct as Record<string, unknown>; const p = o.pct ?? o.accuracy ?? o.python ?? o.final; return typeof p === 'number' ? `${(p <= 1 ? p * 100 : p).toFixed(1)}%` : '—' }
  return String(direct)
}
