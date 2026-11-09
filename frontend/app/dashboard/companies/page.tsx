'use client'

import { useMemo, useState } from 'react'
import { Building, CheckCircle2, PauseCircle, Users } from 'lucide-react'
import { AppShell } from '@/components/layout/app-shell'
import { useAuth } from '@/lib/auth-context'
import { company, type S } from '@/lib/api'
import { useAction, useApi, fmtDate, fmtRelative } from '@/lib/use-api'
import { Badge, Button, Mono } from '@/components/ui/primitives'
import { Field, Input, PasswordInput, SearchBox, Select } from '@/components/ui/forms'
import { Stat, Table, Td, Th, Tr } from '@/components/ui/data'
import { Empty, ErrorState, Modal, SkeletonRows, useToast } from '@/components/ui/feedback'
import catalogue from '@/lib/plans.json'

type Row = S['CompanyRow']
const PLAN_STATUS: Array<[S['SubscriptionUpdate']['status'], string]> = [['trialing', 'Free trial'], ['active', 'Active'], ['past_due', 'Payment due'], ['cancelled', 'Cancelled']]
const planName = (code?: string | null) => catalogue.plans.find((p) => p.code === code)?.name ?? null
const STATUS = [['all', 'All companies'], ['active', 'Active'], ['suspended', 'Suspended']] as const

export default function CompaniesPage() {
  return (
    <AppShell eyebrow="Platform / Companies" roles={['superadmin']} wide>
      <Companies />
    </AppShell>
  )
}

/**
 * The platform's view of every company on it: who registered, how big each
 * one is and whether it may sign in. Only people in the platform organisation
 * reach it (the API refuses everyone else); a company's own administrator
 * runs their company from Company & Access and never sees this list.
 */
function Companies() {
  const { user } = useAuth()
  const toast = useToast()
  const platform = user?.role === 'superadmin'
  const canChange = platform
  const q = useApi(() => (platform ? company.all() : Promise.resolve(null)), [platform])
  const change = useAction((id: string, active: boolean, reason?: string) => company.setStatus(id, active, reason))
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState<(typeof STATUS)[number][0]>('all')
  const [pending, setPending] = useState<Row | null>(null)
  const [reason, setReason] = useState('')
  const [planning, setPlanning] = useState<Row | null>(null)

  const rows = useMemo(() => {
    const needle = search.trim().toLowerCase()
    return (q.data?.items ?? []).filter((r) =>
      (status === 'all' || (status === 'active' ? r.is_active : !r.is_active))
      && (!needle || [r.name, r.slug, r.industry ?? '', r.administrator ?? ''].some((v) => v.toLowerCase().includes(needle))),
    )
  }, [q.data, search, status])

  if (!platform) {
    return <Empty title="Only the super administrator sees every company" body="Your company's own people, policies and access are on Company & Access." className="m-8" />
  }
  if (q.error) return <ErrorState title="The companies could not be loaded" message={q.error} onRetry={q.refresh} />

  const data = q.data
  const totals = data?.items.reduce((t, r) => ({ staff: t.staff + r.staff, complaints: t.complaints + r.complaints }), { staff: 0, complaints: 0 })

  const confirm = async () => {
    if (!pending) return
    const r = await change.run(pending.id, !pending.is_active, reason.trim() || undefined)
    if (r) {
      toast('ok', r.is_active ? `${r.name} is active again.` : `${r.name} is suspended. Its people are signed out and refused.`)
      setPending(null)
      q.refresh()
    } else if (change.error) toast('err', change.error)
  }

  return (
    <div className="flex min-w-0 flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="eyebrow mb-1">Platform</p>
          <h1 className="display text-h2">Companies</h1>
          <p className="mt-2 max-w-[66ch] text-[14.5px] text-taupe-2">
            Every company on the platform, with its size and status. Companies are created here, and you hand
            their administrator the sign-in details; each company sees only its own data.
          </p>
        </div>
        <CreateCompany onCreated={q.refresh} />
      </div>

      <div className="grid grid-cols-2 gap-x-6 gap-y-5 rounded-[var(--radius-xl)] border border-line bg-ivory p-5 sm:grid-cols-4 md:p-6">
        <Stat label="Companies" value={data?.total} icon={<Building size={12} aria-hidden />} />
        <Stat label="Active" value={data?.active} tone="verified" icon={<CheckCircle2 size={12} aria-hidden />} />
        <Stat label="Suspended" value={data?.suspended} tone={data && data.suspended > 0 ? 'warning' : 'neutral'} icon={<PauseCircle size={12} aria-hidden />} />
        <Stat label="Staff across companies" value={totals?.staff} evidence={totals ? `${totals.complaints.toLocaleString()} complaints in total` : undefined} icon={<Users size={12} aria-hidden />} />
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <SearchBox value={search} onChange={setSearch} placeholder="Company, slug, industry or admin email" className="w-full sm:w-[340px]" />
        <Select value={status} onChange={(e) => setStatus(e.target.value as typeof status)} aria-label="Status" className="w-auto">
          {STATUS.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
        </Select>
        {data && <span className="text-[13px] text-taupe-2">{rows.length} of {data.total} shown</span>}
      </div>

      {!data ? <SkeletonRows rows={6} /> : !rows.length ? <Empty title="No company matches" body="Clear the search or choose All companies." /> : (
        <Table>
          <thead>
            <tr>
              <Th>Company</Th><Th>Industry</Th><Th>Status</Th><Th>Plan</Th><Th align="right">Staff</Th><Th align="right">Customers</Th>
              <Th align="right">Complaints</Th><Th align="right">Policies</Th><Th>Administrator</Th><Th>Registered</Th><Th>Last complaint</Th>
              {canChange && <Th />}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <Tr key={r.id} className={r.is_active ? undefined : 'opacity-70'}>
                <Td className="max-w-[260px]">
                  <span className="flex items-center gap-2 font-medium text-espresso">
                    <span className="truncate">{r.name}</span>
                    {r.is_reference && <Badge tone="info">Reference</Badge>}
                  </span>
                  <Mono className="text-[11.5px] text-taupe">{r.slug}</Mono>
                </Td>
                <Td className="text-[13px] text-espresso-2">{r.industry ?? '—'}</Td>
                <Td>{r.is_active ? <Badge tone="verified" dot>Active</Badge> : <Badge tone="critical" dot>Suspended</Badge>}</Td>
                <Td className="whitespace-nowrap text-[13px]">
                  {r.is_reference ? <span className="text-taupe">Not metered</span> : (
                    <button type="button" onClick={() => setPlanning(r)} className="text-left underline decoration-line underline-offset-4 hover:text-ai">
                      {planName(r.plan) ?? 'No plan'}
                      {r.subscription_status && <span className="block text-[12px] text-taupe-2">{PLAN_STATUS.find(([v]) => v === r.subscription_status)?.[1]}</span>}
                    </button>
                  )}
                </Td>
                <Td align="right" mono title={`${r.administrators} administrator(s)`}>{r.staff}</Td>
                <Td align="right" mono>{r.customers}</Td>
                <Td align="right" mono title="open / total">{r.open_complaints}<span className="text-taupe"> / {r.complaints}</span></Td>
                <Td align="right" mono>{r.documents}</Td>
                <Td className="max-w-[220px] truncate text-[13px]" title={r.administrator ?? undefined}>{r.administrator ?? '—'}</Td>
                <Td className="whitespace-nowrap text-[13px]">{fmtDate(r.created_at, false)}</Td>
                <Td className="whitespace-nowrap text-[13px] text-taupe-2">{r.last_complaint_at ? fmtRelative(r.last_complaint_at) : 'None yet'}</Td>
                {canChange && (
                  <Td align="right">
                    {r.is_reference ? <span className="text-[12px] text-taupe" title="Its dataset defines the shared template and the evaluation accounts belong to it">Always on</span> : (
                      <Button size="sm" variant={r.is_active ? 'ghost' : 'secondary'} onClick={() => { setPending(r); setReason('') }}>
                        {r.is_active ? 'Suspend' : 'Reactivate'}
                      </Button>
                    )}
                  </Td>
                )}
              </Tr>
            ))}
          </tbody>
        </Table>
      )}

      <Modal
        open={Boolean(pending)}
        onClose={() => setPending(null)}
        title={pending ? `${pending.is_active ? 'Suspend' : 'Reactivate'} ${pending.name}?` : ''}
        footer={<>
          <Button variant="secondary" onClick={() => setPending(null)}>Cancel</Button>
          <Button loading={change.pending} onClick={confirm}>{pending?.is_active ? 'Suspend company' : 'Reactivate company'}</Button>
        </>}
      >
        {pending && (
          <div className="flex flex-col gap-4">
            <p className="text-[14px] leading-relaxed text-espresso-2">
              {pending.is_active
                ? `All ${pending.staff + pending.customers} of its people are signed out at their next click and cannot sign in. Nothing is deleted: reactivating restores everything as it was.`
                : 'Its people can sign in again straight away, and everything is as they left it.'}
            </p>
            <Field label="Reason (recorded in the audit log)">
              {(id) => <Input id={id} value={reason} onChange={(e) => setReason(e.target.value)} placeholder={pending.is_active ? 'e.g. Trial ended' : 'e.g. Account settled'} />}
            </Field>
          </div>
        )}
      </Modal>

      {planning && <ChangePlan key={planning.id} company={planning} onClose={() => setPlanning(null)} onSaved={q.refresh} />}
    </div>
  )
}

/** Payment is arranged outside the application; this records the result. Audited with the reason. */
function ChangePlan({ company: row, onClose, onSaved }: { company: Row; onClose: () => void; onSaved: () => void }) {
  const toast = useToast()
  const [plan, setPlan] = useState(row.plan ?? 'growth')
  const [status, setStatus] = useState<S['SubscriptionUpdate']['status']>((row.subscription_status as S['SubscriptionUpdate']['status']) ?? 'active')
  const [cycle, setCycle] = useState<S['SubscriptionUpdate']['billing_cycle']>((row.billing_cycle as S['SubscriptionUpdate']['billing_cycle']) ?? 'monthly')
  const [periodEnd, setPeriodEnd] = useState(row.current_period_end?.slice(0, 10) ?? '')
  const [reason, setReason] = useState('')
  const save = useAction(() => company.setSubscription(row.id, {
    plan, status, billing_cycle: cycle, reason: reason.trim() || null,
    trial_ends_at: status === 'trialing' ? row.trial_ends_at : null,
    current_period_end: periodEnd ? new Date(`${periodEnd}T23:59:59Z`).toISOString() : null,
  }))

  const submit = async () => {
    const saved = await save.run()
    if (saved) { toast('ok', `${saved.name} is on ${planName(saved.plan)}.`); onSaved(); onClose() }
    else if (save.error) toast('err', save.error)
  }

  return (
    <Modal
      open
      onClose={onClose}
      title={`Plan for ${row.name}`}
      footer={<>
        <Button variant="secondary" onClick={onClose}>Cancel</Button>
        <Button loading={save.pending} onClick={submit}>Save plan</Button>
      </>}
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Plan">
          {(id) => <Select id={id} value={plan} onChange={(e) => setPlan(e.target.value)}>{catalogue.plans.map((p) => <option key={p.code} value={p.code}>{p.name}</option>)}</Select>}
        </Field>
        <Field label="Status">
          {(id) => <Select id={id} value={status} onChange={(e) => setStatus(e.target.value as typeof status)}>{PLAN_STATUS.map(([v, label]) => <option key={v} value={v}>{label}</option>)}</Select>}
        </Field>
        <Field label="Billing">
          {(id) => <Select id={id} value={cycle} onChange={(e) => setCycle(e.target.value as typeof cycle)}><option value="monthly">Monthly</option><option value="annual">Annual</option></Select>}
        </Field>
        <Field label="Paid until">
          {(id) => <Input id={id} type="date" value={periodEnd} onChange={(e) => setPeriodEnd(e.target.value)} />}
        </Field>
        <div className="sm:col-span-2">
          <Field label="Reason (recorded in the audit log)">
            {(id) => <Input id={id} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Invoice 42 paid" />}
          </Field>
        </div>
      </div>
    </Modal>
  )
}

const MIN_PASSWORD = 12
// No look-alikes (0/O, 1/l/I): this password is read off a screen and typed in.
const ALPHABET = 'ABCDEFGHJKMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789'

function generatePassword(): string {
  const bytes = new Uint32Array(14)
  crypto.getRandomValues(bytes)
  const body = Array.from(bytes, (b) => ALPHABET[b % ALPHABET.length]).join('')
  return `${body.slice(0, 7)}-${body.slice(7)}#${(bytes[0] % 90) + 10}`
}

/**
 * Companies do not sign themselves up: the super administrator creates each
 * one with its first administrator, then hands over the sign-in details. A
 * stranger cannot open a workspace and fill it with whatever they like.
 */
function CreateCompany({ onCreated }: { onCreated: () => void }) {
  const toast = useToast()
  const blank = { company_name: '', industry: '', admin_full_name: '', admin_email: '', admin_password: '', plan: 'growth', trial_days: String(catalogue.trial_days) }
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState(blank)
  const [touched, setTouched] = useState(false)
  const [done, setDone] = useState<{ created: S['CompanyCreated']; password: string } | null>(null)
  const create = useAction((body: S['CompanyCreate']) => company.create(body))
  const set = (k: keyof typeof blank, v: string) => setForm((f) => ({ ...f, [k]: v }))

  const errors = {
    company_name: form.company_name.trim().length < 2 ? 'Give the company name.' : null,
    admin_full_name: form.admin_full_name.trim().length < 2 ? 'Give the administrator’s name.' : null,
    admin_email: form.admin_email.includes('@') ? null : 'Give a valid email address.',
    admin_password: form.admin_password.length < MIN_PASSWORD ? `At least ${MIN_PASSWORD} characters.` : null,
  }
  const ready = Object.values(errors).every((e) => !e)

  const start = () => { setForm({ ...blank, admin_password: generatePassword() }); setTouched(false); setDone(null); setOpen(true) }
  const submit = async () => {
    setTouched(true)
    if (!ready) return
    const r = await create.run({
      company_name: form.company_name.trim(), industry: form.industry.trim() || null,
      admin_full_name: form.admin_full_name.trim(), admin_email: form.admin_email.trim(), admin_password: form.admin_password,
      plan: form.plan, trial_days: Number(form.trial_days),
    })
    if (r) { setDone({ created: r, password: form.admin_password }); onCreated() }
  }

  const origin = typeof window !== 'undefined' ? window.location.origin : ''
  const shareText = done ? [
    'SupportNova: your company workspace is ready',
    `Company: ${done.created.company.name}`,
    `Sign in: ${origin}${done.created.sign_in_path}`,
    `Email: ${done.created.admin_email}`,
    `Temporary password: ${done.password}`,
    'Please change the password after your first sign-in (Profile & security).',
    `Your customers sign up at: ${origin}${done.created.customer_signup_path}`,
  ].join('\n') : ''
  const copy = async () => {
    try { await navigator.clipboard.writeText(shareText); toast('ok', 'Sign-in details copied. Send them to the company administrator.') }
    catch { toast('err', 'The browser refused the copy. Select the text and copy it by hand.') }
  }

  return (
    <>
      <Button onClick={start} icon={<Building size={15} aria-hidden />}>Create company</Button>
      <Modal
        open={open}
        onClose={() => setOpen(false)}
        width={560}
        title={done ? `${done.created.company.name} is ready` : 'Create a company'}
        footer={done ? (
          <>
            <Button variant="secondary" onClick={() => setOpen(false)}>Done</Button>
            <Button onClick={copy}>Copy sign-in details</Button>
          </>
        ) : (
          <>
            <Button variant="secondary" onClick={() => setOpen(false)}>Cancel</Button>
            <Button loading={create.pending} disabled={touched && !ready} onClick={submit}>Create company</Button>
          </>
        )}
      >
        {done ? (
          <div className="flex flex-col gap-3">
            <p className="text-[14px] leading-relaxed text-espresso-2">
              Share these details with the company&apos;s administrator. The password is shown only now and cannot be
              read back later.
            </p>
            <textarea readOnly value={shareText} rows={8} aria-label="Sign-in details to share"
              onFocus={(e) => e.currentTarget.select()}
              className="w-full resize-none rounded-[var(--radius-md)] border border-line bg-ivory p-3 font-mono text-[12.5px] leading-relaxed text-espresso" />
          </div>
        ) : (
          <div className="flex flex-col gap-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Company name" required error={touched ? errors.company_name : null}>
                {(id) => <Input id={id} value={form.company_name} onChange={(e) => set('company_name', e.target.value)} autoFocus />}
              </Field>
              <Field label="Industry" hint="Courier, e-commerce, telecom...">
                {(id) => <Input id={id} value={form.industry} onChange={(e) => set('industry', e.target.value)} />}
              </Field>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Plan">
                {(id) => <Select id={id} value={form.plan} onChange={(e) => set('plan', e.target.value)}>{catalogue.plans.map((p) => <option key={p.code} value={p.code}>{p.name}</option>)}</Select>}
              </Field>
              <Field label="Free trial" hint="0 starts the plan as paid.">
                {(id) => (
                  <Select id={id} value={form.trial_days} onChange={(e) => set('trial_days', e.target.value)}>
                    {['0', '7', '14', '30', '60', '90'].map((d) => <option key={d} value={d}>{d === '0' ? 'No trial' : `${d} days`}</option>)}
                  </Select>
                )}
              </Field>
            </div>
            <p className="eyebrow -mb-1">Its first administrator</p>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Full name" required error={touched ? errors.admin_full_name : null}>
                {(id) => <Input id={id} value={form.admin_full_name} onChange={(e) => set('admin_full_name', e.target.value)} />}
              </Field>
              <Field label="Work email" required error={touched ? errors.admin_email : null}>
                {(id) => <Input id={id} type="email" value={form.admin_email} onChange={(e) => set('admin_email', e.target.value)} />}
              </Field>
            </div>
            <Field label="Temporary password" required error={touched ? errors.admin_password : null}
              hint="Generated for you; they change it after the first sign-in.">
              {(id) => (
                <div className="flex gap-2">
                  <PasswordInput id={id} value={form.admin_password} onChange={(e) => set('admin_password', e.target.value)} className="flex-1" />
                  <Button type="button" variant="secondary" size="sm" onClick={() => set('admin_password', generatePassword())}>Generate</Button>
                </div>
              )}
            </Field>
            {touched && create.error && <p role="alert" className="rounded-[var(--radius-md)] border border-critical/30 bg-critical-dim px-3.5 py-2.5 text-[13.5px] text-espresso">{create.error}</p>}
          </div>
        )}
      </Modal>
    </>
  )
}
