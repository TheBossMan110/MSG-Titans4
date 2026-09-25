'use client'

import { useEffect, useState } from 'react'
import { MOTION_EVENT, prefersReducedMotion, setReducedMotion } from '@/lib/motion-pref'
import { cn } from '@/lib/utils'

/**
 * The one switch for the site's animation. Changing it reloads the page, so
 * smooth scrolling and every scroll-driven scene start again in the new mode.
 */
export function MotionToggle({ className, dark = false }: { className?: string; dark?: boolean }) {
  const [reduced, setReduced] = useState(false)
  useEffect(() => {
    const update = () => setReduced(prefersReducedMotion())
    update()
    window.addEventListener(MOTION_EVENT, update)
    return () => window.removeEventListener(MOTION_EVENT, update)
  }, [])
  return (
    <button
      type="button"
      role="switch"
      aria-checked={reduced}
      onClick={() => { setReducedMotion(!reduced); window.location.reload() }}
      className={cn('inline-flex items-center gap-2.5 text-[13px]', dark ? 'text-ink-on-dark/80 hover:text-ink-on-dark' : 'text-espresso-2 hover:text-espresso', className)}
    >
      <span className={cn('relative inline-flex h-5 w-9 shrink-0 rounded-full transition-colors', reduced ? 'bg-espresso' : dark ? 'bg-ink-on-dark/25' : 'bg-sand-2')}>
        <span className={cn('absolute top-0.5 size-4 rounded-full bg-white shadow transition-transform', reduced ? 'translate-x-[18px]' : 'translate-x-0.5')} />
      </span>
      Reduce motion
    </button>
  )
}
