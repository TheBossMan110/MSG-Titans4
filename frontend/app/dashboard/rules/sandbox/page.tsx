'use client'

import { useState } from 'react'
import Link from 'next/link'
import { AppShell } from '@/components/layout/app-shell'
import { admin, type S } from '@/lib/api'
import { useAction } from '@/lib/use-api'
import { Badge, Button, Mono, humanise, escalationTone, priorityTone, urgencyTone } from '@/components/ui/primitives'
import { Card, PanelHeader } from '@/components/ui/surfaces'
import { Field, Input, Textarea } from '@/components/ui/forms'
import { KV } from '@/components/ui/data'
import { ErrorState } from '@/components/ui/feedback'
import { cn } from '@/lib/utils'

export default function SandboxPage() {
  return (
    <AppShell eyebrow="Rules / Sandbox" roles={['manager', 'admin', 'evaluator']} wide>
      <Sandbox />
    </AppShell>
  )
}

/**
 * The live-modification demonstration. Run a text through the engine, keep
 * the result on the left, change a rule on its page, come back and run again:
 * the right-hand column shows what changed. Nothing is persisted; this is
 * POST /api/admin/rules/test.
 */
function Sandbox() {
  const [form, setForm] = useState<S['RuleTestIn']>({ title: 'Sandbox', description: '', product: null, order_ref: null, amount: null })
  const [before, setBefore] = useState<S['RuleTestOut'] | null>(null)
  const [after, setAfter] = useState<S['RuleTestOut'] | null>(null)
  const run = useAction((b: S['RuleTestIn']) => admin.testRules(b))
  const set = <K extends keyof S['RuleTestIn']>(k: K, v: S['RuleTestIn'][K]) => setForm((f) => ({ ...f, [k]: v }))

  const go = async () => {
    const r = await run.run(form)
    if (!r) return
    if (!before) setBefore(r)
    else setAfter(r)
  }

  return (
    <div className="flex flex-col gap-6">
      <div><p className="eyebrow mb-1">Pipeline 2, live</p><h1 className="display text-h2">Rule sandbox</h1><p className="mt-3 max-w-[64ch] text-[14.5px] text-espresso-2">Run a complaint through the rule engine as it is configured right now. Keep that as the baseline, change a rule in the <Link href="/dashboard/rules" className="underline decoration-line underline-offset-4">matrix</Link>, and run again: the second column shows the difference. Nothing is saved.</p></div>

      <Card>
        <div className="grid gap-4 lg:grid-cols-[1fr_260px]">
          <Field label="Complaint text" required>{(id) => <Textarea id={id} value={form.description} onChange={(e) => set('description', e.target.value)} rows={6} placeholder="Paste or write a complaint…" />}</Field>
          <div className="flex flex-col gap-3">
            <Field label="Order reference">{(id) => <Input id={id} value={form.order_ref ?? ''} onChange={(e) => set('order_ref', e.target.value || null)} className="font-mono" />}</Field>
            <Field label="Amount">{(id) => <Input id={id} type="number" value={form.amount ?? ''} onChange={(e) => set('amount', e.target.value === '' ? null : Number(e.target.value))} />}</Field>
            <Field label="Product">{(id) => <Input id={id} value={form.product ?? ''} onChange={(e) => set('product', e.target.value || null)} />}</Field>
          </div>
        </div>
        {run.error && <ErrorState message={run.error} className="mt-4" />}
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <Button loading={run.pending} disabled={form.description.trim().length < 5} onClick={go}>{before ? 'Run again' : 'Run'}</Button>
          {before && <Button variant="ghost" size="sm" onClick={() => { setBefore(null); setAfter(null) }}>Reset baseline</Button>}
          {before && !after && <span className="text-[13px] text-taupe-2">Baseline kept. Change a rule, then run again.</span>}
        </div>
      </Card>

      {before && (
        <div className="grid gap-6 lg:grid-cols-2">
          <Result title="Baseline" r={before} />
          {after ? <Result title="After your change" r={after} diff={before} /> : <Card tone="ghost" className="flex items-center justify-center text-center text-[14px] text-taupe-2"><p>The second run lands here.</p></Card>}
        </div>
      )}
    </div>
  )
}

function Result({ title, r, diff }: { title: string; r: S['RuleTestOut']; diff?: S['RuleTestOut'] }) {
  const changed = (k: keyof S['RuleTestOut']) => diff && JSON.stringify(diff[k]) !== JSON.stringify(r[k])
  const cell = (k: keyof S['RuleTestOut'], node: React.ReactNode) => <span className={cn('inline-flex items-center gap-1.5', changed(k) && 'rounded-md bg-warning-dim px-1.5 py-0.5')}>{node}{changed(k) && <span className="eyebrow text-[9px] text-warning">changed</span>}</span>
  return (
    <Card>
      <PanelHeader title={title} aside={<Mono className="text-[12px] text-taupe-2">{r.ruleset_version} · {r.latency_ms ?? '—'} ms</Mono>} />
      <KV rows={[
        ['Category', cell('category', <Badge tone="ink">{r.category ?? 'UNMATCHED'}</Badge>)],
        ['Subcategory', cell('subcategory', r.subcategory ? <Badge>{r.subcategory}</Badge> : '—')],
        ['Department', cell('department', r.department ? <Badge tone="info">{r.department}</Badge> : '—')],
        ['Support dept', cell('support_department', r.support_department ?? '—')],
        ['Urgency', cell('urgency', <Badge tone={urgencyTone(r.urgency)}>{r.urgency ?? '—'}</Badge>)],
        ['Priority', cell('priority', <Badge tone={priorityTone(r.priority)}>{r.priority ?? '—'}</Badge>)],
        ['Escalation', cell('escalation_code', <Badge tone={escalationTone(r.escalation_code)}>{r.escalation_code ?? 'NONE'}</Badge>)],
        ['Floor', cell('escalation_floor_code', <Mono>{r.escalation_floor_code ?? 'NONE'}</Mono>)],
        ['Flags', <span key="f" className="flex flex-wrap gap-1">{r.escalation_required && <Badge tone="warning">escalation required</Badge>}{r.follow_up_required && <Badge tone="info">follow-up</Badge>}{r.unmatched && <Badge tone="warning">unmatched</Badge>}{r.conflict_detected && <Badge tone="critical">conflict</Badge>}{!r.escalation_required && !r.follow_up_required && !r.unmatched && !r.conflict_detected && '—'}</span>],
      ]} />
      <div className="mt-5 flex flex-col gap-3 text-[13px]">
        <div><p className={cn('eyebrow mb-1.5', changed('matched_rules') && 'text-warning')}>Matched rules ({r.matched_rules?.length ?? 0})</p><div className="flex flex-wrap gap-1">{(r.matched_rules ?? []).map((m) => <Link key={m} href={`/dashboard/rules/${encodeURIComponent(m)}`}><Badge tone={r.mandatory_escalation_refs?.includes(m) ? 'critical' : diff && !diff.matched_rules?.includes(m) ? 'warning' : 'neutral'}><Mono>{m}</Mono></Badge></Link>)}</div></div>
        <div><p className={cn('eyebrow mb-1.5', changed('signals_fired') && 'text-warning')}>Signals ({r.signals_fired?.length ?? 0})</p><p className="font-mono text-[11.5px] leading-relaxed text-espresso-2">{(r.signals_fired ?? []).join('  ') || '—'}</p></div>
        {(r.required_actions?.length ?? 0) > 0 && <div><p className="eyebrow mb-1.5">Required actions</p><ul className="list-disc pl-5">{r.required_actions!.map((a) => <li key={a}>{a}</li>)}</ul></div>}
        {(r.prohibited_actions?.length ?? 0) > 0 && <div><p className="eyebrow mb-1.5 text-critical">Prohibited</p><ul className="list-disc pl-5">{r.prohibited_actions!.map((a) => <li key={a}>{a}</li>)}</ul></div>}
      </div>
    </Card>
  )
}
