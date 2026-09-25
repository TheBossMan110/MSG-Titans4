'use client'

import { use, useEffect, useState } from 'react'
import Link from 'next/link'
import { AppShell } from '@/components/layout/app-shell'
import { useAuth } from '@/lib/auth-context'
import { admin, type S } from '@/lib/api'
import { useApi, useAction } from '@/lib/use-api'
import { Badge, Button, Mono, humanise, escalationTone } from '@/components/ui/primitives'
import { Card, PanelHeader } from '@/components/ui/surfaces'
import { Field, Input, Select, Textarea, Checkbox } from '@/components/ui/forms'
import { KV } from '@/components/ui/data'
import { ErrorState, Loading, useToast } from '@/components/ui/feedback'
import { AuditTrail } from '@/components/app/complaint-bits'

export default function RulePage({ params }: { params: Promise<{ ref: string }> }) {
  const { ref } = use(params)
  const ruleRef = decodeURIComponent(ref)
  return (
    <AppShell eyebrow={<span>Rules / <Mono>{ruleRef}</Mono></span>} roles={['manager', 'admin', 'evaluator']} wide>
      <Rule ruleRef={ruleRef} />
    </AppShell>
  )
}

/**
 * One rule, readable by oversight roles and editable by an admin. The form
 * sends only what changed. Mandatory escalation rules cannot be deactivated
 * or lowered; the server refuses and the refusal is shown, not hidden.
 */
function Rule({ ruleRef }: { ruleRef: string }) {
  const { user } = useAuth()
  const toast = useToast()
  const q = useApi(() => admin.rule(ruleRef), [ruleRef])
  const taxonomy = useApi(() => admin.taxonomy())
  const save = useAction((body: S['RuleUpdateIn']) => admin.updateRule(ruleRef, body))
  const [form, setForm] = useState<S['RuleUpdateIn']>({})
  const [conditions, setConditions] = useState('')
  const [condError, setCondError] = useState<string | null>(null)
  const isAdmin = user?.role === 'admin'

  useEffect(() => {
    if (!q.data) return
    const r = q.data
    setForm({ name: r.name, precedence: r.precedence, is_active: r.is_active, rationale: r.rationale ?? '', outcome_urgency: r.outcome_urgency ?? '', outcome_priority_code: r.outcome_priority_code ?? '', outcome_escalation_code: r.outcome_escalation_code ?? '', outcome_category: r.outcome_category ?? '', outcome_subcategory: r.outcome_subcategory ?? '', outcome_department: r.outcome_department ?? '', follow_up_required: r.follow_up_required ?? false, reason: '' })
    setConditions(r.conditions ? JSON.stringify(r.conditions, null, 2) : '')
  }, [q.data])

  if (q.loading && !q.data) return <Loading label="Opening the rule" />
  if (q.error) return <ErrorState message={q.error} onRetry={q.refresh} />
  const r = q.data!
  const set = <K extends keyof S['RuleUpdateIn']>(k: K, v: S['RuleUpdateIn'][K]) => setForm((f) => ({ ...f, [k]: v }))
  const opts = (rows?: S['CodeOut'][]) => (rows ?? []).map((c) => <option key={c.code} value={c.code}>{c.code} — {c.name}</option>)

  const onSave = async (e: React.FormEvent) => {
    e.preventDefault()
    let parsed: unknown = undefined
    if (conditions.trim() && conditions.trim() !== JSON.stringify(r.conditions, null, 2).trim()) {
      try { parsed = JSON.parse(conditions); setCondError(null) } catch { setCondError('Conditions must be valid JSON.'); return }
    }
    const body: S['RuleUpdateIn'] = { reason: form.reason || null }
    if (form.name !== r.name) body.name = form.name
    if (form.precedence !== r.precedence) body.precedence = form.precedence
    if (form.is_active !== r.is_active) body.is_active = form.is_active
    if ((form.rationale ?? '') !== (r.rationale ?? '')) body.rationale = form.rationale || null
    for (const k of ['outcome_urgency', 'outcome_priority_code', 'outcome_escalation_code', 'outcome_category', 'outcome_subcategory', 'outcome_department'] as const) {
      if ((form[k] ?? '') !== (r[k] ?? '')) body[k] = form[k] || null
    }
    if ((form.follow_up_required ?? false) !== (r.follow_up_required ?? false)) body.follow_up_required = form.follow_up_required
    if (parsed !== undefined) body.conditions = parsed
    if (Object.keys(body).length === 1) { toast('warn', 'Nothing changed.'); return }
    const res = await save.run(body)
    if (res) { toast('ok', `Saved ${res.changed_fields?.join(', ') || 'rule'} · ruleset ${res.ruleset_version} (${res.active_rule_count} active)`); q.setData(res.rule) }
    else if (save.error) toast('err', save.error)
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <p className="eyebrow mb-2"><Link href="/dashboard/rules" className="underline decoration-line underline-offset-4">Rule matrix</Link> / <Mono>{r.rule_ref}</Mono></p>
        <h1 className="display text-h2">{r.name}</h1>
        <div className="mt-3 flex flex-wrap gap-2"><Badge>{humanise(r.rule_type)}</Badge><Badge tone={r.is_active ? 'verified' : 'neutral'}>{r.is_active ? 'active' : 'inactive'}</Badge>{r.is_mandatory_escalation && <Badge tone="critical">mandatory escalation · floor {r.outcome_escalation_code}</Badge>}{r.is_catch_all && <Badge tone="info">catch-all</Badge>}<Badge>v{r.version}</Badge><Badge>precedence {r.precedence}</Badge>{r.source_ref && <Mono className="text-[12px] text-taupe-2">{r.source_ref}</Mono>}</div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1.1fr_1fr]">
        <form onSubmit={onSave} className="flex flex-col gap-5">
          <Card>
            <PanelHeader title={isAdmin ? 'Edit' : 'Definition'} eyebrow={isAdmin ? 'Saved changes take effect on the next analysis' : 'Read only for your role'} />
            <fieldset disabled={!isAdmin} className="flex flex-col gap-4">
              <Field label="Name">{(id) => <Input id={id} value={form.name ?? ''} onChange={(e) => set('name', e.target.value)} />}</Field>
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Precedence" hint="Lower fires first.">{(id) => <Input id={id} type="number" value={form.precedence ?? ''} onChange={(e) => set('precedence', Number(e.target.value))} />}</Field>
                <div className="flex items-end pb-3"><Checkbox label={r.can_deactivate === false ? 'Active (mandatory rules cannot be deactivated)' : 'Active'} checked={Boolean(form.is_active)} disabled={!isAdmin || r.can_deactivate === false} onChange={(e) => set('is_active', e.target.checked)} /></div>
                <Field label="Outcome · urgency">{(id) => <Select id={id} value={form.outcome_urgency ?? ''} onChange={(e) => set('outcome_urgency', e.target.value)}><option value="">—</option>{['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'].map((u) => <option key={u} value={u}>{u}</option>)}</Select>}</Field>
                <Field label="Outcome · priority">{(id) => <Select id={id} value={form.outcome_priority_code ?? ''} onChange={(e) => set('outcome_priority_code', e.target.value)}><option value="">—</option>{opts(taxonomy.data?.priority_levels)}</Select>}</Field>
                <Field label="Outcome · escalation" hint={r.is_mandatory_escalation ? 'A mandatory floor may be raised, never lowered.' : undefined}>{(id) => <Select id={id} value={form.outcome_escalation_code ?? ''} onChange={(e) => set('outcome_escalation_code', e.target.value)}><option value="">—</option>{opts(taxonomy.data?.escalation_levels)}</Select>}</Field>
                <Field label="Outcome · category">{(id) => <Select id={id} value={form.outcome_category ?? ''} onChange={(e) => set('outcome_category', e.target.value)}><option value="">—</option>{opts(taxonomy.data?.categories)}</Select>}</Field>
                <Field label="Outcome · subcategory">{(id) => <Select id={id} value={form.outcome_subcategory ?? ''} onChange={(e) => set('outcome_subcategory', e.target.value)}><option value="">—</option>{opts(taxonomy.data?.subcategories)}</Select>}</Field>
                <Field label="Outcome · department">{(id) => <Select id={id} value={form.outcome_department ?? ''} onChange={(e) => set('outcome_department', e.target.value)}><option value="">—</option>{opts(taxonomy.data?.departments)}</Select>}</Field>
              </div>
              <Checkbox label="Follow-up required" checked={Boolean(form.follow_up_required)} onChange={(e) => set('follow_up_required', e.target.checked)} />
              <Field label="Rationale">{(id) => <Textarea id={id} value={form.rationale ?? ''} onChange={(e) => set('rationale', e.target.value)} rows={3} className="min-h-[90px]" />}</Field>
              <Field label="Conditions (JSON)" error={condError} hint="signal:, fact:, field:, all_of / any_of. Validated on save.">{(id) => <Textarea id={id} value={conditions} onChange={(e) => setConditions(e.target.value)} rows={10} className="font-mono text-[12.5px]" />}</Field>
              {isAdmin && <Field label="Reason for the change" hint="Written to the audit trail.">{(id) => <Input id={id} value={form.reason ?? ''} onChange={(e) => set('reason', e.target.value)} />}</Field>}
            </fieldset>
            {save.error && <ErrorState title="The change was refused" message={save.error} className="mt-4" />}
            {isAdmin && <div className="mt-5"><Button type="submit" loading={save.pending}>Save rule</Button></div>}
          </Card>
        </form>

        <div className="flex flex-col gap-6">
          <Card>
            <PanelHeader title="Effects" />
            <KV rows={[['Escalation', r.outcome_escalation_code ? <Badge key="e" tone={escalationTone(r.outcome_escalation_code)}>{r.outcome_escalation_code}</Badge> : null], ['Support department', r.outcome_support_department], ['Signals referenced', (r.signals_referenced ?? []).length ? <span key="s" className="flex flex-wrap gap-1">{r.signals_referenced!.map((s) => <Badge key={s}><Mono>{s}</Mono></Badge>)}</span> : null]]} />
            {Array.isArray(r.required_actions) && r.required_actions.length > 0 && <div className="mt-4"><p className="eyebrow mb-1.5">Required actions</p><ul className="list-disc pl-5 text-[13.5px]">{(r.required_actions as unknown[]).map((a, i) => <li key={i}>{typeof a === 'string' ? a : JSON.stringify(a)}</li>)}</ul></div>}
            {Array.isArray(r.prohibited_actions) && r.prohibited_actions.length > 0 && <div className="mt-4"><p className="eyebrow mb-1.5 text-critical">Prohibited actions</p><ul className="list-disc pl-5 text-[13.5px]">{(r.prohibited_actions as unknown[]).map((a, i) => <li key={i}>{typeof a === 'string' ? a : JSON.stringify(a)}</li>)}</ul></div>}
            {r.eligibility != null && <div className="mt-4"><p className="eyebrow mb-1.5">Eligibility</p><pre className="overflow-x-auto rounded bg-cream p-3 font-mono text-[11.5px]">{JSON.stringify(r.eligibility, null, 2)}</pre></div>}
            {r.policy_refs != null && <div className="mt-4"><p className="eyebrow mb-1.5">Policy references</p><pre className="overflow-x-auto rounded bg-cream p-3 font-mono text-[11.5px]">{JSON.stringify(r.policy_refs, null, 2)}</pre></div>}
          </Card>
          <section><PanelHeader title="Change history" eyebrow="Audit trail" /><AuditTrail entityType="rule" entityId={r.rule_ref} /></section>
        </div>
      </div>
    </div>
  )
}
