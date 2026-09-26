'use client'

import Link from 'next/link'
import { use, useState } from 'react'
import { ArrowLeft, ArrowRight, ChevronDown, Mail, ShieldCheck, ShieldOff } from 'lucide-react'
import { AppShell } from '@/components/layout/app-shell'
import { people, type S } from '@/lib/api'
import { useApi, fmtDate, fmtRelative } from '@/lib/use-api'
import { Badge, humanise, priorityTone, statusTone } from '@/components/ui/primitives'
import { Card, PanelHeader } from '@/components/ui/surfaces'
import { KV } from '@/components/ui/data'
import { Empty, ErrorState, SkeletonRows } from '@/components/ui/feedback'
import { cn } from '@/lib/utils'
import { useAuth } from '@/lib/auth-context'
import { ManageAccount } from '@/components/app/user-admin'

const OVERSIGHT = ['manager', 'admin', 'evaluator'] as const
const CHANNEL: Record<string, string> = { WEB: 'Web form', CHAT: 'Chat with Nova', EMAIL: 'Email', UPLOAD: 'Uploaded file', PHONE: 'Phone', IMPORT: 'Dataset' }

export default function UserPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params)
  return (
    <AppShell eyebrow="Users" roles={[...OVERSIGHT]} wide>
      <Person id={id} />
    </AppShell>
  )
}

function Person({ id }: { id: string }) {
  const { user } = useAuth()
  const q = useApi(() => people.get(id), [id], true, { live: true })
  if (q.error) return <ErrorState message={q.error} onRetry={q.refresh} />
  if (!q.data) return <SkeletonRows rows={10} />
  const { person: p, complaints, activity, emails } = q.data
  const initials = p.full_name.split(/\s+/).map((w) => w[0]).slice(0, 2).join('').toUpperCase()

  return (
    <div className="flex flex-col gap-6">
      <Link href="/dashboard/users" className="inline-flex items-center gap-1.5 self-start text-[13.5px] text-taupe-2 hover:text-espresso">
        <ArrowLeft size={14} aria-hidden /> {user?.role === 'admin' ? 'Users & roles' : 'Team'}
      </Link>

      <section className="mesh-banner grain relative overflow-hidden rounded-[var(--radius-xl)] px-6 py-7 text-ink-on-dark md:px-10 md:py-9">
        <div className="relative z-[1] flex flex-wrap items-center gap-5">
          <span className="inline-flex size-16 shrink-0 items-center justify-center rounded-full bg-ivory text-[20px] font-semibold text-espresso" aria-hidden>{initials}</span>
          <div className="min-w-0">
            <p className="eyebrow mb-1.5 text-sand-2"><span className="capitalize">{p.role}</span>{p.department ? ` · ${p.department}` : ''}{p.customer_ref ? ` · ${p.customer_ref}` : ''}</p>
            <h1 className="display text-h2 text-ink-on-dark">{p.full_name}</h1>
            <p className="mt-1 text-[14.5px] text-ink-on-dark/80 [overflow-wrap:anywhere]">{p.email}</p>
          </div>
        </div>
      </section>

      <div className="grid gap-6 xl:grid-cols-[1fr_1.6fr]">
        <div className="flex flex-col gap-6">
          {user?.role === 'admin' && <ManageAccount key={`${p.role}-${p.department}-${p.is_active}`} person={p} self={p.id === user.id} onSaved={q.refresh} />}
          <Card radius="xl">
            <PanelHeader title="Account" />
            <KV rows={[
              ['Joined', fmtDate(p.created_at)],
              ['Last sign-in', p.last_login_at ? `${fmtDate(p.last_login_at)} (${fmtRelative(p.last_login_at)})` : 'Never'],
              ['Status', p.is_active ? <Badge key="a" tone="verified">Active</Badge> : <Badge key="d" tone="critical">Disabled</Badge>],
              ['Two-step sign-in', p.mfa_on ? <span key="m" className="inline-flex items-center gap-1.5 text-verified"><ShieldCheck size={14} aria-hidden /> On</span> : <span key="n" className="inline-flex items-center gap-1.5 text-taupe-2"><ShieldOff size={14} aria-hidden /> Off</span>],
              ...(q.data.phone ? [['Phone', q.data.phone] as [string, string]] : []),
              ...(q.data.tier ? [['Customer tier', humanise(q.data.tier)] as [string, string]] : []),
              ...(q.data.region ? [['Region', q.data.region] as [string, string]] : []),
              ...(p.role === 'customer'
                ? [['Complaints', `${p.complaints} raised · ${p.open_complaints} open`] as [string, string]]
                : [['Assigned to them', `${p.assigned} open complaint${p.assigned === 1 ? '' : 's'}`] as [string, string]]),
            ]} />
          </Card>

          <Card radius="xl">
            <PanelHeader title="Sign-ins and security" />
            {!activity.length ? <Empty title="Nothing yet" body="Sign-ins and security changes appear here." /> : (
              <ul className="divide-y divide-line-soft">
                {activity.map((a, i) => (
                  <li key={`${a.at}-${i}`} className="flex items-start gap-3 py-2.5">
                    <span className={cn('mt-1.5 size-2 shrink-0 rounded-full', a.ok ? 'bg-verified' : 'bg-critical')} aria-hidden />
                    <span className="min-w-0 flex-1">
                      <span className="block text-[14px] text-espresso">{a.label}</span>
                      <span className="block text-[12.5px] text-taupe-2">{fmtDate(a.at)}{a.ip_address ? ` · ${a.ip_address}` : ''}</span>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card radius="xl">
            <PanelHeader title="Emails" />
            {!emails.length ? <Empty title="No emails" body="Emails to or from this address appear here." /> : (
              <ul className="divide-y divide-line-soft">
                {emails.map((m) => (
                  <li key={m.id} className="flex items-start gap-3 py-2.5">
                    <Mail size={15} className="mt-0.5 shrink-0 text-taupe" aria-hidden />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[14px] text-espresso">{m.subject}</span>
                      <span className="block text-[12.5px] text-taupe-2">{m.direction === 'IN' ? 'Received' : 'Sent'} · {fmtRelative(m.at)}{m.complaint_ref ? ` · ${m.complaint_ref}` : ''}</span>
                    </span>
                    <Badge tone={m.status === 'SENT' || m.status === 'HANDLED' ? 'verified' : m.status === 'FAILED' ? 'critical' : 'neutral'}>{humanise(m.status)}</Badge>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>

        <Card radius="xl">
          <PanelHeader title={p.role === 'customer' ? 'Complaints and their history' : 'Complaints'} />
          {!complaints.length ? (
            <Empty title="No complaints" body={p.role === 'customer' ? 'This customer has not raised a complaint yet.' : 'Staff accounts do not raise complaints; see what is assigned to them on the complaints page.'} />
          ) : (
            <ul className="flex flex-col gap-3">
              {complaints.map((c, i) => <ComplaintHistory key={c.public_ref} c={c} open={i === 0} />)}
            </ul>
          )}
        </Card>
      </div>
    </div>
  )
}

function ComplaintHistory({ c, open: startOpen }: { c: S['PersonComplaint']; open: boolean }) {
  const [open, setOpen] = useState(startOpen)
  return (
    <li className="rounded-2xl border border-line-soft bg-white/70">
      <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open} className="flex w-full items-start gap-3 px-4 py-3.5 text-left">
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-[12.5px] text-taupe-2">{c.public_ref}</span>
            <Badge tone={statusTone(c.status)}>{humanise(c.status)}</Badge>
            {c.priority ? <Badge tone={priorityTone(c.priority)}>{c.priority}</Badge> : null}
          </span>
          <span className="mt-1 block text-[15px] font-medium text-espresso">{c.title}</span>
          <span className="mt-0.5 block text-[12.5px] text-taupe-2">
            {CHANNEL[c.channel] ?? humanise(c.channel)} · {fmtDate(c.created_at, false)}{c.category ? ` · ${c.category}` : ''}{c.department ? ` · ${c.department}` : ''}
          </span>
        </span>
        <ChevronDown size={16} className={cn('mt-1 shrink-0 text-taupe transition-transform', open && 'rotate-180')} aria-hidden />
      </button>
      {open && (
        <div className="border-t border-line-soft px-4 pb-4 pt-3">
          {!c.history.length ? <p className="text-[13.5px] text-taupe-2">No status changes recorded.</p> : (
            <ol className="relative ml-1.5 border-l border-line pl-5">
              {c.history.map((h, i) => (
                <li key={`${h.at}-${i}`} className="relative pb-3 last:pb-0">
                  <span className={cn('absolute -left-[26px] top-1 size-2.5 rounded-full border-2 border-ivory', i === c.history.length - 1 ? 'bg-espresso' : 'bg-taupe')} aria-hidden />
                  <span className="block text-[14px] text-espresso">{humanise(h.to_status)}{h.from_status ? <span className="text-taupe-2"> (from {humanise(h.from_status).toLowerCase()})</span> : null}</span>
                  <span className="block text-[12.5px] text-taupe-2">{fmtDate(h.at)}{h.reason ? ` · ${h.reason}` : ''}</span>
                </li>
              ))}
            </ol>
          )}
          <Link href={`/dashboard/complaints/${encodeURIComponent(c.public_ref)}`} className="mt-3 inline-flex items-center gap-1.5 text-[13.5px] text-espresso-2 underline underline-offset-4">
            Open the complaint <ArrowRight size={14} aria-hidden />
          </Link>
        </div>
      )}
    </li>
  )
}
