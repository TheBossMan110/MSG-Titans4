'use client'

import { forwardRef, useId, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from 'react'
import { cn } from '@/lib/utils'

const control =
  'w-full rounded-[var(--radius-md)] border border-line bg-ivory px-3.5 text-[14px] text-charcoal placeholder:text-taupe ' +
  'transition-[border-color,box-shadow] duration-150 focus:border-espresso focus:shadow-[0_0_0_3px_rgba(42,31,23,0.08)] focus:outline-none ' +
  'disabled:opacity-60 aria-[invalid=true]:border-critical'

export function Field({
  label,
  hint,
  error,
  children,
  required,
  className,
}: {
  label: string
  hint?: ReactNode
  error?: string | null
  children: (id: string) => ReactNode
  required?: boolean
  className?: string
}) {
  const id = useId()
  return (
    <div className={cn('flex flex-col gap-1.5', className)}>
      <label htmlFor={id} className="text-[13px] font-medium text-espresso-2">
        {label}
        {required && <span className="ml-1 text-critical" aria-hidden>*</span>}
      </label>
      {children(id)}
      {error ? (
        <p role="alert" className="text-[12.5px] text-critical">{error}</p>
      ) : hint ? (
        <p className="text-[12.5px] text-taupe-2">{hint}</p>
      ) : null}
    </div>
  )
}

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function Input(
  { className, ...rest },
  ref,
) {
  return <input ref={ref} className={cn(control, 'h-11', className)} {...rest} />
})

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(
  function Textarea({ className, ...rest }, ref) {
    return <textarea ref={ref} className={cn(control, 'min-h-[132px] py-3 leading-relaxed', className)} {...rest} />
  },
)

export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(function Select(
  { className, children, ...rest },
  ref,
) {
  return (
    <div className="relative">
      <select ref={ref} className={cn(control, 'h-11 appearance-none pr-9', className)} {...rest}>
        {children}
      </select>
      <svg
        aria-hidden
        className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-taupe"
        width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
      >
        <path d="m6 9 6 6 6-6" />
      </svg>
    </div>
  )
})

export function Checkbox({
  label,
  className,
  ...rest
}: InputHTMLAttributes<HTMLInputElement> & { label: ReactNode }) {
  const id = useId()
  return (
    <label htmlFor={id} className={cn('inline-flex cursor-pointer items-center gap-2.5 text-[14px]', className)}>
      <input id={id} type="checkbox" className="size-4 accent-espresso" {...rest} />
      {label}
    </label>
  )
}

/** A search box that submits on Enter and clears with Escape. */
export function SearchBox({
  value,
  onChange,
  placeholder = 'Search',
  className,
}: {
  value: string
  onChange: (v: string) => void
  placeholder?: string
  className?: string
}) {
  return (
    <div className={cn('relative', className)}>
      <svg
        aria-hidden
        className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-taupe"
        width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
      >
        <circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" />
      </svg>
      <input
        type="search"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => e.key === 'Escape' && onChange('')}
        placeholder={placeholder}
        aria-label={placeholder}
        className={cn(control, 'h-10 pl-9')}
      />
    </div>
  )
}

/* ------------------------------------------------------------------ floating labels */

const floatControl =
  'peer w-full rounded-2xl border border-line bg-white/85 px-4 text-[15px] text-charcoal placeholder-transparent ' +
  'shadow-[0_1px_2px_rgba(42,31,23,0.04)] transition-[border-color,box-shadow,background-color] duration-200 ' +
  'hover:border-taupe focus:border-ai focus:bg-white focus:shadow-[0_0_0_4px_rgba(79,63,209,0.12)] focus:outline-none ' +
  'aria-[invalid=true]:border-critical'

const floatLabel =
  'pointer-events-none absolute left-4 origin-left text-taupe transition-all duration-200 ease-[var(--ease-out-expo)] ' +
  'peer-focus:text-ai'

/**
 * A text input whose label sits inside the field until it has a value or
 * focus, then shrinks to the top edge. The label is a real <label>, so it is
 * announced by screen readers and clicking it focuses the field.
 */
export const FloatInput = forwardRef<
  HTMLInputElement,
  InputHTMLAttributes<HTMLInputElement> & { label: string; hint?: ReactNode; error?: string | null; trailing?: ReactNode }
>(function FloatInput({ label, hint, error, trailing, className, id, ...rest }, ref) {
  const auto = useId()
  const fid = id ?? auto
  return (
    <div className={cn('flex flex-col gap-1.5', className)}>
      <div className="relative">
        <input ref={ref} id={fid} placeholder={label} aria-invalid={!!error || undefined} className={cn(floatControl, 'h-14 pb-2 pt-6', trailing && 'pr-12')} {...rest} />
        <label
          htmlFor={fid}
          className={cn(
            floatLabel,
            'top-1/2 -translate-y-1/2 text-[15px]',
            'peer-focus:top-4 peer-focus:text-[11.5px] peer-focus:font-medium',
            'peer-[:not(:placeholder-shown)]:top-4 peer-[:not(:placeholder-shown)]:text-[11.5px] peer-[:not(:placeholder-shown)]:font-medium',
          )}
        >
          {label}{rest.required && <span className="ml-0.5 text-critical">*</span>}
        </label>
        {trailing && <span className="absolute right-4 top-1/2 -translate-y-1/2">{trailing}</span>}
      </div>
      {error ? <p role="alert" className="px-1 text-[12.5px] text-critical">{error}</p> : hint ? <p className="px-1 text-[12.5px] text-taupe">{hint}</p> : null}
    </div>
  )
})

export const FloatTextarea = forwardRef<
  HTMLTextAreaElement,
  TextareaHTMLAttributes<HTMLTextAreaElement> & { label: string; footer?: ReactNode; error?: string | null }
>(function FloatTextarea({ label, footer, error, className, id, ...rest }, ref) {
  const auto = useId()
  const fid = id ?? auto
  return (
    <div className={cn('flex flex-col gap-1.5', className)}>
      <div className="relative">
        <textarea ref={ref} id={fid} placeholder={label} aria-invalid={!!error || undefined} className={cn(floatControl, 'min-h-[200px] resize-y pb-4 pt-8 leading-relaxed')} {...rest} />
        <label
          htmlFor={fid}
          className={cn(
            floatLabel,
            'top-5 text-[15px]',
            'peer-focus:top-3 peer-focus:text-[11.5px] peer-focus:font-medium',
            'peer-[:not(:placeholder-shown)]:top-3 peer-[:not(:placeholder-shown)]:text-[11.5px] peer-[:not(:placeholder-shown)]:font-medium',
          )}
        >
          {label}{rest.required && <span className="ml-0.5 text-critical">*</span>}
        </label>
      </div>
      {error ? <p role="alert" className="px-1 text-[12.5px] text-critical">{error}</p> : footer}
    </div>
  )
})
