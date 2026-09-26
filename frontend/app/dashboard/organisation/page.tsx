'use client'

import { useMemo, useState } from 'react'
import Link from 'next/link'
import {
  Building2, Clock, Database, FileText, Layers, Mail, MapPin, Package, ShieldAlert, Users,
} from 'lucide-react'
import { AppShell } from '@/components/layout/app-shell'
import { organisation, type S } from '@/lib/api'
import { useApi } from '@/lib/use-api'
import { Badge, Button, Mono, humanise, priorityTone } from '@/components/ui/primitives'
import { Card } from '@/components/ui/surfaces'
import { Stat, Table, Td, Th, Tr } from '@/components/ui/data'
import { ErrorState, Skeleton, Tabs } from '@/components/ui/feedback'
import { cn } from '@/lib/utils'
import { useAuth } from '@/lib/auth-context'
import { AddDepartment } from '@/components/app/user-admin'

const STAFF = ['agent', 'reviewer', 'manager', 'admin', 'evaluator'] as const
type Tab = 'teams' | 'taxonomy' | 'sla' | 'templates' | 'datasets'

export default function OrganisationPage() {
  return (
    <AppShell eyebrow="Organisation" roles={[...STAFF]} wide>
      <Organisation />
    </AppShell>
  )
}

function Organisation() {
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'
  const q = useApi(() => organisation.get())
  const [tab, setTab] = useState<Tab>('teams')

  if (q.error) return <ErrorState title="The organisation could not be loaded" message={q.error} onRetry={q.refresh} />
  const o = q.data
  const subcategories = o?.categories.reduce((n, c) => n + c.subcategories.length, 0)

  return (
    <div className="flex min-w-0 flex-col gap-6">
      <Profile profile={o?.profile} />

      <div className="grid grid-cols-2 gap-x-6 gap-y-5 rounded-[var(--radius-xl)] border border-line bg-ivory p-5 sm:grid-cols-3 lg:grid-cols-6 md:p-6">
        <Stat label="Teams" value={o?.departments.length} icon={<Users size={12} aria-hidden />} />
        <Stat label="Categories" value={o?.categories.length} icon={<Layers size={12} aria-hidden />} />
        <Stat label="Subcategories" value={subcategories} />
        <Stat label="Reply templates" value={o?.templates.length} icon={<FileText size={12} aria-hidden />} />
        <Stat label="Policy documents" value={o ? Number(o.knowledge_base.documents ?? 0) : undefined} />
        <Stat label="Dataset complaints" value={o ? o.datasets.reduce((n, d) => n + d.total, 0) : undefined} icon={<Database size={12} aria-hidden />} />
      </div>

      {o && o.customer_mix.length > 0 && <CustomerMix mix={o.customer_mix} />}

      <div className="flex flex-wrap items-center justify-between gap-4">
        <Tabs
          value={tab}
          onChange={setTab}
          tabs={[
            { id: 'teams', label: 'Teams', count: o?.departments.length },
            { id: 'taxonomy', label: 'Categories', count: o?.categories.length },
            { id: 'sla', label: 'Service levels' },
            { id: 'templates', label: 'Reply templates', count: o?.templates.length },
            { id: 'datasets', label: 'Datasets', count: o?.datasets.length },
          ]}
        />
        {isAdmin && tab === 'teams' && (
          <AddDepartment onCreated={() => q.refresh()} />
        )}
      </div>

      {!o ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{Array.from({ length: 6 }, (_, i) => <Skeleton key={i} className="h-56" />)}</div>
      ) : tab === 'teams' ? <Teams teams={o.departments} />
        : tab === 'taxonomy' ? <Taxonomy categories={o.categories} teams={o.departments} />
        : tab === 'sla' ? <ServiceLevels rows={o.sla} categories={o.categories} />
        : tab === 'templates' ? <Templates templates={o.templates} />
        : <Datasets datasets={o.datasets} />}
    </div>
  )
}

/* ------------------------------------------------------------------ profile */

function Profile({ profile }: { profile?: S['OrganisationProfileOut'] }) {
  return (
    <section className="mesh-banner grain relative overflow-hidden rounded-[var(--radius-xl)] px-6 py-8 text-ink-on-dark md:px-10 md:py-10">
      <div className="relative z-[1] grid gap-6 lg:grid-cols-[1.4fr_1fr] lg:items-end">
        <div className="min-w-0">
          <p className="eyebrow mb-3 flex items-center gap-2 text-sand-2"><Building2 size={13} aria-hidden /> The organisation</p>
          {profile ? (
            <>
              <h1 className="display text-h1 text-ink-on-dark">{profile.name}</h1>
              <p className="mt-3 max-w-[60ch] text-[15.5px] leading-relaxed text-ink-on-dark/80">
                {profile.industry}{profile.founded_year ? ` · founded ${profile.founded_year}` : ''}
              </p>
            </>
          ) : <Skeleton className="h-14 w-80 opacity-30" />}
        </div>
        {profile && (
          <dl className="grid gap-3 text-[14px]">
            <div className="flex items-start gap-2.5"><Clock size={15} className="mt-0.5 shrink-0 text-sand-2" aria-hidden /><div><dt className="sr-only">Support hours</dt><dd>{profile.support_hours ?? 'Not set'}</dd></div></div>
            {profile.branches.length > 0 && (
              <div className="flex items-start gap-2.5"><MapPin size={15} className="mt-0.5 shrink-0 text-sand-2" aria-hidden /><div><dt className="sr-only">Branches</dt><dd className="text-ink-on-dark/85">{profile.branches.join(' · ')}</dd></div></div>
            )}
            {profile.services.length > 0 && (
              <div className="flex items-start gap-2.5"><Package size={15} className="mt-0.5 shrink-0 text-sand-2" aria-hidden /><div><dt className="sr-only">Services</dt><dd className="flex flex-wrap gap-1.5">{profile.services.map((s) => <span key={s} className="rounded-full border border-white/20 bg-white/10 px-2.5 py-0.5 text-[12.5px]">{s}</span>)}</dd></div></div>
            )}
          </dl>
        )}
      </div>
    </section>
  )
}

function CustomerMix({ mix }: { mix: S['CustomerMixOut'][] }) {
  const total = mix.reduce((n, m) => n + m.complaints, 0)
  const shades = ['bg-espresso', 'bg-rule', 'bg-warning', 'bg-taupe']
  return (
    <Card tone="glass" radius="xl">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <p className="eyebrow">Who complains</p>
        <p className="text-[13px] text-taupe">{total.toLocaleString()} complaints with a customer type</p>
      </div>
      <div className="flex h-3 overflow-hidden rounded-full bg-sand/70" aria-hidden>
        {mix.map((m, i) => <div key={m.customer_type} className={shades[i % shades.length]} style={{ width: `${(m.complaints / total) * 100}%` }} />)}
      </div>
      <ul className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        {mix.map((m, i) => (
          <li key={m.customer_type} className="flex items-center gap-2 text-[13.5px]">
            <span className={cn('size-2.5 shrink-0 rounded-full', shades[i % shades.length])} aria-hidden />
            <Link href={`/dashboard/complaints?customer_type=${encodeURIComponent(m.customer_type)}`} className="min-w-0 truncate text-espresso-2 hover:underline">{m.customer_type}</Link>
            <span className="ml-auto font-mono tnum text-taupe">{m.complaints} · {Math.round((m.complaints / total) * 100)}%</span>
          </li>
        ))}
      </ul>
    </Card>
  )
}

/* ------------------------------------------------------------------ teams */

function Teams({ teams }: { teams: S['TeamOut'][] }) {
  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      {teams.map((t) => (
        <Card key={t.code} tone="glass" radius="xl" className="flex min-w-0 flex-col gap-4">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <h2 className="font-display text-[20px] leading-tight text-espresso">{t.name}</h2>
              <Mono className="text-[11.5px] text-taupe">{t.code}</Mono>
            </div>
            <Link href={`/dashboard/complaints?department=${t.code}`} className="shrink-0 rounded-full border border-line bg-white/70 px-2.5 py-1 text-right text-[12px] leading-tight text-espresso-2 hover:bg-white" title="Open complaints / all complaints">
              <span className="font-mono tnum">{t.open_complaints}</span><span className="text-taupe"> open</span>
            </Link>
          </div>
          {t.description && <p className="text-[13.5px] leading-relaxed text-espresso-2">{t.description}</p>}

          <dl className="grid grid-cols-2 gap-3 rounded-2xl border border-line-soft bg-white/60 p-3 text-[13px]">
            <div><dt className="text-taupe">First response</dt><dd className="font-medium text-espresso">{hours(t.sla_response_hours)}</dd></div>
            <div><dt className="text-taupe">Resolution</dt><dd className="font-medium text-espresso">{hours(t.sla_resolution_hours)}</dd></div>
            {t.escalation_contact && <div className="col-span-2"><dt className="text-taupe">Escalates to</dt><dd className="flex items-center gap-1.5 text-espresso"><ShieldAlert size={13} className="text-taupe" aria-hidden />{t.escalation_contact}</dd></div>}
          </dl>

          {t.handles.length > 0 && (
            <div>
              <p className="mb-1.5 text-[12px] font-medium text-taupe">Handles</p>
              <div className="flex flex-wrap gap-1.5">{t.handles.map((h) => <Badge key={h} tone="neutral">{h}</Badge>)}</div>
            </div>
          )}

          <div className="mt-auto flex flex-wrap items-center justify-between gap-2 border-t border-line-soft pt-3 text-[13px]">
            {t.email ? <a href={`mailto:${t.email}`} className="flex min-w-0 items-center gap-1.5 text-espresso-2 hover:underline"><Mail size={13} aria-hidden /><span className="truncate">{t.email}</span></a> : <span className="text-taupe">No mailbox</span>}
            <span className="text-taupe">{t.total_complaints} total</span>
          </div>
        </Card>
      ))}
    </div>
  )
}

function hours(h?: number | null) {
  if (h == null) return 'Not set'
  return h < 1 ? `${Math.round(h * 60)} min` : `${h} hour${h === 1 ? '' : 's'}`
}

/* ------------------------------------------------------------------ taxonomy */

function Taxonomy({ categories, teams }: { categories: S['CategoryOut'][]; teams: S['TeamOut'][] }) {
  const teamName = useMemo(() => Object.fromEntries(teams.map((t) => [t.code, t.name])), [teams])
  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      {categories.map((c) => (
        <Card key={c.code} tone="glass" radius="xl" className="flex min-w-0 flex-col gap-3">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <h2 className="font-display text-[19px] leading-tight text-espresso">{c.name}</h2>
              <Mono className="text-[11.5px] text-taupe">{c.code}</Mono>
            </div>
            <Link href={`/dashboard/complaints?category=${c.code}`} className="shrink-0 font-mono text-[12.5px] tnum text-espresso-2 hover:underline">{c.complaints} complaints</Link>
          </div>
          {c.description && <p className="text-[13.5px] leading-relaxed text-espresso-2">{c.description}</p>}
          <ul className="flex flex-col gap-1 border-t border-line-soft pt-3">
            {c.subcategories.map((s) => (
              <li key={s.code} className="flex items-baseline justify-between gap-3 text-[13.5px]">
                <span className="min-w-0 text-espresso">{s.name}</span>
                <Mono className="shrink-0 text-[11px] text-taupe">{s.code}</Mono>
              </li>
            ))}
          </ul>
          {c.default_department && (
            <p className="mt-auto text-[12.5px] text-taupe">Routed by default to <span className="font-medium text-espresso-2">{teamName[c.default_department] ?? humanise(c.default_department)}</span></p>
          )}
        </Card>
      ))}
    </div>
  )
}

/* ------------------------------------------------------------------ SLA */

function ServiceLevels({ rows, categories }: { rows: S['SLARowOut'][]; categories: S['CategoryOut'][] }) {
  const name = Object.fromEntries(categories.map((c) => [c.code, c.name]))
  const defaults = rows.filter((r) => r.category == null)
  const overrides = rows.filter((r) => r.category != null)
  return (
    <div className="grid gap-6 xl:grid-cols-[1fr_1.4fr]">
      <Card tone="glass" radius="xl">
        <p className="eyebrow mb-1">Default ladder</p>
        <p className="mb-4 text-[13.5px] text-taupe">Applies to every category without an override of its own.</p>
        <Table>
          <thead><tr><Th>Priority</Th><Th>First response</Th><Th>Resolution</Th></tr></thead>
          <tbody>{defaults.map((r) => (
            <Tr key={r.priority}><Td><Badge tone={priorityTone(r.priority)}>{r.priority}</Badge></Td><Td className="tnum">{minutes(r.first_response_mins)}</Td><Td className="tnum">{minutes(r.resolution_mins)}</Td></Tr>
          ))}</tbody>
        </Table>
      </Card>
      <Card tone="glass" radius="xl">
        <p className="eyebrow mb-1">Tighter commitments</p>
        <p className="mb-4 text-[13.5px] text-taupe">Where a team promises faster than the default, the faster time applies.</p>
        <Table>
          <thead><tr><Th>Category</Th><Th>Priority</Th><Th>First response</Th><Th>Resolution</Th></tr></thead>
          <tbody>{overrides.map((r) => (
            <Tr key={`${r.category}-${r.priority}`}><Td className="min-w-0">{name[r.category!] ?? humanise(r.category!)}</Td><Td><Badge tone={priorityTone(r.priority)}>{r.priority}</Badge></Td><Td className="tnum">{minutes(r.first_response_mins)}</Td><Td className="tnum">{minutes(r.resolution_mins)}</Td></Tr>
          ))}</tbody>
        </Table>
      </Card>
    </div>
  )
}

function minutes(m: number) {
  if (m < 60) return `${m} min`
  const h = m / 60
  if (h < 24) return `${Number.isInteger(h) ? h : h.toFixed(1)} h`
  const d = h / 24
  return `${Number.isInteger(d) ? d : d.toFixed(1)} day${d === 1 ? '' : 's'}`
}

/* ------------------------------------------------------------------ templates */

function Templates({ templates }: { templates: S['TemplateOut'][] }) {
  const [open, setOpen] = useState<string | null>(templates[0]?.id ?? null)
  const current = templates.find((t) => t.id === open)
  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,320px)_1fr]">
      <ul className="flex flex-col gap-1.5" role="listbox" aria-label="Reply templates">
        {templates.map((t) => (
          <li key={t.id}>
            <button
              type="button"
              role="option"
              aria-selected={t.id === open}
              onClick={() => setOpen(t.id)}
              className={cn(
                'flex w-full items-start gap-3 rounded-2xl border px-3.5 py-3 text-left transition-colors',
                t.id === open ? 'border-espresso/25 bg-white shadow-sm' : 'border-transparent hover:bg-white/60',
              )}
            >
              <Mono className="mt-0.5 shrink-0 text-[11px] text-taupe">{t.id}</Mono>
              <span className="min-w-0">
                <span className="block text-[14px] font-medium text-espresso">{t.scenario}</span>
                {t.tone && <span className="text-[12.5px] text-taupe">{t.tone}</span>}
              </span>
            </button>
          </li>
        ))}
      </ul>
      {current && (
        <Card tone="glass" radius="xl" className="min-w-0">
          <div className="mb-4 flex flex-wrap items-center gap-2">
            <h2 className="font-display text-[22px] leading-tight text-espresso">{current.scenario}</h2>
            {current.tone && <Badge tone="neutral">{current.tone}</Badge>}
          </div>
          <div className="whitespace-pre-wrap break-words rounded-2xl border border-line-soft bg-white/80 p-5 text-[14.5px] leading-relaxed text-espresso-2">
            {current.text.split(/(\{\{[^}]+\}\})/g).map((part, i) =>
              /^\{\{[^}]+\}\}$/.test(part)
                ? <span key={i} className="rounded-md bg-sand px-1 font-mono text-[12.5px] text-espresso">{part.slice(2, -2)}</span>
                : <span key={i}>{part}</span>,
            )}
          </div>
          <p className="mt-3 text-[12.5px] text-taupe">Highlighted words are filled in from the complaint when a reply is written.</p>
        </Card>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------ datasets */

function Datasets({ datasets }: { datasets: S['DatasetBrief'][] }) {
  return (
    <Card tone="glass" radius="xl" padding="none" className="overflow-hidden">
      <div className="overflow-x-auto">
        <Table>
          <thead><tr><Th>Dataset</Th><Th>Complaints</Th><Th>Analysed</Th><Th>With answers</Th><Th /></tr></thead>
          <tbody>{datasets.map((d) => (
            <Tr key={d.dataset_tag}>
              <Td><Mono className="text-[13px] text-espresso">{d.dataset_tag}</Mono></Td>
              <Td className="tnum">{d.total}</Td>
              <Td className="tnum">{d.analysed}<span className="text-taupe"> / {d.total}</span></Td>
              <Td className="tnum">{d.labelled}</Td>
              <Td className="text-right">
                <div className="flex justify-end gap-2">
                  <Button href={`/dashboard/complaints?dataset_tag=${d.dataset_tag}`} variant="secondary" size="sm">Complaints</Button>
                  {d.labelled > 0 && <Button href={`/dashboard/benchmark/datasets/${d.dataset_tag}`} variant="secondary" size="sm">Scores</Button>}
                </div>
              </Td>
            </Tr>
          ))}</tbody>
        </Table>
      </div>
    </Card>
  )
}
