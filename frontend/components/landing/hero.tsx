'use client'

import { useRef } from 'react'
import gsap from 'gsap'
import { ParcelScan } from '@/components/landing/parcel-scan'
import { useGsap } from '@/components/motion/hooks'
import { Button } from '@/components/ui/primitives'

const STATS: Array<[string, string]> = [
  ['Pipelines', 'Two'],
  ['GenAI calls in the verifier', 'Zero'],
  ['Escalation floor', 'Never lowered'],
]

/**
 * One screen: the promise on the left, the parcel being opened, scanned and
 * verified on the right, the numbers along the foot. The parcel loops on its
 * own, so the hero no longer pins the page while the reader scrolls -- the
 * first scroll moves the page, as a reader expects.
 *
 * Everything is sized against the viewport's height as well as its width,
 * so the statistics rail is on screen on a 657px-tall laptop too.
 */
export function Hero() {
  const root = useRef<HTMLElement>(null)

  useGsap(() => {
    const intro = gsap.timeline({ defaults: { ease: 'expo.out' } })
    intro
      .from('[data-hero-line]', { yPercent: 135, duration: 1.25, stagger: 0.085 }, 0.1)
      .from('[data-hero-fade]', { opacity: 0, y: 16, duration: 0.95, stagger: 0.07 }, 0.55)
      .from('[data-hero-art]', { opacity: 0, scale: 0.96, duration: 1.4 }, 0.2)
      .from('[data-hero-rail]', { opacity: 0, y: 14, duration: 0.9 }, 0.9)
  }, root)

  const SH = '[@media(max-height:820px)]:'
  return (
    <section ref={root} aria-label="Introduction" className="mesh-hero relative">
      <div className="flex min-h-dvh flex-col">
        <div className="container-x flex flex-1 items-center pt-[calc(var(--nav-h)+24px)] lg:pt-[var(--nav-h)]">
          <div className="grid w-full items-center gap-10 lg:grid-cols-[1.02fr_0.98fr] lg:gap-8">
            <div className="relative z-10">
              <p data-hero-fade className={`eyebrow mb-5 flex flex-wrap items-center gap-x-3 gap-y-1 ${SH}mb-3`}>
                <span aria-hidden className="inline-block size-1.5 rounded-full bg-taupe" />
                ResponseX Intelligence
                <span aria-hidden className="hidden h-px w-6 bg-line sm:inline-block" />
                <span className="text-taupe">RaftarXpress Logistics</span>
              </p>

              <h1 className="display text-hero">
                <span className="block overflow-hidden pb-[0.2em] -mb-[0.14em]"><span data-hero-line className="block">Every complaint,</span></span>
                <span className="block overflow-hidden pb-[0.2em] -mb-[0.14em]">
                  <span data-hero-line className="block">understood by <span className="text-ai-gradient">AI.</span></span>
                </span>
                <span className="block overflow-hidden pb-[0.2em] -mb-[0.14em]"><span data-hero-line className="display-italic block text-espresso-2">Every decision,</span></span>
                <span className="block overflow-hidden pb-[0.2em]"><span data-hero-line className="display-italic block text-rule">verified by rules.</span></span>
              </h1>

              <p data-hero-fade className={`mt-7 max-w-[50ch] text-lead text-espresso-2 ${SH}mt-4 ${SH}text-[1.05rem]`}>
                A generative model reads, classifies and drafts. An independent rule engine,
                written from the company&rsquo;s own policies, checks every field before a
                customer sees a word.
              </p>

              <div data-hero-fade className={`mt-8 flex flex-wrap items-center gap-3 ${SH}mt-5`}>
                <Button href="/dashboard/complaints/new" size="lg" arrow>Submit a complaint</Button>
                <Button href="#intelligence" variant="secondary" size="lg">See how it works</Button>
                <a href="#demo" className="link-underline ml-1 text-[14px] font-medium text-espresso-2">Try the live rule engine</a>
              </div>
            </div>

            {/* Never taller than the room the screen leaves for it. */}
            <div data-hero-art className="relative mx-auto w-full max-w-[min(600px,calc((100dvh-var(--nav-h)-150px)*1.12))]">
              <ParcelScan />
            </div>
          </div>
        </div>

        {/* footer rail: the numbers */}
        <div data-hero-rail className={`container-x mt-10 shrink-0 pb-[max(18px,env(safe-area-inset-bottom))] lg:mt-2 ${SH}pb-3`}>
          <div className={`flex flex-wrap items-end justify-between gap-x-10 gap-y-5 border-t border-line pt-5 ${SH}pt-3`}>
            <dl className="grid grid-cols-2 gap-x-8 gap-y-4 sm:flex sm:flex-wrap sm:items-end sm:gap-x-14">
              {STATS.map(([label, value]) => (
                <div key={label}>
                  <dt className="eyebrow mb-1.5">{label}</dt>
                  <dd className="font-display text-[clamp(18px,min(2vw,3.4vh),27px)] leading-none text-espresso">{value}</dd>
                </div>
              ))}
            </dl>
            <span className="eyebrow hidden items-center gap-2.5 text-[10px] lg:mr-[190px] lg:flex">
              <span aria-hidden className="block h-7 w-px origin-top bg-taupe/70 [animation:scrollcue_2.4s_ease-in-out_infinite]" />
              One parcel, opened, scanned and verified
            </span>
          </div>
        </div>
      </div>

      <style>{`@keyframes scrollcue{0%,100%{transform:scaleY(.25);opacity:.35}50%{transform:scaleY(1);opacity:1}}`}</style>
    </section>
  )
}
