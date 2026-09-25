'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import {
  AlertTriangle, ArrowRight, Calendar, CheckCircle2, CreditCard, Hash, Lightbulb, Mail,
  Package, Phone, Receipt, ScanSearch, ShieldCheck, Sparkles, Wand2,
} from 'lucide-react'
import { AppShell } from '@/components/layout/app-shell'
import { useAuth } from '@/lib/auth-context'
import { complaints, errorMessage, type S } from '@/lib/api'
import {
  AiBadge, Badge, Button, Mono, Pulse, RuleBadge, humanise, escalationTone,
  priorityTone, statusTone, urgencyTone, verificationTone,
} from '@/components/ui/primitives'
import { Card } from '@/components/ui/surfaces'
import { Checkbox, FloatInput, FloatTextarea } from '@/components/ui/forms'
import { ErrorState } from '@/components/ui/feedback'
import { MilestoneTimeline, TeamCard } from '@/components/app/customer'
import { cn } from '@/lib/utils'

const CHANNELS = ['WEB', 'EMAIL', 'PHONE', 'CHAT', 'SOCIAL', 'IN_PERSON']
const RESOLUTIONS = ['Refund', 'Replacement', 'Redelivery', 'Repair', 'An explanation', 'Compensation']
const MAX_DESC = 10_000
const BLANK: S['ComplaintCreate'] = { title: '', description: '', channel: 'WEB', currency: 'PKR' }

export default function NewComplaintPage() {
  return (
    <AppShell eyebrow="Submit a complaint" wide>
      <Intake />
    </AppShell>
  )
}

function Intake() {
  const { user } = useAuth()
  const staff = !!user && user.role !== 'customer'
  const [form, setForm] = useState<S['ComplaintCreate']>(BLANK)
  const [analyse, setAnalyse] = useState(true)
  const [phase, setPhase] = useState<'form' | 'running' | 'done'>('form')
  const [result, setResult] = useState<S['IntakeResponse'] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const set = <K extends keyof S['ComplaintCreate']>(k: K, v: S['ComplaintCreate'][K]) => setForm((f) => ({ ...f, [k]: v }))
  const preview = usePreview(form.title, form.description)

  const words = form.description.trim() ? form.description.trim().split(/\s+/).length : 0
  const ready = form.title.trim().length >= 3 && form.description.trim().length >= 10

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!ready) return
    setError(null)
    setPhase('running')
    const body: S['ComplaintCreate'] = { ...form }
    for (const k of Object.keys(body) as Array<keyof S['ComplaintCreate']>) if (body[k] === '' || body[k] === undefined) delete body[k]
    try {
      const r = await complaints.create(body, staff ? analyse : true)
      setResult(r)
      setPhase('done')
    } catch (err) {
      setError(errorMessage(err))
      setPhase('form')
    }
  }

  if (phase === 'running') return <AnalysisProgress genai={staff ? analyse : true} />
  if (phase === 'done' && result) return <Result result={result} staff={staff} onAnother={() => { setForm(BLANK); setResult(null); setPhase('form') }} />

  const suggestedRef = !form.order_ref ? preview.data?.entities?.find((e) => e.type === 'ORDER_ID' || e.type === 'TRACKING_ID')?.value : undefined

  return (
    <div className="grid gap-7 xl:grid-cols-[1.3fr_1fr]">
      <form onSubmit={submit} className="flex flex-col gap-6" noValidate>
        <header className="animate-rise">
          <p className="eyebrow mb-2">Intake</p>
          <h1 className="display text-h2">Tell us what happened.</h1>
          <p className="mt-3 max-w-[60ch] text-[15px] leading-relaxed text-taupe">
            Write it the way you would say it. References, amounts and dates are picked up as you
            type — the panel on the right shows exactly what the system will read.
          </p>
        </header>

        <Card tone="glass" padding="lg" radius="xl" className="flex flex-col gap-5">
          <FloatInput label="Title — one line, in your words" value={form.title} onChange={(e) => set('title', e.target.value)} required maxLength={200} autoFocus />
          <FloatTextarea
            label="What happened"
            value={form.description}
            onChange={(e) => set('description', e.target.value)}
            required
            maxLength={MAX_DESC}
            rows={8}
            footer={
              <div className="flex items-center gap-3 px-1">
                <div className="h-1 flex-1 overflow-hidden rounded-full bg-sand/80">
                  <div
                    className={cn('h-full rounded-full transition-[width] duration-300', words < 12 ? 'bg-warning-glow' : 'bg-gradient-to-r from-ai to-rule-2')}
                    style={{ width: `${Math.min(100, (words / 60) * 100)}%` }}
                  />
                </div>
                <span className="text-[12px] tnum text-taupe">{words} words · {form.description.length.toLocaleString()} / {MAX_DESC.toLocaleString()}</span>
              </div>
            }
          />

          {suggestedRef && (
            <button
              type="button"
              onClick={() => set('order_ref', suggestedRef)}
              className="flex animate-rise items-center gap-3 rounded-2xl border border-ai-line bg-ai-soft/70 px-4 py-3 text-left transition-colors hover:bg-ai-soft"
            >
              <Wand2 size={16} className="shrink-0 text-ai" aria-hidden />
              <span className="flex-1 text-[14px] text-espresso-2">We spotted <Mono className="font-medium text-ai">{suggestedRef}</Mono> in your text. Use it as the consignment number?</span>
              <span className="text-[13px] font-medium text-ai">Use it</span>
            </button>
          )}

          <div className="grid gap-4 sm:grid-cols-2">
            <FloatInput label="Consignment / order reference" value={form.order_ref ?? ''} onChange={(e) => set('order_ref', e.target.value || null)} className="[&_input]:font-mono" />
            <FloatInput label="Invoice / transaction reference" value={form.transaction_ref ?? ''} onChange={(e) => set('transaction_ref', e.target.value || null)} className="[&_input]:font-mono" />
            <FloatInput label="Product or service" value={form.product ?? ''} onChange={(e) => set('product', e.target.value || null)} />
            <div className="grid grid-cols-[1fr_96px] gap-2">
              <FloatInput label="Amount involved" type="number" min={0} step="0.01" value={form.amount ?? ''} onChange={(e) => set('amount', e.target.value === '' ? null : Number(e.target.value))} />
              <FloatInput label="Currency" value={form.currency ?? ''} onChange={(e) => set('currency', e.target.value.toUpperCase() || null)} maxLength={3} />
            </div>
          </div>

          <div>
            <p className="mb-2 text-[13px] font-medium text-espresso-2">What would put this right?</p>
            <div className="flex flex-wrap gap-2">
              {RESOLUTIONS.map((r) => {
                const on = form.requested_resolution === r
                return (
                  <button
                    key={r}
                    type="button"
                    onClick={() => set('requested_resolution', on ? null : r)}
                    aria-pressed={on}
                    className={cn(
                      'rounded-full border px-3.5 py-1.5 text-[13.5px] transition-[background-color,border-color,color,transform] duration-200 active:scale-95',
                      on ? 'border-espresso bg-espresso text-ink-on-dark' : 'border-line bg-white/70 text-espresso-2 hover:border-taupe',
                    )}
                  >
                    {r}
                  </button>
                )
              })}
            </div>
          </div>

          <div>
            <p className="mb-2 text-[13px] font-medium text-espresso-2">How did this reach us?</p>
            <div className="flex flex-wrap gap-2">
              {CHANNELS.map((c) => (
                <button
                  key={c}
                  type="button"
                  onClick={() => set('channel', c)}
                  aria-pressed={form.channel === c}
                  className={cn(
                    'rounded-full border px-3 py-1 text-[13px] transition-colors duration-200',
                    form.channel === c ? 'border-ai bg-ai-soft text-ai' : 'border-line-soft bg-white/60 text-taupe hover:text-espresso',
                  )}
                >
                  {humanise(c)}
                </button>
              ))}
            </div>
          </div>

          {staff && (
            <div className="grid gap-4 border-t border-line-soft pt-5 sm:grid-cols-2">
              <FloatInput label="Customer email (on their behalf)" type="email" value={form.customer_email ?? ''} onChange={(e) => set('customer_email', e.target.value || null)} />
              <FloatInput label="Customer name" value={form.customer_name ?? ''} onChange={(e) => set('customer_name', e.target.value || null)} />
              <FloatInput label="Dataset tag (benchmark imports only)" value={form.dataset_tag ?? ''} onChange={(e) => set('dataset_tag', e.target.value || null)} className="[&_input]:font-mono" />
              <div className="flex items-center px-1"><Checkbox label="Run both pipelines now" checked={analyse} onChange={(e) => setAnalyse(e.target.checked)} /></div>
            </div>
          )}
        </Card>

        {error && <ErrorState title="Not accepted" message={error} />}
        <div className="flex flex-wrap items-center gap-4">
          <Button type="submit" size="lg" disabled={!ready} arrow>Submit complaint</Button>
          <span className="text-[13px] text-taupe">
            {ready ? 'Takes about 15–30 seconds: the AI reads it, then the rules check every decision.' : 'A title and a sentence or two are enough to start.'}
          </span>
        </div>
      </form>

      <aside className="xl:sticky xl:top-24 xl:self-start">
        <LivePreview description={form.description} state={preview} />
      </aside>
    </div>
  )
}

/* ------------------------------------------------------------------ live pre-check */

type PreviewState = { data: S['PreviewOut'] | null; loading: boolean; error: string | null }

/** Debounced so it runs on a pause in typing, not every keystroke; stale replies are dropped. */
function usePreview(title: string, description: string): PreviewState {
  const [state, setState] = useState<PreviewState>({ data: null, loading: false, error: null })
  const seq = useRef(0)
  useEffect(() => {
    const text = `${title} ${description}`.trim()
    if (text.split(/\s+/).length < 3) { setState({ data: null, loading: false, error: null }); return }
    const id = ++seq.current
    setState((s) => ({ ...s, loading: true }))
    const t = window.setTimeout(async () => {
      try {
        const data = await complaints.preview(title, description)
        if (id === seq.current) setState({ data, loading: false, error: null })
      } catch (e) {
        if (id === seq.current) setState((s) => ({ ...s, loading: false, error: errorMessage(e) }))
      }
    }, 550)
    return () => clearTimeout(t)
  }, [title, description])
  return state
}

const ENTITY_ICON: Record<string, typeof Hash> = {
  ORDER_ID: Package, TRACKING_ID: Package, AMOUNT: CreditCard, DATE: Calendar,
  EMAIL: Mail, PHONE: Phone, INVOICE_ID: Receipt, TRANSACTION_ID: Receipt,
}

function LivePreview({ description, state }: { description: string; state: PreviewState }) {
  const { data, loading, error } = state
  const highlighted = useMemo(() => highlight(description, data?.entities ?? []), [description, data])

  return (
    <Card tone="glass" padding="lg" radius="xl" className="overflow-hidden">
      <span aria-hidden className="pointer-events-none absolute -right-20 -top-20 size-56 rounded-full bg-ai-2/20 blur-3xl" />
      <div className="relative">
        <div className="mb-5 flex items-center justify-between gap-3">
          <p className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-ai">
            <ScanSearch size={14} aria-hidden /> Live pre-check
          </p>
          <span className="flex items-center gap-2 text-[12px] text-taupe">
            {loading ? <><Pulse tone="ai" /> reading…</> : data ? 'up to date' : 'waiting for text'}
          </span>
        </div>

        {!data && !loading ? (
          <div className="rounded-2xl border border-dashed border-ai-line bg-white/50 px-5 py-10 text-center">
            <Sparkles size={22} className="mx-auto mb-3 text-ai" aria-hidden />
            <p className="font-display text-[19px] text-espresso">Start typing on the left</p>
            <p className="mx-auto mt-1.5 max-w-[34ch] text-[13.5px] text-taupe">Consignment numbers, amounts and dates light up here as the system recognises them.</p>
          </div>
        ) : (
          <div className="flex flex-col gap-5">
            {data?.injection_suspected && (
              <div className="flex gap-3 rounded-2xl border border-critical/30 bg-critical-dim/70 p-3.5 text-[13.5px] text-critical">
                <AlertTriangle size={16} className="mt-0.5 shrink-0" aria-hidden />
                <span>Part of this reads like instructions to our system. It will be kept as part of your complaint, not followed.</span>
              </div>
            )}

            <div>
              <p className="eyebrow mb-2">Recognised</p>
              {data?.entities?.length ? (
                <div className="flex flex-wrap gap-1.5">
                  {(data.entities ?? []).map((e, i) => {
                    const Icon = ENTITY_ICON[e.type] ?? Hash
                    return (
                      <span key={`${e.type}-${e.value}-${i}`} className="inline-flex animate-rise items-center gap-1.5 rounded-full border border-ai-line bg-white px-2.5 py-1 text-[12.5px] shadow-[0_1px_2px_rgba(79,63,209,0.08)]">
                        <Icon size={12} className="text-ai" aria-hidden />
                        <span className="text-taupe">{humanise(e.type)}</span>
                        <span className="font-mono font-medium text-espresso">{e.value}</span>
                      </span>
                    )
                  })}
                </div>
              ) : (
                <p className="text-[13.5px] text-taupe">Nothing yet — try adding a consignment number or an amount.</p>
              )}
            </div>

            {description.trim() && (
              <div>
                <p className="eyebrow mb-2">Your text, as the system reads it</p>
                <p className="max-h-44 overflow-y-auto whitespace-pre-wrap rounded-2xl border border-line-soft bg-white/70 p-4 text-[14px] leading-[1.9] text-espresso-2" data-lenis-prevent>
                  {highlighted}
                </p>
              </div>
            )}

            {data?.likely_category && (
              <div className="flex items-center justify-between gap-3 rounded-2xl border border-rule-line bg-rule-soft/70 px-4 py-3">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-rule">Likely category</p>
                  <p className="font-display text-[19px] text-rule">{data.likely_category.name}</p>
                </div>
                <RuleBadge>rule engine</RuleBadge>
              </div>
            )}

            {(data?.hints?.length ?? 0) > 0 && (
              <ul className="flex flex-col gap-2">
                {(data?.hints ?? []).map((h) => (
                  <li key={h.message} className="flex gap-2.5 rounded-xl bg-warning-dim/60 px-3 py-2.5 text-[13.5px] text-warning">
                    <Lightbulb size={15} className="mt-0.5 shrink-0" aria-hidden />{h.message}
                  </li>
                ))}
              </ul>
            )}

            {data?.has_reference && !(data.hints?.length) && !data.injection_suspected && (
              <p className="flex items-center gap-2 text-[13.5px] text-verified"><CheckCircle2 size={15} aria-hidden /> Everything we need to get started is here.</p>
            )}
            {error && <p className="text-[13px] text-taupe">Pre-check unavailable: {error}</p>}
          </div>
        )}

        <p className="mt-6 border-t border-line-soft pt-4 text-[12px] leading-relaxed text-taupe">
          Pattern matching and the rule engine only — no AI call is made and nothing is saved until you submit.
          Priority and escalation are decided after submission and are not shown here.
        </p>
      </div>
    </Card>
  )
}

/** Mark each recognised value in the text. By value, not offset: offsets refer to the cleaned text. */
function highlight(text: string, entities: S['PreviewEntityOut'][]) {
  if (!text || !entities.length) return text
  const values = Array.from(new Set(entities.map((e) => e.value).filter((v) => v.length > 1))).sort((a, b) => b.length - a.length)
  if (!values.length) return text
  const escaped = values.map((v) => v.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
  const parts = text.split(new RegExp(`(${escaped.join('|')})`, 'g'))
  return parts.map((part, i) =>
    values.includes(part) ? (
      <mark key={i} className="rounded-md bg-ai-soft px-1 py-0.5 font-medium text-ai ring-1 ring-ai-line">{part}</mark>
    ) : (
      <span key={i}>{part}</span>
    ),
  )
}

/* ------------------------------------------------------------------ analysis progress */

const STEPS: Array<{ label: string; detail: string; at: number; kind: 'ai' | 'rule' | 'plain' }> = [
  { label: 'Reading the complaint', detail: 'Cleaning the text and checking it is complete', at: 0, kind: 'plain' },
  { label: 'Screening for manipulation', detail: 'Instructions hidden in the text are neutralised, never obeyed', at: 1.2, kind: 'rule' },
  { label: 'Retrieving policy', detail: 'Finding the sections of company policy that apply', at: 2.6, kind: 'plain' },
  { label: 'Understanding intent', detail: 'The AI proposes category, urgency and a resolution', at: 4.2, kind: 'ai' },
  { label: 'Checking against the rules', detail: 'The deterministic engine decides every field independently', at: 11, kind: 'rule' },
  { label: 'Comparing and preparing', detail: 'Where the two disagree, the rules win and a person reviews it', at: 15, kind: 'rule' },
]

/**
 * The submit call is one request, so the stages below advance on the times
 * they typically take rather than on server events. The last stage holds
 * until the response arrives — it never claims to be finished early.
 */
function AnalysisProgress({ genai }: { genai: boolean }) {
  const [elapsed, setElapsed] = useState(0)
  useEffect(() => {
    const start = Date.now()
    const id = window.setInterval(() => setElapsed((Date.now() - start) / 1000), 200)
    return () => clearInterval(id)
  }, [])
  const steps = genai ? STEPS : STEPS.filter((s) => s.kind !== 'ai')
  const activeIndex = steps.reduce((acc, s, i) => (elapsed >= s.at ? i : acc), 0)

  return (
    <div className="mx-auto flex max-w-[720px] flex-col gap-7 py-6">
      <div className="animate-rise text-center">
        <p className="eyebrow mb-3 flex items-center justify-center gap-2"><Pulse tone="ai" /> Analysing</p>
        <h1 className="display text-h2">Two opinions, one decision.</h1>
        <p className="mx-auto mt-3 max-w-[52ch] text-[15px] text-taupe">
          The AI reads your complaint and proposes what should happen. Then the company&rsquo;s own rules
          check every part of it, independently.
        </p>
      </div>
      <Card tone="glass" padding="lg" radius="xl">
        <ol className="flex flex-col gap-1">
          {steps.map((s, i) => {
            const done = i < activeIndex
            const active = i === activeIndex
            return (
              <li key={s.label} className={cn('flex items-center gap-4 rounded-2xl px-3 py-3 transition-colors duration-500', active && 'bg-white/80')}>
                <span className="w-7 font-mono text-[12px] text-taupe">{String(i + 1).padStart(2, '0')}</span>
                <span
                  className={cn(
                    'relative inline-flex size-8 shrink-0 items-center justify-center rounded-full border-2 transition-colors duration-500',
                    done ? (s.kind === 'ai' ? 'border-ai bg-ai text-white' : s.kind === 'rule' ? 'border-rule bg-rule text-white' : 'border-espresso bg-espresso text-ink-on-dark')
                      : active ? 'border-ai bg-white text-ai' : 'border-line bg-white text-taupe',
                  )}
                >
                  {active && <span aria-hidden className="absolute inset-0 rounded-full border-2 border-ai animate-pulse-ring" />}
                  {done ? <CheckCircle2 size={15} aria-hidden /> : s.kind === 'ai' ? <Sparkles size={14} aria-hidden /> : s.kind === 'rule' ? <ShieldCheck size={14} aria-hidden /> : <Hash size={13} aria-hidden />}
                </span>
                <div className="min-w-0 flex-1">
                  <p className={cn('text-[15px] font-medium', done || active ? 'text-espresso' : 'text-taupe')}>{s.label}</p>
                  <p className="text-[13px] text-taupe">{s.detail}</p>
                </div>
                {s.kind === 'ai' && <AiBadge>AI</AiBadge>}
                {s.kind === 'rule' && <RuleBadge>rules</RuleBadge>}
              </li>
            )
          })}
        </ol>
        <div className="mt-5 h-1.5 overflow-hidden rounded-full bg-sand/80">
          <div className="h-full rounded-full bg-gradient-to-r from-ai via-ai-2 to-rule-2 transition-[width] duration-700" style={{ width: `${Math.min(94, (elapsed / 22) * 100)}%` }} />
        </div>
        <p className="mt-3 text-center text-[12.5px] tnum text-taupe">{elapsed.toFixed(0)} s</p>
      </Card>
    </div>
  )
}

/* ------------------------------------------------------------------ result */

function Result({ result, staff, onAnother }: { result: S['IntakeResponse']; staff: boolean; onAnother: () => void }) {
  const ref = result.public_ref
  const issues = result.validation_issues ?? []

  if (!staff) {
    const v = result.customer_view
    const open = (v?.questions ?? []).filter((q) => !q.answered)
    return (
      <div className="mx-auto flex max-w-[980px] flex-col gap-6">
        <section className="mesh-banner grain relative overflow-hidden rounded-[var(--radius-xl)] px-6 py-10 text-ink-on-dark md:px-10">
          <div className="relative z-[1] animate-rise">
            <p className="eyebrow mb-3 flex items-center gap-2 text-sand-2"><CheckCircle2 size={13} aria-hidden /> Received and checked</p>
            <h1 className="display text-h1 text-ink-on-dark">{ref}</h1>
            <p className="mt-3 max-w-[56ch] text-[16px] text-ink-on-dark/80">
              Keep this reference. Your complaint has been read and every decision on it checked against
              company policy. You can follow each step from here on.
            </p>
            <div className="mt-5 flex flex-wrap gap-2">
              {v && <Badge tone={statusTone(v.status)} dot>{humanise(v.status)}</Badge>}
              {v?.category_name && <Badge tone="neutral">{v.category_name}</Badge>}
              {v?.escalated && <Badge tone="warning">A specialist is involved</Badge>}
            </div>
          </div>
        </section>

        <div className="grid gap-6 lg:grid-cols-[1.3fr_1fr]">
          <div className="flex flex-col gap-6">
            {v?.summary && (
              <Card tone="ai" radius="xl">
                <p className="mb-2 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-ai"><Sparkles size={12} aria-hidden /> What we understood</p>
                <p className="font-display text-[19px] leading-relaxed text-espresso">{v.summary}</p>
              </Card>
            )}
            {open.length > 0 && (
              <Card tone="glass" radius="xl" className="ring-2 ring-warning-glow/40">
                <p className="eyebrow mb-2 flex items-center gap-2"><Pulse tone="warning" /> We need something from you</p>
                <ul className="mb-4 list-disc pl-5 text-[14.5px] text-espresso-2">{open.map((q) => <li key={q.id}>{q.question}</li>)}</ul>
                <Button href={`/track/${ref}`} arrow>Answer now</Button>
              </Card>
            )}
            {issues.length > 0 && (
              <Card tone="sand" radius="xl">
                <p className="eyebrow mb-2">Worth knowing</p>
                <ul className="flex flex-col gap-1.5 text-[14px]">{issues.map((i, k) => <li key={k}>{i.message}</li>)}</ul>
              </Card>
            )}
            <div className="flex flex-wrap gap-2">
              <Button href={`/track/${ref}`} size="lg" arrow>Track {ref}</Button>
              <Button variant="secondary" size="lg" onClick={onAnother}>Submit another</Button>
            </div>
          </div>
          <div className="flex flex-col gap-6">
            {v && <TeamCard department={v.department} publicRef={ref} />}
            <Card tone="glass" radius="xl">
              <p className="eyebrow mb-4">Where it is now</p>
              <MilestoneTimeline milestones={v?.milestones ?? []} />
            </Card>
          </div>
        </div>
      </div>
    )
  }

  const c = result.complaint!
  const verification = c.verification
  return (
    <div className="mx-auto flex max-w-[1100px] flex-col gap-6">
      <section className="mesh-banner grain relative overflow-hidden rounded-[var(--radius-xl)] px-6 py-10 text-ink-on-dark md:px-10">
        <div className="relative z-[1] animate-rise">
          <p className="eyebrow mb-3 text-sand-2">{result.analysed ? 'Both pipelines have run' : 'Recorded — analysis not run'}</p>
          <h1 className="display text-h1 text-ink-on-dark">{ref}</h1>
          <p className="mt-2 max-w-[60ch] text-[16px] text-ink-on-dark/80">{c.title}</p>
          <div className="mt-5 flex flex-wrap gap-2">
            <Badge tone={statusTone(c.status)} dot>{humanise(c.status)}</Badge>
            {c.verification_outcome && <Badge tone={verificationTone(c.verification_outcome)}>{humanise(c.verification_outcome)}</Badge>}
            {c.injection_suspected && <Badge tone="critical" pulse>Injection suspected</Badge>}
            {result.duplicate_of && <Badge tone="warning">Duplicate of {result.duplicate_of}</Badge>}
            {(result.repeat_count ?? 0) > 1 && <Badge>Repeat ×{result.repeat_count}</Badge>}
          </div>
        </div>
      </section>

      <div className="grid gap-4 md:grid-cols-4">
        {[
          ['Category', c.category ? humanise(c.category) : '—', 'neutral'],
          ['Department', c.department ? humanise(c.department) : '—', 'info'],
          ['Urgency · priority', `${c.urgency ? humanise(c.urgency) : '—'} · ${c.priority_code ?? '—'}`, urgencyTone(c.urgency)],
          ['Escalation', humanise(c.escalation_code ?? 'NONE'), escalationTone(c.escalation_code)],
        ].map(([label, value]) => (
          <Card key={label} tone="glass" radius="xl" padding="sm">
            <p className="eyebrow mb-2">{label}</p>
            <p className="font-display text-[19px] leading-tight text-espresso">{value}</p>
          </Card>
        ))}
      </div>

      {verification && (
        <Card tone="glass" radius="xl">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2"><AiBadge>AI proposed</AiBadge><ArrowRight size={14} className="text-taupe" aria-hidden /><RuleBadge>Rules decided</RuleBadge></div>
            <span className="text-[13.5px] text-taupe">
              {verification.genai_available === false ? 'GenAI unavailable — the rules decided alone' : `Agreement ${verification.agreement_score != null ? Math.round(verification.agreement_score <= 1 ? verification.agreement_score * 100 : verification.agreement_score) : '—'}% on ${verification.matched_fields ?? 0}/${verification.total_fields ?? 0} fields`}
            </span>
          </div>
          {(verification.review_reasons ?? []).length > 0 && (
            <p className="mt-3 text-[14px] text-espresso-2">Sent for human review: {(verification.review_reasons ?? []).map(humanise).join(', ')}.</p>
          )}
        </Card>
      )}

      {c.summary && (
        <Card tone="ai" radius="xl">
          <p className="mb-2 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-ai"><Sparkles size={12} aria-hidden /> Summary</p>
          <p className="font-display text-[19px] leading-relaxed text-espresso">{c.summary}</p>
        </Card>
      )}

      {result.analysis_error && <ErrorState title="Analysis did not complete" message={result.analysis_error} />}

      <div className="flex flex-wrap gap-2">
        <Button href={`/dashboard/complaints/${ref}`} size="lg" arrow>Open the full record</Button>
        <Button href={`/dashboard/review/${ref}`} variant="secondary" size="lg">Review desk</Button>
        <Button variant="ghost" size="lg" onClick={onAnother}>Submit another</Button>
        {c.priority_code && <Badge tone={priorityTone(c.priority_code)} pulse={c.priority_code === 'P0'} className="self-center">{c.priority_code}</Badge>}
      </div>
    </div>
  )
}
