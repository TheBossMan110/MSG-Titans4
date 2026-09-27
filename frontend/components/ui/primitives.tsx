'use client'

import Link from 'next/link'
import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from 'react'
import { ShieldCheck, Sparkles } from 'lucide-react'
import { cn } from '@/lib/utils'

/* ------------------------------------------------------------------ Button */

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'pencil' | 'onDark' | 'ai'
type Size = 'sm' | 'md' | 'lg'

/**
 * Every variant states its own colour explicitly, and base styles live in
 * @layer base, so `text-*` here always wins over `a { color: inherit }`.
 *
 * Press physics: a 3% scale-down on :active, released on a spring. It is the
 * cheapest possible acknowledgement that the press registered, and it runs
 * on the compositor.
 */
const variants: Record<Variant, string> = {
  primary:
    'bg-espresso text-ink-on-dark shadow-[inset_0_1px_0_rgba(255,255,255,0.12),0_1px_2px_rgba(42,31,23,0.25)] hover:bg-espresso-2 hover:shadow-[inset_0_1px_0_rgba(255,255,255,0.14),0_8px_22px_-8px_rgba(42,31,23,0.55)]',
  secondary:
    'bg-white/80 text-espresso border border-line shadow-[0_1px_2px_rgba(42,31,23,0.06)] hover:border-taupe hover:bg-white',
  ghost: 'text-espresso-2 hover:text-espresso hover:bg-sand/60',
  danger: 'bg-critical text-white hover:bg-[#86291d]',
  pencil: 'pencil hover:border-ai',
  onDark: 'bg-ink-on-dark text-espresso hover:bg-white',
  ai: 'bg-ai text-white shadow-ai hover:bg-[#154b70]',
}

const sizes: Record<Size, string> = {
  sm: 'h-9 px-3.5 gap-1.5',
  md: 'h-11 px-5 gap-2',
  lg: 'h-[52px] px-7 gap-2.5',
}

const sizeText: Record<Size, string> = { sm: 'text-[13px]', md: 'text-[14px]', lg: 'text-[15px]' }

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
  href?: string
  loading?: boolean
  icon?: ReactNode
  arrow?: boolean
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'primary', size = 'md', href, loading, icon, arrow, className, children, disabled, ...rest },
  ref,
) {
  const classes = cn(
    'group/btn relative inline-flex items-center justify-center rounded-full font-medium tracking-[-0.005em]',
    'transition-[background-color,border-color,color,box-shadow,transform] duration-300 ease-[var(--ease-out-expo)]',
    'active:scale-[0.97] active:duration-100 disabled:opacity-50 disabled:pointer-events-none select-none whitespace-nowrap',
    sizeText[size],
    variants[variant],
    sizes[size],
    className,
  )
  const inner = (
    <>
      {loading ? <Spinner size={14} className="opacity-80" /> : icon}
      <span>{children}</span>
      {arrow && (
        <svg
          className="transition-transform duration-300 ease-[var(--ease-out-expo)] group-hover/btn:translate-x-1"
          width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden
        >
          <path d="M2 8h11M9 4l4 4-4 4" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      )}
    </>
  )
  if (href) {
    return (
      <Link href={href} className={classes} aria-disabled={disabled || loading}>
        {inner}
      </Link>
    )
  }
  return (
    <button ref={ref} className={classes} disabled={disabled || loading} {...rest}>
      {inner}
    </button>
  )
})

/* ------------------------------------------------------------------ Type */

export function Eyebrow({
  children,
  index,
  className,
}: {
  children: ReactNode
  /** An editorial section number, e.g. 03 — rendered before a hairline rule. */
  index?: string
  className?: string
}) {
  if (index) {
    return (
      <p className={cn('eyebrow flex items-center gap-3', className)}>
        <span className="tnum">{index}</span>
        <span aria-hidden className="h-px w-8 bg-current opacity-40" />
        <span>{children}</span>
      </p>
    )
  }
  return <p className={cn('eyebrow', className)}>{children}</p>
}

const displaySize = { h2: 'text-h2', h1: 'text-h1', hero: 'text-hero' } as const

/** A stacked editorial headline: one line per row, each revealed from its own mask. */
export function Display({
  lines,
  as: Tag = 'h2',
  size = 'h1',
  italicLast = false,
  className,
}: {
  lines: string[]
  as?: 'h1' | 'h2' | 'h3'
  size?: keyof typeof displaySize
  italicLast?: boolean
  className?: string
}) {
  return (
    <Tag className={cn('display', displaySize[size], className)}>
      {lines.map((line, i) => (
        // The mask reaches 0.22em below the line so descenders (p, g, y) are not
        // cut off, and the next line is pulled up by the same amount so the
        // headline keeps its tight leading.
        <span key={i} className={cn('block overflow-hidden pb-[0.22em]', i < lines.length - 1 && '-mb-[0.16em]')}>
          <span
            className={cn('block', italicLast && i === lines.length - 1 && 'display-italic opacity-80')}
            data-line
          >
            {line}
          </span>
        </span>
      ))}
    </Tag>
  )
}

export function Kbd({ children }: { children: ReactNode }) {
  return (
    <kbd className="inline-flex h-5 items-center rounded border border-line bg-ivory px-1.5 font-mono text-[11px] text-taupe-2">
      {children}
    </kbd>
  )
}

export function Mono({ children, className }: { children: ReactNode; className?: string }) {
  // Identifiers like comparison_engine.decision.build_reconciled have no
  // break points; wrapping anywhere only when they do not fit keeps them from
  // pushing a page wider than the screen.
  return <span className={cn('font-mono text-[0.92em] tnum [overflow-wrap:anywhere]', className)}>{children}</span>
}

/* ------------------------------------------------------------------ Badges */

export type Tone = 'neutral' | 'verified' | 'warning' | 'critical' | 'info' | 'ink' | 'pencil' | 'ai' | 'rule'

const tones: Record<Tone, string> = {
  neutral: 'bg-sand/80 text-espresso-2 border-line',
  verified: 'bg-verified-dim text-verified border-verified/25',
  warning: 'bg-warning-dim text-warning border-warning/25',
  critical: 'bg-critical-dim text-critical border-critical/25',
  info: 'bg-info-dim text-info border-info/25',
  ink: 'bg-espresso text-ink-on-dark border-espresso',
  pencil: 'pencil',
  ai: 'bg-ai-soft text-ai border-ai-line',
  rule: 'bg-rule-soft text-rule border-rule-line',
}

export function Badge({
  tone = 'neutral',
  children,
  className,
  dot,
  pulse,
  icon,
}: {
  tone?: Tone
  children: ReactNode
  className?: string
  dot?: boolean
  /** A radiating ring — for P0 and SLA breaches only, never decoration. */
  pulse?: boolean
  icon?: ReactNode
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[12px] font-medium leading-5 whitespace-nowrap',
        tones[tone],
        className,
      )}
    >
      {pulse ? <Pulse tone={tone === 'warning' ? 'warning' : 'alert'} /> : dot ? <span className="size-1.5 rounded-full bg-current opacity-80" aria-hidden /> : null}
      {icon}
      {children}
    </span>
  )
}

/** The model's opinion. Blue, with a sparkle: provisional. */
export function AiBadge({ children = 'AI', className }: { children?: ReactNode; className?: string }) {
  return (
    <Badge tone="ai" className={className} icon={<Sparkles size={12} strokeWidth={2.2} aria-hidden />}>
      {children}
    </Badge>
  )
}

/** The rule engine's decision. Forest, with a shield: final. */
export function RuleBadge({ children = 'Verified by rules', className }: { children?: ReactNode; className?: string }) {
  return (
    <Badge tone="rule" className={className} icon={<ShieldCheck size={12} strokeWidth={2.2} aria-hidden />}>
      {children}
    </Badge>
  )
}

/** A radiating dot. Motion that means "act now" — used for P0 and breaches only. */
export function Pulse({ tone = 'alert', className }: { tone?: 'alert' | 'warning' | 'ai' | 'verified'; className?: string }) {
  const color = { alert: 'bg-alert', warning: 'bg-warning-glow', ai: 'bg-ai', verified: 'bg-verified' }[tone]
  return (
    <span className={cn('relative inline-flex size-2', className)} aria-hidden>
      <span className={cn('absolute inset-0 rounded-full animate-pulse-ring', color)} />
      <span className={cn('relative inline-flex size-2 rounded-full', color)} />
    </span>
  )
}

/* Domain vocabularies → tones. One place, so a colour never disagrees with itself. */

export function priorityTone(code?: string | null): Tone {
  switch ((code || '').toUpperCase()) {
    case 'P0': return 'critical'
    case 'P1': return 'warning'
    case 'P2': return 'info'
    default:   return 'neutral'
  }
}

export function urgencyTone(u?: string | null): Tone {
  switch ((u || '').toUpperCase()) {
    case 'CRITICAL': return 'critical'
    case 'HIGH':     return 'warning'
    case 'MEDIUM':   return 'info'
    default:         return 'neutral'
  }
}

export function escalationTone(code?: string | null): Tone {
  const c = (code || 'NONE').toUpperCase()
  if (c === 'NONE') return 'neutral'
  if (c === 'CRITICAL_MGMT' || c === 'COMPLIANCE_REVIEW') return 'critical'
  if (c === 'SPECIALIST' || c === 'DEPT_MANAGER') return 'warning'
  return 'info'
}

export function statusTone(s?: string | null): Tone {
  switch ((s || '').toUpperCase()) {
    case 'RESOLVED': case 'CLOSED': case 'VALIDATED': return 'verified'
    case 'MANUAL_REVIEW': case 'ESCALATED': case 'REOPENED': case 'AWAITING_CUSTOMER': return 'warning'
    case 'FAILED': return 'critical'
    case 'ANALYZING': case 'NEW': return 'info'
    default: return 'neutral'
  }
}

export function verificationTone(v?: string | null): Tone {
  switch ((v || '').toUpperCase()) {
    case 'VERIFIED': case 'AGREED': return 'verified'
    case 'CORRECTED_BY_RULES': return 'rule'
    case 'VERIFIED_WITH_WARNING': case 'INCOMPLETE': case 'MANUAL_REVIEW_REQUIRED': return 'warning'
    case 'BLOCKED': return 'critical'
    default: return 'neutral'
  }
}

export function eligibilityTone(o?: string | null): Tone {
  switch ((o || '').toUpperCase()) {
    case 'ELIGIBLE': return 'verified'
    case 'NOT_ELIGIBLE': return 'critical'
    case 'REQUIRES_VERIFICATION': case 'CONDITIONAL': return 'warning'
    default: return 'neutral'
  }
}

export const humanise = (code?: string | null) =>
  (code || '—').toString().replaceAll('_', ' ').toLowerCase().replace(/(^|\s)\S/g, (c) => c.toUpperCase())

/* ------------------------------------------------------------------ Spinner */

export function Spinner({ size = 18, className }: { size?: number; className?: string }) {
  return (
    <svg className={cn('animate-spin', className)} width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden>
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeOpacity="0.2" strokeWidth="2.5" />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
    </svg>
  )
}

/* ------------------------------------------------------------------ Wordmark */

/** The brand badge on its own: complaint → AI → department, copper on espresso. */
export function BrandMark({ size = 30, dark = false, className }: { size?: number; dark?: boolean; className?: string }) {
  return (
    // eslint-disable-next-line @next/next/no-img-element -- a 128 px PNG; next/image would add a request for nothing
    <img
      src={size > 56 ? '/brand/supportnova-mark-256.png' : '/brand/supportnova-mark.png'}
      alt=""
      aria-hidden
      width={size}
      height={size}
      draggable={false}
      className={cn('shrink-0 rounded-[24%]', dark ? 'ring-1 ring-ink-on-dark/20' : 'shadow-[0_1px_2px_rgba(42,31,23,0.18)]', className)}
    />
  )
}

/** Nova, the assistant: the robot from the brand mark, drawn so it stays crisp at 20 px. */
export function NovaAvatar({ size = 36, className }: { size?: number; className?: string }) {
  return (
    <svg viewBox="0 0 40 40" width={size} height={size} aria-hidden className={cn('shrink-0', className)}>
      <circle cx="20" cy="20" r="20" fill="#2a1f17" />
      <path d="M20 10v2.6" stroke="#e2bb8f" strokeWidth="1.9" strokeLinecap="round" />
      <circle cx="20" cy="8.2" r="2.3" fill="#e2bb8f" />
      <rect x="10.3" y="12.4" width="19.4" height="16.2" rx="7.4" fill="none" stroke="#e2bb8f" strokeWidth="2.6" />
      <rect x="6.6" y="16.6" width="3.6" height="7.8" rx="1.8" fill="#c8976a" />
      <rect x="29.8" y="16.6" width="3.6" height="7.8" rx="1.8" fill="#c8976a" />
      <path d="M14.9 22.4a2.3 2.3 0 0 1 4.6 0M20.5 22.4a2.3 2.3 0 0 1 4.6 0" fill="none" stroke="#efd0ab" strokeWidth="1.9" strokeLinecap="round" />
    </svg>
  )
}

export function Wordmark({ dark = false, className }: { dark?: boolean; className?: string }) {
  return (
    <span className={cn('group/mark inline-flex items-center gap-2.5 select-none', className)}>
      <BrandMark dark={dark} className="transition-transform duration-500 ease-[var(--ease-out-expo)] group-hover/mark:-rotate-6" />
      <span className={cn('font-display text-[21px] leading-none tracking-[-0.025em]', dark ? 'text-ink-on-dark' : 'text-espresso')}>
        Support<span className="italic font-light">Nova</span>
      </span>
    </span>
  )
}
