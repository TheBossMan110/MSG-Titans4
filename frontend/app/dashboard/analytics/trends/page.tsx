'use client'

import { useState } from 'react'
import { AppShell } from '@/components/layout/app-shell'
import { useAuth } from '@/lib/auth-context'
import { analytics, type S } from '@/lib/api'
import { useApi, useAction, fmtDate, pct } from '@/lib/use-api'
import { Badge, Button, Mono, humanise } from '@/components/ui/primitives'
import { Card, PanelHeader } from '@/components/ui/surfaces'
import { Select } from '@/components/ui/forms'
import { Table, Th, Td, Tr } from '@/components/ui/data'
import { Empty, ErrorState, SkeletonRows, useToast } from '@/components/ui/feedback'
import { Sparkline } from '@/components/app/charts'
import { cn } from '@/lib/utils'

export default function TrendsPage() {
  return (
    <AppShell eyebrow="Analytics / Trends" roles={['manager', 'admin', 'evaluator']} wide>
      <Trends />
    </AppShell>
  )
}

/**
 * Rising trends: each period is snapshotted, and a dimension value that moved
 * materially against its previous period is flagged. Anomalies are separate
 * from material moves so a small category doubling is not mistaken for a
 * large one shifting.
 */
function Trends() {
  const { user } = useAuth()
  const toast = useToast()
  const [period, setPeriod] = useState('WEEK')
  const q = useApi(() => analytics.trends(period), [period])
  const snapshot = useAction((p: string) => analytics.snapshotTrends(p))
  const [selected, setSelected] = useState<S['TrendOut'] | null>(null)
  const history = useApi(() => analytics.trendHistory(selected!.metric, selected!.dimension_value, 24), [selected?.metric, selected?.dimension_value], Boolean(selected))
  const canSnapshot = user && ['manager', 'admin'].includes(user.role)
  const rows = q.data ?? []
  const material = rows.filter((r) => r.material || r.anomaly)

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div><p className="eyebrow mb-1">Insight</p><h1 className="display text-h2">Rising trends</h1></div>
        <div className="flex items-center gap-2">
          <Select value={period} onChange={(e) => setPeriod(e.target.value)} aria-label="Period" className="w-auto">{['DAY', 'WEEK', 'MONTH'].map((p) => <option key={p} value={p}>{humanise(p)}</option>)}</Select>
          {canSnapshot && <Button variant="secondary" size="sm" loading={snapshot.pending} onClick={async () => { const r = await snapshot.run(period); if (r) { toast('ok', `Snapshot taken: ${JSON.stringify(r).slice(0, 80)}`); q.refresh() } else if (snapshot.error) toast('err', snapshot.error) }}>Take a snapshot</Button>}
        </div>
      </div>

      {material.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {material.slice(0, 8).map((t) => (
            <button key={`${t.metric}-${t.dimension_value}`} onClick={() => setSelected(t)} className="text-left">
              <Card tone={t.anomaly ? 'sand' : 'ivory'} padding="sm" radius="md" lift className="h-full">
                <div className="flex items-center justify-between"><span className="eyebrow text-[10px]">{humanise(t.metric)}</span><Badge tone={t.direction === 'UP' ? 'warning' : t.direction === 'DOWN' ? 'verified' : 'neutral'}>{t.direction === 'UP' ? '▲' : t.direction === 'DOWN' ? '▼' : '—'} {pct(t.delta_pct, 0)}</Badge></div>
                <p className="mt-1 font-display text-[18px] leading-tight">{t.dimension_value}</p>
                <p className="mt-1 text-[12px] text-taupe-2">{t.value.toLocaleString()} vs {t.previous_value.toLocaleString()} · {humanise(t.dimension)}{t.anomaly && ' · anomaly'}</p>
              </Card>
            </button>
          ))}
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <Card padding="none">
          {q.error ? <ErrorState message={q.error} onRetry={q.refresh} className="m-4" /> : q.loading && !q.data ? <SkeletonRows rows={8} className="m-4" /> : !rows.length ? <Empty title="No trend data" body="Take a snapshot to begin a series. Trends compare consecutive snapshots." className="m-4" /> : (
            <Table dense>
              <thead><tr><Th>Metric</Th><Th>Dimension</Th><Th>Value</Th><Th align="right">Now</Th><Th align="right">Before</Th><Th align="right">Δ</Th><Th>Flags</Th><Th>Period</Th></tr></thead>
              <tbody>
                {rows.map((t) => (
                  <Tr key={`${t.metric}-${t.dimension}-${t.dimension_value}`} onClick={() => setSelected(t)} className={cn(selected?.dimension_value === t.dimension_value && selected.metric === t.metric && 'bg-sand/40')}>
                    <Td>{humanise(t.metric)}</Td><Td className="text-taupe-2">{humanise(t.dimension)}</Td><Td mono>{t.dimension_value}</Td>
                    <Td align="right" mono>{t.value.toLocaleString()}</Td><Td align="right" mono className="text-taupe-2">{t.previous_value.toLocaleString()}</Td>
                    <Td align="right"><Badge tone={t.direction === 'UP' ? 'warning' : t.direction === 'DOWN' ? 'verified' : 'neutral'}>{t.direction === 'UP' ? '▲' : t.direction === 'DOWN' ? '▼' : '—'} {pct(t.delta_pct, 0)}</Badge></Td>
                    <Td><span className="flex gap-1">{t.material && <Badge tone="warning">material</Badge>}{t.anomaly && <Badge tone="critical">anomaly</Badge>}</span></Td>
                    <Td className="whitespace-nowrap text-taupe-2">{humanise(t.period_type)} · {fmtDate(t.period_start, false)}</Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
          )}
        </Card>
        <Card>
          <PanelHeader title="History" eyebrow={selected ? <><Mono>{selected.metric}</Mono> · {selected.dimension_value}</> : 'Select a row'} />
          {!selected ? <p className="text-[13.5px] text-taupe-2">Choose a trend to see its snapshots over time.</p> : history.loading && !history.data ? <SkeletonRows rows={4} /> : history.error ? <p className="text-[13px] text-critical">{history.error}</p> : !history.data?.length ? <Empty title="No history" /> : (
            <div className="flex flex-col gap-4">
              <div className="text-espresso"><Sparkline values={[...history.data].reverse().map((h) => h.value)} width={320} height={64} fluid /></div>
              <ul className="divide-y divide-line-soft text-[13px]">
                {history.data.map((h, i) => <li key={i} className="grid grid-cols-[1fr_auto_auto] items-center gap-3 py-1.5"><span className="text-taupe-2">{fmtDate(h.period_start, false)}</span><span className="font-mono tnum">{h.value.toLocaleString()}</span><span className={cn('font-mono text-[12px]', h.direction === 'UP' ? 'text-warning' : h.direction === 'DOWN' ? 'text-verified' : 'text-taupe')}>{pct(h.delta_pct, 0)}{h.anomaly && ' !'}</span></li>)}
              </ul>
            </div>
          )}
        </Card>
      </div>
    </div>
  )
}
