'use client'

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { cn } from '@/lib/utils'
import { Button, Spinner } from './primitives'

/* ------------------------------------------------------------------ Empty */

export function Empty({
  title,
  body,
  action,
  icon,
  className,
}: {
  title: string
  body?: ReactNode
  action?: ReactNode
  icon?: ReactNode
  className?: string
}) {
  return (
    <div className={cn('flex flex-col items-center gap-3 rounded-[var(--radius-lg)] border border-dashed border-line bg-white/40 px-6 py-14 text-center', className)}>
      {icon && (
        <div className="mb-1 inline-flex size-12 items-center justify-center rounded-2xl border border-line-soft bg-white text-taupe-2 shadow-card">
          {icon}
        </div>
      )}
      <h3 className="font-display text-h3">{title}</h3>
      {body && <p className="max-w-[46ch] text-[14px] text-taupe">{body}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  )
}

/* ------------------------------------------------------------------ Error */

/**
 * A failure the person can read.
 *
 * Every backend error carries a human sentence; this shows that sentence and
 * never a status code on its own. A 422 from a refused override is an
 * explanation the reviewer needs, not a failure to hide.
 */
export function ErrorState({
  title = 'Something went wrong',
  message,
  onRetry,
  className,
}: {
  title?: string
  message?: string | null
  onRetry?: () => void
  className?: string
}) {
  return (
    <div role="alert" className={cn('rounded-[var(--radius-lg)] border border-critical/30 bg-critical-dim px-6 py-8', className)}>
      <p className="eyebrow mb-2 text-critical">Couldn’t complete that</p>
      <h3 className="font-display text-h3 text-espresso">{title}</h3>
      {message && <p className="mt-2 max-w-[60ch] text-[14px] text-espresso-2">{message}</p>}
      {onRetry && (
        <Button variant="secondary" size="sm" className="mt-5" onClick={onRetry}>Try again</Button>
      )}
    </div>
  )
}

/** A calm banner for a degraded system: nothing is broken, one part is resting. */
export function DegradedBanner({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div role="status" className={cn('flex items-center gap-3 rounded-[var(--radius-md)] border border-warning/30 bg-warning-dim px-4 py-3 text-[13.5px] text-espresso-2', className)}>
      <span aria-hidden className="size-2 shrink-0 rounded-full bg-warning" />
      <span>{children}</span>
    </div>
  )
}

/* ------------------------------------------------------------------ Skeleton */

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cn('shimmer rounded-[var(--radius-md)]', className)} />
}

export function SkeletonRows({ rows = 6, className }: { rows?: number; className?: string }) {
  return (
    <div className={cn('flex flex-col gap-2.5', className)} aria-busy>
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-11 w-full" />
      ))}
    </div>
  )
}

export function Loading({ label = 'Loading' }: { label?: string }) {
  return (
    <div className="flex items-center gap-2.5 py-10 text-[13.5px] text-taupe-2" role="status">
      <Spinner size={16} /> {label}…
    </div>
  )
}

/* ------------------------------------------------------------------ Tabs */

export function Tabs<T extends string>({
  tabs,
  value,
  onChange,
  className,
}: {
  tabs: Array<{ id: T; label: ReactNode; count?: number | null }>
  value: T
  onChange: (id: T) => void
  className?: string
}) {
  return (
    <div role="tablist" className={cn('flex gap-1 overflow-x-auto border-b border-line', className)}>
      {tabs.map((t) => {
        const active = t.id === value
        return (
          <button
            key={t.id}
            role="tab"
            aria-selected={active}
            onClick={() => onChange(t.id)}
            className={cn(
              'relative -mb-px whitespace-nowrap px-3.5 py-2.5 text-[13.5px] font-medium transition-colors',
              active ? 'text-espresso' : 'text-taupe-2 hover:text-espresso',
            )}
          >
            {t.label}
            {typeof t.count === 'number' && (
              <span className="ml-1.5 rounded-full bg-sand px-1.5 font-mono text-[11px] tnum text-espresso-2">{t.count}</span>
            )}
            <span
              aria-hidden
              className={cn('absolute inset-x-2 bottom-0 h-[2px] rounded-full bg-espresso transition-transform duration-300', active ? 'scale-x-100' : 'scale-x-0')}
            />
          </button>
        )
      })}
    </div>
  )
}

/* ------------------------------------------------------------------ Modal */

export function Modal({
  open,
  onClose,
  title,
  children,
  footer,
  width = 520,
}: {
  open: boolean
  onClose: () => void
  title: ReactNode
  children: ReactNode
  footer?: ReactNode
  width?: number
}) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const d = ref.current
    if (!d) return
    if (open && !d.open) d.showModal()
    if (!open && d.open) d.close()
  }, [open])
  return (
    <dialog
      ref={ref}
      onClose={onClose}
      onClick={(e) => e.target === ref.current && onClose()}
      className="m-auto w-[min(92vw,var(--w))] rounded-[var(--radius-xl)] border border-line bg-ivory p-0 text-charcoal shadow-float backdrop:bg-espresso/40 backdrop:backdrop-blur-[2px]"
      style={{ ['--w' as string]: `${width}px` }}
    >
      <div className="p-6 md:p-7">
        <h3 className="mb-4 font-display text-h3">{title}</h3>
        <div className="text-[14px] leading-relaxed">{children}</div>
        {footer && <div className="mt-6 flex justify-end gap-2">{footer}</div>}
      </div>
    </dialog>
  )
}

/* ------------------------------------------------------------------ Toast */

type Toast = { id: number; tone: 'ok' | 'warn' | 'err'; text: string }
const ToastCtx = createContext<(tone: Toast['tone'], text: string) => void>(() => {})

export function useToast() {
  return useContext(ToastCtx)
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([])
  const push = useCallback((tone: Toast['tone'], text: string) => {
    const id = Date.now() + Math.random()
    setItems((s) => [...s, { id, tone, text }])
    setTimeout(() => setItems((s) => s.filter((t) => t.id !== id)), 4200)
  }, [])
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="pointer-events-none fixed inset-x-0 bottom-[max(16px,env(safe-area-inset-bottom))] z-[90] flex flex-col items-center gap-2 px-4" aria-live="polite">
        {items.map((t) => (
          <div
            key={t.id}
            className={cn(
              'pointer-events-auto rounded-full border px-4 py-2 text-[13.5px] shadow-float',
              t.tone === 'ok' && 'border-verified/30 bg-ivory text-espresso',
              t.tone === 'warn' && 'border-warning/40 bg-warning-dim text-espresso',
              t.tone === 'err' && 'border-critical/40 bg-critical-dim text-espresso',
            )}
          >
            {t.text}
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  )
}
