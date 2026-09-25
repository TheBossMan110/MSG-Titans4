'use client'

import { useRef, useState } from 'react'
import { useAuth } from '@/lib/auth-context'
import { admin, system, type S } from '@/lib/api'
import { useApi, useAction } from '@/lib/use-api'
import { useReveal } from '@/components/motion/hooks'
import { Badge, Button, Display, Eyebrow, Mono, escalationTone, priorityTone, urgencyTone } from '@/components/ui/primitives'
import { Card, PencilInk, Section } from '@/components/ui/surfaces'
import { Textarea } from '@/components/ui/forms'
import { Stat } from '@/components/ui/data'
import { cn } from '@/lib/utils'

/* ------------------------------------------------------------------ 11. Live demo */

const PRESETS: Array<{ label: string; text: string }> = [
  { label: 'Lost shipment', text: 'Parcel CN-482913 shows delivered on 14 March but I never received it. The rider signed on my behalf. I paid Rs. 5,000 cash on delivery. Nobody at the Lahore hub answers. I will complain to the ombudsman if this is not resolved by Friday.' },
  { label: 'Damaged with injury', text: 'The crate FWD-220118 arrived with the strapping cut and a corner split open. When my staff lifted it a metal edge cut his hand and he needed stitches. We need someone from your safety team to contact us today.' },
  { label: 'Billing dispute', text: 'Invoice INV-77021 charges me Rs. 3,400 for express delivery but I booked standard. This is the third month in a row you have overcharged and I already raised ticket CN-431900 for the same thing.' },
]

/**
 * A real complaint, processed live by the rule engine. This calls
 * POST /api/admin/rules/test, which needs a signed-in staff account, so
 * without a session the demo shows what it would run and asks for one.
 */
export function LiveDemo() {
  const root = useRef<HTMLDivElement>(null)
  useReveal(root)
  const { user } = useAuth()
  const [text, setText] = useState(PRESETS[0].text)
  const { run, pending, error } = useAction((description: string) => admin.testRules({ description, title: 'Landing page demo' }))
  const [result, setResult] = useState<S['RuleTestOut'] | null>(null)
  const canRun = user && user.role !== 'customer'

  const onRun = async () => {
    const r = await run(text)
    if (r) setResult(r)
  }

  return (
    <Section id="demo" className="bg-ivory">
      <div ref={root}>
        <div className="mb-10 grid gap-6 lg:grid-cols-2 lg:items-end">
          <div>
            <Eyebrow index="08" className="mb-6" data-reveal>Interactive demo</Eyebrow>
            <Display lines={['Type a complaint.', 'Watch the rules decide.']} size="h1" italicLast />
          </div>
          <p data-reveal className="max-w-[48ch] text-[15.5px] text-espresso-2 lg:justify-self-end">
            This runs Pipeline 2 alone: the deterministic engine, live, against the current
            ruleset. No model, no cache, no prepared answer. The latency you see is the
            latency it took.
          </p>
        </div>

        <div className="grid gap-6 lg:grid-cols-[1fr_1fr]">
          <Card data-reveal padding="lg">
            <div className="mb-4 flex flex-wrap gap-2">
              {PRESETS.map((p) => (
                <button key={p.label} onClick={() => { setText(p.text); setResult(null) }} className={cn('rounded-full border px-3 py-1 text-[12.5px] transition-colors', text === p.text ? 'border-espresso bg-espresso text-ink-on-dark' : 'border-line hover:border-taupe')}>{p.label}</button>
              ))}
            </div>
            <Textarea value={text} onChange={(e) => setText(e.target.value)} rows={7} aria-label="Complaint text" maxLength={4000} />
            <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
              <span className="text-[12.5px] text-taupe-2 tnum">{text.length} / 4000</span>
              {canRun ? (
                <Button onClick={onRun} loading={pending} disabled={!text.trim()}>Run through the rule engine</Button>
              ) : (
                <div className="flex items-center gap-3">
                  <span className="text-[12.5px] text-taupe-2">{user ? 'Staff accounts can run the engine.' : 'Sign in to run it live.'}</span>
                  {!user && <Button href="/login?next=/%23demo" size="sm">Sign in</Button>}
                </div>
              )}
            </div>
            {error && <p role="alert" className="mt-3 text-[13px] text-critical">{error}</p>}
          </Card>

          <Card data-reveal tone="cream" padding="lg" className="min-h-[320px]">
            {!result ? (
              <div className="flex h-full flex-col justify-center text-center">
                <p className="font-display text-h3 text-taupe">The verdict appears here.</p>
                <p className="mx-auto mt-2 max-w-[36ch] text-[13.5px] text-taupe-2">Category, department, urgency, priority, the escalation floor, every rule that matched and every signal that fired.</p>
              </div>
            ) : (
              <div className="flex flex-col gap-5">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone="ink">{result.category ?? 'UNMATCHED'}</Badge>
                  {result.subcategory && <Badge>{result.subcategory}</Badge>}
                  {result.department && <Badge tone="info">{result.department}</Badge>}
                  <Badge tone={urgencyTone(result.urgency)}>{result.urgency ?? '—'}</Badge>
                  <Badge tone={priorityTone(result.priority)}>{result.priority ?? '—'}</Badge>
                  <Badge tone={escalationTone(result.escalation_code)}>{result.escalation_code ?? 'NONE'}</Badge>
                </div>
                <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-[13px]">
                  <div><dt className="eyebrow text-[10px]">Escalation floor</dt><dd><Mono>{result.escalation_floor_code ?? 'NONE'}</Mono></dd></div>
                  <div><dt className="eyebrow text-[10px]">Latency</dt><dd><Mono>{result.latency_ms ?? '—'} ms</Mono></dd></div>
                  <div><dt className="eyebrow text-[10px]">Ruleset</dt><dd><Mono>{result.ruleset_version}</Mono></dd></div>
                  <div><dt className="eyebrow text-[10px]">Flags</dt><dd className="flex gap-1.5">{result.unmatched && <Badge tone="warning">unmatched</Badge>}{result.conflict_detected && <Badge tone="critical">conflict</Badge>}{result.follow_up_required && <Badge tone="info">follow-up</Badge>}{!result.unmatched && !result.conflict_detected && !result.follow_up_required && '—'}</dd></div>
                </dl>
                <div>
                  <p className="eyebrow mb-2 text-[10px]">Matched rules ({result.matched_rules?.length ?? 0})</p>
                  <div className="flex flex-wrap gap-1.5">{(result.matched_rules ?? []).slice(0, 14).map((r) => <Badge key={r} tone={result.mandatory_escalation_refs?.includes(r) ? 'critical' : 'neutral'}><Mono>{r}</Mono></Badge>)}{(result.matched_rules?.length ?? 0) > 14 && <span className="text-[12px] text-taupe-2">+{result.matched_rules!.length - 14}</span>}</div>
                </div>
                <div>
                  <p className="eyebrow mb-2 text-[10px]">Signals fired ({result.signals_fired?.length ?? 0})</p>
                  <p className="font-mono text-[12px] leading-relaxed text-espresso-2">{(result.signals_fired ?? []).join('  ') || '—'}</p>
                </div>
                {(result.required_actions?.length ?? 0) > 0 && (
                  <div>
                    <p className="eyebrow mb-2 text-[10px]">Required actions</p>
                    <ul className="list-disc pl-5 text-[13px] text-espresso-2">{result.required_actions!.slice(0, 5).map((a) => <li key={a}>{a}</li>)}</ul>
                  </div>
                )}
              </div>
            )}
          </Card>
        </div>
      </div>
    </Section>
  )
}

/* ------------------------------------------------------------------ 12. Analytics (live health) */

export function Analytics() {
  const root = useRef<HTMLDivElement>(null)
  useReveal(root)
  const health = useApi(() => system.health())
  const h = health.data

  return (
    <Section id="analytics" dark>
      <div ref={root}>
        <div className="mb-12 grid gap-6 lg:grid-cols-2 lg:items-end">
          <div>
            <Eyebrow index="09" className="mb-6" data-reveal>Analytics</Eyebrow>
            <Display lines={['Figures with', 'their denominators.']} size="h1" italicLast />
          </div>
          <p data-reveal className="max-w-[48ch] text-[15.5px] text-sand-2 lg:justify-self-end">
            Every percentage in the product is shown with the count it came from. Where
            there is no denominator, the figure reads <em>not measured</em>. A metric that
            cannot be wrong is not a metric. The three below are read live from the server.
          </p>
        </div>
        <div className="grid gap-8 border-t border-ink-on-dark/15 pt-10 sm:grid-cols-3">
          <div data-reveal className="[&_.eyebrow]:text-sand-2 [&_span]:!text-ink-on-dark">
            <Stat label="Policy documents active" value={h ? h.knowledge_base_documents : health.error ? null : undefined} size="lg" evidence={h ? `knowledge base ${h.version}` : health.error ? 'server unreachable' : 'reading…'} />
          </div>
          <div data-reveal className="[&_.eyebrow]:text-sand-2 [&_span]:!text-ink-on-dark">
            <Stat label="Rules active" value={h ? h.active_rules : health.error ? null : undefined} size="lg" evidence={h ? `${h.environment} · ${h.database}` : health.error ? 'server unreachable' : 'reading…'} />
          </div>
          <div data-reveal className="[&_.eyebrow]:text-sand-2 [&_span]:!text-ink-on-dark">
            <Stat label="GenAI provider" value={h ? (h.llm_configured ? h.llm_primary : 'degraded') : health.error ? null : undefined} size="lg" evidence={h ? (h.llm_configured ? 'rules still decide alone if it fails' : 'rule engine carrying every decision') : health.error ? 'server unreachable' : 'reading…'} />
          </div>
        </div>
      </div>
    </Section>
  )
}

/* ------------------------------------------------------------------ 13. Human review */

export function HumanReview() {
  const root = useRef<HTMLDivElement>(null)
  useReveal(root)
  return (
    <Section>
      <div ref={root} className="grid gap-12 lg:grid-cols-[1fr_1.2fr]">
        <div>
          <Eyebrow index="10" className="mb-6" data-reveal>Human review</Eyebrow>
          <Display lines={['People can overrule', 'the model.', 'Nobody overrules', 'the floor.']} size="h2" />
          <p data-reveal className="mt-6 max-w-[46ch] text-[15.5px] text-espresso-2">
            Reviewers claim a complaint, see both opinions and the reasons it was queued,
            and can reclassify, reassign, escalate, regenerate or approve. Every action is
            an audit row with before and after. One action is refused: lowering an
            escalation beneath what a mandatory rule set.
          </p>
        </div>
        <div data-reveal className="flex flex-col gap-4">
          <PencilInk
            pencilLabel="Reviewer attempts"
            inkLabel="The API answers"
            pencil={<>Set escalation to <Mono className="not-italic">NONE</Mono> on CN-482913 &mdash; &ldquo;customer has calmed down&rdquo;</>}
            ink={<><Badge tone="critical" className="mb-2">422 · refused</Badge><br />Escalation floor is COMPLIANCE_REVIEW, set by ESC-0031 (regulatory body named). Floors may be raised, never lowered.</>}
          />
          <div className="rounded-[var(--radius-lg)] border border-line bg-ivory p-5">
            <p className="eyebrow mb-3">What a reviewer can do</p>
            <div className="flex flex-wrap gap-1.5">
              {['APPROVE', 'REJECT', 'MODIFY', 'RECLASSIFY', 'REASSIGN', 'ESCALATE', 'REGENERATE', 'COMMENT', 'OVERRIDE'].map((a) => <Badge key={a}>{a}</Badge>)}
            </div>
          </div>
        </div>
      </div>
    </Section>
  )
}

/* ------------------------------------------------------------------ 14. Complete workflow */

const CHAIN = ['Submit', 'Analyse', 'Verify', 'Review', 'Resolve', 'Follow up', 'Audit']

export function Workflow() {
  const root = useRef<HTMLDivElement>(null)
  useReveal(root, { stagger: 0.06 })
  return (
    <Section className="!py-[clamp(56px,7vw,110px)] border-y border-line">
      <div ref={root}>
        <p className="eyebrow mb-8 text-center" data-reveal>The complete workflow</p>
        <ol className="flex flex-wrap items-center justify-center gap-x-3 gap-y-4">
          {CHAIN.map((step, i) => (
            <li key={step} data-reveal className="flex items-center gap-3">
              <span className="font-display text-[clamp(22px,3vw,40px)] text-espresso">{step}</span>
              {i < CHAIN.length - 1 && <span aria-hidden className="h-px w-8 bg-taupe/60 sm:w-12" />}
            </li>
          ))}
        </ol>
        <p data-reveal className="mx-auto mt-8 max-w-[62ch] text-center text-[14px] text-taupe-2">
          Every step is an endpoint. Every endpoint writes to the audit trail. The trail is a page in this product, not a promise in a slide.
        </p>
      </div>
    </Section>
  )
}

/* ------------------------------------------------------------------ 15. Final CTA */

export function FinalCTA() {
  const root = useRef<HTMLDivElement>(null)
  useReveal(root)
  return (
    <Section dark className="!pb-[clamp(72px,9vw,140px)]">
      <div ref={root} className="mx-auto max-w-[880px] text-center">
        <Display lines={['Open the workspace.', 'Bring your own complaint.']} size="h1" italicLast className="text-ink-on-dark" />
        <p data-reveal className="mx-auto mt-6 max-w-[52ch] text-[15.5px] text-sand-2">
          Sign in as an agent, a reviewer, a manager or an evaluator. Change a rule and
          re-run. Activate a policy version and watch the citations go stale. Try to lower
          the floor.
        </p>
        <div data-reveal className="mt-9 flex flex-wrap justify-center gap-3">
          <Button href="/login" size="lg" variant="secondary">Sign in</Button>
          <Button href="/dashboard/rules/sandbox" size="lg" className="bg-ink-on-dark text-espresso hover:bg-white">Rule sandbox</Button>
        </div>
      </div>
    </Section>
  )
}
