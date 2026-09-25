import type { HTMLAttributes, ReactNode } from 'react'
import { ShieldCheck, Sparkles } from 'lucide-react'
import { cn } from '@/lib/utils'

/* ------------------------------------------------------------------ Card */

type CardTone = 'ivory' | 'glass' | 'cream' | 'sand' | 'ink' | 'pencil' | 'ghost' | 'ai' | 'rule'

const cardTones: Record<CardTone, string> = {
  ivory: 'bg-ivory border border-line-soft shadow-card',
  // Frosted: only reads over a varied background, which the app shell's mesh provides.
  glass: 'glass',
  cream: 'bg-cream/80 border border-line',
  sand: 'bg-sand/70 border border-line',
  ink: 'ink shadow-float',
  pencil: 'pencil',
  ghost: 'border border-dashed border-line',
  ai: 'bg-ai-soft/80 border border-ai-line',
  rule: 'bg-rule-soft/80 border border-rule-line',
}

export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  tone?: CardTone
  padding?: 'none' | 'sm' | 'md' | 'lg'
  radius?: 'md' | 'lg' | 'xl'
  lift?: boolean
}

const paddings = { none: '', sm: 'p-4', md: 'p-6', lg: 'p-8 md:p-10' }
const radii = { md: 'rounded-[var(--radius-md)]', lg: 'rounded-[var(--radius-lg)]', xl: 'rounded-[var(--radius-xl)]' }

export function Card({ tone = 'ivory', padding = 'md', radius = 'lg', lift, className, children, ...rest }: CardProps) {
  return (
    <div
      className={cn(
        'relative',
        cardTones[tone],
        paddings[padding],
        radii[radius],
        lift && 'transition-[transform,box-shadow,border-color] duration-300 ease-[var(--ease-out-expo)] hover:-translate-y-0.5 hover:shadow-float',
        className,
      )}
      {...rest}
    >
      {children}
    </div>
  )
}

/* ------------------------------------------------------------------ Section */

export function Section({
  dark = false,
  id,
  className,
  children,
  bleed = false,
}: {
  dark?: boolean
  id?: string
  className?: string
  children: ReactNode
  bleed?: boolean
}) {
  return (
    <section
      id={id}
      className={cn(
        'relative py-[clamp(64px,8.2vw,136px)]',
        dark ? 'section-dark grain overflow-hidden' : 'paper',
        className,
      )}
    >
      <div className={cn(!bleed && 'container-x', 'relative z-[1]')}>{children}</div>
    </section>
  )
}

/* ------------------------------------------------------------------ Rules */

export function Hairline({ className, vertical }: { className?: string; vertical?: boolean }) {
  return <div aria-hidden className={cn(vertical ? 'w-px self-stretch' : 'h-px w-full', 'bg-line', className)} />
}

/* ------------------------------------------------------------------ Panel header */

export function PanelHeader({
  title,
  aside,
  eyebrow,
  icon,
  className,
}: {
  title: ReactNode
  aside?: ReactNode
  eyebrow?: ReactNode
  icon?: ReactNode
  className?: string
}) {
  return (
    <div className={cn('mb-5 flex flex-wrap items-end justify-between gap-3', className)}>
      <div className="flex items-end gap-3">
        {icon && (
          <span className="mb-0.5 inline-flex size-9 shrink-0 items-center justify-center rounded-[10px] border border-line-soft bg-white/80 text-espresso-2 shadow-[0_1px_2px_rgba(42,31,23,0.06)]">
            {icon}
          </span>
        )}
        <div>
          {eyebrow && <p className="eyebrow mb-1.5">{eyebrow}</p>}
          <h3 className="font-display text-h3 leading-none">{title}</h3>
        </div>
      </div>
      {aside && <div className="flex items-center gap-2">{aside}</div>}
    </div>
  )
}

/* ------------------------------------------------------------------ Pencil → Ink */

/**
 * The product's central visual: a proposal beside a decision.
 *
 * Left is what the AI wrote — violet, dashed, italic: provisional. Right is
 * what the rules confirmed — espresso, solid, shielded: final. Used on the
 * landing page, the complaint's "Why" tab and the review desk, so the reading
 * is learnt once.
 */
export function PencilInk({
  pencil,
  ink,
  pencilLabel = 'AI proposed',
  inkLabel = 'Rules decided',
  className,
}: {
  pencil: ReactNode
  ink: ReactNode
  pencilLabel?: string
  inkLabel?: string
  className?: string
}) {
  return (
    <div className={cn('grid gap-3 md:grid-cols-2', className)}>
      <div className="pencil rounded-[var(--radius-lg)] p-5">
        <p className="mb-2.5 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-ai">
          <Sparkles size={12} strokeWidth={2.2} aria-hidden /> {pencilLabel}
        </p>
        <div className="font-display text-[18px] italic leading-snug text-[#2c2380]">{pencil}</div>
      </div>
      <div className="ink relative overflow-hidden rounded-[var(--radius-lg)] p-5">
        <span aria-hidden className="pointer-events-none absolute -right-10 -top-10 size-32 rounded-full bg-rule-2/40 blur-2xl" />
        <p className="relative mb-2.5 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-[#a9d4bd]">
          <ShieldCheck size={12} strokeWidth={2.2} aria-hidden /> {inkLabel}
        </p>
        <div className="relative text-[16px] font-medium leading-snug">{ink}</div>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ Page header */

/**
 * The top of every application page: an eyebrow, a serif title, an optional
 * sentence of context, and actions. One component so the rhythm is identical
 * everywhere.
 */
export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
  className,
}: {
  eyebrow?: ReactNode
  title: ReactNode
  description?: ReactNode
  actions?: ReactNode
  className?: string
}) {
  return (
    <header className={cn('flex flex-wrap items-end justify-between gap-5', className)}>
      <div className="min-w-0 animate-rise">
        {eyebrow && <p className="eyebrow mb-2">{eyebrow}</p>}
        <h1 className="display text-h2">{title}</h1>
        {description && <p className="mt-3 max-w-[64ch] text-[15px] leading-relaxed text-taupe">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  )
}
