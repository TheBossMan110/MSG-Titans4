'use client'

import { useState } from 'react'
import { MotionToggle } from '@/components/ui/motion-toggle'
import { useRouter } from 'next/navigation'
import { AppShell } from '@/components/layout/app-shell'
import { useAuth } from '@/lib/auth-context'
import { admin, system, type S } from '@/lib/api'
import { useApi, useAction, fmtDate, fmtMinutes } from '@/lib/use-api'
import { Badge, Button, Mono, humanise } from '@/components/ui/primitives'
import { Card, PanelHeader } from '@/components/ui/surfaces'
import { Field, Input, Select, Textarea, Checkbox } from '@/components/ui/forms'
import { KV, Table, Th, Td, Tr } from '@/components/ui/data'
import { Empty, ErrorState, Modal, SkeletonRows, Tabs, useToast } from '@/components/ui/feedback'
import { cn } from '@/lib/utils'

type Tab = 'account' | 'system' | 'config' | 'lexicon' | 'sla'

export default function SettingsPage() {
  return (
    <AppShell eyebrow="Settings" wide>
      <Settings />
    </AppShell>
  )
}

function Settings() {
  const { user } = useAuth()
  const [tab, setTab] = useState<Tab>('account')
  const oversight = user && ['manager', 'admin', 'evaluator'].includes(user.role)
  const tabs: Array<{ id: Tab; label: string }> = [{ id: 'account', label: 'Account' }, { id: 'system', label: 'System' }]
  if (oversight) tabs.push({ id: 'config', label: 'Configuration' }, { id: 'lexicon', label: 'Lexicon' }, { id: 'sla', label: 'SLA policies' })
  return (
    <div className="flex flex-col gap-6">
      <div><p className="eyebrow mb-1">Settings</p><h1 className="display text-h2">Account and configuration</h1></div>
      <Tabs value={tab} onChange={setTab} tabs={tabs} />
      {tab === 'account' && <Account />}
      {tab === 'system' && <SystemInfo />}
      {tab === 'config' && oversight && <Config />}
      {tab === 'lexicon' && oversight && <Lexicon />}
      {tab === 'sla' && oversight && <Sla />}
    </div>
  )
}

/* ------------------------------------------------------------------ account */

function Account() {
  const { user, logout } = useAuth()
  const router = useRouter()
  if (!user) return null
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card>
        <PanelHeader title="You" />
        <KV rows={[['Name', user.full_name], ['Email', user.email], ['Role', <Badge key="r" tone="ink">{user.role}</Badge>], ['Department', user.department?.name ?? '—'], ['Last sign-in', fmtDate(user.last_login_at)], ['Since', fmtDate(user.created_at, false)]]} />
        <Button variant="secondary" size="sm" className="mt-6" onClick={async () => { await logout(); router.replace('/login') }}>Sign out</Button>
      </Card>
      <Card>
        <PanelHeader title="Password and sign-in security" />
        <p className="text-[14px] leading-relaxed text-espresso-2">
          Change your password, turn on two-step sign-in with an authenticator app, see every device
          you are signed in on and sign them out, and review recent sign-ins — all on one page.
        </p>
        <Button href="/dashboard/profile" className="mt-5">Open profile &amp; security</Button>
      </Card>
      <Card>
        <PanelHeader title="Display" />
        <p className="mb-4 text-[14px] leading-relaxed text-espresso-2">Animations are on by default. Switch this on if motion is uncomfortable; it applies to the whole site on this device.</p>
        <MotionToggle />
      </Card>
    </div>
  )
}

/* ------------------------------------------------------------------ system */

function SystemInfo() {
  const h = useApi(() => system.health())
  const v = useApi(() => system.version())
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card>
        <PanelHeader title="Health" aside={h.data && <Badge tone={h.data.status === 'ok' || h.data.status === 'healthy' ? 'verified' : 'warning'} dot>{h.data.status}</Badge>} />
        {h.error ? <ErrorState message={h.error} onRetry={h.refresh} /> : !h.data ? <SkeletonRows rows={5} /> : <KV rows={[['Application', `${h.data.app} ${h.data.version}`], ['Environment', h.data.environment], ['Database', h.data.database], ['Knowledge base documents', h.data.knowledge_base_documents], ['Active rules', h.data.active_rules], ['GenAI', <span key="g" className="flex items-center gap-2"><Mono>{h.data.llm_primary}</Mono><Badge tone={h.data.llm_configured ? 'verified' : 'warning'}>{h.data.llm_configured ? 'configured' : 'not configured · rules alone'}</Badge></span>], ['Checked', fmtDate(h.data.timestamp)]]} />}
      </Card>
      <Card>
        <PanelHeader title="Versions" eyebrow="What every decision is stamped with" />
        {v.error ? <ErrorState message={v.error} onRetry={v.refresh} /> : !v.data ? <SkeletonRows rows={5} /> : <KV rows={[['App', v.data.app_version], ['Ruleset', <Mono key="r">{v.data.ruleset_version}</Mono>], ['Knowledge base', <Mono key="k">{v.data.knowledge_base_version ?? '—'}</Mono>], ['Primary model', <Mono key="m">{v.data.llm_primary_provider} · {v.data.llm_primary_model}</Mono>], ['Fallback', v.data.llm_fallback_provider ?? 'none'], ['Embeddings', v.data.embedding_model ?? 'none (lexical search only)'], ['Active prompts', <span key="p" className="flex flex-wrap gap-1">{Object.entries(v.data.active_prompts).map(([n, ver]) => <Badge key={n}><Mono>{n}@{ver}</Mono></Badge>)}</span>], ['Policy precedence', <span key="pp" className="text-[12.5px]">{v.data.policy_precedence.join(' › ')}</span>]]} />}
      </Card>
    </div>
  )
}

/* ------------------------------------------------------------------ config */

function Config() {
  const { user } = useAuth()
  const toast = useToast()
  const q = useApi(() => admin.config())
  const [editing, setEditing] = useState<S['ConfigEntryOut'] | null>(null)
  const [value, setValue] = useState('')
  const [reason, setReason] = useState('')
  const save = useAction((k: string, v: unknown, r?: string) => admin.updateConfig(k, v, r))
  const isAdmin = user?.role === 'admin'
  const open = (e: S['ConfigEntryOut']) => { setEditing(e); setValue(typeof e.value === 'string' ? e.value : JSON.stringify(e.value, null, 2)); setReason('') }
  const submit = async () => {
    if (!editing) return
    let parsed: unknown = value
    try { parsed = JSON.parse(value) } catch { /* keep as string */ }
    const r = await save.run(editing.key, parsed, reason || undefined)
    if (r) { toast('ok', `${r.key} is now version ${r.version}.`); setEditing(null); q.refresh() } else if (save.error) toast('err', save.error)
  }
  return (
    <div className="flex flex-col gap-4">
      <p className="max-w-[64ch] text-[13.5px] text-espresso-2">Thresholds, weights and switches the pipelines read at run time. Changing one is versioned and audited with a reason. Structural keys are shown but locked.</p>
      {q.error ? <ErrorState message={q.error} onRetry={q.refresh} /> : q.loading && !q.data ? <SkeletonRows rows={8} /> : (
        <Table dense>
          <thead><tr><Th>Key</Th><Th>Value</Th><Th>Description</Th><Th align="right">v</Th><Th>Updated</Th><Th /></tr></thead>
          <tbody>{(q.data ?? []).map((e) => <Tr key={e.key}><Td mono>{e.key}</Td><Td mono className="max-w-[240px] truncate" title={JSON.stringify(e.value)}>{typeof e.value === 'object' ? JSON.stringify(e.value) : String(e.value)}</Td><Td className="max-w-[360px] text-[12.5px] text-taupe-2">{e.description}</Td><Td align="right" mono>{e.version}</Td><Td className="whitespace-nowrap text-[12px] text-taupe-2">{e.updated_by ?? '—'}{e.updated_at ? ` · ${fmtDate(e.updated_at)}` : ''}</Td><Td align="right">{isAdmin && e.editable !== false ? <Button size="sm" variant="ghost" onClick={() => open(e)}>Edit</Button> : <Badge>locked</Badge>}</Td></Tr>)}</tbody>
        </Table>
      )}
      <Modal open={Boolean(editing)} onClose={() => setEditing(null)} title={<>Edit <Mono>{editing?.key}</Mono></>} footer={<><Button variant="secondary" onClick={() => setEditing(null)}>Cancel</Button><Button loading={save.pending} onClick={submit}>Save</Button></>}>
        {editing && <div className="flex flex-col gap-4"><p className="text-[13px] text-taupe-2">{editing.description}</p><Field label="Value" hint="JSON is parsed; anything else is kept as text.">{(id) => <Textarea id={id} value={value} onChange={(e) => setValue(e.target.value)} rows={4} className="min-h-[90px] font-mono text-[12.5px]" />}</Field><Field label="Reason">{(id) => <Input id={id} value={reason} onChange={(e) => setReason(e.target.value)} />}</Field>{save.error && <p className="text-[13px] text-critical">{save.error}</p>}</div>}
      </Modal>
    </div>
  )
}

/* ------------------------------------------------------------------ lexicon */

function Lexicon() {
  const { user } = useAuth()
  const toast = useToast()
  const [signal, setSignal] = useState('')
  const q = useApi(() => admin.lexicon(signal || undefined), [signal])
  const [form, setForm] = useState<S['LexiconTermIn']>({ signal_key: '', term: '', match_type: 'PHRASE', weight: 1, is_active: true })
  const add = useAction((b: S['LexiconTermIn']) => admin.addTerm(b))
  const edit = useAction((id: string, b: S['LexiconTermUpdateIn']) => admin.editTerm(id, b))
  const remove = useAction((id: string) => admin.removeTerm(id))
  const isAdmin = user?.role === 'admin'
  const signals = Array.from(new Set((q.data ?? []).map((t) => t.signal_key))).sort()
  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
      <div className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center gap-3">
          <Input value={signal} onChange={(e) => setSignal(e.target.value)} placeholder="Filter by signal key" aria-label="Signal key" className="w-full font-mono sm:w-[300px]" list="signals" />
          <datalist id="signals">{signals.map((s) => <option key={s} value={s} />)}</datalist>
          <span className="text-[13px] text-taupe-2">{q.data?.length ?? 0} terms</span>
        </div>
        <p className="max-w-[64ch] text-[13px] text-taupe-2">Terms are authored from policy and taxonomy text, never harvested from the complaints. Analytics-only signals are recorded but never decide anything.</p>
        {q.error ? <ErrorState message={q.error} onRetry={q.refresh} /> : q.loading && !q.data ? <SkeletonRows rows={8} /> : !q.data?.length ? <Empty title="No terms" /> : (
          <Table dense>
            <thead><tr><Th>Signal</Th><Th>Term</Th><Th>Match</Th><Th align="right">Weight</Th><Th>Flags</Th><Th /></tr></thead>
            <tbody>{q.data.map((t) => <Tr key={t.id} className={cn(!t.is_active && 'opacity-50')}><Td mono>{t.signal_key}</Td><Td className="max-w-[320px]"><span title={t.description ?? ''}>{t.term}</span></Td><Td><Badge>{t.match_type}</Badge></Td><Td align="right" mono>{t.weight ?? '—'}</Td><Td><span className="flex gap-1">{t.analytics_only && <Badge tone="info">analytics only</Badge>}{!t.is_active && <Badge>inactive</Badge>}</span></Td><Td align="right">{isAdmin && <span className="flex justify-end gap-1"><Button size="sm" variant="ghost" loading={edit.pending} onClick={async () => { const r = await edit.run(t.id, { is_active: !t.is_active }); if (r) q.refresh(); else if (edit.error) toast('err', edit.error) }}>{t.is_active ? 'Disable' : 'Enable'}</Button><Button size="sm" variant="ghost" className="text-critical" loading={remove.pending} onClick={async () => { if (!confirm(`Remove "${t.term}" from ${t.signal_key}?`)) return; const r = await remove.run(t.id); if (r) { toast('ok', 'Removed.'); q.refresh() } else if (remove.error) toast('err', remove.error) }}>Remove</Button></span>}</Td></Tr>)}</tbody>
          </Table>
        )}
      </div>
      {isAdmin && (
        <Card className="self-start">
          <PanelHeader title="Add a term" />
          <form className="flex flex-col gap-3" onSubmit={async (e) => { e.preventDefault(); const r = await add.run(form); if (r) { toast('ok', `Added “${r.term}” to ${r.signal_key}.`); setForm((f) => ({ ...f, term: '' })); q.refresh() } else if (add.error) toast('err', add.error) }}>
            <Field label="Signal key">{(id) => <Input id={id} value={form.signal_key} onChange={(e) => setForm((f) => ({ ...f, signal_key: e.target.value }))} className="font-mono" list="signals" required />}</Field>
            <Field label="Term">{(id) => <Input id={id} value={form.term} onChange={(e) => setForm((f) => ({ ...f, term: e.target.value }))} required />}</Field>
            <div className="grid grid-cols-2 gap-2">
              <Field label="Match">{(id) => <Select id={id} value={form.match_type ?? 'PHRASE'} onChange={(e) => setForm((f) => ({ ...f, match_type: e.target.value }))}>{['PHRASE', 'WORD', 'REGEX'].map((m) => <option key={m} value={m}>{m}</option>)}</Select>}</Field>
              <Field label="Weight">{(id) => <Input id={id} type="number" step="0.1" value={form.weight ?? ''} onChange={(e) => setForm((f) => ({ ...f, weight: e.target.value === '' ? null : Number(e.target.value) }))} />}</Field>
            </div>
            <Field label="Description">{(id) => <Input id={id} value={form.description ?? ''} onChange={(e) => setForm((f) => ({ ...f, description: e.target.value || null }))} />}</Field>
            <Checkbox label="Active" checked={form.is_active ?? true} onChange={(e) => setForm((f) => ({ ...f, is_active: e.target.checked }))} />
            {add.error && <p className="text-[13px] text-critical">{add.error}</p>}
            <Button type="submit" size="sm" loading={add.pending}>Add term</Button>
          </form>
        </Card>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------ SLA */

function Sla() {
  const { user } = useAuth()
  const toast = useToast()
  const q = useApi(() => admin.sla())
  const [editing, setEditing] = useState<S['SLAPolicyOut'] | null>(null)
  const [form, setForm] = useState<S['SLAPolicyUpdateIn']>({})
  const save = useAction((id: string, b: S['SLAPolicyUpdateIn']) => admin.updateSla(id, b))
  const isAdmin = user?.role === 'admin'
  return (
    <div className="flex flex-col gap-4">
      <p className="max-w-[64ch] text-[13.5px] text-espresso-2">First-response and resolution targets by category and priority. The tighter of the two applies. The sweep marks breaches and at-risk items against these.</p>
      {q.error ? <ErrorState message={q.error} onRetry={q.refresh} /> : q.loading && !q.data ? <SkeletonRows rows={6} /> : (
        <Table dense>
          <thead><tr><Th>Category</Th><Th>Priority</Th><Th align="right">First response</Th><Th align="right">Resolution</Th><Th align="right">Risk at</Th><Th>Active</Th><Th /></tr></thead>
          <tbody>{(q.data ?? []).map((p) => <Tr key={p.id}><Td>{p.category ? humanise(p.category) : <span className="text-taupe">any</span>}</Td><Td>{p.priority_code ? <Badge>{p.priority_code}</Badge> : <span className="text-taupe">any</span>}</Td><Td align="right" mono>{fmtMinutes(p.first_response_mins)}</Td><Td align="right" mono>{fmtMinutes(p.resolution_mins)}</Td><Td align="right" mono>{p.risk_threshold_pct != null ? `${p.risk_threshold_pct}%` : '—'}</Td><Td><Badge tone={p.is_active !== false ? 'verified' : 'neutral'}>{p.is_active !== false ? 'yes' : 'no'}</Badge></Td><Td align="right">{isAdmin && <Button size="sm" variant="ghost" onClick={() => { setEditing(p); setForm({ first_response_mins: p.first_response_mins, resolution_mins: p.resolution_mins, risk_threshold_pct: p.risk_threshold_pct ?? null, is_active: p.is_active ?? true, reason: '' }) }}>Edit</Button>}</Td></Tr>)}</tbody>
        </Table>
      )}
      <Modal open={Boolean(editing)} onClose={() => setEditing(null)} title="Edit SLA policy" footer={<><Button variant="secondary" onClick={() => setEditing(null)}>Cancel</Button><Button loading={save.pending} onClick={async () => { if (!editing) return; const r = await save.run(editing.id, form); if (r) { toast('ok', 'SLA policy saved.'); setEditing(null); q.refresh() } else if (save.error) toast('err', save.error) }}>Save</Button></>}>
        {editing && <div className="grid gap-3 sm:grid-cols-2">
          <Field label="First response (minutes)">{(id) => <Input id={id} type="number" min={1} value={form.first_response_mins ?? ''} onChange={(e) => setForm((f) => ({ ...f, first_response_mins: Number(e.target.value) }))} />}</Field>
          <Field label="Resolution (minutes)">{(id) => <Input id={id} type="number" min={1} value={form.resolution_mins ?? ''} onChange={(e) => setForm((f) => ({ ...f, resolution_mins: Number(e.target.value) }))} />}</Field>
          <Field label="Risk threshold (%)">{(id) => <Input id={id} type="number" min={1} max={100} value={form.risk_threshold_pct ?? ''} onChange={(e) => setForm((f) => ({ ...f, risk_threshold_pct: e.target.value === '' ? null : Number(e.target.value) }))} />}</Field>
          <div className="flex items-end pb-3"><Checkbox label="Active" checked={form.is_active ?? true} onChange={(e) => setForm((f) => ({ ...f, is_active: e.target.checked }))} /></div>
          <Field label="Reason" className="sm:col-span-2">{(id) => <Input id={id} value={form.reason ?? ''} onChange={(e) => setForm((f) => ({ ...f, reason: e.target.value || null }))} />}</Field>
          {save.error && <p className="text-[13px] text-critical sm:col-span-2">{save.error}</p>}
        </div>}
      </Modal>
    </div>
  )
}
