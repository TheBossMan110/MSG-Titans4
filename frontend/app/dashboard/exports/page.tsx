'use client'

import { AppShell } from '@/components/layout/app-shell'
import { analytics } from '@/lib/api'
import { useApi, fmtDate } from '@/lib/use-api'
import { Badge, Button, Mono, humanise } from '@/components/ui/primitives'
import { Table, Th, Td, Tr } from '@/components/ui/data'
import { Empty, ErrorState, SkeletonRows } from '@/components/ui/feedback'

export default function ExportsPage() {
  return (
    <AppShell eyebrow="Exports" roles={['manager', 'admin', 'evaluator']}>
      <Exports />
    </AppShell>
  )
}

/** Every report download, with who took it and what filters it had. Data leaving the system is itself an event. */
function Exports() {
  const q = useApi(() => analytics.exports(200))
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div><p className="eyebrow mb-1">Data that left the system</p><h1 className="display text-h2">Export history</h1></div>
        <Button href="/dashboard/reports" variant="secondary" size="sm">Reports</Button>
      </div>
      {q.error ? <ErrorState message={q.error} onRetry={q.refresh} /> : q.loading && !q.data ? <SkeletonRows rows={6} /> : !q.data?.length ? <Empty title="Nothing exported yet" body="Downloads from the reports page appear here." /> : (
        <Table dense>
          <thead><tr><Th>When</Th><Th>Report</Th><Th>Format</Th><Th align="right">Rows</Th><Th>Filters</Th></tr></thead>
          <tbody>{q.data.map((e, i) => <Tr key={i}><Td className="whitespace-nowrap text-taupe-2">{fmtDate(e.at)}</Td><Td>{humanise(e.report_type)}</Td><Td><Badge>{e.format.toUpperCase()}</Badge></Td><Td align="right" mono>{e.rows ?? '—'}</Td><Td className="text-[12px]">{e.filters && Object.keys(e.filters).length ? Object.entries(e.filters).map(([k, v]) => <Mono key={k} className="mr-2 text-taupe-2">{k}={String(v)}</Mono>) : <span className="text-taupe">none</span>}</Td></Tr>)}</tbody>
        </Table>
      )}
    </div>
  )
}
