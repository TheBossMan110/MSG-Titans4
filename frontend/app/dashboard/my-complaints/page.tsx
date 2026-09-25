'use client'

import { useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import {
  ArrowRight, CheckCircle2, ChevronDown, Clock, FileSearch, Inbox, MessageSquareReply,
  Paperclip, Plus, ShieldCheck, Sparkles,
} from 'lucide-react'
import { AppShell } from '@/components/layout/app-shell'
import { useAuth } from '@/lib/auth-context'
import { complaints, type S } from '@/lib/api'
import { useApi, fmtRelative } from '@/lib/use-api'
import { Badge, Button, Pulse, humanise, statusTone } from '@/components/ui/primitives'
import { Card } from '@/components/ui/surfaces'
import { CountUp } from '@/components/ui/data'
import { ErrorState, Skeleton } from '@/components/ui/feedback'
import { MilestoneTimeline, TeamCard } from '@/components/app/customer'
import { cn } from '@/lib/utils'

type Row = S['ComplaintStatusOut']
const DONE = new Set(['RESOLVED', 'CLOSED'])

export default function MyComplaintsPage() {
  return (
    <AppShell eyebrow="My complaints" wide>
      <Mine />
    </AppShell>
  )
}

function Mine() {
  const { user } = useAuth()
  const q = useApi(() => complaints.mine(1, 50), [])
  const rows = useMemo(() => q.data?.items ?? [], [q.data])
  const [selected, setSelected] = useState<string | null>(null)

  useEffect(() => {
    if (!selected && rows.length) {
      setSelected((rows.find((r) => r.action_needed) ?? rows.find((r) => !DONE.has(r.status)) ?? rows[0]).public_ref)
    }
  }, [rows, selected])

  const metrics = useMemo(() => {
    const open = rows.filter((r) => !DONE.has(r.status))
    const waiting = rows.filter((r) => r.action_needed)
    const resolved = rows.filter((r) => DONE.has(r.status))
    const durations = resolved
      .map((r) => (r.submitted_at && r.last_updated ? new Date(r.last_updated).getTime() - new Date(r.submitted_at).getTime() : null))
      .filter((n): n is number => n !== null && n > 0)
    const avgHours = durations.length ? durations.reduce((a, b) => a + b, 0) / durations.length / 3_600_000 : null
    const nextDue = open
      .map((r) => r.target_resolution_at)
      .filter(Boolean)
      .sort()[0] ?? null
    return { open: open.length, waiting: waiting.length, resolved: resolved.length, avgHours, nextDue }
  }, [rows])

  const current = rows.find((r) => r.public_ref === selected) ?? null
  const hour = new Date().getHours()
  const greeting = hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening'
  const first = (user?.full_name || '').split(' ')[0] || 'there'

  return (
    <div className="flex flex-col gap-7">
      {/* hero */}
      <section className="mesh-banner grain relative overflow-hidden rounded-[var(--radius-xl)] px-6 py-9 text-ink-on-dark md:px-10 md:py-12">
        <div className="relative z-[1] grid gap-8 lg:grid-cols-[1.4fr_1fr] lg:items-end">
          <div className="animate-rise">
            <p className="eyebrow mb-3 text-sand-2">{greeting}</p>
            <h1 className="display text-h1 text-ink-on-dark">{first}.</h1>
            <p className="mt-4 max-w-[48ch] text-[16px] leading-relaxed text-ink-on-dark/80">
              {metrics.waiting
                ? `${metrics.waiting === 1 ? 'One of your complaints needs' : `${metrics.waiting} of your complaints need`} an answer from you before we can move on.`
                : metrics.open
                  ? 'Everything is with us. You will see each step here as it happens.'
                  : 'Submit a complaint and follow every step the system takes on it — read by AI, confirmed against company policy.'}
            </p>
            <div className="mt-7 flex flex-wrap gap-3">
              <Button href="/dashboard/complaints/new" variant="onDark" size="lg" icon={<Plus size={16} aria-hidden />}>Submit a complaint</Button>
              <Button href="/track" size="lg" className="border border-ink-on-dark/25 bg-transparent text-ink-on-dark hover:bg-ink-on-dark/10" icon={<FileSearch size={16} aria-hidden />}>Track by reference</Button>
            </div>
          </div>
          <div className="glass-dark rounded-2xl p-5">
            <p className="mb-3 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-sand-2">
              <ShieldCheck size={13} aria-hidden /> Our guarantee
            </p>
            <p className="text-[14.5px] leading-relaxed text-ink-on-dark/85">
              Every decision on your complaint — its category, its priority, anything we offer — is
              checked against the company&rsquo;s own written policy before you see it. If the AI and
              the policy disagree, a person decides.
            </p>
          </div>
        </div>
      </section>

      {/* metrics */}
      <section className="grid gap-4 md:grid-cols-3" aria-label="Summary">
        <Metric
          icon={<Inbox size={18} aria-hidden />}
          label="Open"
          value={q.data ? metrics.open : undefined}
          note={metrics.nextDue ? `Next target ${fmtRelative(metrics.nextDue)}` : metrics.open ? 'Target dates appear once triaged' : 'Nothing in progress'}
        />
        <Metric
          icon={<MessageSquareReply size={18} aria-hidden />}
          label="Waiting on you"
          value={q.data ? metrics.waiting : undefined}
          tone={metrics.waiting ? 'warning' : 'neutral'}
          pulse={metrics.waiting > 0}
          note={metrics.waiting ? 'Answer to keep them moving' : 'Nothing needs your reply'}
        />
        <Metric
          icon={<CheckCircle2 size={18} aria-hidden />}
          label="Resolved"
          value={q.data ? metrics.resolved : undefined}
          tone="verified"
          note={
            metrics.avgHours === null
              ? 'No resolved complaints yet'
              : `Average ${metrics.avgHours < 48 ? `${Math.round(metrics.avgHours)} h` : `${(metrics.avgHours / 24).toFixed(1)} days`} to resolve`
          }
        />
      </section>

      {q.error ? (
        <ErrorState message={q.error} onRetry={q.refresh} />
      ) : q.loading && !q.data ? (
        <div className="grid gap-6 lg:grid-cols-[1.35fr_1fr]"><div className="flex flex-col gap-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-28" />)}</div><Skeleton className="h-96" /></div>
      ) : !rows.length ? (
        <Onboarding />
      ) : (
        <section className="grid gap-6 lg:grid-cols-[1.35fr_1fr]">
          <div className="flex flex-col gap-3">
            <div className="flex items-baseline justify-between">
              <h2 className="font-display text-h3">Your complaints</h2>
              <span className="text-[13px] text-taupe">{rows.length} total</span>
            </div>
            <ul className="flex flex-col gap-3">
              {rows.map((r) => (
                <li key={r.public_ref}>
                  <ComplaintCard row={r} active={r.public_ref === selected} onSelect={() => setSelected(r.public_ref)} />
                </li>
              ))}
            </ul>
          </div>

          <aside className="lg:sticky lg:top-24 lg:self-start">
            {current && (
              <Card tone="glass" padding="lg" radius="xl" className="animate-rise" key={current.public_ref}>
                <div className="mb-5 flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="eyebrow mb-1.5 font-mono normal-case tracking-normal">{current.public_ref}</p>
                    <h3 className="font-display text-[22px] leading-tight">{current.title}</h3>
                  </div>
                  <Badge tone={statusTone(current.status)} dot>{humanise(current.status)}</Badge>
                </div>
                {current.action_needed && (
                  <Link href={`/track/${current.public_ref}`} className="mb-5 flex items-center gap-3 rounded-2xl border border-warning/30 bg-warning-dim/70 p-3.5 transition-colors hover:bg-warning-dim">
                    <Pulse tone="warning" />
                    <span className="flex-1 text-[14px] font-medium text-warning">{(current.awaiting_information?.length ?? 0) === 1 ? 'We have one question for you' : `We have ${current.awaiting_information?.length ?? 0} questions for you`}</span>
                    <ArrowRight size={16} className="text-warning" aria-hidden />
                  </Link>
                )}
                <MilestoneTimeline milestones={current.milestones ?? []} />
                {current.summary && (
                  <div className="mt-6 rounded-2xl border border-ai-line/70 bg-ai-soft/50 p-4">
                    <p className="mb-1.5 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-ai"><Sparkles size={12} aria-hidden /> What we understood</p>
                    <p className="text-[14px] leading-relaxed text-espresso-2">{current.summary}</p>
                  </div>
                )}
                <div className="mt-6"><TeamCard department={current.department} publicRef={current.public_ref} compact /></div>
                <Button href={`/track/${current.public_ref}`} className="mt-6 w-full" arrow>
                  {current.action_needed ? 'Answer and add evidence' : 'Open full tracking'}
                </Button>
              </Card>
            )}
          </aside>
        </section>
      )}

      <Faq />
    </div>
  )
}

function Metric({ icon, label, value, note, tone = 'neutral', pulse }: {
  icon: React.ReactNode; label: string; value: number | undefined; note: string
  tone?: 'neutral' | 'warning' | 'verified'; pulse?: boolean
}) {
  const ring = { neutral: 'text-espresso-2 bg-white', warning: 'text-warning bg-warning-dim', verified: 'text-verified bg-verified-dim' }[tone]
  const num = { neutral: 'text-espresso', warning: 'text-warning', verified: 'text-verified' }[tone]
  return (
    <Card tone="glass" radius="xl" lift className="flex items-start gap-4">
      <span className={cn('inline-flex size-11 shrink-0 items-center justify-center rounded-2xl shadow-card', ring)}>{icon}</span>
      <div className="min-w-0">
        <p className="eyebrow flex items-center gap-2">{label}{pulse && <Pulse tone="warning" />}</p>
        <p className={cn('mt-1.5 font-display text-[40px] leading-none tracking-[-0.03em]', num)}>
          {value === undefined ? <span className="inline-block h-8 w-12 rounded-md shimmer align-middle" /> : <CountUp value={value} />}
        </p>
        <p className="mt-2 text-[13px] text-taupe">{note}</p>
      </div>
    </Card>
  )
}

function ComplaintCard({ row, active, onSelect }: { row: Row; active: boolean; onSelect: () => void }) {
  const reached = (row.milestones ?? []).filter((m) => m.reached).length
  const total = (row.milestones ?? []).length || 5
  return (
    <button
      onClick={onSelect}
      aria-pressed={active}
      className={cn(
        'group/card w-full rounded-[var(--radius-xl)] border p-5 text-left transition-[transform,box-shadow,border-color,background-color] duration-300 ease-[var(--ease-out-expo)]',
        active
          ? 'border-ai-line bg-white shadow-[0_0_0_3px_rgba(79,63,209,0.10),0_18px_40px_-22px_rgba(42,31,23,0.35)]'
          : 'border-white/70 bg-white/60 hover:-translate-y-0.5 hover:bg-white/85 hover:shadow-float',
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-mono text-[12.5px] text-taupe">{row.public_ref}</p>
          <p className="mt-1 truncate font-display text-[19px] leading-tight text-espresso">{row.title}</p>
        </div>
        <Badge tone={statusTone(row.status)} dot pulse={row.action_needed}>{row.action_needed ? 'Needs your reply' : humanise(row.status)}</Badge>
      </div>
      <div className="mt-4 flex items-center gap-3">
        <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-sand/80">
          <div
            className={cn('h-full rounded-full transition-[width] duration-700', DONE.has(row.status) ? 'bg-verified' : 'bg-gradient-to-r from-ai to-rule-2')}
            style={{ width: `${Math.round((reached / total) * 100)}%` }}
          />
        </div>
        <span className="text-[12px] tnum text-taupe">{reached}/{total}</span>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-[12.5px] text-taupe">
        {row.category_name && <span>{row.category_name}</span>}
        {row.department && <span className="font-medium text-espresso-2">{row.department.name}</span>}
        <span className="inline-flex items-center gap-1"><Clock size={12} aria-hidden /> {fmtRelative(row.last_updated)}</span>
        {(row.evidence?.length ?? 0) > 0 && <span className="inline-flex items-center gap-1"><Paperclip size={12} aria-hidden /> {row.evidence!.length}</span>}
      </div>
    </button>
  )
}

function Onboarding() {
  const steps = [
    { icon: <Plus size={18} aria-hidden />, title: 'Tell us what happened', body: 'In your own words. Add a consignment number if you have one — we spot it automatically.' },
    { icon: <Sparkles size={18} aria-hidden />, title: 'AI reads it, rules check it', body: 'A model works out what the problem is; the company’s policy confirms every decision.' },
    { icon: <CheckCircle2 size={18} aria-hidden />, title: 'Follow it to the end', body: 'Answer any questions, add photos or receipts, and watch each step land here.' },
  ]
  return (
    <Card tone="glass" padding="lg" radius="xl">
      <h2 className="font-display text-h3">You have not raised a complaint yet</h2>
      <p className="mt-2 max-w-[56ch] text-[14.5px] text-taupe">Here is how it works — about two minutes to submit, and you can see everything that happens after.</p>
      <ol className="mt-7 grid gap-4 md:grid-cols-3">
        {steps.map((s, i) => (
          <li key={s.title} className="rounded-2xl border border-white/70 bg-white/70 p-5">
            <span className="mb-4 inline-flex size-10 items-center justify-center rounded-xl bg-espresso text-ink-on-dark">{s.icon}</span>
            <p className="eyebrow mb-1">Step {i + 1}</p>
            <p className="font-display text-[19px] leading-tight text-espresso">{s.title}</p>
            <p className="mt-2 text-[13.5px] leading-relaxed text-taupe">{s.body}</p>
          </li>
        ))}
      </ol>
      <Button href="/dashboard/complaints/new" size="lg" className="mt-7" arrow>Submit your first complaint</Button>
    </Card>
  )
}

const FAQ: Array<[string, string]> = [
  ['How long will it take?', 'Each complaint gets a target resolution time the moment it is triaged, based on how urgent it is. You can see it on the tracking page, counting down.'],
  ['Why is a question waiting for me?', 'When something we need is missing — a consignment number, a date, a photo — we ask instead of guessing. Answering moves the complaint straight back to the team.'],
  ['Who decides what happens?', 'An AI model reads your complaint and proposes an outcome. The company’s written rules then confirm or correct every part of it, and where they disagree a person reviews it. The AI never approves itself.'],
  ['Can I add photos or receipts later?', 'Yes. Open the complaint’s tracking page and drop files onto the evidence panel at any time. PDF, Word, PNG, JPEG, WEBP or text, up to 10 MB each.'],
  ['Is my information safe?', 'Only you and the support team can see your complaint. Files are checked by their contents, not their names, and are only ever downloaded — never opened in the browser.'],
]

function Faq() {
  return (
    <section className="grid gap-6 lg:grid-cols-[1fr_1.6fr]" aria-label="Questions">
      <div>
        <p className="eyebrow mb-2">Help</p>
        <h2 className="font-display text-h3">Common questions</h2>
        <p className="mt-2 max-w-[40ch] text-[14px] text-taupe">Short answers to what customers ask most.</p>
      </div>
      <div className="flex flex-col gap-2">
        {FAQ.map(([question, answer]) => (
          <details key={question} className="group/faq rounded-2xl border border-white/70 bg-white/60 px-5 py-4 transition-colors open:bg-white/90">
            <summary className="flex cursor-pointer list-none items-center justify-between gap-4 text-[15px] font-medium text-espresso">
              {question}
              <ChevronDown size={16} className="shrink-0 text-taupe transition-transform duration-300 group-open/faq:rotate-180" aria-hidden />
            </summary>
            <p className="mt-3 text-[14px] leading-relaxed text-taupe">{answer}</p>
          </details>
        ))}
      </div>
    </section>
  )
}
