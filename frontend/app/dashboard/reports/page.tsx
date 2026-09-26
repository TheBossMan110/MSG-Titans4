'use client'

import { useState } from 'react'
import { AppShell } from '@/components/layout/app-shell'
import { useAuth } from '@/lib/auth-context'
import { analytics, type ReportFilters } from '@/lib/api'
import { plainValue } from '@/components/app/complaint-bits'
import { useApi, useAction, fmtDate } from '@/lib/use-api'
import { Badge, Button, Mono, humanise } from '@/components/ui/primitives'
import { Card, PanelHeader } from '@/components/ui/surfaces'
import { Checkbox, Input, Select } from '@/components/ui/forms'
import { Table, Th, Td, Tr } from '@/components/ui/data'
import { Empty, ErrorState, SkeletonRows, useToast } from '@/components/ui/feedback'
import { cn } from '@/lib/utils'

export default function ReportsPage() {
  return (
    <AppShell eyebrow="Reports" roles={['manager', 'admin', 'evaluator']} wide>
      <Reports />
    </AppShell>
  )
}

/**
 * Report types come from the server; this page never invents one. Reading is
 * for every oversight role; downloading (CSV, Excel or PDF) is for managers and
 * admins, and each download is itself recorded under /dashboard/exports.
 */
function Reports() {
  const { user } = useAuth()
  const toast = useToast()
  const types = useApi(() => analytics.reports())
  const [type, setType] = useState<string | null>(null)
  const [f, setF] = useState<ReportFilters>({ limit: 200 })
  const report = useApi(() => analytics.report(type!, f), [type, JSON.stringify(f)], Boolean(type))
  const exp = useAction((fmt: 'csv' | 'xlsx' | 'pdf' | 'json') => analytics.exportReport(type!, fmt, f))
  const canExport = user && ['manager', 'admin'].includes(user.role)
  const set = <K extends keyof ReportFilters>(k: K, v: ReportFilters[K]) => setF((s) => ({ ...s, [k]: v }))

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div><p className="eyebrow mb-1">Insight</p><h1 className="display text-h2">Reports</h1></div>
        {canExport && type && (
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" size="sm" loading={exp.pending} onClick={async () => { const n = await exp.run('csv'); if (n) toast('ok', `Downloaded ${n}`); else if (exp.error) toast('err', exp.error) }}>Download CSV</Button>
            <Button variant="secondary" size="sm" loading={exp.pending} onClick={async () => { const n = await exp.run('xlsx'); if (n) toast('ok', `Downloaded ${n}`); else if (exp.error) toast('err', exp.error) }}>Download Excel</Button>
            <Button variant="secondary" size="sm" loading={exp.pending} onClick={async () => { const n = await exp.run('pdf'); if (n) toast('ok', `Downloaded ${n}`); else if (exp.error) toast('err', exp.error) }}>Download PDF</Button>
            <Button variant="secondary" size="sm" loading={exp.pending} onClick={async () => { const n = await exp.run('json'); if (n) toast('ok', `Downloaded ${n}`); else if (exp.error) toast('err', exp.error) }}>Download JSON</Button>
          </div>
        )}
      </div>

      <div className="grid gap-6 lg:grid-cols-[300px_1fr]">
        <div className="flex flex-col gap-4">
          <Card padding="sm">
            <p className="eyebrow mb-2 px-1">Report types</p>
            {types.error ? <p className="px-1 text-[13px] text-critical">{types.error}</p> : types.loading && !types.data ? <SkeletonRows rows={5} /> : (
              <ul className="flex flex-col gap-0.5">{(types.data ?? []).map((t) => <li key={t.report_type}><button onClick={() => setType(t.report_type)} className={cn('w-full rounded-[var(--radius-md)] px-3 py-2 text-left transition-colors', type === t.report_type ? 'bg-espresso text-ink-on-dark' : 'hover:bg-sand/60')}><span className="block text-[13.5px] font-medium">{humanise(t.report_type)}</span><span className={cn('block text-[12px]', type === t.report_type ? 'text-sand-2' : 'text-taupe-2')}>{t.description}</span></button></li>)}</ul>
            )}
          </Card>
          {type && (
            <Card padding="sm">
              <p className="eyebrow mb-3 px-1">Filters</p>
              <div className="flex flex-col gap-2.5 px-1">
                <Checkbox label="Mismatches only" checked={Boolean(f.mismatches_only)} onChange={(e) => set('mismatches_only', e.target.checked || undefined)} />
                <Checkbox label="SLA breached only" checked={Boolean(f.breached_only)} onChange={(e) => set('breached_only', e.target.checked || undefined)} />
                <Checkbox label="Overrides only" checked={Boolean(f.overrides_only)} onChange={(e) => set('overrides_only', e.target.checked || undefined)} />
                <Checkbox label="Unresolved only" checked={Boolean(f.unresolved_only)} onChange={(e) => set('unresolved_only', e.target.checked || undefined)} />
                <Input value={f.status ?? ''} onChange={(e) => set('status', e.target.value || undefined)} placeholder="Status" aria-label="Status" className="h-9 text-[13px]" />
                <Input value={f.dataset_tag ?? ''} onChange={(e) => set('dataset_tag', e.target.value || undefined)} placeholder="Dataset tag" aria-label="Dataset tag" className="h-9 font-mono text-[13px]" />
                <Input value={f.field ?? ''} onChange={(e) => set('field', e.target.value || undefined)} placeholder="Field (for mismatch reports)" aria-label="Field" className="h-9 font-mono text-[13px]" />
                <Select value={String(f.limit ?? 200)} onChange={(e) => set('limit', Number(e.target.value))} aria-label="Limit" className="h-9 text-[13px]">{[50, 200, 500, 1000].map((n) => <option key={n} value={n}>{n} rows</option>)}</Select>
              </div>
            </Card>
          )}
        </div>

        <div>
          {!type ? <Empty title="Choose a report" body="Each report is a live query against the register with the filters on the left." /> : report.error ? <ErrorState message={report.error} onRetry={report.refresh} /> : !report.data ? <SkeletonRows rows={10} /> : (
            <div className="flex flex-col gap-4">
              <PanelHeader title={report.data!.title} eyebrow={<><Mono>{report.data!.report_type}</Mono> · {report.data!.row_count ?? report.data!.rows?.length ?? 0} rows · generated {fmtDate(report.data!.generated_at)}</>} />
              {!report.data!.rows?.length ? <Empty title="No rows" body="Nothing matches these filters." /> : (
                <Table dense>
                  <thead><tr>{(report.data!.columns ?? Object.keys(report.data!.rows![0])).map((c) => <Th key={c}>{humanise(c)}</Th>)}</tr></thead>
                  <tbody>{report.data!.rows!.map((row, i) => <Tr key={i}>{(report.data!.columns ?? Object.keys(row)).map((c) => <Td key={c} className="max-w-[280px] truncate text-[12.5px]" title={String(row[c] ?? '')}>{cell(row[c])}</Td>)}</Tr>)}</tbody>
                </Table>
              )}
              {report.data!.filters && Object.keys(report.data!.filters).length > 0 && <p className="text-[12px] text-taupe-2">Filters applied: {Object.entries(report.data!.filters).map(([k, v]) => <Badge key={k} className="mr-1">{k}={String(v)}</Badge>)}</p>}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function cell(v: unknown): React.ReactNode {
  if (v === null || v === undefined || v === '') return <span className="text-taupe">—</span>
  if (typeof v === 'boolean') return <Badge tone={v ? 'verified' : 'neutral'}>{v ? 'yes' : 'no'}</Badge>
  if (typeof v === 'number') return <span className="font-mono tnum">{v.toLocaleString()}</span>
  if (typeof v === 'object') return plainValue(v)
  const s = String(v)
  if (/^\d{4}-\d{2}-\d{2}T/.test(s)) return fmtDate(s)
  return plainValue(s)
}
