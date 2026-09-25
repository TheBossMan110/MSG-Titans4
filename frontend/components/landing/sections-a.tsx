'use client'

import { useRef } from 'react'
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import { useGsap, useReveal } from '@/components/motion/hooks'
import { Badge, Display, Eyebrow, Mono } from '@/components/ui/primitives'
import { Card, Section } from '@/components/ui/surfaces'
import { cn } from '@/lib/utils'

gsap.registerPlugin(ScrollTrigger)

/* ------------------------------------------------------------------ 3. Trust statement */

export function Trust() {
  const root = useRef<HTMLDivElement>(null)
  useReveal(root)
  return (
    <Section id="product" className="!py-[clamp(56px,8vw,120px)]">
      <div ref={root} className="mx-auto max-w-[900px] text-center">
        <p data-reveal className="display text-h2 text-espresso">
          Nothing reaches a customer that the rule engine did not confirm.
          <span className="display-italic text-taupe-2"> Not a category, not a promise, not a citation.</span>
        </p>
        <p data-reveal className="mx-auto mt-6 max-w-[58ch] text-[15px] text-taupe-2">
          Built for RaftarXpress Logistics: 13 categories, 34 subcategories, 9 departments,
          25 versioned policy documents and 619 rules, 74 of them mandatory escalations that no
          model, reviewer or administrator can lower.
        </p>
      </div>
    </Section>
  )
}

/* ------------------------------------------------------------------ 4. Nine dimensions */

const SAMPLE = {
  ref: 'CN-482913',
  text: 'My parcel CN-482913 was marked delivered on 14 March but never arrived. The driver signed it himself. I have paid Rs. 5,000 COD and nobody at the Lahore hub picks up. If this is not sorted by Friday I will go to the ombudsman.',
}

const DIMENSIONS = [
  ['Category', 'LOST_SHIPMENT', 'ink'],
  ['Subcategory', 'MARKED_DELIVERED_NOT_RECEIVED', 'ink'],
  ['Department', 'LOGISTICS_OPS', 'ink'],
  ['Urgency', 'HIGH', 'warning'],
  ['Priority', 'P1', 'warning'],
  ['Sentiment', 'FRUSTRATED', 'neutral'],
  ['Escalation floor', 'COMPLIANCE_REVIEW', 'critical'],
  ['Eligibility', 'REFUND · REQUIRES_VERIFICATION', 'pencil'],
  ['Missing', 'Proof-of-delivery photo', 'neutral'],
] as const

export function Dimensions() {
  const root = useRef<HTMLDivElement>(null)
  useReveal(root)
  useGsap((ctx, el) => {
    const cards = el.querySelectorAll('[data-dim]')
    gsap.from(cards, {
      opacity: 0, y: 26, scale: 0.98, duration: 0.8, ease: 'expo.out', stagger: 0.07,
      scrollTrigger: { trigger: el, start: 'top 70%', once: true },
    })
    gsap.from(el.querySelector('[data-complaint]'), {
      opacity: 0, x: -20, duration: 1, ease: 'expo.out',
      scrollTrigger: { trigger: el, start: 'top 75%', once: true },
    })
  }, root)

  return (
    <Section>
      <div ref={root} className="grid gap-12 lg:grid-cols-[1fr_1.2fr] lg:gap-16">
        <div>
          <Eyebrow index="01" className="mb-6">A complaint is more than text</Eyebrow>
          <Display lines={['One paragraph.', 'Nine decisions.']} size="h1" italicLast />
          <p className="mt-6 max-w-[46ch] text-[15.5px] text-espresso-2">
            Each is made twice: once by the model, once by the rules. The customer only
            ever sees the version both agreed on, or the one the rules corrected.
          </p>
          <blockquote data-complaint className="pencil mt-8 rounded-[var(--radius-lg)] p-6">
            <p className="font-display italic text-[17px] leading-relaxed text-espresso-2">&ldquo;{SAMPLE.text}&rdquo;</p>
            <footer className="mt-4 flex items-center gap-3 text-[12px] text-taupe-2">
              <Mono>{SAMPLE.ref}</Mono> <span aria-hidden>·</span> <span>Web form</span> <span aria-hidden>·</span> <span>Rs. 5,000 COD</span>
            </footer>
          </blockquote>
        </div>
        <ul className="grid gap-3 self-center sm:grid-cols-2 lg:grid-cols-3">
          {DIMENSIONS.map(([label, value, tone]) => (
            <li key={label} data-dim>
              <Card tone="ivory" padding="sm" radius="md" className="flex h-full flex-col gap-2">
                <p className="eyebrow">{label}</p>
                <Badge tone={tone} className="w-fit max-w-full whitespace-normal [overflow-wrap:anywhere] text-[11.5px] leading-snug">{value}</Badge>
              </Card>
            </li>
          ))}
        </ul>
      </div>
    </Section>
  )
}

/* ------------------------------------------------------------------ 5. Understanding */

type Span = { text: string; kind?: 'ORDER_ID' | 'AMOUNT' | 'DATE' | 'LOCATION' | 'THREAT' }
const SPANS: Span[] = [
  { text: 'My parcel ' }, { text: 'CN-482913', kind: 'ORDER_ID' }, { text: ' was marked delivered on ' },
  { text: '14 March', kind: 'DATE' }, { text: ' but never arrived. The driver signed it himself. I have paid ' },
  { text: 'Rs. 5,000', kind: 'AMOUNT' }, { text: ' COD and nobody at the ' }, { text: 'Lahore hub', kind: 'LOCATION' },
  { text: ' picks up. If this is not sorted by Friday I will go to the ' }, { text: 'ombudsman', kind: 'THREAT' }, { text: '.' },
]
const SIGNALS = [
  ['delivery_confirmed_not_received', 'topic'],
  ['pod_disputed', 'evidence'],
  ['regulatory_body', 'cross-cutting'],
  ['has_order_ref', 'entity'],
  ['amount_present', 'entity'],
]

export function Understanding() {
  const root = useRef<HTMLDivElement>(null)
  useReveal(root)
  useGsap((ctx, el) => {
    const marks = el.querySelectorAll('[data-mark]')
    gsap.set(marks, { '--mark': 0 })
    ScrollTrigger.create({
      trigger: el, start: 'top 65%', once: true,
      onEnter: () => {
        gsap.to(marks, { '--mark': 1, duration: 0.7, ease: 'power3.out', stagger: 0.18 })
        gsap.from(el.querySelectorAll('[data-signal]'), { opacity: 0, x: -10, duration: 0.6, ease: 'power3.out', stagger: 0.1, delay: 0.6 })
      },
    })
  }, root)

  return (
    <Section dark>
      <div ref={root} className="grid gap-12 lg:grid-cols-[1.2fr_1fr]">
        <div>
          <Eyebrow index="02" className="mb-6">Complaint understanding</Eyebrow>
          <Display lines={['The engine reads', 'what the customer wrote.']} size="h1" />
          <p className="mt-6 max-w-[48ch] text-[15.5px] text-sand-2">
            Entities are found by pattern, not by the model: order references, amounts,
            dates, places and threats. Signals fire from a lexicon authored from policy text,
            never from the complaints themselves. Both pipelines see the same evidence.
          </p>
          <p className="mt-12 max-w-[58ch] font-display text-[clamp(19px,2vw,26px)] leading-[1.95] text-ink-on-dark">
            {SPANS.map((s, i) =>
              s.kind ? (
                <mark
                  key={i}
                  data-mark
                  data-kind={s.kind}
                  className="relative mx-[1px] rounded-[4px] bg-transparent px-1 text-ink-on-dark [background:linear-gradient(90deg,rgba(231,220,203,.22),rgba(231,220,203,.22))_left/calc(var(--mark)*100%)_100%_no-repeat] [box-shadow:inset_0_-1.5px_0_rgba(231,220,203,calc(var(--mark)*.9))]"
                >
                  {s.text}
                  <span className="absolute -top-[1.15em] left-0 eyebrow text-[8.5px] tracking-[0.12em] text-sand-2 opacity-[var(--mark)]">{s.kind}</span>
                </mark>
              ) : (
                <span key={i}>{s.text}</span>
              ),
            )}
          </p>
        </div>
        <div className="lg:pt-24">
          <p className="eyebrow mb-4 text-sand-2">Signals fired</p>
          <ul className="flex flex-col gap-2">
            {SIGNALS.map(([sig, kind]) => (
              <li key={sig} data-signal className="flex items-center justify-between rounded-[var(--radius-md)] border border-ink-on-dark/15 bg-ink-on-dark/5 px-4 py-3">
                <Mono className="text-[13px] text-ink-on-dark">{sig}</Mono>
                <span className="eyebrow text-[10px] text-sand-2">{kind}</span>
              </li>
            ))}
          </ul>
          <p className="mt-5 text-[13px] text-sand-2">
            Evidence escalates; it does not gate. A topic alone reaches the baseline rule.
            Evidence on top of it reaches the stricter one.
          </p>
        </div>
      </div>
    </Section>
  )
}

/* ------------------------------------------------------------------ 6. Pipeline */

const STAGES = [
  ['Intake', 'Validated, normalised, checked for injection and for duplicates of earlier complaints.'],
  ['Retrieval', 'Lexical, exact-reference and semantic search over the active policy versions only.'],
  ['Pipeline 1 · GenAI', 'Gemini proposes classification, priority, resolution steps and a response draft, citing chunks.'],
  ['Pipeline 2 · Rules', '619 deterministic rules run over the same text. No model call anywhere in this path.'],
  ['Comparison', 'Field by field. Agreement is scored; disagreement is resolved in favour of the rules.'],
  ['Hallucination checks', 'Every citation is resolved against the knowledge base; every claim against the cited text.'],
  ['Response guard', 'Unsupported promises, ceilings exceeded and lowered escalations are blocked before send.'],
  ['Resolution', 'A checklist of required steps, follow-ups with due dates, and an escalation note when needed.'],
]

export function Pipeline() {
  const root = useRef<HTMLDivElement>(null)
  useReveal(root)
  useGsap((ctx, el) => {
    const line = el.querySelector<SVGPathElement>("[data-rail]")
    if (line) {
      const len = line.getTotalLength()
      gsap.set(line, { strokeDasharray: len, strokeDashoffset: len })
      gsap.to(line, { strokeDashoffset: 0, ease: 'none', scrollTrigger: { trigger: el, start: 'top 60%', end: 'bottom 70%', scrub: 0.4 } })
    }
    el.querySelectorAll<HTMLElement>('[data-stage]').forEach((s) => {
      gsap.from(s, { opacity: 0, x: 18, duration: 0.8, ease: 'expo.out', scrollTrigger: { trigger: s, start: 'top 78%', once: true } })
    })
  }, root)

  return (
    <Section id="intelligence">
      <div ref={root} className="grid gap-12 lg:grid-cols-[0.8fr_1.2fr]">
        <div className="lg:sticky lg:top-28 lg:self-start">
          <Eyebrow index="03" className="mb-6">The pipeline</Eyebrow>
          <Display lines={['Eight stages.', 'One continuous line.']} size="h1" italicLast />
          <p className="mt-6 max-w-[42ch] text-[15.5px] text-espresso-2">
            The two pipelines never share a result until the comparison stage. If GenAI is
            unavailable, the rule engine completes the whole line on its own and the
            decision is marked degraded, not invented.
          </p>
        </div>
        <ol className="relative pl-10">
          {/* The rail scales to the list rather than running a fixed 4000
              units past it — an overflowing path drew a stray line straight
              down through every section below. */}
          <svg
            className="absolute left-[11px] top-3 h-[calc(100%-24px)] w-[2px]"
            viewBox="0 0 2 100"
            preserveAspectRatio="none"
            aria-hidden
          >
            <path data-rail d="M1 0 V 100" stroke="var(--color-espresso)" strokeWidth="2" fill="none" vectorEffect="non-scaling-stroke" />
          </svg>
          {STAGES.map(([title, body], i) => (
            <li key={title} data-stage className="relative mb-9 last:mb-0">
              <span className={cn('absolute -left-10 top-1.5 flex size-6 items-center justify-center rounded-full border-2 border-espresso bg-cream font-mono text-[10px]', i === 3 && 'bg-espresso text-ink-on-dark', i === 2 && 'pencil')}>{i + 1}</span>
              <h3 className="font-display text-h3 leading-none">{title}</h3>
              <p className="mt-2 max-w-[54ch] text-[14.5px] text-espresso-2">{body}</p>
            </li>
          ))}
        </ol>
      </div>
    </Section>
  )
}
