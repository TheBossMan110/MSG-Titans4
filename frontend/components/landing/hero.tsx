'use client'

import { useRef } from 'react'
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import { EngineLoader } from '@/components/three/engine-loader'
import { SLABS, type Progress } from '@/components/three/engine'
import { useGsap, useIsCompact } from '@/components/motion/hooks'
import { Button } from '@/components/ui/primitives'
import { ShieldCheck, Sparkles } from 'lucide-react'
import { cn } from '@/lib/utils'

gsap.registerPlugin(ScrollTrigger)

const STATS: Array<[string, string]> = [
  ['Pipelines', 'Two'],
  ['GenAI calls in the verifier', 'Zero'],
  ['Escalation floor', 'Never lowered'],
]

/**
 * The hero runs tall so the scroll that follows can pull the six slabs apart,
 * but the sticky frame it pins is a strict column: content above, a measured
 * footer rail below. Nothing is allowed to overflow the viewport, because a
 * headline that clips its own statistics is worse than a smaller headline.
 *
 * 175vh, not 260vh. Every extra viewport of height is another screenful of
 * scrolling during which the page does not appear to move, and past about
 * three quarters of a screen that stops reading as a scrubbed animation and
 * starts reading as a page that has frozen.
 */
export function Hero() {
  const root = useRef<HTMLElement>(null)
  const progress = useRef<Progress>({ value: 0, pointer: { x: 0, y: 0 } }).current
  const compact = useIsCompact()

  useGsap((ctx, el) => {
    const labels = el.querySelectorAll<HTMLElement>('[data-slab-label]')
    gsap.set(labels, { opacity: 0, y: 8 })

    ScrollTrigger.create({
      trigger: el,
      start: 'top top',
      end: 'bottom bottom',
      scrub: 0.6,
      invalidateOnRefresh: true,
      onUpdate: (self) => {
        progress.value = self.progress
        labels.forEach((l, i) => {
          const local = Math.min(1, Math.max(0, (self.progress - 0.35 - i * 0.06) / 0.3))
          gsap.set(l, { opacity: local, y: 8 - 8 * local })
        })
      },
    })

    const intro = gsap.timeline({ defaults: { ease: 'expo.out' } })
    intro
      .from('[data-hero-line]', { yPercent: 112, duration: 1.25, stagger: 0.085 }, 0.1)
      .from('[data-hero-fade]', { opacity: 0, y: 16, duration: 0.95, stagger: 0.07 }, 0.55)
      .from('[data-hero-engine]', { opacity: 0, scale: 0.94, duration: 1.5 }, 0.2)
      .from('[data-hero-rail]', { opacity: 0, y: 14, duration: 0.9 }, 0.9)
  }, root)

  return (
    <section
      ref={root}
      aria-label="Introduction"
      className={cn('mesh-hero relative', compact ? 'min-h-dvh' : 'h-[175vh]')}
    >
      {/* Pinning only makes sense where there is a scrub to pin for. On a
          phone the hero is an ordinary block that grows to fit its content,
          so nothing at the foot of it can be cut off. */}
      <div
        className={cn(
          'flex flex-col',
          compact
            ? 'min-h-dvh pb-8'
            : 'sticky top-0 h-dvh min-h-[640px] overflow-hidden',
        )}
      >
        {/* main */}
        <div className="container-x flex flex-1 items-center pt-[calc(var(--nav-h)+24px)] lg:pt-[var(--nav-h)]">
          <div className="grid w-full items-center gap-10 lg:grid-cols-[1.06fr_0.94fr] lg:gap-10">
            <div className="relative z-10">
              <p data-hero-fade className="eyebrow mb-5 flex flex-wrap items-center gap-x-3 gap-y-1">
                <span aria-hidden className="inline-block size-1.5 rounded-full bg-taupe" />
                ResponseX Intelligence
                <span aria-hidden className="hidden h-px w-6 bg-line sm:inline-block" />
                <span className="text-taupe">RaftarXpress Logistics</span>
              </p>

              <h1 className="display text-hero">
                <span className="block overflow-hidden pb-[0.05em]"><span data-hero-line className="block">Every complaint,</span></span>
                <span className="block overflow-hidden pb-[0.05em]">
                  <span data-hero-line className="block">understood by <span className="text-ai-gradient">AI.</span></span>
                </span>
                <span className="block overflow-hidden pb-[0.05em]"><span data-hero-line className="display-italic block text-espresso-2">Every decision,</span></span>
                <span className="block overflow-hidden pb-[0.05em]"><span data-hero-line className="display-italic block text-rule">verified by rules.</span></span>
              </h1>

              <p data-hero-fade className="mt-7 max-w-[46ch] text-lead text-espresso-2">
                A generative model reads, classifies and drafts. An independent rule engine,
                written from the company&rsquo;s own policies, checks every field before a
                customer sees a word.
              </p>

              <div data-hero-fade className="mt-8 flex flex-wrap items-center gap-3">
                <Button href="/dashboard/complaints/new" size="lg" arrow>Submit a complaint</Button>
                <Button href="#intelligence" variant="secondary" size="lg">See how it works</Button>
                <a href="#demo" className="link-underline ml-1 text-[14px] font-medium text-espresso-2">Try the live rule engine</a>
              </div>
            </div>

            <div data-hero-engine className="relative hidden lg:block">
              <span aria-hidden className="pointer-events-none absolute left-1/2 top-1/2 size-[80%] -translate-x-1/2 -translate-y-1/2 rounded-full bg-[radial-gradient(closest-side,rgba(123,111,240,0.28),transparent)] blur-2xl" />
              <EngineLoader progress={progress} className="aspect-[1/1] w-[112%] -translate-x-[4%]" />
              <div className="glass absolute left-0 top-[14%] flex animate-float-slow items-center gap-2.5 rounded-2xl px-4 py-3">
                <span className="inline-flex size-8 items-center justify-center rounded-xl bg-ai text-white shadow-ai"><Sparkles size={15} aria-hidden /></span>
                <span><span className="block text-[11px] font-semibold uppercase tracking-[0.12em] text-ai">AI proposes</span><span className="block text-[13px] text-espresso-2">Lost shipment · P2 · refund</span></span>
              </div>
              <div className="glass absolute bottom-[16%] right-0 flex animate-float-slow items-center gap-2.5 rounded-2xl px-4 py-3 [animation-delay:-4.5s]">
                <span className="inline-flex size-8 items-center justify-center rounded-xl bg-rule text-white shadow-rule"><ShieldCheck size={15} aria-hidden /></span>
                <span><span className="block text-[11px] font-semibold uppercase tracking-[0.12em] text-rule">Rules confirm</span><span className="block text-[13px] text-espresso-2">P1 · compliance review · verify first</span></span>
              </div>
              <ol className="pointer-events-none absolute inset-x-0 -bottom-4 grid grid-cols-6 gap-1 text-center" aria-hidden>
                {SLABS.map((s) => (
                  <li key={s.key} data-slab-label className="eyebrow text-[9.5px] tracking-[0.1em]">{s.label}</li>
                ))}
              </ol>
            </div>
          </div>
        </div>

        {/* footer rail: the numbers, and the invitation to scroll */}
        <div data-hero-rail className="container-x mt-10 shrink-0 pb-[max(18px,env(safe-area-inset-bottom))] lg:mt-0">
          <div className="flex flex-wrap items-end justify-between gap-x-10 gap-y-5 border-t border-line pt-5">
            <dl className="grid grid-cols-2 gap-x-8 gap-y-4 sm:flex sm:flex-wrap sm:items-end sm:gap-x-14">
              {STATS.map(([label, value]) => (
                <div key={label}>
                  <dt className="eyebrow mb-1.5">{label}</dt>
                  <dd className="font-display text-[clamp(20px,2vw,27px)] leading-none text-espresso">{value}</dd>
                </div>
              ))}
            </dl>
            <span className="eyebrow hidden items-center gap-2.5 text-[10px] lg:flex">
              <span aria-hidden className="block h-7 w-px origin-top bg-taupe/70 [animation:scrollcue_2.4s_ease-in-out_infinite]" />
              Scroll to separate the engine
            </span>
          </div>
        </div>
      </div>

      <style>{`@keyframes scrollcue{0%,100%{transform:scaleY(.25);opacity:.35}50%{transform:scaleY(1);opacity:1}}`}</style>
    </section>
  )
}
