'use client'

import { useEffect, useRef, useState, type ReactNode } from 'react'
import { prefersReducedMotion } from '@/lib/motion-pref'
import { cn } from '@/lib/utils'
import { Button } from './primitives'

/* ------------------------------------------------------------------ Table */

/**
 * Tables are the working surface of the app, so they are built to be read:
 * 14px body, rows tall enough to scan, a zebra wash so the eye does not slip
 * a line, a lifted hover so the row under the pointer is obvious, and a
 * sticky header that stays put while the body scrolls.
 */
export function Table({ children, className, dense }: { children: ReactNode; className?: string; dense?: boolean }) {
  return (
    <div className={cn('overflow-x-auto rounded-[var(--radius-lg)] border border-line-soft bg-white/75 shadow-card backdrop-blur-sm', className)}>
      <table
        className={cn(
          'w-full border-separate border-spacing-0 text-[14px]',
          '[&_tbody_tr:nth-child(even)>td]:bg-cream/45',
          dense ? '[&_td]:py-2.5' : '[&_td]:py-3.5',
        )}
      >
        {children}
      </table>
    </div>
  )
}

export function Th({ children, className, align = 'left' }: { children?: ReactNode; className?: string; align?: 'left' | 'right' }) {
  return (
    <th
      scope="col"
      className={cn(
        'sticky top-0 z-[1] whitespace-nowrap border-b border-line bg-cream/90 px-4 py-3 text-[11px] font-semibold uppercase tracking-[0.12em] text-taupe-2 backdrop-blur-md first:rounded-tl-[var(--radius-lg)] last:rounded-tr-[var(--radius-lg)]',
        align === 'right' ? 'text-right' : 'text-left',
        className,
      )}
    >
      {children}
    </th>
  )
}

export function Td({ children, className, align = 'left', mono, title }: { children?: ReactNode; className?: string; align?: 'left' | 'right'; mono?: boolean; title?: string }) {
  return (
    <td
      title={title}
      className={cn(
        'border-b border-line-soft px-4 align-middle text-charcoal transition-colors duration-200',
        align === 'right' && 'text-right',
        mono && 'font-mono text-[13px] tnum',
        className,
      )}
    >
      {children}
    </td>
  )
}

export function Tr({ children, className, onClick, href }: { children: ReactNode; className?: string; onClick?: () => void; href?: string }) {
  const interactive = Boolean(onClick || href)
  return (
    <tr
      onClick={onClick}
      className={cn(
        'group/row last:[&>td]:border-b-0',
        '[&>td]:transition-[background-color,box-shadow] hover:[&>td]:bg-white',
        interactive && 'cursor-pointer hover:[&>td:first-child]:shadow-[inset_3px_0_0_var(--color-ai)]',
        className,
      )}
      role={interactive ? 'link' : undefined}
      tabIndex={interactive ? 0 : undefined}
      onKeyDown={(e) => interactive && e.key === 'Enter' && onClick?.()}
    >
      {children}
    </tr>
  )
}

/* ------------------------------------------------------------------ Pagination */

export function Pagination({
  page,
  size,
  total,
  onPage,
  className,
}: {
  page: number
  size: number
  total: number
  onPage: (p: number) => void
  className?: string
}) {
  const pages = Math.max(1, Math.ceil(total / size))
  const from = total === 0 ? 0 : (page - 1) * size + 1
  const to = Math.min(total, page * size)
  return (
    <div className={cn('flex flex-wrap items-center justify-between gap-3 text-[13.5px] text-taupe', className)}>
      <span className="tnum">
        {total === 0 ? 'Nothing to show' : <>Showing <b className="text-espresso">{from}–{to}</b> of <b className="text-espresso">{total}</b></>}
      </span>
      <div className="flex items-center gap-1.5">
        <Button size="sm" variant="secondary" disabled={page <= 1} onClick={() => onPage(page - 1)}>Previous</Button>
        <span className="px-2 tnum text-espresso-2">{page} / {pages}</span>
        <Button size="sm" variant="secondary" disabled={page >= pages} onClick={() => onPage(page + 1)}>Next</Button>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ CountUp */

/**
 * A number that counts up once, when it first scrolls into view.
 *
 * anime.js drives it — the one place in the app it earns its keep: a
 * tween on a plain object with a formatter on every frame, which is what it
 * does better than a CSS transition can. Reduced motion shows the final
 * value immediately.
 */
export function CountUp({ value, decimals = 0, className }: { value: number; decimals?: number; className?: string }) {
  const ref = useRef<HTMLSpanElement>(null)
  const format = (n: number) => n.toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals })
  const [shown, setShown] = useState(() => format(value))

  useEffect(() => {
    const el = ref.current
    if (!el) return
    if (prefersReducedMotion() || value === 0) {
      setShown(format(value))
      return
    }
    let anim: { pause: () => void } | null = null
    let cancelled = false
    setShown(format(0))
    const io = new IntersectionObserver(async ([entry]) => {
      if (!entry.isIntersecting) return
      io.disconnect()
      const { animate } = await import('animejs')
      if (cancelled) return
      const counter = { v: 0 }
      anim = animate(counter, {
        v: value,
        duration: 1400,
        ease: 'outExpo',
        onUpdate: () => setShown(format(counter.v)),
        onComplete: () => setShown(format(value)),
      })
    }, { threshold: 0.2 })
    io.observe(el)
    return () => { cancelled = true; io.disconnect(); anim?.pause() }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, decimals])

  return <span ref={ref} className={cn('tnum', className)}>{shown}</span>
}

/* ------------------------------------------------------------------ Stat */

/**
 * A figure with its evidence.
 *
 * `value` may be null, and null renders as "Not measured" -- never 0, never a
 * full bar. SRS 1.8 #17: a figure with no denominator is not a figure.
 */
export function Stat({
  label,
  value,
  unit,
  evidence,
  tone = 'neutral',
  className,
  size = 'md',
  icon,
}: {
  label: string
  value: number | string | null | undefined
  unit?: string
  evidence?: ReactNode
  tone?: 'neutral' | 'verified' | 'warning' | 'critical' | 'ai' | 'rule'
  className?: string
  size?: 'md' | 'lg'
  icon?: ReactNode
}) {
  const unmeasured = value === null || value === ''
  const loading = value === undefined
  const toneClass = {
    neutral: 'text-espresso', verified: 'text-verified', warning: 'text-warning',
    critical: 'text-critical', ai: 'text-ai', rule: 'text-rule',
  }[tone]
  return (
    <div className={cn('stat flex flex-col gap-1.5', className)}>
      <span className="eyebrow flex items-center gap-1.5">{icon}{label}</span>
      <span className={cn('font-display leading-none tracking-[-0.03em]', size === 'lg' ? 'text-h1' : 'text-h2', unmeasured ? 'text-taupe' : toneClass)}>
        {loading ? (
          <span className="inline-block h-[0.8em] w-24 rounded-md shimmer align-middle" aria-label="Loading" />
        ) : unmeasured ? (
          <span className="text-[0.42em] font-sans font-medium italic text-taupe">Not measured</span>
        ) : (
          <>
            {typeof value === 'number' ? <CountUp value={value} decimals={Number.isInteger(value) ? 0 : 1} /> : value}
            {unit && <span className="ml-0.5 text-[0.5em] font-sans font-medium text-taupe">{unit}</span>}
          </>
        )}
      </span>
      {evidence && <span className="text-[13px] text-taupe">{evidence}</span>}
    </div>
  )
}

/* ------------------------------------------------------------------ Key/value */

export function KV({ rows, className }: { rows: Array<[ReactNode, ReactNode]>; className?: string }) {
  return (
    <dl className={cn('grid grid-cols-[max-content_1fr] gap-x-6 gap-y-2.5 text-[14px]', className)}>
      {rows.map(([k, v], i) => (
        <div key={i} className="contents">
          <dt className="text-taupe">{k}</dt>
          <dd className="min-w-0 text-charcoal">{v ?? <span className="text-taupe">—</span>}</dd>
        </div>
      ))}
    </dl>
  )
}

/* ------------------------------------------------------------------ Ratio bar */

/** A proportion, with its fraction shown. Never rendered from a null. */
export function Ratio({ numerator, denominator, label, tone = 'neutral' }: { numerator: number; denominator: number; label?: string; tone?: 'neutral' | 'verified' | 'warning' | 'critical' | 'ai' | 'rule' }) {
  const pct = denominator > 0 ? Math.round((numerator / denominator) * 100) : null
  const fill = {
    neutral: 'bg-espresso', verified: 'bg-verified', warning: 'bg-warning-glow',
    critical: 'bg-critical', ai: 'bg-gradient-to-r from-ai to-ai-2', rule: 'bg-rule-2',
  }[tone]
  return (
    <div className="flex flex-col gap-1.5">
      {label && <span className="text-[13.5px] text-taupe">{label}</span>}
      <div className="flex items-center gap-3">
        <div className="h-2 flex-1 overflow-hidden rounded-full bg-sand/80">
          {pct !== null && <div className={cn('h-full rounded-full transition-[width] duration-1000 ease-[var(--ease-out-expo)]', fill)} style={{ width: `${pct}%` }} />}
        </div>
        <span className="font-mono text-[12.5px] tnum text-espresso-2">
          {pct === null ? 'not measured' : `${numerator}/${denominator} · ${pct}%`}
        </span>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ SLA meter */

function remaining(ms: number): string {
  const m = Math.round(Math.abs(ms) / 60000)
  if (m < 60) return `${m} min`
  if (m < 1440) return `${Math.floor(m / 60)} h ${m % 60} min`
  return `${Math.floor(m / 1440)} d ${Math.floor((m % 1440) / 60)} h`
}

/**
 * How much of the SLA window has been spent, live.
 *
 * Re-renders every 30 seconds so an open page does not quietly lie about how
 * close a deadline is. Breached rings red and pulses; at risk turns amber.
 */
export function SlaMeter({
  start,
  due,
  metAt,
  breached,
  atRisk,
  label = 'Resolution',
  className,
}: {
  start?: string | null
  due?: string | null
  metAt?: string | null
  breached?: boolean
  atRisk?: boolean
  label?: string
  className?: string
}) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (metAt) return
    const id = window.setInterval(() => setNow(Date.now()), 30_000)
    return () => clearInterval(id)
  }, [metAt])

  if (!due) return <p className={cn('text-[13px] text-taupe', className)}>No SLA applies yet.</p>
  const s = start ? new Date(start).getTime() : now
  const d = new Date(due).getTime()
  const end = metAt ? new Date(metAt).getTime() : now
  const spent = d > s ? Math.min(1, Math.max(0, (end - s) / (d - s))) : 1
  const late = !metAt && now > d
  const state = metAt ? 'met' : breached || late ? 'breached' : atRisk || spent > 0.75 ? 'risk' : 'ok'
  const fill = { met: 'bg-verified', breached: 'bg-alert', risk: 'bg-warning-glow', ok: 'bg-rule-2' }[state]

  return (
    <div className={cn('flex flex-col gap-2', className)}>
      <div className="flex items-baseline justify-between gap-3 text-[13px]">
        <span className="font-medium text-espresso-2">{label}</span>
        <span className={cn('tnum font-medium', state === 'breached' ? 'text-critical' : state === 'risk' ? 'text-warning' : state === 'met' ? 'text-verified' : 'text-espresso-2')}>
          {state === 'met' ? 'Met' : late ? `${remaining(now - d)} over` : `${remaining(d - now)} left`}
        </span>
      </div>
      <div className="relative h-2 overflow-hidden rounded-full bg-sand/80">
        <div
          className={cn('h-full rounded-full transition-[width] duration-1000 ease-[var(--ease-out-expo)]', fill, state === 'breached' && 'shadow-[0_0_12px_rgba(217,58,52,0.55)]')}
          style={{ width: `${Math.round(spent * 100)}%` }}
        />
      </div>
      <span className="text-[12px] text-taupe">
        Due {new Date(d).toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}
      </span>
    </div>
  )
}
