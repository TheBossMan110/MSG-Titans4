'use client'

import { useState } from 'react'
import { CheckCircle2, Eye, Inbox, RefreshCw, Send, XCircle } from 'lucide-react'
import { AppShell } from '@/components/layout/app-shell'
import { useAuth } from '@/lib/auth-context'
import { mail } from '@/lib/api'
import { useAction, useApi, fmtRelative } from '@/lib/use-api'
import { Badge, Button } from '@/components/ui/primitives'
import { Card, PanelHeader } from '@/components/ui/surfaces'
import { Checkbox, Field, Input, Textarea } from '@/components/ui/forms'
import { Modal, useToast } from '@/components/ui/feedback'
import { Mailbox } from '@/components/app/email-views'

const STAFF = ['agent', 'reviewer', 'manager', 'admin', 'evaluator'] as const
const OPERATORS = ['manager', 'admin', 'evaluator']

export default function EmailPage() {
  return (
    <AppShell eyebrow="Email" roles={[...STAFF]} wide>
      <EmailInbox />
    </AppShell>
  )
}

function EmailInbox() {
  const { user } = useAuth()
  const toast = useToast()
  const operator = Boolean(user && OPERATORS.includes(user.role))
  const status = useApi(() => mail.status())
  const [refresh, setRefresh] = useState(0)
  const [simOpen, setSimOpen] = useState(false)
  const [preview, setPreview] = useState<string | null>(null)
  const poll = useAction(() => mail.poll())
  const s = status.data

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="eyebrow mb-1">Complaints by email</p>
          <h1 className="display text-h2">Support mailbox</h1>
          <p className="mt-2 max-w-[62ch] text-[14.5px] text-taupe-2">
            Customers email <span className="font-medium text-espresso">{s?.address ?? 'the support address'}</span>. Each email is read by the AI:
            a complaint is registered and analysed like any other, and the customer gets a reply written for their email, with the reference and a link to follow it.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" size="sm" icon={<Eye size={14} aria-hidden />} onClick={async () => { const r = await mail.preview(); setPreview(r.html) }}>Reply template</Button>
          {operator && <Button variant="secondary" size="sm" icon={<Send size={14} aria-hidden />} onClick={() => setSimOpen(true)}>Simulate an email</Button>}
          {operator && <Button size="sm" icon={<RefreshCw size={14} aria-hidden />} loading={poll.pending} disabled={!s?.receiving}
            onClick={async () => { const r = await poll.run(); if (r) { toast('ok', `Checked the inbox: ${String(r.fetched ?? 0)} new.`); setRefresh((n) => n + 1); status.refresh() } else if (poll.error) toast('err', poll.error) }}>Check inbox now</Button>}
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <StatusCard ok={s?.receiving} title="Receiving" value={s ? (s.receiving ? 'Connected' : 'Not connected') : undefined}
          note={s?.receiving ? (s.last_poll_at ? `Checked ${fmtRelative(s.last_poll_at)}` : 'Checked every minute') : 'Add the Gmail App Password to backend/.env (EMAIL_APP_PASSWORD).'} />
        <StatusCard ok={Boolean(s?.sending)} title="Sending replies" value={s ? (s.sending === 'smtp' ? 'From Gmail' : s.sending === 'resend' ? 'Through Resend' : 'Not connected') : undefined}
          note={s?.sending ? 'Replies go out automatically' : 'Replies are written and stored, but not sent'} />
        <StatusCard ok={!s?.last_error} title="Last check" value={s ? (s.last_error ? 'Problem' : 'OK') : undefined} note={s?.last_error ?? 'No errors'} />
      </div>

      {s && !s.receiving && operator && (
        <Card tone="sand" radius="xl">
          <PanelHeader title="Connect the Gmail mailbox" />
          <ol className="list-decimal space-y-1.5 pl-5 text-[14px] leading-relaxed text-espresso-2">
            <li>Sign in to <span className="font-medium">{s.address}</span> and turn on <b>2-Step Verification</b> (Google Account → Security).</li>
            <li>Open <b>App passwords</b> (Google Account → Security → App passwords), create one called “SupportNova”, copy the 16 letters.</li>
            <li>Put it in <span className="font-mono text-[13px]">backend/.env</span> as <span className="font-mono text-[13px]">EMAIL_APP_PASSWORD=</span> and restart the backend.</li>
          </ol>
          <p className="mt-3 text-[13px] text-taupe-2">Resend cannot receive for, or send as, a gmail.com address; it is used only if you set <span className="font-mono">RESEND_FROM</span> to an address on a domain you verified with Resend.{s.resend_key_present ? ' Your Resend key is already saved.' : ''}</p>
        </Card>
      )}

      <Mailbox staff refreshKey={refresh} />

      {simOpen && <Simulate onClose={() => setSimOpen(false)} onDone={() => { setSimOpen(false); setRefresh((n) => n + 1) }} canSend={Boolean(s?.sending)} />}
      {preview && (
        <Modal open title="The reply customers receive" onClose={() => setPreview(null)} width={760}>
          <iframe title="Email template preview" srcDoc={preview} sandbox="" className="h-[70vh] w-full rounded-xl border border-line-soft bg-white" />
        </Modal>
      )}
    </div>
  )
}

function StatusCard({ ok, title, value, note }: { ok?: boolean; title: string; value?: string; note: string }) {
  return (
    <Card tone="glass" padding="sm" radius="lg" className="flex items-start gap-3">
      <span className={ok ? 'mt-0.5 text-verified' : 'mt-0.5 text-warning'}>{ok ? <CheckCircle2 size={18} aria-hidden /> : <XCircle size={18} aria-hidden />}</span>
      <div className="min-w-0"><p className="eyebrow">{title}</p><p className="mt-1 text-[15px] font-medium text-espresso">{value ?? '…'}</p><p className="text-[12.5px] text-taupe-2 [overflow-wrap:anywhere]">{note}</p></div>
    </Card>
  )
}

function Simulate({ onClose, onDone, canSend }: { onClose: () => void; onDone: () => void; canSend: boolean }) {
  const toast = useToast()
  const [form, setForm] = useState({ from_address: '', from_name: '', subject: '', body: '', send_reply: false })
  const run = useAction(() => mail.simulate({ ...form, from_name: form.from_name || null }))
  return (
    <Modal open title="Simulate an email" onClose={onClose}
      footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button loading={run.pending} disabled={!form.from_address || !form.body.trim()} icon={<Inbox size={14} aria-hidden />}
        onClick={async () => { const r = await run.run(); if (r) { toast('ok', r.complaint_ref ? `Registered as ${r.complaint_ref}.` : 'Handled.'); onDone() } else if (run.error) toast('err', run.error) }}>Put it through</Button></>}>
      <div className="flex flex-col gap-3">
        <p className="text-[13.5px] text-taupe-2">Runs exactly what happens when a real email arrives — triage, complaint, AI reply — without Gmail. Takes about 20–40 seconds for a complaint.</p>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="From (email)">{(id) => <Input id={id} type="email" value={form.from_address} onChange={(e) => setForm((f) => ({ ...f, from_address: e.target.value }))} placeholder="ayesha@example.com" />}</Field>
          <Field label="Name">{(id) => <Input id={id} value={form.from_name} onChange={(e) => setForm((f) => ({ ...f, from_name: e.target.value }))} placeholder="Ayesha Khan" />}</Field>
        </div>
        <Field label="Subject">{(id) => <Input id={id} value={form.subject} onChange={(e) => setForm((f) => ({ ...f, subject: e.target.value }))} placeholder="Parcel CN-77451209 not delivered" />}</Field>
        <Field label="Email">{(id) => <Textarea id={id} rows={6} value={form.body} onChange={(e) => setForm((f) => ({ ...f, body: e.target.value }))} placeholder="Write it the way a customer would." />}</Field>
        <Checkbox label={canSend ? 'Also send the reply to this address for real' : 'Also send the reply (connect sending first)'} checked={form.send_reply} disabled={!canSend} onChange={(e) => setForm((f) => ({ ...f, send_reply: e.target.checked }))} />
        {!canSend && <Badge tone="neutral">Replies will be written and stored, not sent</Badge>}
      </div>
    </Modal>
  )
}
