'use client'

import { useRef } from 'react'
import { prefersReducedMotion } from '@/lib/motion-pref'
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import { useGsap, useReveal } from '@/components/motion/hooks'
import { AiBadge, Display, Eyebrow, Mono, RuleBadge } from '@/components/ui/primitives'
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

// What each decision reads as, not the code it is stored under: a visitor
// should not have to parse MARKED_DELIVERED_NOT_RECEIVED to follow the point.
const DIMENSIONS = [
  ['Category', 'Lost shipment', 'ink'],
  ['Subcategory', 'Marked delivered, not received', 'ink'],
  ['Department', 'Delivery & Logistics Ops', 'ink'],
  ['Urgency', 'High', 'warning'],
  ['Priority', 'P1 · high', 'warning'],
  ['Sentiment', 'Frustrated', 'neutral'],
  ['Escalation floor', 'Compliance review', 'critical'],
  ['Eligibility', 'Refund, once verified', 'ai'],
  ['Missing', 'Proof-of-delivery photo', 'neutral'],
] as const

const DOT = {
  ink: 'bg-espresso', warning: 'bg-warning-glow', neutral: 'bg-taupe', critical: 'bg-alert', ai: 'bg-ai',
} as const

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
        <ul className="grid grid-cols-2 gap-3 self-center sm:grid-cols-3">
          {DIMENSIONS.map(([label, value, tone], i) => (
            <li key={label} data-dim>
              <Card tone="ivory" padding="sm" radius="md" className="flex h-full min-h-[104px] flex-col justify-between gap-3">
                <p className="eyebrow flex items-center justify-between gap-2">
                  <span>{label}</span>
                  <span className="font-mono text-[10px] tnum text-taupe/70">{String(i + 1).padStart(2, '0')}</span>
                </p>
                <p className="flex items-start gap-2 text-[15px] font-medium leading-snug text-espresso">
                  <span aria-hidden className={cn('mt-[7px] size-2 shrink-0 rounded-full', DOT[tone])} />
                  <span className="min-w-0">{value}</span>
                </p>
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

// The complaint workflow, stage for stage as the project defines it: four
// ways in, one validation, the knowledge base and the rule matrix, then two
// pipelines side by side until the comparison engine decides.
type Stage = { title: string; body: string; kind?: 'ai' | 'rule'; chips?: string[]; fork?: boolean }
const STAGES: Stage[] = [
  { title: 'Customer complaint inputs', body: 'Four ways in, one register. Every channel is treated the same from here on.', chips: ['Web form', 'Email', 'Chat', 'Uploaded complaint'] },
  { title: 'Submission & validation', body: 'Empty, too short, duplicate or invalid-reference complaints are caught; text is normalised and scanned for injection.' },
  { title: 'Complaint context + knowledge base', body: 'Only active policy versions are searched, and every passage keeps its document, section and version.', chips: ['Policies', 'SOPs', 'Routing rules', 'FAQs', 'Escalation rules'] },
  { title: 'Complaint resolution rule matrix', body: 'The approved handling logic, written as data: category, department, urgency, priority, policy, escalation, required and prohibited actions.', kind: 'rule' },
  { title: 'Two pipelines, side by side', body: 'They never share a result until the comparison engine.', fork: true },
  { title: 'Comparison engine', body: 'Field by field. Agreement is scored; where they differ, the rules win and the reason is kept.' },
  { title: 'Verification decision', body: 'Agreement verifies. A critical disagreement, a missing policy or an unclear escalation goes to a person.', chips: ['Verified', 'Manual review'] },
  { title: 'Final complaint resolution', body: 'Only what the rules allow reaches the customer, checked for unsupported promises first.', chips: ['Response', 'Resolution', 'Escalation', 'Follow-up'] },
  { title: 'Dashboard & reports', body: 'Admin, agent and customer dashboards, trends, and reports exportable as CSV, PDF and Excel.' },
]

const PIPELINE_1 = ['Issue classification', 'Sentiment', 'Urgency', 'Department', 'Resolution steps', 'Customer response', 'Escalation notes', 'Follow-up']
const PIPELINE_2 = ['Category check', 'Department check', 'Priority check', 'Policy check', 'Escalation check', 'Resolution rules', 'Follow-up rules', 'Source validation']

// Node geometry, shared by the markup and the scroll maths.
const NODE = 32

/**
 * One rail from the first node's centre to the last, filled as the reader
 * scrolls; each node fills when the line reaches it. The rail is a plain
 * element scaled on Y -- an SVG dash pattern measured in viewBox units drew
 * the "one continuous line" as broken segments once the stroke was scaled.
 */
export function Pipeline() {
  const root = useRef<HTMLDivElement>(null)
  useReveal(root)
  useGsap((ctx, el) => {
    const list = el.querySelector<HTMLElement>('[data-stages]')
    const track = el.querySelector<HTMLElement>('[data-track]')
    const fill = el.querySelector<HTMLElement>('[data-rail]')
    const items = Array.from(el.querySelectorAll<HTMLElement>('[data-stage]'))
    const nodes = items.map((li) => li.querySelector<HTMLElement>('[data-node]')!)
    if (!list || !track || !fill || !items.length) return

    // Where each node sits along the rail, as a fraction of its length.
    let marks: number[] = []
    const measure = () => {
      const first = items[0].offsetTop + NODE / 2
      const last = items[items.length - 1].offsetTop + NODE / 2
      const length = Math.max(1, last - first)
      for (const bar of [track, fill]) {
        bar.style.top = `${first}px`
        bar.style.height = `${length}px`
      }
      marks = items.map((li) => (li.offsetTop + NODE / 2 - first) / length)
    }
    const paint = (progress: number) => {
      nodes.forEach((n, i) => { n.dataset.on = String(progress >= marks[i] - 0.001) })
    }
    measure()

    if (prefersReducedMotion()) {
      gsap.set(fill, { scaleY: 1 })
      paint(1)
      return
    }
    gsap.set(fill, { scaleY: 0, transformOrigin: 'top center' })
    paint(0)
    ScrollTrigger.create({
      trigger: list,
      start: 'top 62%',
      end: 'bottom 62%',
      scrub: 0.35,
      invalidateOnRefresh: true,
      onRefresh: () => measure(),
      onUpdate: (self) => {
        gsap.set(fill, { scaleY: self.progress })
        paint(self.progress)
      },
    })
    items.forEach((li) => {
      gsap.from(li.querySelector('[data-stage-body]'), {
        opacity: 0, x: 18, duration: 0.8, ease: 'expo.out',
        scrollTrigger: { trigger: li, start: 'top 80%', once: true },
      })
    })
  }, root)

  return (
    <Section id="intelligence">
      <div ref={root} className="grid gap-12 lg:grid-cols-[0.95fr_1.05fr]">
        <div className="lg:sticky lg:top-28 lg:self-start">
          <Eyebrow index="03" className="mb-6">The workflow</Eyebrow>
          <Display lines={['Nine stages.', 'Two pipelines.']} size="h1" italicLast />
          <p className="mt-6 max-w-[42ch] text-[15.5px] text-espresso-2">
            A complaint arrives by form, email, chat or file. Python and GenAI read it; Python
            alone checks it against the rule matrix. The two never share a result until the
            comparison engine. If GenAI is unavailable, the rules complete the whole line on
            their own and the decision is marked degraded, not invented.
          </p>
        </div>
        <ol data-stages className="relative">
          <span aria-hidden data-track className="absolute left-[15px] top-4 bottom-4 w-[2px] rounded-full bg-line" />
          <span aria-hidden data-rail className="absolute left-[15px] top-4 bottom-4 w-[2px] rounded-full bg-espresso" />
          {STAGES.map(({ title, body, kind, chips, fork }, i) => (
            <li key={title} data-stage className="relative grid grid-cols-[32px_1fr] gap-x-5 pb-10 last:pb-0">
              <span
                data-node
                data-on="false"
                className="relative z-[1] flex size-8 items-center justify-center rounded-full border-2 border-line bg-ivory font-mono text-[11px] tnum text-taupe transition-[background-color,border-color,color] duration-300 data-[on=true]:border-espresso data-[on=true]:bg-espresso data-[on=true]:text-ink-on-dark"
              >
                {String(i + 1).padStart(2, '0')}
              </span>
              <div data-stage-body className="min-w-0 pt-0.5">
                <h3 className="flex flex-wrap items-center gap-x-3 gap-y-1 font-display text-h3 leading-tight">
                  {title}
                  {kind === 'ai' && <AiBadge>AI</AiBadge>}
                  {kind === 'rule' && <RuleBadge>rules</RuleBadge>}
                </h3>
                <p className="mt-2 max-w-[54ch] text-[14.5px] leading-relaxed text-espresso-2">{body}</p>
                {chips && (
                  <ul className="mt-3 flex flex-wrap gap-1.5" aria-label={`${title}: parts`}>
                    {chips.map((c) => <li key={c} className="rounded-full border border-line-soft bg-white/70 px-2.5 py-1 text-[12.5px] text-espresso-2">{c}</li>)}
                  </ul>
                )}
                {fork && (
                  <div className="mt-4 grid gap-3 sm:grid-cols-2">
                    <PipelineCard tone="ai" title="Pipeline 1" subtitle="Python + GenAI" items={PIPELINE_1} />
                    <PipelineCard tone="rule" title="Pipeline 2" subtitle="Python validation" items={PIPELINE_2} />
                  </div>
                )}
              </div>
            </li>
          ))}
        </ol>
      </div>
    </Section>
  )
}

function PipelineCard({ tone, title, subtitle, items }: { tone: 'ai' | 'rule'; title: string; subtitle: string; items: string[] }) {
  return (
    <div className={cn('rounded-2xl border p-4', tone === 'ai' ? 'border-ai-line bg-ai-soft/60' : 'border-rule-line bg-rule-soft/60')}>
      <p className={cn('font-display text-[19px] leading-tight', tone === 'ai' ? 'text-ai' : 'text-rule')}>{title}</p>
      <p className={cn('eyebrow mt-0.5 text-[10px]', tone === 'ai' ? 'text-ai' : 'text-rule')}>{subtitle}</p>
      <ul className="mt-3 space-y-1.5">
        {items.map((item) => (
          <li key={item} className="flex items-center gap-2 text-[13.5px] text-espresso-2">
            <span aria-hidden className={cn('size-1.5 shrink-0 rounded-full', tone === 'ai' ? 'bg-ai' : 'bg-rule')} />
            {item}
          </li>
        ))}
      </ul>
    </div>
  )
}
