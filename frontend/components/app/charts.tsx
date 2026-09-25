'use client'

import { cn } from '@/lib/utils'

/**
 * Small, honest charts in the house palette. No library: three shapes cover
 * everything the analytics pages need, and every one prints its numbers.
 */

export function Bars({ rows, max, tone = 'espresso', className }: { rows: Array<{ label: string; value: number; sub?: string }>; max?: number; tone?: 'espresso' | 'taupe' | 'warning' | 'critical' | 'verified'; className?: string }) {
  const top = max ?? Math.max(1, ...rows.map((r) => r.value))
  const fill = { espresso: 'bg-espresso', taupe: 'bg-taupe', warning: 'bg-warning', critical: 'bg-critical', verified: 'bg-verified' }[tone]
  if (!rows.length) return <p className="text-[13.5px] text-taupe-2">No data in the window.</p>
  return (
    <ul className={cn('flex flex-col gap-2', className)}>
      {rows.map((r) => (
        <li key={r.label} className="grid grid-cols-[minmax(120px,200px)_1fr_56px] items-center gap-3 text-[13px]">
          <span className="truncate" title={r.label}>{r.label}{r.sub && <span className="block text-[11px] text-taupe-2">{r.sub}</span>}</span>
          <span className="h-4 overflow-hidden rounded-full bg-sand"><span className={cn('block h-full rounded-full transition-[width] duration-700', fill)} style={{ width: `${(r.value / top) * 100}%` }} /></span>
          <span className="text-right font-mono text-[12px] tnum">{r.value.toLocaleString()}</span>
        </li>
      ))}
    </ul>
  )
}

export function Columns({ points, height = 120, className }: { points: Array<{ label: string; value: number }>; height?: number; className?: string }) {
  const max = Math.max(1, ...points.map((p) => p.value))
  if (!points.length) return <p className="text-[13.5px] text-taupe-2">No data in the window.</p>
  return (
    <div className={cn('flex items-end gap-[3px]', className)} style={{ height }} role="img" aria-label="Volume over time">
      {points.map((p) => (
        <div key={p.label} className="group relative flex flex-1 flex-col justify-end" title={`${p.label}: ${p.value}`}>
          <div className="w-full rounded-t-[3px] bg-espresso/85 transition-colors group-hover:bg-espresso" style={{ height: `${Math.max(2, (p.value / max) * 100)}%` }} />
        </div>
      ))}
    </div>
  )
}

export function Stacked({ parts, className }: { parts: Array<{ label: string; value: number; tone?: 'espresso' | 'taupe' | 'sand' | 'warning' | 'critical' | 'verified' | 'info' }>; className?: string }) {
  const total = parts.reduce((a, b) => a + b.value, 0)
  const fill = { espresso: 'bg-espresso', taupe: 'bg-taupe', sand: 'bg-sand-2', warning: 'bg-warning', critical: 'bg-critical', verified: 'bg-verified', info: 'bg-info' }
  if (!total) return <p className="text-[13.5px] text-taupe-2">Nothing to show.</p>
  return (
    <div className={className}>
      <div className="flex h-3 overflow-hidden rounded-full">{parts.filter((p) => p.value > 0).map((p) => <span key={p.label} className={cn('h-full', fill[p.tone ?? 'espresso'])} style={{ width: `${(p.value / total) * 100}%` }} title={`${p.label}: ${p.value}`} />)}</div>
      <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[12px] text-espresso-2">{parts.map((p) => <li key={p.label} className="flex items-center gap-1.5"><span className={cn('size-2 rounded-full', fill[p.tone ?? 'espresso'])} />{p.label} <span className="font-mono tnum text-taupe-2">{p.value} · {Math.round((p.value / total) * 100)}%</span></li>)}</ul>
    </div>
  )
}

export function Sparkline({ values, width = 160, height = 36, className }: { values: number[]; width?: number; height?: number; className?: string }) {
  if (values.length < 2) return <span className="text-[12px] text-taupe-2">—</span>
  const min = Math.min(...values), max = Math.max(...values)
  const span = max - min || 1
  const pts = values.map((v, i) => `${(i / (values.length - 1)) * width},${height - ((v - min) / span) * (height - 4) - 2}`).join(' ')
  return <svg width={width} height={height} className={className} aria-hidden><polyline points={pts} fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" /></svg>
}
