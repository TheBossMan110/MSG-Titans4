'use client'

import { useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { Building2, Check, Copy, FileText, Inbox, KeyRound, Lock, ShieldCheck, UserPlus, Users } from 'lucide-react'
import { AppShell } from '@/components/layout/app-shell'
import { useAuth } from '@/lib/auth-context'
import { company, type S } from '@/lib/api'
import { useAction, useApi, fmtDate } from '@/lib/use-api'
import { Badge, Button, Mono } from '@/components/ui/primitives'
import { Card, PanelHeader } from '@/components/ui/surfaces'
import { Field, Input } from '@/components/ui/forms'
import { Stat } from '@/components/ui/data'
import { ErrorState, Skeleton, useToast } from '@/components/ui/feedback'
import { cn } from '@/lib/utils'

const ROLE_LABEL: Record<string, string> = { manager: 'Manager', reviewer: 'Reviewer', agent: 'Agent' }
const SCOPE_LABEL: Record<string, [string, string]> = {
  assigned: ['Only their cases', 'Complaints assigned to them, nothing else.'],
  team: ['Their team', "Their department's complaints, plus anything assigned to them."],
  all: ['Everything', "Every complaint in the company."],
}

export default function AccessPage() {
  return (
    <AppShell eyebrow="Company & Access" roles={['admin', 'evaluator']} wide>
      <Access />
    </AppShell>
  )
}

type Policy = S['AccessPolicy']

/** A stable form of a policy, for "has anything changed?". */
function key(p: Policy | undefined) {
  if (!p) return ''
  const perms = Object.fromEntries(Object.entries(p.permissions ?? {}).map(([r, ks]) => [r, [...ks].sort()]).sort())
  const scope = Object.fromEntries(Object.entries(p.complaint_scope ?? {}).sort())
  return JSON.stringify({ perms, scope })
}

/**
 * One company's own workspace on the platform: who it is, how far along it is,
 * and -- the point of the page -- which work each of its roles may do and how
 * much of the complaint register each sees. The API enforces exactly what
 * this page saves, on every request.
 */
function Access() {
  const { user } = useAuth()
  const toast = useToast()
  const isAdmin = user?.role === 'admin'
  const q = useApi(() => company.get())
  const save = useAction((p: Policy) => company.setAccess(p))
  const [draft, setDraft] = useState<Policy | null>(null)

  useEffect(() => { if (q.data) setDraft(q.data.access) }, [q.data])

  const c = q.data
  const dirty = Boolean(c && draft && key(draft) !== key(c.access))
  const customised = Boolean(c && key(c.access) !== key(c.defaults))

  if (q.error) return <ErrorState title="Your company could not be loaded" message={q.error} onRetry={q.refresh} />

  const toggle = (role: string, permission: string) => setDraft((d) => {
    if (!d) return d
    const held = new Set(d.permissions?.[role] ?? [])
    if (held.has(permission)) held.delete(permission); else held.add(permission)
    return { ...d, permissions: { ...d.permissions, [role]: [...held].sort() } }
  })
  const setScope = (role: string, scope: string) => setDraft((d) => d && ({ ...d, complaint_scope: { ...d.complaint_scope, [role]: scope } }))

  const submit = async () => {
    if (!draft) return
    const r = await save.run(draft)
    if (r) { toast('ok', 'Access saved. It applies to everyone in the company from their next click.'); q.refresh() }
    else if (save.error) toast('err', save.error)
  }

  return (
    <div className="flex min-w-0 flex-col gap-6">
      <Banner c={c} canEdit={isAdmin} onSaved={q.refresh} />

      <div className="grid grid-cols-2 gap-x-6 gap-y-5 rounded-[var(--radius-xl)] border border-line bg-ivory p-5 sm:grid-cols-3 lg:grid-cols-5 md:p-6">
        <Stat label="Staff" value={c?.counts.staff} icon={<Users size={12} aria-hidden />} />
        <Stat label="Customers" value={c?.counts.customers} />
        <Stat label="Complaints" value={c?.counts.complaints} icon={<Inbox size={12} aria-hidden />} />
        <Stat label="Open" value={c?.counts.open_complaints} tone={c && c.counts.open_complaints > 0 ? 'warning' : 'neutral'} />
        <Stat label="Policy documents" value={c?.counts.documents} icon={<FileText size={12} aria-hidden />} />
      </div>

      {c && <GettingStarted c={c} customised={customised} />}

      <Card tone="glass" radius="xl" id="matrix">
        <PanelHeader
          eyebrow="Work"
          title="Who may do what"
          icon={<KeyRound size={15} aria-hidden />}
          aside={customised ? <Badge tone="info">Customised</Badge> : <Badge>Platform defaults</Badge>}
        />
        <p className="mb-4 max-w-[70ch] text-[13.5px] text-taupe-2">
          Ticked work is allowed for everyone with that role. The API checks this on every request, so a page
          or a button that is withheld is refused even if someone types its address. Administrators always keep
          everything, so the company can never lock itself out.
        </p>
        {!c || !draft ? <Skeleton className="h-72" /> : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-left text-[13.5px]">
              <thead>
                <tr className="border-b border-line">
                  <th className="py-2.5 pr-4 font-medium text-taupe-2">Permission</th>
                  {c.roles.map((r) => <th key={r} className="px-3 py-2.5 text-center font-medium text-taupe-2">{ROLE_LABEL[r] ?? r}</th>)}
                  <th className="px-3 py-2.5 text-center font-medium text-taupe-2">Administrator</th>
                </tr>
              </thead>
              <tbody>
                {c.catalogue.map((p) => (
                  <tr key={p.key} className="border-b border-line-soft last:border-0">
                    <td className="py-3 pr-4 align-top">
                      <p className="font-medium text-espresso">{p.label}</p>
                      <p className="text-[12.5px] text-taupe-2">{p.description}</p>
                      <Mono className="text-[11px] text-taupe">{p.key}</Mono>
                    </td>
                    {c.roles.map((r) => {
                      const on = (draft.permissions?.[r] ?? []).includes(p.key)
                      const changed = on !== (c.access.permissions?.[r] ?? []).includes(p.key)
                      return (
                        <td key={r} className="px-3 py-3 text-center align-top">
                          <label className={cn('inline-flex size-9 cursor-pointer items-center justify-center rounded-xl border transition-colors',
                            changed ? 'border-ai-line bg-ai-soft' : 'border-transparent hover:bg-white/70', !isAdmin && 'cursor-not-allowed opacity-70')}>
                            <input type="checkbox" className="size-4 accent-espresso" checked={on} disabled={!isAdmin}
                              onChange={() => toggle(r, p.key)} aria-label={`${ROLE_LABEL[r]}: ${p.label}`} />
                          </label>
                          {p.defaults.includes(r) && <p className="text-[10.5px] text-taupe">default</p>}
                        </td>
                      )
                    })}
                    <td className="px-3 py-3 text-center align-top">
                      <span className="inline-flex size-9 items-center justify-center text-verified" title="Administrators always hold every permission">
                        <Lock size={14} aria-hidden /><span className="sr-only">Always</span>
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card tone="glass" radius="xl">
        <PanelHeader eyebrow="Data" title="How much of the register each role sees" icon={<ShieldCheck size={15} aria-hidden />} />
        <p className="mb-5 max-w-[70ch] text-[13.5px] text-taupe-2">
          Applied to every list, search, count and complaint page. A complaint outside someone&apos;s scope answers
          &ldquo;not found&rdquo;, so nobody can learn which references exist elsewhere. Other companies&apos; complaints are
          never in reach at all.
        </p>
        {!c || !draft ? <Skeleton className="h-40" /> : (
          <div className="grid gap-4 lg:grid-cols-3">
            {c.roles.map((r) => (
              <div key={r} className="rounded-2xl border border-line-soft bg-white/60 p-4">
                <p className="mb-3 font-medium text-espresso">{ROLE_LABEL[r] ?? r}s</p>
                <div role="radiogroup" aria-label={`${ROLE_LABEL[r]} sees`} className="flex flex-col gap-1.5">
                  {c.scopes.map((s) => {
                    const active = draft.complaint_scope?.[r] === s
                    return (
                      <button key={s} type="button" role="radio" aria-checked={active} disabled={!isAdmin} onClick={() => setScope(r, s)}
                        className={cn('flex items-start gap-2.5 rounded-xl border px-3 py-2 text-left transition-colors',
                          active ? 'border-espresso/30 bg-white shadow-sm' : 'border-transparent hover:bg-white/70', !isAdmin && 'cursor-not-allowed')}>
                        <span className={cn('mt-1 inline-flex size-3.5 shrink-0 items-center justify-center rounded-full border', active ? 'border-espresso bg-espresso' : 'border-taupe')}>
                          {active && <span className="size-1.5 rounded-full bg-ink-on-dark" />}
                        </span>
                        <span className="min-w-0">
                          <span className="block text-[13.5px] font-medium text-espresso">
                            {SCOPE_LABEL[s]?.[0] ?? s}
                            {c.defaults.complaint_scope?.[r] === s && <span className="ml-1.5 text-[11px] font-normal text-taupe">default</span>}
                          </span>
                          <span className="block text-[12.5px] text-taupe-2">{SCOPE_LABEL[s]?.[1]}</span>
                        </span>
                      </button>
                    )
                  })}
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      {isAdmin && c && draft && (
        <div className="sticky bottom-4 z-10 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-line bg-ivory/95 px-5 py-3 shadow-card backdrop-blur">
          <p className="text-[13.5px] text-espresso-2">{dirty ? 'You have unsaved changes.' : 'Everything is saved. Every change is written to the audit log with before and after.'}</p>
          <div className="flex gap-2">
            <Button variant="ghost" size="sm" disabled={key(draft) === key(c.defaults)} onClick={() => setDraft(c.defaults)}>Use platform defaults</Button>
            <Button variant="secondary" size="sm" disabled={!dirty} onClick={() => setDraft(c.access)}>Discard</Button>
            <Button size="sm" loading={save.pending} disabled={!dirty} onClick={submit}>Save access</Button>
          </div>
        </div>
      )}

      <SharedTemplate ownsTemplate={Boolean(c?.owns_template)} />
    </div>
  )
}

function Banner({ c, canEdit, onSaved }: { c?: S['CompanyOut'] | null; canEdit: boolean; onSaved: () => void }) {
  const toast = useToast()
  const [editing, setEditing] = useState(false)
  const [name, setName] = useState('')
  const [industry, setIndustry] = useState('')
  const update = useAction((body: S['CompanyUpdate']) => company.update(body))
  const open = () => { setName(c?.name ?? ''); setIndustry(c?.industry ?? ''); setEditing(true) }
  const submit = async () => {
    const r = await update.run({ name: name.trim(), industry: industry.trim() })
    if (r) { toast('ok', 'Company details saved.'); setEditing(false); onSaved() } else if (update.error) toast('err', update.error)
  }
  return (
    <section className="mesh-banner grain relative overflow-hidden rounded-[var(--radius-xl)] px-6 py-8 text-ink-on-dark md:px-10 md:py-10">
      <div className="relative z-[1] flex flex-wrap items-end justify-between gap-6">
        <div className="min-w-0">
          <p className="eyebrow mb-3 flex items-center gap-2 text-sand-2"><Building2 size={13} aria-hidden /> Your company</p>
          {c ? (
            <>
              <h1 className="display text-h1 text-ink-on-dark">{c.name}</h1>
              <p className="mt-3 text-[15px] text-ink-on-dark/80">
                {c.industry ?? 'Industry not set'}{c.created_at ? ` · on the platform since ${fmtDate(c.created_at, false)}` : ''}
                {c.owns_template && ' · reference company'}
              </p>
            </>
          ) : <Skeleton className="h-14 w-80 opacity-30" />}
        </div>
        {canEdit && c && !editing && <Button variant="secondary" size="sm" onClick={open}>Edit details</Button>}
      </div>
      {editing && (
        <div className="relative z-[1] mt-6 grid gap-3 rounded-2xl bg-white/95 p-4 text-espresso sm:grid-cols-[1fr_1fr_auto] sm:items-end">
          <Field label="Company name">{(id) => <Input id={id} value={name} onChange={(e) => setName(e.target.value)} />}</Field>
          <Field label="Industry">{(id) => <Input id={id} value={industry} onChange={(e) => setIndustry(e.target.value)} placeholder="e.g. Courier, E-commerce, Telecom" />}</Field>
          <div className="flex gap-2 pb-0.5">
            <Button variant="secondary" size="sm" onClick={() => setEditing(false)}>Cancel</Button>
            <Button size="sm" loading={update.pending} disabled={name.trim().length < 2} onClick={submit}>Save</Button>
          </div>
        </div>
      )}
    </section>
  )
}

/** The first five things a new company does, ticked off from its own data. */
function GettingStarted({ c, customised }: { c: S['CompanyOut']; customised: boolean }) {
  const toast = useToast()
  const [origin, setOrigin] = useState('')
  useEffect(() => setOrigin(window.location.origin), [])
  const link = `${origin}${c.customer_signup_path}`
  const steps = useMemo(() => [
    { done: c.counts.documents > 0, title: 'Upload your policies', body: 'Refund, delivery, SLA and FAQ documents: the only text the AI may cite for your company.', href: '/dashboard/knowledge-base/upload', cta: 'Upload' },
    { done: c.counts.staff > 1, title: 'Add your team', body: 'Managers, reviewers and agents, each in a department. They see only your company.', href: '/dashboard/users', cta: 'Add people' },
    { done: customised, title: 'Decide who can do what', body: 'Start from the platform defaults and change what your company needs, below.', href: '#matrix', cta: 'Review' },
    { done: c.counts.customers > 0, title: 'Share your customer sign-up link', body: 'Customers who sign up with it are your customers, and only yours.', href: null, cta: null },
    { done: c.counts.complaints > 0, title: 'Take your first complaint', body: 'Both pipelines read it against your policies; the rules decide.', href: '/dashboard/complaints/new', cta: 'Submit one' },
  ], [c, customised])
  const done = steps.filter((s) => s.done).length
  if (c.owns_template && done === steps.length) return null
  return (
    <Card tone="glass" radius="xl">
      <PanelHeader eyebrow="Getting started" title={done === steps.length ? 'Your company is set up' : `${done} of ${steps.length} done`} icon={<UserPlus size={15} aria-hidden />} />
      <div className="mb-4 flex h-1.5 overflow-hidden rounded-full bg-sand/70" aria-hidden>
        <div className="bg-verified transition-[width] duration-500" style={{ width: `${(done / steps.length) * 100}%` }} />
      </div>
      <ol className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
        {steps.map((s, i) => (
          <li key={s.title} className={cn('flex flex-col gap-2 rounded-2xl border p-4', s.done ? 'border-verified/30 bg-verified-dim/40' : 'border-line-soft bg-white/70')}>
            <span className={cn('inline-flex size-6 items-center justify-center rounded-full text-[12px] font-semibold', s.done ? 'bg-verified text-white' : 'bg-sand text-espresso-2')}>
              {s.done ? <Check size={13} aria-hidden /> : i + 1}
            </span>
            <p className="font-medium text-espresso">{s.title}</p>
            <p className="text-[12.5px] leading-relaxed text-taupe-2">{s.body}</p>
            {s.href && !s.done && (
              s.href.startsWith('#')
                ? <a href={s.href} className="mt-auto text-[13px] font-medium text-espresso underline decoration-line underline-offset-4">{s.cta}</a>
                : <Link href={s.href} className="mt-auto text-[13px] font-medium text-espresso underline decoration-line underline-offset-4">{s.cta}</Link>
            )}
            {!s.href && (
              <button type="button" className="mt-auto inline-flex items-center gap-1.5 text-left text-[13px] font-medium text-espresso underline decoration-line underline-offset-4"
                onClick={async () => { try { await navigator.clipboard.writeText(link); toast('ok', 'Sign-up link copied.') } catch { toast('err', link) } }}>
                <Copy size={12} aria-hidden /> Copy link
              </button>
            )}
          </li>
        ))}
      </ol>
      <p className="mt-4 break-all text-[12.5px] text-taupe-2">Customer sign-up link: <Mono className="text-espresso-2">{link}</Mono></p>
    </Card>
  )
}

function SharedTemplate({ ownsTemplate }: { ownsTemplate: boolean }) {
  return (
    <Card tone="glass" radius="xl">
      <PanelHeader eyebrow="Shared" title="What every company runs on" />
      <p className="max-w-[78ch] text-[13.5px] leading-relaxed text-espresso-2">
        Your complaints, customers, people, policy documents, review queue, emails, reports and audit log are your
        company&apos;s alone: every query the platform runs is filtered to your company before it reaches the database.
        The complaint taxonomy, the rule matrix, the signal lexicon and the AI prompts are one shared template, so
        every company gets the same deterministic rules checking the AI.{' '}
        {ownsTemplate
          ? 'Your dataset defined that template, so your administrators maintain it together with the platform.'
          : 'It is read-only for your company; the platform maintains it.'}
      </p>
    </Card>
  )
}
