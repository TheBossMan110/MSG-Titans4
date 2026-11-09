'use client'

import { useEffect, useState, type FormEvent } from 'react'
import { Check } from 'lucide-react'
import catalogue from '@/lib/plans.json'
import { billing, errorMessage } from '@/lib/api'
import { cn } from '@/lib/utils'
import { Badge, Button, Eyebrow } from '@/components/ui/primitives'
import { Field, Input, Select, Textarea } from '@/components/ui/forms'
import { Card, Section } from '@/components/ui/surfaces'

type Cycle = 'monthly' | 'annual'
type Plan = (typeof catalogue.plans)[number]

const money = (value: number) => `${catalogue.currency} ${value.toLocaleString('en-PK')}`
const annualMonthly = (monthly: number) => Math.round((monthly * catalogue.annual_months_charged) / 12)

/** Only what the product does today. A claim here is a promise to a paying customer. */
const INCLUDED = [
  'AI reads every complaint, and your rules check every answer',
  'Mandatory escalation that nothing can lower',
  'Policy citations you can click through to the source paragraph',
  'Prompt-injection and manipulation defences',
  'Automatic routing to the right team and agent',
  'SLA clocks, a review queue and a full audit trail',
  'Customer portal, complaint tracking and the Nova chat assistant',
  'Agent, reviewer, manager and administrator dashboards',
  'Reports in Excel, PDF, CSV and JSON',
  'Your data kept separate from every other company',
]

const QUESTIONS: Array<[string, string]> = [
  ['What happens if we reach a limit?',
    'Your customers are never turned away. Past your monthly allowance, or after a trial ends, complaints are still accepted, routed and escalated by your rules. Only the AI analysis pauses until the next month or a plan change. Staff accounts are the one hard limit.'],
  ['How do we pay?',
    'We send an invoice and you pay by bank transfer. Prices are in Pakistani rupees and do not include any sales tax that applies.'],
  ['Do we need a card for the trial?',
    `No. The ${catalogue.trial_days}-day trial is free, and we set it up with you.`],
  ['What counts as an AI-analysed complaint?',
    'One complaint that a model read and analysed this calendar month. Re-reading it, drafting replies and chatting about it do not count again. If the AI could not answer, it does not count.'],
  ['Can we use WhatsApp or our own support mailbox?',
    'Not yet. Today complaints come through your web portal, the Nova chat and uploaded letters. WhatsApp is next on our roadmap, so tell us if it matters to you.'],
  ['Is the AI always right?',
    'No AI is, which is why your own rules have the last word on routing, urgency and escalation, and disagreements go to a person. You can see the evidence behind every decision.'],
]

export function PricingView() {
  const [cycle, setCycle] = useState<Cycle>('monthly')
  const [chosen, setChosen] = useState('growth')

  useEffect(() => {
    const wanted = new URLSearchParams(window.location.search).get('plan')
    if (wanted && catalogue.plans.some((p) => p.code === wanted)) setChosen(wanted)
  }, [])

  const choose = (code: string) => {
    setChosen(code)
    document.getElementById('request')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  return (
    <>
      <Section className="pt-[calc(var(--nav-h)+clamp(40px,6vw,88px))]">
        <div className="mx-auto max-w-[760px] text-center">
          <Eyebrow>Pricing</Eyebrow>
          <h1 className="display mt-4 text-h1 text-espresso">Pay for the complaints you handle.</h1>
          <p className="mx-auto mt-5 max-w-[56ch] text-[16px] leading-relaxed text-taupe-2">
            Every plan includes the AI and the rule engine that checks it. Starter costs less than a month of one
            support agent. Try any plan free for {catalogue.trial_days} days.
          </p>
          <div role="group" aria-label="Billing period" className="mt-8 inline-flex rounded-full border border-line bg-ivory p-1">
            {(['monthly', 'annual'] as const).map((c) => (
              <button key={c} type="button" aria-pressed={cycle === c} onClick={() => setCycle(c)}
                className={cn('rounded-full px-5 py-2 text-[14px] font-medium transition-colors', cycle === c ? 'bg-espresso text-ink-on-dark' : 'text-espresso-2 hover:text-espresso')}>
                {c === 'monthly' ? 'Monthly' : `Annual · ${12 - catalogue.annual_months_charged} months free`}
              </button>
            ))}
          </div>
        </div>

        <div className="mt-12 grid gap-5 md:grid-cols-2 xl:grid-cols-4">
          {catalogue.plans.map((plan) => <PlanCard key={plan.code} plan={plan} cycle={cycle} onChoose={() => choose(plan.code)} />)}
        </div>

        <div className="mt-16 grid gap-8 lg:grid-cols-[1fr_1.4fr]">
          <div>
            <Eyebrow>On every plan</Eyebrow>
            <h2 className="display mt-3 text-h3 text-espresso">The checking is not an add-on.</h2>
            <p className="mt-3 max-w-[42ch] text-[15px] leading-relaxed text-taupe-2">
              Plans differ in how many people use them and how many complaints the AI reads. Nothing that keeps a
              wrong answer away from your customer is held back for a higher tier.
            </p>
          </div>
          <ul className="grid gap-x-8 gap-y-3 sm:grid-cols-2">
            {INCLUDED.map((item) => (
              <li key={item} className="flex gap-2.5 text-[14.5px] leading-snug text-espresso-2">
                <Check size={16} className="mt-0.5 shrink-0 text-verified" aria-hidden />{item}
              </li>
            ))}
          </ul>
        </div>
      </Section>

      <Section className="!pt-0">
        <div className="grid gap-10 lg:grid-cols-2">
          <div>
            <Eyebrow>Questions</Eyebrow>
            <h2 className="display mt-3 text-h3 text-espresso">Before you ask</h2>
            <dl className="mt-6 flex flex-col divide-y divide-line-soft">
              {QUESTIONS.map(([q, a]) => (
                <div key={q} className="py-4">
                  <dt className="text-[15px] font-medium text-espresso">{q}</dt>
                  <dd className="mt-1.5 text-[14px] leading-relaxed text-taupe-2">{a}</dd>
                </div>
              ))}
            </dl>
          </div>
          <RequestForm chosen={chosen} cycle={cycle} onPlan={setChosen} onCycle={setCycle} />
        </div>
      </Section>
    </>
  )
}

function PlanCard({ plan, cycle, onChoose }: { plan: Plan; cycle: Cycle; onChoose: () => void }) {
  const price = plan.monthly_price
  return (
    <Card tone={plan.featured ? 'ink' : 'ivory'} radius="xl" className="flex flex-col">
      <div className="flex items-center justify-between gap-2">
        <h2 className={cn('font-display text-[24px] leading-tight', plan.featured ? 'text-ink-on-dark' : 'text-espresso')}>{plan.name}</h2>
        {plan.featured && <Badge tone="verified">Recommended</Badge>}
      </div>
      <p className={cn('mt-2 min-h-[64px] text-[14px] leading-snug', plan.featured ? 'text-sand-2' : 'text-taupe-2')}>{plan.tagline}</p>
      <div className="mt-4 min-h-[76px]">
        {price === null ? (
          <p className="font-display text-[30px] leading-tight">Let&apos;s talk</p>
        ) : (
          <>
            <p className="font-display text-[30px] leading-tight">{money(cycle === 'annual' ? annualMonthly(price) : price)}</p>
            <p className={cn('mt-1 text-[12.5px]', plan.featured ? 'text-sand-2' : 'text-taupe-2')}>
              per month{cycle === 'annual' ? `, billed ${money(price * catalogue.annual_months_charged)} a year` : ''}
            </p>
          </>
        )}
      </div>
      <ul className="mt-4 flex flex-1 flex-col gap-2 text-[14px]">
        <Line dark={plan.featured}>{plan.seats === null ? 'As many staff accounts as you need' : `Up to ${plan.seats} staff accounts`}</Line>
        <Line dark={plan.featured}>{plan.ai_complaints === null ? 'Volume agreed with you' : `${plan.ai_complaints.toLocaleString('en-PK')} AI-analysed complaints a month`}</Line>
        <Line dark={plan.featured}>Unlimited customers</Line>
        <Line dark={plan.featured}>{plan.support}</Line>
      </ul>
      <Button className="mt-6 w-full" variant={plan.featured ? 'onDark' : 'secondary'} onClick={onChoose}>
        {price === null ? 'Talk to us' : 'Start free trial'}
      </Button>
    </Card>
  )
}

function Line({ children, dark }: { children: string; dark: boolean }) {
  return (
    <li className={cn('flex gap-2 leading-snug', dark ? 'text-ink-on-dark/90' : 'text-espresso-2')}>
      <Check size={15} className={cn('mt-0.5 shrink-0', dark ? 'text-sand-2' : 'text-verified')} aria-hidden />{children}
    </li>
  )
}

function RequestForm({ chosen, cycle, onPlan, onCycle }: { chosen: string; cycle: Cycle; onPlan: (c: string) => void; onCycle: (c: Cycle) => void }) {
  const [form, setForm] = useState({ company_name: '', contact_name: '', email: '', phone: '', team_size: '', monthly_complaints: '', message: '', website: '' })
  const [touched, setTouched] = useState(false)
  const [sending, setSending] = useState(false)
  const [sent, setSent] = useState(false)
  const [problem, setProblem] = useState<string | null>(null)
  const set = (k: keyof typeof form, v: string) => setForm((f) => ({ ...f, [k]: v }))

  const errors = {
    company_name: form.company_name.trim().length < 2 ? 'Give your company name.' : null,
    contact_name: form.contact_name.trim().length < 2 ? 'Give your name.' : null,
    email: /\S+@\S+\.\S+/.test(form.email) ? null : 'Give a valid work email.',
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setTouched(true)
    setProblem(null)
    if (Object.values(errors).some(Boolean)) return
    setSending(true)
    try {
      await billing.request({
        company_name: form.company_name.trim(), contact_name: form.contact_name.trim(), email: form.email.trim(),
        phone: form.phone.trim() || null, plan_code: chosen, billing_cycle: cycle,
        team_size: form.team_size ? Number(form.team_size) : null,
        monthly_complaints: form.monthly_complaints ? Number(form.monthly_complaints) : null,
        message: form.message.trim() || null, website: form.website || null,
      })
      setSent(true)
    } catch (err) {
      setProblem(errorMessage(err))
    } finally {
      setSending(false)
    }
  }

  return (
    <Card id="request" radius="xl" padding="lg" className="scroll-mt-28 self-start">
      {sent ? (
        <div role="status">
          <Eyebrow>Thank you</Eyebrow>
          <h2 className="display mt-3 text-h3 text-espresso">We have your request.</h2>
          <p className="mt-3 text-[15px] leading-relaxed text-taupe-2">
            We will contact {form.email.trim()} to set up your workspace and your {catalogue.trial_days}-day trial.
          </p>
        </div>
      ) : (
        <form onSubmit={submit} noValidate className="flex flex-col gap-4">
          <div>
            <Eyebrow>Get started</Eyebrow>
            <h2 className="display mt-3 text-h3 text-espresso">Request your trial</h2>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Company" required error={touched ? errors.company_name : null}>
              {(id) => <Input id={id} autoComplete="organization" value={form.company_name} onChange={(e) => set('company_name', e.target.value)} />}
            </Field>
            <Field label="Your name" required error={touched ? errors.contact_name : null}>
              {(id) => <Input id={id} autoComplete="name" value={form.contact_name} onChange={(e) => set('contact_name', e.target.value)} />}
            </Field>
            <Field label="Work email" required error={touched ? errors.email : null}>
              {(id) => <Input id={id} type="email" autoComplete="email" value={form.email} onChange={(e) => set('email', e.target.value)} />}
            </Field>
            <Field label="Phone or WhatsApp">
              {(id) => <Input id={id} type="tel" autoComplete="tel" value={form.phone} onChange={(e) => set('phone', e.target.value)} />}
            </Field>
            <Field label="Plan">
              {(id) => (
                <Select id={id} value={chosen} onChange={(e) => onPlan(e.target.value)}>
                  {catalogue.plans.map((p) => <option key={p.code} value={p.code}>{p.name}</option>)}
                </Select>
              )}
            </Field>
            <Field label="Billing">
              {(id) => (
                <Select id={id} value={cycle} onChange={(e) => onCycle(e.target.value as Cycle)}>
                  <option value="monthly">Monthly</option>
                  <option value="annual">Annual</option>
                </Select>
              )}
            </Field>
            <Field label="Support staff">
              {(id) => <Input id={id} type="number" min={1} inputMode="numeric" value={form.team_size} onChange={(e) => set('team_size', e.target.value)} />}
            </Field>
            <Field label="Complaints a month">
              {(id) => <Input id={id} type="number" min={0} inputMode="numeric" value={form.monthly_complaints} onChange={(e) => set('monthly_complaints', e.target.value)} />}
            </Field>
          </div>
          <Field label="Anything we should know?">
            {(id) => <Textarea id={id} rows={3} maxLength={1000} value={form.message} onChange={(e) => set('message', e.target.value)} />}
          </Field>
          {/* Hidden from people; bots fill in every field they find. */}
          <div aria-hidden className="absolute left-[-9999px] top-auto size-px overflow-hidden">
            <label>Website<input tabIndex={-1} autoComplete="off" value={form.website} onChange={(e) => set('website', e.target.value)} /></label>
          </div>
          {problem && <p role="alert" className="rounded-[var(--radius-md)] border border-critical/30 bg-critical-dim px-3.5 py-2.5 text-[13.5px] text-espresso">{problem}</p>}
          <Button type="submit" loading={sending}>Request my trial</Button>
          <p className="text-[12.5px] text-taupe-2">No card needed. We only use these details to set up your account.</p>
        </form>
      )}
    </Card>
  )
}
