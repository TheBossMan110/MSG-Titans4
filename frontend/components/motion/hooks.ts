'use client'

import { useEffect, useLayoutEffect, useRef, useState, type RefObject } from 'react'
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'

gsap.registerPlugin(ScrollTrigger)

const useIsoLayoutEffect = typeof window === 'undefined' ? useEffect : useLayoutEffect

/** True when the visitor has asked for less motion. Re-evaluates if they change it. */
export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false)
  useEffect(() => {
    const query = window.matchMedia('(prefers-reduced-motion: reduce)')
    const update = () => setReduced(query.matches)
    update()
    query.addEventListener('change', update)
    return () => query.removeEventListener('change', update)
  }, [])
  return reduced
}

/** True below the large breakpoint, where 3D and pinned scrubs are switched off. */
export function useIsCompact(): boolean {
  const [compact, setCompact] = useState(false)
  useEffect(() => {
    const query = window.matchMedia('(max-width: 1023px)')
    const update = () => setCompact(query.matches)
    update()
    query.addEventListener('change', update)
    return () => query.removeEventListener('change', update)
  }, [])
  return compact
}

/**
 * One gsap.context per component, reverted on unmount.
 *
 * Every tween and ScrollTrigger created inside `setup` is scoped to `scope`
 * and torn down together — which is what stops a page you have navigated away
 * from leaving triggers behind that fire against elements that no longer
 * exist.
 */
export function useGsap(
  setup: (ctx: gsap.Context, scope: HTMLElement) => void,
  scope: RefObject<HTMLElement | null>,
  deps: ReadonlyArray<unknown> = [],
) {
  const reduced = useReducedMotion()
  useIsoLayoutEffect(() => {
    const el = scope.current
    if (!el || reduced) return
    const ctx = gsap.context((self) => setup(self, el), el)
    return () => ctx.revert()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reduced, ...deps])
}

/**
 * Reveal on entry, driven by IntersectionObserver rather than ScrollTrigger.
 *
 * ScrollTrigger has to resolve each element to a scroll offset up front, and
 * those offsets go stale the moment the page reflows — a web font landing, a
 * pin spacer appearing, the 3D canvas mounting. With `once: true` a trigger
 * whose start line has already slipped past never fires again, which is how
 * sixty-one elements ended up stranded at opacity 0. IntersectionObserver
 * asks the browser "is it on screen now?", so reflow simply cannot desync it.
 *
 * The hidden state is applied here, in JavaScript, and never in CSS. If this
 * module fails to load, every word on the page is still readable.
 *
 * Two kinds of target:
 *   [data-reveal]  fades and rises
 *   [data-line]    a headline line, wiped up from behind its parent's mask
 */
export function useReveal(
  scope: RefObject<HTMLElement | null>,
  { stagger = 0.075, y = 24 }: { stagger?: number; y?: number } = {},
) {
  const reduced = useReducedMotion()

  useIsoLayoutEffect(() => {
    const root = scope.current
    if (!root || reduced) return

    const items = Array.from(root.querySelectorAll<HTMLElement>('[data-reveal]'))
    const lines = Array.from(root.querySelectorAll<HTMLElement>('[data-line]'))
    if (!items.length && !lines.length) return

    gsap.set(items, { opacity: 0, y, willChange: 'transform, opacity' })
    gsap.set(lines, { yPercent: 115, willChange: 'transform' })

    // What we OBSERVE is not always what we ANIMATE. A headline line sits at
    // yPercent 115 inside an overflow-hidden mask, which means it is entirely
    // clipped — and IntersectionObserver honours ancestor clipping, so it
    // would report such a line as never on screen and the headline would stay
    // hidden for ever. Observe the unclipped headline instead, and animate
    // its lines together so the stagger survives.
    const groups = new Map<Element, HTMLElement[]>()
    const addTo = (key: Element, el: HTMLElement) => {
      const list = groups.get(key)
      if (list) list.push(el)
      else groups.set(key, [el])
    }
    items.forEach((el) => addTo(el, el))
    lines.forEach((el) => addTo(el.closest('h1, h2, h3, [data-lines]') ?? el.parentElement ?? el, el))

    const play = (targets: HTMLElement[]) => {
      const reveal = targets.filter((t) => t.hasAttribute('data-reveal'))
      const line = targets.filter((t) => t.hasAttribute('data-line'))
      if (line.length) {
        gsap.to(line, {
          yPercent: 0,
          duration: 1.05,
          ease: 'expo.out',
          stagger: 0.075,
          clearProps: 'willChange',
        })
      }
      if (reveal.length) {
        gsap.to(reveal, {
          opacity: 1,
          y: 0,
          duration: 0.9,
          ease: 'expo.out',
          stagger,
          clearProps: 'willChange',
        })
      }
    }

    const io = new IntersectionObserver(
      (entries) => {
        const fired: HTMLElement[] = []
        for (const e of entries) {
          if (!e.isIntersecting) continue
          io.unobserve(e.target)
          fired.push(...(groups.get(e.target) ?? []))
        }
        if (!fired.length) return
        // Keep document order so a stagger reads top-to-bottom, not by however
        // the observer happened to queue them.
        fired.sort((a, b) => (a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1))
        play(fired)
      },
      { rootMargin: '0px 0px -10% 0px', threshold: 0.01 },
    )

    groups.forEach((_, key) => io.observe(key))

    // Belt and braces: whatever has not been reached after eight seconds is
    // shown anyway. No visitor should ever be looking at invisible text
    // because an observer callback went missing.
    const failsafe = window.setTimeout(() => {
      io.disconnect()
      gsap.to(items, { opacity: 1, y: 0, duration: 0.4, overwrite: true })
      gsap.to(lines, { yPercent: 0, duration: 0.4, overwrite: true })
    }, 8000)

    return () => {
      clearTimeout(failsafe)
      io.disconnect()
      gsap.set([...items, ...lines], { clearProps: 'all' })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reduced])
}

/**
 * Recompute every ScrollTrigger once the page has actually stopped moving.
 *
 * Fonts, the WebGL canvas and images all change layout after first paint, and
 * a scrubbed or pinned trigger measured before that is measuring the wrong
 * page.
 */
export function useScrollTriggerRefresh() {
  useEffect(() => {
    let cancelled = false
    const refresh = () => { if (!cancelled) ScrollTrigger.refresh() }

    const t1 = window.setTimeout(refresh, 300)
    const t2 = window.setTimeout(refresh, 1200)
    if (document.fonts?.ready) void document.fonts.ready.then(refresh)
    window.addEventListener('load', refresh)

    return () => {
      cancelled = true
      clearTimeout(t1)
      clearTimeout(t2)
      window.removeEventListener('load', refresh)
    }
  }, [])
}

/** A ref that also reports whether the element is currently on screen. */
export function useOnScreen<T extends HTMLElement>(rootMargin = '0px'): [RefObject<T | null>, boolean] {
  const ref = useRef<T | null>(null)
  const [visible, setVisible] = useState(false)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const io = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting), { rootMargin })
    io.observe(el)
    return () => io.disconnect()
  }, [rootMargin])
  return [ref, visible]
}
