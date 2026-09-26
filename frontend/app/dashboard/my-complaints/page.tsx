'use client'

import { useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import {
  ArrowRight, CheckCircle2, ChevronDown, Clock, FileSearch, Inbox, Lock, Mail, MessageCircleQuestion, MessageSquareReply, Paperclip, Plus, RotateCcw, Scale, Search, ShieldCheck, Sparkles,
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
    <AppShell eyebrow="Customer Dashboard" wide>
      <Mine />
    </AppShell>
  )
}

function Mine() {
  const { user } = useAuth()
  const q = useApi(() => complaints.mine(1, 50), [])
  const rows = useMemo(() => q.data?.items ?? [], [q.data])
  const [selected, setSelected] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [tab, setTab] = useState<'all' | 'open' | 'waiting' | 'resolved'>('all')
  const [confirming, setConfirming] = useState(false)

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

  const filteredRows = useMemo(() => {
    const s = search.trim().toLowerCase()
    return rows.filter((r) => {
      if (tab === 'open' && DONE.has(r.status)) return false
      if (tab === 'waiting' && !r.action_needed) return false
      if (tab === 'resolved' && !DONE.has(r.status)) return false
      if (!s) return true
      return (
        r.public_ref.toLowerCase().includes(s) ||
        r.title.toLowerCase().includes(s) ||
        (r.category_name && r.category_name.toLowerCase().includes(s)) ||
        (r.department?.name && r.department.name.toLowerCase().includes(s))
      )
    })
  }, [rows, search, tab])

  const allFollowUps = useMemo(() => {
    return rows.flatMap((r) =>
      (r.follow_ups ?? []).map((f) => ({
        ...f,
        complaintRef: r.public_ref,
        complaintTitle: r.title,
      }))
    )
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
              <Button href="/dashboard/complaints/new" variant="onDark" size="lg" icon={<Plus size={16} aria-hidden />}>Submit Complaint</Button>
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
        <>
        <AtAGlance rows={rows} onPick={setSelected} />

        {/* My Complaints Section */}
        <section id="my-complaints" className="scroll-mt-24 flex flex-col gap-4">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line-soft pb-3">
            <div>
              <h2 className="font-display text-h3">My Complaints</h2>
              <p className="text-[13px] text-taupe">Track, inspect details, respond to clarification questions, and view resolution.</p>
            </div>
            <div className="flex items-center gap-2">
              <Button href="/dashboard/complaints/new" size="sm" icon={<Plus size={14} aria-hidden />}>New complaint</Button>
            </div>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap gap-1.5">
              {(['all', 'open', 'waiting', 'resolved'] as const).map((t) => (
                <button
                  key={t}
                  type="button"
                  onClick={() => setTab(t)}
                  className={cn(
                    'rounded-full px-3.5 py-1.5 text-[12.5px] font-medium transition',
                    tab === t ? 'bg-espresso text-white shadow-sm' : 'bg-white/80 text-espresso-2 hover:bg-white',
                  )}
                >
                  {t === 'all' && `All (${rows.length})`}
                  {t === 'open' && `Open (${metrics.open})`}
                  {t === 'waiting' && `Waiting on reply (${metrics.waiting})`}
                  {t === 'resolved' && `Resolved (${metrics.resolved})`}
                </button>
              ))}
            </div>

            <div className="relative min-w-[220px]">
              <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-taupe" />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search reference or topic..."
                className="h-9 w-full rounded-full border border-line bg-white/80 pl-8 pr-3 text-[13px] text-espresso placeholder:text-taupe focus:border-espresso focus:outline-none"
              />
            </div>
          </div>

          <div className="grid gap-6 lg:grid-cols-[1.35fr_1fr]">
            <div className="flex flex-col gap-3">
              {!filteredRows.length ? (
                <div className="rounded-2xl border border-line-soft bg-white/70 p-8 text-center">
                  <p className="text-[14.5px] font-medium text-espresso">No complaints match your selection</p>
                  <p className="mt-1 text-[13px] text-taupe-2">Try clearing your search or filter tab.</p>
                </div>
              ) : (
                <ul className="flex flex-col gap-3">
                  {filteredRows.map((r) => (
                    <li key={r.public_ref}>
                      <ComplaintCard row={r} active={r.public_ref === selected} onSelect={() => setSelected(r.public_ref)} />
                    </li>
                  ))}
                </ul>
              )}
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

                  {current.status === 'RESOLVED' && (
                    <div className="mt-5 rounded-2xl border border-verified/30 bg-verified-dim/50 p-4">
                      <p className="font-medium text-espresso">Satisfied with the outcome?</p>
                      <p className="mt-0.5 text-[13px] text-taupe-2">Confirming resolution will complete and close this complaint.</p>
                      <Button
                        className="mt-3 w-full bg-verified text-white hover:bg-verified/90"
                        disabled={confirming}
                        onClick={async () => {
                          setConfirming(true)
                          try {
                            await complaints.confirmResolution(current.public_ref)
                            await q.refresh()
                          } finally {
                            setConfirming(false)
                          }
                        }}
                      >
                        {confirming ? 'Confirming...' : 'Confirm Resolution & Close'}
                      </Button>
                    </div>
                  )}

                  <Button href={`/track/${current.public_ref}`} className="mt-6 w-full" arrow>
                    {current.action_needed ? 'Answer and add evidence' : 'Open full tracking'}
                  </Button>
                </Card>
              )}
            </aside>
          </div>
        </section>

        {/* Follow-ups Section */}
        <section id="follow-ups" className="scroll-mt-24 flex flex-col gap-3 rounded-[var(--radius-xl)] border border-line-soft bg-white/70 p-6 shadow-card">
          <div className="flex flex-wrap items-baseline justify-between gap-3">
            <div>
              <p className="eyebrow mb-1 flex items-center gap-1.5 text-espresso-2"><MessageSquareReply size={13} /> Scheduled Commitments</p>
              <h2 className="font-display text-h3">Follow-ups</h2>
            </div>
            <span className="text-[13px] text-taupe">{allFollowUps.length} follow-up commitments</span>
          </div>

          {!allFollowUps.length ? (
            <p className="text-[14px] text-taupe-2">
              No follow-ups currently scheduled. When support promises to verify eligibility, contact you by phone, or follow up on satisfaction, commitments appear here.
            </p>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {allFollowUps.map((f) => (
                <div key={f.id} className="flex flex-col justify-between rounded-2xl border border-line-soft bg-white p-4 shadow-sm">
                  <div>
                    <div className="flex items-center justify-between gap-2">
                      <Link href={`/track/${encodeURIComponent(f.complaintRef)}`} className="font-mono text-[12px] font-semibold text-espresso underline underline-offset-2">
                        {f.complaintRef}
                      </Link>
                      <Badge tone={f.open ? 'warning' : 'verified'}>{f.open ? 'Pending' : 'Completed'}</Badge>
                    </div>
                    <p className="mt-2 text-[14px] font-medium text-espresso">{f.message || humanise(f.type)}</p>
                  </div>
                  <div className="mt-4 border-t border-line-soft pt-2 text-[12px] font-mono text-taupe-2">
                    {f.due_at ? `Due: ${new Date(f.due_at).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })}` : 'Scheduled'}
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
        </>
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
          ? 'border-ai-line bg-white shadow-[0_0_0_3px_rgba(27,94,140,0.10),0_18px_40px_-22px_rgba(42,31,23,0.35)]'
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

const FAQ: Array<{ q: string; a: string; icon: typeof Clock; topic: string }> = [
  { topic: 'Timing', icon: Clock, q: 'How long will it take?', a: 'Each complaint gets a target resolution time the moment it is checked, based on how urgent it is. The tracking page shows it counting down, and every step as it happens.' },
  { topic: 'Tracking', icon: Search, q: 'How do I follow my complaint?', a: 'Open it from the list above, or go to Track by reference and enter the number we gave you (it looks like CMP-000123). You will see each step, the team handling it and how to reach them.' },
  { topic: 'Questions', icon: MessageCircleQuestion, q: 'Why is a question waiting for me?', a: 'When something we need is missing — a consignment number, a date, a photo — we ask instead of guessing. Answering moves the complaint straight back to the team.' },
  { topic: 'Decisions', icon: Scale, q: 'Who decides what happens?', a: 'An AI model reads your complaint and proposes an outcome. The company’s written rules then confirm or correct every part of it, and where they disagree a person reviews it. The AI never approves itself.' },
  { topic: 'Evidence', icon: Paperclip, q: 'Can I add photos or receipts later?', a: 'Yes. Open the complaint’s tracking page and drop files onto the evidence panel at any time. PDF, Word, PNG, JPEG, WEBP or text, up to 10 MB each.' },
  { topic: 'Decisions', icon: RotateCcw, q: 'What if I disagree with the outcome?', a: 'Add what we missed on the tracking page — a photo, a receipt, the details — and the team looks again. If it is a new problem, raise a new complaint and mention your earlier reference; we link the two.' },
  { topic: 'Contact', icon: Mail, q: 'Can I talk to the team directly?', a: 'Yes. Once your complaint is with a team, its tracking page shows that team’s email address and support hours. Quote your reference so they find it at once.' },
  { topic: 'Privacy', icon: Lock, q: 'Is my information safe?', a: 'Only you and the support team can see your complaint. Files are checked by their contents, not their names, and are only ever downloaded — never opened in the browser.' },
]

/**
 * Searchable, one-open-at-a-time answers. Each answer expands with a height
 * transition (grid rows 0fr -> 1fr) rather than snapping, and the controls
 * are real buttons that announce whether they are open.
 */
function Faq() {
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState<number | null>(0)
  const q = query.trim().toLowerCase()
  const shown = FAQ.map((f, i) => ({ ...f, i })).filter((f) => !q || f.q.toLowerCase().includes(q) || f.a.toLowerCase().includes(q) || f.topic.toLowerCase().includes(q))

  return (
    <section className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.7fr)]" aria-labelledby="faq-title">
      <div className="flex flex-col gap-4 lg:sticky lg:top-24 lg:self-start">
        <div>
          <p className="eyebrow mb-2">Help</p>
          <h2 id="faq-title" className="font-display text-h3">Common questions</h2>
          <p className="mt-2 max-w-[40ch] text-[14px] text-taupe-2">Short answers to what customers ask most.</p>
        </div>
        <label className="relative block">
          <span className="sr-only">Search the questions</span>
          <Search size={16} className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-taupe" aria-hidden />
          <input
            value={query}
            onChange={(e) => { setQuery(e.target.value); setOpen(null) }}
            placeholder="Search, e.g. refund, photo, how long"
            className="h-11 w-full rounded-full border border-line bg-white/85 pl-10 pr-4 text-[14px] text-espresso placeholder:text-taupe focus:border-espresso focus:outline-none"
          />
        </label>
        <Card tone="glass" padding="sm" radius="lg" className="flex flex-col gap-3">
          <p className="text-[14px] font-medium text-espresso">Still need help?</p>
          <p className="text-[13px] leading-relaxed text-taupe-2">The team handling your complaint is shown on its tracking page, with their email and hours.</p>
          <div className="flex flex-wrap gap-2">
            <Button href="/track" size="sm" variant="secondary" icon={<Search size={14} aria-hidden />}>Track by reference</Button>
            <Button href="/dashboard/complaints/new" size="sm" icon={<Plus size={14} aria-hidden />}>New complaint</Button>
          </div>
        </Card>
      </div>

      <div className="flex flex-col gap-2.5" role="list">
        {shown.length === 0 && (
          <p className="rounded-2xl border border-dashed border-line bg-white/60 px-5 py-6 text-center text-[14px] text-taupe-2">
            No answer mentions “{query}”. Try another word, or raise it as a complaint and we will answer you directly.
          </p>
        )}
        {shown.map((f) => {
          const isOpen = open === f.i
          const Icon = f.icon
          return (
            <div key={f.q} role="listitem" className={cn('rounded-2xl border transition-[background-color,border-color,box-shadow] duration-300', isOpen ? 'border-line bg-white shadow-card' : 'border-line-soft bg-white/80 hover:bg-white')}>
              <h3 className="font-sans">
                <button
                  type="button"
                  id={`faq-q-${f.i}`}
                  aria-expanded={isOpen}
                  aria-controls={`faq-a-${f.i}`}
                  onClick={() => setOpen(isOpen ? null : f.i)}
                  className="flex w-full items-center gap-4 px-5 py-4 text-left"
                >
                  <span className={cn('inline-flex size-9 shrink-0 items-center justify-center rounded-xl transition-colors', isOpen ? 'bg-espresso text-ink-on-dark' : 'bg-sand/70 text-espresso-2')}><Icon size={16} aria-hidden /></span>
                  <span className="min-w-0 flex-1">
                    <span className="block font-sans text-[15px] font-medium leading-snug tracking-normal text-espresso">{f.q}</span>
                    <span className="mt-0.5 block font-sans text-[12px] tracking-normal text-taupe-2">{f.topic}</span>
                  </span>
                  <ChevronDown size={18} className={cn('shrink-0 text-taupe transition-transform duration-300', isOpen && 'rotate-180')} aria-hidden />
                </button>
              </h3>
              <div
                id={`faq-a-${f.i}`}
                role="region"
                aria-labelledby={`faq-q-${f.i}`}
                className={cn('grid transition-[grid-template-rows] duration-300 ease-out', isOpen ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]')}
              >
                <div className="overflow-hidden">
                  <p className="px-5 pb-5 text-[14px] leading-relaxed text-espresso-2 sm:pl-[4.25rem]">{f.a}</p>
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </section>
  )
}

/**
 * Every complaint on one table, one column per thing the SRS says a user
 * sees: ID, status, submitted date, department, latest update and resolution
 * status. The sidebar links to each column.
 */
function AtAGlance({ rows, onPick }: { rows: S['ComplaintStatusOut'][]; onPick: (ref: string) => void }) {
  const th = 'scroll-mt-28 px-3.5 py-3 text-left text-[11px] font-semibold uppercase tracking-[0.1em] text-taupe-2 transition-colors data-[flash=true]:bg-sand'
  return (
    <section id="overview" aria-labelledby="glance-title" className="scroll-mt-24 flex flex-col gap-3">
      <div className="flex items-baseline justify-between">
        <h2 id="glance-title" className="font-display text-h3">At a glance</h2>
        <span className="text-[13px] text-taupe">SRS Complaint Tracking</span>
      </div>
      <div className="overflow-x-auto rounded-2xl border border-line-soft bg-white/80 shadow-card">
        <table className="w-full min-w-[720px] border-separate border-spacing-0 text-[14px]">
          <thead className="bg-cream/70">
            <tr>
              <th id="complaint-id" data-dash-target className={th}>Complaint ID</th>
              <th id="status" data-dash-target className={th}>Status</th>
              <th id="submitted" data-dash-target className={th}>Submitted date</th>
              <th id="department" data-dash-target className={th}>Department</th>
              <th id="latest-update" data-dash-target className={th}>Latest update</th>
              <th id="resolution" data-dash-target className={th}>Resolution status</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const done = DONE.has(r.status)
              const reached = (r.milestones ?? []).filter((m) => m.reached || m.current)
              const latest = reached[reached.length - 1]
              return (
                <tr key={r.public_ref} className="[&>td]:border-t [&>td]:border-line-soft [&>td]:px-3 [&>td]:py-3 hover:bg-cream/40">
                  <td><Link href={`/track/${encodeURIComponent(r.public_ref)}`} className="font-mono text-[13px] text-espresso underline decoration-line underline-offset-4 hover:decoration-espresso" onClick={() => onPick(r.public_ref)}>{r.public_ref}</Link></td>
                  <td><Badge tone={statusTone(r.status)} dot pulse={Boolean(r.action_needed)}>{r.action_needed ? 'Waiting for you' : humanise(r.status)}</Badge></td>
                  <td className="whitespace-nowrap text-espresso-2">{r.submitted_at ? new Date(r.submitted_at).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }) : '—'}</td>
                  <td className="text-espresso-2">{r.department?.name ?? <span className="text-taupe">Being assigned</span>}</td>
                  <td className="text-espresso-2">{latest?.label ?? 'Received'}<span className="block text-[12.5px] text-taupe-2">{fmtRelative(r.last_updated ?? r.submitted_at)}</span></td>
                  <td>{done ? <span className="inline-flex items-center gap-1.5 text-verified"><CheckCircle2 size={15} aria-hidden /> Resolved</span> : <span className="text-espresso-2">In progress{r.target_resolution_at && <span className="block text-[12.5px] text-taupe-2">target {fmtRelative(r.target_resolution_at)}</span>}</span>}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </section>
  )
}
