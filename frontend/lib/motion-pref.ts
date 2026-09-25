'use client'

/**
 * Whether the site animates.
 *
 * On by default, and set by the visitor from the "Reduce motion" switch
 * (footer and Settings), not from the operating system. Windows users who
 * have "Animation effects" turned off -- a common default on laptops --
 * otherwise got a site with every animation silently switched off, which read
 * as "the animations are broken" rather than as a preference being honoured.
 * Anyone who needs less motion still has one switch that turns all of it off.
 */
const KEY = 'sn-motion'
export const MOTION_EVENT = 'sn-motion-change'

export function prefersReducedMotion(): boolean {
  if (typeof window === 'undefined') return false
  try {
    return window.localStorage.getItem(KEY) === 'reduced'
  } catch {
    return false
  }
}

export function setReducedMotion(reduced: boolean): void {
  try {
    if (reduced) window.localStorage.setItem(KEY, 'reduced')
    else window.localStorage.removeItem(KEY)
  } catch {}
  applyMotionClass()
  window.dispatchEvent(new CustomEvent(MOTION_EVENT))
}

/** Mirror the preference onto <html> so CSS animations follow it too. */
export function applyMotionClass(): void {
  if (typeof document === 'undefined') return
  document.documentElement.classList.toggle('reduce-motion', prefersReducedMotion())
}
