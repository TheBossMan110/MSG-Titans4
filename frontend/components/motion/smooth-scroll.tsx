'use client'

import { useEffect } from 'react'
import { applyMotionClass, prefersReducedMotion } from '@/lib/motion-pref'
import Lenis from 'lenis'
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import { useScrollTriggerRefresh } from './hooks'

gsap.registerPlugin(ScrollTrigger)

let instance: Lenis | null = null

/** The live Lenis instance, for anything that needs to scroll programmatically. */
export function getLenis(): Lenis | null {
  return instance
}

/**
 * Smooth scrolling, driven by GSAP's ticker.
 *
 * The sync is the point. Given its own requestAnimationFrame loop, Lenis
 * never tells ScrollTrigger the page moved, so every scrubbed animation runs
 * a frame behind and stutters. Here Lenis is stepped by gsap.ticker,
 * ScrollTrigger is updated on each Lenis scroll, and lag smoothing is off so
 * a dropped frame is dropped rather than replayed.
 *
 * With "Reduce motion" switched on it does not mount at all: native scrolling
 * is the accessible default and nothing else depends on Lenis existing.
 */
export default function SmoothScroll() {
  useScrollTriggerRefresh()

  useEffect(() => {
    applyMotionClass()
    if (prefersReducedMotion()) return

    const lenis = new Lenis({
      duration: 1.05,
      easing: (t) => Math.min(1, 1.001 - Math.pow(2, -10 * t)),
      smoothWheel: true,
      wheelMultiplier: 1,
      touchMultiplier: 1.6,
    })
    instance = lenis

    lenis.on('scroll', ScrollTrigger.update)
    const tick = (time: number) => lenis.raf(time * 1000)
    gsap.ticker.add(tick)
    gsap.ticker.lagSmoothing(0)

    // In-page anchors have to go through Lenis, or the browser jumps while
    // Lenis believes it is still where it was.
    const onClick = (e: MouseEvent) => {
      const link = (e.target as HTMLElement | null)?.closest?.('a[href^="#"]') as HTMLAnchorElement | null
      if (!link) return
      const id = link.getAttribute('href')
      if (!id || id === '#') return
      const target = document.querySelector(id)
      if (!target) return
      e.preventDefault()
      lenis.scrollTo(target as HTMLElement, { offset: -80, duration: 1.2 })
    }
    document.addEventListener('click', onClick)

    return () => {
      document.removeEventListener('click', onClick)
      gsap.ticker.remove(tick)
      lenis.destroy()
      instance = null
    }
  }, [])

  return null
}
