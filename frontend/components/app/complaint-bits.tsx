'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useState } from 'react'
import { complaints, review, audit, type S } from '@/lib/api'
import { useApi, useAction, fmtDate, fmtRelative, pct } from '@/lib/use-api'
import { useAuth } from '@/lib/auth-context'
import {
  Badge, Button, Mono, humanise, priorityTone, urgencyTone, escalationTone, statusTone, verificationTone, eligibilityTone,
} from '@/components/ui/primitives'
import { Card, PanelHeader } from '@/components/ui/surfaces'
import { Table, Th, Td, Tr, KV, Ratio } from '@/components/ui/data'
import { Empty, ErrorState, Loading, SkeletonRows } from '@/components/ui/feedback'
import { Select, Textarea, Field } from '@/components/ui/forms'
import { cn } from '@/lib/utils'

/* ------------------------------------------------------------------ badges */

export const StatusBadge = ({ status }: { status?: string | null }) => <Badge tone={statusTone(status)} dot>{humanise(status)}</Badge>
// Short forms: the full enum names are long enough to push a column off-screen.
const OUTCOME_LABEL: Record<string, string> = {
  VERIFIED: 'Verified', VERIFIED_WITH_WARNING: 'Verified · warning', CORRECTED_BY_RULES: 'Rules corrected',
  MANUAL_REVIEW_REQUIRED: 'Needs review', INCOMPLETE: 'Incomplete', BLOCKED: 'Blocked',
}
export const OutcomeBadge = ({ outcome }: { outcome?: string | null }) => (outcome ? <Badge tone={verificationTone(outcome)}>{OUTCOME_LABEL[outcome.toUpperCase()] ?? humanise(outcome)}</Badge> : <span className="text-taupe">—</span>)
export const PriorityBadge = ({ code }: { code?: string | null }) => (code ? <Badge tone={priorityTone(code)} pulse={code.toUpperCase() === 'P0'}>{code}</Badge> : <span className="text-taupe">—</span>)
export const UrgencyBadge = ({ u }: { u?: string | null }) => (u ? <Badge tone={urgencyTone(u)}>{humanise(u)}</Badge> : <span className="text-taupe">—</span>)
export const EscalationBadge = ({ code }: { code?: string | null }) => <Badge tone={escalationTone(code)}>{humanise(code ?? 'NONE')}</Badge>

/* ------------------------------------------------------------------ complaint table */

export function ComplaintTable({ items, hrefFor = (r) => `/dashboard/complaints/${r}` }: { items: S['ComplaintSummary'][]; hrefFor?: (ref: string) => string }) {
  const router = useRouter()
  if (!items.length) return <Empty title="No complaints match" body="Try widening the filters, or submit one." />
  // Six columns, not ten. Reference sits above its title, category above
  // its department, urgency beside priority, the age beside the reference: pairs a reader compares anyway,
  // so the table stops reading like a spreadsheet dump.
  return (
    <Table>
      <thead>
        <tr><Th>Complaint</Th><Th>Status</Th><Th>Classification</Th><Th>Urgency · priority</Th><Th>Escalation</Th><Th>Verification</Th></tr>
      </thead>
      <tbody>
        {items.map((c) => (
          <Tr key={c.id} onClick={() => router.push(hrefFor(c.public_ref))}>
            <Td className="max-w-[300px]">
              <span className="flex items-baseline gap-2 text-[12.5px] text-taupe">
                <Link href={hrefFor(c.public_ref)} onClick={(e) => e.stopPropagation()} className="font-mono transition-colors hover:text-ai">{c.public_ref}</Link>
                <span aria-hidden>·</span><span>{fmtRelative(c.created_at)}</span>
              </span>
              <span className="mt-0.5 block truncate font-medium text-espresso">{c.title}</span>
              {c.customer_type && <span className="mt-0.5 block truncate text-[12.5px] text-taupe">{c.customer_type}</span>}
              {(c.injection_suspected || c.is_duplicate || (c.repeat_count ?? 0) > 1) && (
                <span className="mt-1.5 flex flex-wrap gap-1.5">
                  {c.injection_suspected && <Badge tone="critical" pulse>Injection</Badge>}
                  {c.is_duplicate && <Badge tone="warning">Duplicate</Badge>}
                  {(c.repeat_count ?? 0) > 1 && <Badge>Repeat ×{c.repeat_count}</Badge>}
                </span>
              )}
            </Td>
            <Td><StatusBadge status={c.status} /></Td>
            <Td>
              <span className="block text-espresso">{c.category ? humanise(c.category) : <span className="text-taupe">Not classified</span>}</span>
              <span className="block text-[12.5px] text-taupe">{c.department ? humanise(c.department) : 'Not routed'}</span>
            </Td>
            <Td><span className="flex flex-wrap items-center gap-1.5"><UrgencyBadge u={c.urgency} /><PriorityBadge code={c.priority_code} /></span></Td>
            <Td><EscalationBadge code={c.escalation_code} /></Td>
            <Td><OutcomeBadge outcome={c.verification_outcome} /></Td>
          </Tr>
        ))}
      </tbody>
    </Table>
  )
}

/* ------------------------------------------------------------------ verification */

export function VerificationCard({ v }: { v?: S['VerificationOut'] | null }) {
  if (!v) return <Card tone="ghost"><p className="text-[14px] text-taupe-2">Not yet verified. The complaint has not been through both pipelines.</p></Card>
  return (
    <Card>
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="eyebrow mb-1">Verification</p>
          <OutcomeBadge outcome={v.outcome} />
        </div>
        <div className="flex flex-wrap gap-1.5">
          {v.genai_available === false && <Badge tone="warning">GenAI unavailable · rules alone</Badge>}
          {v.requires_review && <Badge tone="warning">Review required</Badge>}
          {(v.critical_mismatches ?? 0) > 0 && <Badge tone="critical">{v.critical_mismatches} critical mismatch{v.critical_mismatches === 1 ? '' : 'es'}</Badge>}
          {(v.high_mismatches ?? 0) > 0 && <Badge tone="warning">{v.high_mismatches} high</Badge>}
        </div>
      </div>
      <div className="grid gap-4 md:grid-cols-3">
        <Score label="Agreement" value={v.agreement_score} note={v.matched_fields != null && v.total_fields ? `${v.matched_fields}/${v.total_fields} fields` : undefined} />
        <Score label="Traceability" value={v.traceability_score} note="citations resolved" />
        <Score label="Compliance" value={v.compliance_score} note="claims supported by policy" />
      </div>
      {v.review_reasons && v.review_reasons.length > 0 && (
        <div className="mt-5 border-t border-line-soft pt-4">
          <p className="eyebrow mb-2">Why it was queued</p>
          <ul className="flex flex-wrap gap-1.5">{v.review_reasons.map((r) => <li key={r}><Badge tone="neutral"><Mono>{r}</Mono></Badge></li>)}</ul>
        </div>
      )}
    </Card>
  )
}

function Score({ label, value, note }: { label: string; value?: number | null; note?: string }) {
  const v = value === null || value === undefined ? null : value <= 1 ? value * 100 : value
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <span className="text-[13px] text-taupe-2">{label}</span>
        <span className={cn('font-display text-[24px] leading-none', v === null ? 'text-taupe' : 'text-espresso')}>{v === null ? <span className="font-sans text-[12px] italic">not measured</span> : pct(v)}</span>
      </div>
      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-sand">{v !== null && <div className="h-full rounded-full bg-espresso" style={{ width: `${Math.min(100, v)}%` }} />}</div>
      {note && <p className="mt-1.5 text-[11.5px] text-taupe-2">{note}</p>}
    </div>
  )
}

/* ------------------------------------------------------------------ comparisons (pencil vs ink) */

export function ComparisonTable({ rows }: { rows?: S['ComparisonOut'][] }) {
  if (!rows?.length) return <Empty title="No comparison recorded" body="Both pipelines have to run before their answers can be compared." />
  const tone = (s: string) => (s === 'MATCH' || s === 'AGREED' ? 'verified' : s === 'MISMATCH' || s === 'CONFLICT' ? (rows ? 'critical' : 'warning') : 'warning')
  const winner = (w?: string | null) => (!w ? '—' : /python|rule/i.test(w) ? 'Rules' : /genai|ai/i.test(w) ? 'AI' : /agree/i.test(w) ? 'Both agreed' : humanise(w))
  const status = (st: string) => (st === 'PYTHON_MISSING' ? 'Rules silent' : st === 'GENAI_MISSING' ? 'AI silent' : humanise(st))
  return (
    <Table>
      <thead><tr><Th>Field</Th><Th>AI proposed</Th><Th>Rules decided</Th><Th>Used</Th><Th>Result</Th><Th>Why</Th></tr></thead>
      <tbody>
        {rows.map((r) => (
          <Tr key={r.field}>
            <Td className="font-medium">{humanise(r.field)}</Td>
            <Td><span className="pencil inline-block rounded-md px-2 py-0.5 font-display italic text-[14px]">{plainValue(r.genai_value)}</span></Td>
            <Td><span className="ink inline-block rounded-md px-2 py-0.5 text-[13px]">{plainValue(r.python_value)}</span></Td>
            <Td className="font-medium text-espresso">{plainValue(r.final_value)}<span className="block text-[12px] font-normal text-taupe-2">{winner(r.winner)}</span></Td>
            <Td><span className="flex flex-wrap gap-1"><Badge tone={tone(r.status)}>{status(r.status)}</Badge>{r.severity && !['NONE', 'INFORMATIONAL'].includes(r.severity) && <Badge tone={r.severity === 'CRITICAL' ? 'critical' : r.severity === 'HIGH' ? 'warning' : 'neutral'}>{humanise(r.severity)}</Badge>}</span></Td>
            <Td className="min-w-[220px] max-w-[360px] text-[12.5px] leading-relaxed text-taupe-2"><span title={r.reason_code ?? ''}>{plainSentence(r.explanation)}</span></Td>
          </Tr>
        ))}
      </tbody>
    </Table>
  )
}

export function RuleHits({ hits, floor }: { hits?: S['RuleHitOut'][]; floor?: string | null }) {
  if (!hits?.length) return <Empty title="No rule matched" body="The rule engine found no applicable rule; the complaint fell to the catch-all." />
  return (
    <div className="flex flex-col gap-2">
      {floor && <p className="text-[13px] text-taupe-2">Escalation floor from mandatory rules: <EscalationBadge code={floor} /></p>}
      {hits.map((h) => (
        <div key={h.rule_ref} className={cn('rounded-[var(--radius-md)] border px-4 py-3', h.mandatory_escalation ? 'border-critical/30 bg-critical-dim/40' : 'border-line bg-ivory', h.applied === false && 'opacity-60')}>
          <div className="flex flex-wrap items-center gap-2">
            <Link href={`/dashboard/rules/${encodeURIComponent(h.rule_ref)}`}><Mono className="font-medium underline decoration-line underline-offset-4 hover:decoration-espresso">{h.rule_ref}</Mono></Link>
            {h.precedence != null && <span className="text-[12px] text-taupe-2">precedence {h.precedence}</span>}
            {h.mandatory_escalation && <Badge tone="critical">mandatory escalation</Badge>}
            {h.applied === false && <Badge>superseded by precedence</Badge>}
          </div>
          {h.rationale && <p className="mt-1.5 text-[13.5px] text-espresso-2">{h.rationale}</p>}
          {h.signals && h.signals.length > 0 && <p className="mt-1.5 text-[12px] text-taupe-2">Matched on: {(h.signals as unknown[]).map((x) => String(x).replace(/_/g, ' ')).join(' · ')}</p>}
        </div>
      ))}
    </div>
  )
}

export function PolicyTrace({ rows }: { rows?: S['TraceRowOut'][] }) {
  if (!rows?.length) return <Empty title="Nothing cited" body="No policy references were produced for this complaint." />
  return (
    <Table dense>
      <thead><tr><Th>Source</Th><Th>Document</Th><Th>Section</Th><Th>Resolved</Th><Th>Was active</Th><Th>Applicability</Th><Th>Reason</Th></tr></thead>
      <tbody>
        {rows.map((r, i) => (
          <Tr key={i}>
            <Td>{humanise(r.source)}</Td>
            <Td mono><Link href={`/dashboard/knowledge-base/search?doc_ref=${encodeURIComponent(r.doc_ref)}${r.section ? `&section_ref=${encodeURIComponent(r.section)}` : ''}`} className="underline decoration-line underline-offset-4">{r.doc_ref}{r.version ? ` ${r.version}` : ''}</Link></Td>
            <Td mono>{r.section ?? '—'}{r.page != null ? ` · p.${r.page}` : ''}</Td>
            <Td><Badge tone={r.resolved ? 'verified' : 'critical'}>{r.resolved ? 'yes' : 'no'}</Badge></Td>
            <Td><Badge tone={r.was_active ? 'verified' : 'warning'}>{r.was_active ? 'yes' : 'no'}</Badge></Td>
            <Td><Badge tone={r.applicability === 'APPLICABLE' ? 'verified' : r.applicability === 'SUPERSEDED' || r.applicability === 'EXPIRED' ? 'warning' : 'neutral'}>{humanise(r.applicability)}</Badge></Td>
            <Td className="text-[12.5px] text-taupe-2">{r.reason ?? ''}</Td>
          </Tr>
        ))}
      </tbody>
    </Table>
  )
}

export function Conflicts({ rows }: { rows?: S['PolicyConflictOut'][] }) {
  if (!rows?.length) return null
  return (
    <Card tone="sand">
      <p className="eyebrow mb-3">Contradictory policies detected</p>
      <ul className="flex flex-col gap-2 text-[13.5px]">
        {rows.map((c, i) => (
          <li key={i}><Mono>{c.overruled_ref}{c.overruled_section ? ` §${c.overruled_section}` : ''}{c.overruled_version ? ` ${c.overruled_version}` : ''}</Mono> is governed by <Mono>{c.governed_by_ref}</Mono>{c.overruled_tier ? <span className="text-taupe-2"> ({humanise(c.overruled_tier)} tier)</span> : null}{c.reason ? <span className="text-taupe-2"> — {c.reason}</span> : null}</li>
        ))}
      </ul>
    </Card>
  )
}

export function GenAIRuns({ runs }: { runs?: S['GenAIRunOut'][] }) {
  if (!runs?.length) return <p className="text-[13.5px] text-taupe-2">No GenAI run recorded. The rule engine carried this decision alone.</p>
  return (
    <Table dense>
      <thead><tr><Th>#</Th><Th>Pipeline</Th><Th>Provider · model</Th><Th>Status</Th><Th>Prompt</Th><Th>KB</Th><Th align="right">Chunks</Th><Th align="right">Tokens</Th><Th align="right">Latency</Th><Th>Cache</Th><Th>Error</Th></tr></thead>
      <tbody>
        {runs.map((r) => (
          <Tr key={`${r.attempt}-${r.pipeline}`}>
            <Td mono>{r.attempt}</Td><Td>{r.pipeline}</Td><Td mono>{r.provider} · {r.model}</Td>
            <Td><Badge tone={r.status === 'SUCCESS' || r.status === 'OK' ? 'verified' : r.status === 'FAILED' || r.status === 'ERROR' ? 'critical' : 'warning'}>{r.status}</Badge></Td>
            <Td mono>{r.prompt}</Td><Td mono>{r.knowledge_base_version ?? '—'}</Td>
            <Td align="right" mono>{r.cited_chunks ?? 0}</Td>
            <Td align="right" mono>{r.tokens ? Object.values(r.tokens as Record<string, number>).reduce((a, b) => a + (Number(b) || 0), 0) : '—'}</Td>
            <Td align="right" mono>{r.latency_ms != null ? `${r.latency_ms} ms` : '—'}</Td>
            <Td>{r.cache_hit ? <Badge>hit</Badge> : '—'}</Td>
            <Td className="max-w-[260px] truncate text-[12px] text-critical" title={r.error ?? ''}>{r.error ?? ''}</Td>
          </Tr>
        ))}
      </tbody>
    </Table>
  )
}

/* ------------------------------------------------------------------ resolution */

export function ResolutionSteps({ steps }: { steps?: S['ResolutionStepOut'][] }) {
  if (!steps?.length) return <p className="text-[13.5px] text-taupe-2">No resolution steps recorded.</p>
  const tone = (s: string) => (s === 'REQUIRED_MET' || s === 'SUPPORTED' || s === 'CONFIRMED' ? 'verified' : s === 'PROHIBITED' ? 'critical' : s === 'MISSING' || s === 'UNSUPPORTED' ? 'warning' : 'neutral')
  return (
    <ol className="flex flex-col gap-2">
      {steps.map((s) => (
        <li key={s.ordinal} className={cn('flex gap-3 rounded-[var(--radius-md)] border px-4 py-3', s.source === 'GENAI' || s.source === 'genai' ? 'pencil' : 'border-line bg-ivory')}>
          <span className="font-mono text-[12px] text-taupe-2">{s.ordinal}</span>
          <div className="flex-1">
            <p className={cn('text-[14px]', (s.source === 'GENAI' || s.source === 'genai') && 'font-display italic')}>{s.text}</p>
            <p className="mt-1 flex flex-wrap gap-1.5 text-[12px] text-taupe-2"><Badge tone={tone(s.status)}>{humanise(s.status)}</Badge><span>{humanise(s.source)}</span>{s.action_code && <Mono>{s.action_code}</Mono>}{s.rule_ref && <Mono>{s.rule_ref}</Mono>}{s.policy_ref && <Mono>{s.policy_ref}</Mono>}</p>
          </div>
        </li>
      ))}
    </ol>
  )
}

export function Eligibility({ rows }: { rows?: S['EligibilityOut'][] }) {
  if (!rows?.length) return <p className="text-[13.5px] text-taupe-2">No eligibility decision applies.</p>
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {rows.map((e) => (
        <Card key={e.eligibility_type} padding="sm" radius="md">
          <div className="flex items-center justify-between"><span className="font-medium">{humanise(e.eligibility_type)}</span><Badge tone={eligibilityTone(e.final_outcome)}>{humanise(e.final_outcome)}</Badge></div>
          <p className="mt-2 text-[12.5px] text-taupe-2">Rules said <b className="text-espresso-2">{humanise(e.python_outcome)}</b>{e.requires_human_approval && ' · human approval required'}{e.rule_ref && <> · <Mono>{e.rule_ref}</Mono></>}</p>
          {e.reason && <p className="mt-1.5 text-[13px] text-espresso-2">{e.reason}</p>}
        </Card>
      ))}
    </div>
  )
}

export function Guidance({ rows }: { rows?: S['GuidanceOut'][] }) {
  if (!rows?.length) return null
  return (
    <ul className="flex flex-col gap-1.5">
      {rows.map((g) => (
        <li key={g.ordinal} className="flex items-start gap-2 text-[13.5px]"><Badge tone={g.kind === 'PROHIBITED' || g.kind === 'prohibited' ? 'critical' : g.is_mandatory ? 'ink' : 'neutral'} className="mt-0.5 shrink-0">{humanise(g.kind)}</Badge><span>{g.text}{g.rule_ref && <Mono className="ml-1 text-taupe-2">{g.rule_ref}</Mono>}</span></li>
      ))}
    </ul>
  )
}

export function Entities({ rows }: { rows?: S['EntityOut'][] }) {
  if (!rows?.length) return <p className="text-[13.5px] text-taupe-2">No entities extracted.</p>
  return <div className="flex flex-wrap gap-1.5">{rows.map((e, i) => <Badge key={i}><span className="text-taupe-2">{e.entity_type}</span>&nbsp;<Mono>{e.normalized ?? e.value}</Mono></Badge>)}</div>
}

export function Links({ rows }: { rows?: S['LinkOut'][] }) {
  if (!rows?.length) return null
  return (
    <ul className="flex flex-col gap-1.5 text-[13.5px]">
      {rows.map((l, i) => <li key={i}><Badge tone={l.link_type === 'DUPLICATE' ? 'warning' : 'neutral'}>{humanise(l.link_type)}</Badge> <Link href={`/dashboard/complaints/${l.related_ref}`} className="ml-1 font-mono underline decoration-line underline-offset-4">{l.related_ref}</Link>{l.related_status && <span className="text-taupe-2"> · {humanise(l.related_status)}</span>}{l.similarity != null && <span className="text-taupe-2"> · {Math.round(l.similarity * 100)}% similar</span>}</li>)}
    </ul>
  )
}

/** What was asked, and what the customer replied. */
export function Clarifications({ rows }: { rows?: S['ClarificationOut'][] }) {
  if (!rows?.length) return null
  return (
    <ol className="flex flex-col gap-2.5">
      {rows.map((q) => (
        <li key={q.id ?? q.ordinal} className={cn('rounded-2xl border p-3.5', q.answered_at ? 'border-verified/25 bg-verified-dim/40' : 'border-warning/30 bg-warning-dim/50')}>
          <p className="flex items-start gap-2 text-[14px] font-medium text-espresso">
            <span className="font-mono text-[12px] text-taupe">{q.ordinal}.</span>
            <span className="flex-1">{q.question}</span>
            {q.answered_at ? <Badge tone="verified">Answered</Badge> : <Badge tone="warning" pulse>Waiting</Badge>}
          </p>
          {q.missing_field && <p className="mt-1 pl-5 text-[12px] text-taupe">Asked for: <Mono>{q.missing_field}</Mono></p>}
          {q.answer && <p className="mt-2 whitespace-pre-wrap rounded-xl bg-white/85 px-3 py-2 text-[13.5px] text-espresso-2">{q.answer}</p>}
          {q.answered_at && <p className="mt-1 pl-1 text-[12px] text-taupe">Replied {fmtRelative(q.answered_at)}</p>}
        </li>
      ))}
    </ol>
  )
}

/* ------------------------------------------------------------------ self-fetching panels */

export function ChecklistPanel({ refId, canConfirm }: { refId: string; canConfirm: boolean }) {
  const q = useApi(() => complaints.checklist(refId), [refId])
  const confirm = useAction((stepId: string) => complaints.confirmStep(refId, stepId))
  if (q.loading && !q.data) return <SkeletonRows rows={4} />
  if (q.error) return <ErrorState message={q.error} onRetry={q.refresh} />
  const d = q.data!
  const s = d.summary
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-4">
        <Ratio numerator={s.confirmed ?? 0} denominator={s.required ?? 0} label="Required steps confirmed" tone={s.complete ? 'verified' : 'neutral'} />
        <div className="flex gap-1.5">{(s.prohibited ?? 0) > 0 && <Badge tone="critical">{s.prohibited} prohibited</Badge>}{(s.unsupported ?? 0) > 0 && <Badge tone="warning">{s.unsupported} unsupported</Badge>}{s.complete && <Badge tone="verified">complete</Badge>}</div>
      </div>
      {confirm.error && <p role="alert" className="text-[13px] text-critical">{confirm.error}</p>}
      <ol className="flex flex-col gap-2">
        {(d.steps ?? []).map((st) => (
          <li key={st.id} className={cn('flex items-start gap-3 rounded-[var(--radius-md)] border px-4 py-3', st.status === 'CONFIRMED' || st.status === 'REQUIRED_MET' ? 'border-verified/30 bg-verified-dim/40' : st.status === 'PROHIBITED' ? 'border-critical/30 bg-critical-dim/40' : 'border-line bg-ivory')}>
            <span className="font-mono text-[12px] text-taupe-2">{st.ordinal}</span>
            <div className="flex-1">
              <p className="text-[14px]">{st.text}</p>
              <p className="mt-1 flex flex-wrap gap-1.5 text-[12px] text-taupe-2"><Badge tone={st.status === 'CONFIRMED' || st.status === 'REQUIRED_MET' ? 'verified' : st.status === 'PROHIBITED' ? 'critical' : st.status === 'MISSING' ? 'warning' : 'neutral'}>{humanise(st.status)}</Badge><span>{humanise(st.source)}</span>{st.policy_ref && <Mono>{st.policy_ref}</Mono>}</p>
              {st.explanation && <p className="mt-1 text-[12.5px] text-espresso-2">{st.explanation}</p>}
            </div>
            {canConfirm && st.confirmable && <Button size="sm" variant="secondary" loading={confirm.pending} onClick={async () => { const r = await confirm.run(st.id); if (r) q.setData(r) }}>Confirm</Button>}
          </li>
        ))}
      </ol>
    </div>
  )
}

export function FollowUpsPanel({ refId, canComplete }: { refId: string; canComplete: boolean }) {
  const q = useApi(() => complaints.followUps(refId), [refId])
  const done = useAction((id: string) => complaints.completeFollowUp(refId, id))
  if (q.loading && !q.data) return <SkeletonRows rows={3} />
  if (q.error) return <ErrorState message={q.error} onRetry={q.refresh} />
  const items = q.data ?? []
  if (!items.length) return <Empty title="No follow-ups" body="Nothing is scheduled for this complaint." />
  return (
    <div className="flex flex-col gap-2">
      {done.error && <p role="alert" className="text-[13px] text-critical">{done.error}</p>}
      {items.map((f) => {
        const overdue = f.open && f.due_at && new Date(f.due_at).getTime() < Date.now()
        return (
          <div key={f.id} className={cn('flex flex-wrap items-center gap-3 rounded-[var(--radius-md)] border px-4 py-3', overdue ? 'border-critical/30 bg-critical-dim/40' : 'border-line bg-ivory')}>
            <Badge tone={f.open ? (overdue ? 'critical' : 'warning') : 'verified'}>{f.open ? (overdue ? 'overdue' : 'open') : 'done'}</Badge>
            <span className="font-medium">{humanise(f.type)}</span>
            <span className="flex-1 text-[13.5px] text-espresso-2">{f.message}</span>
            <span className="text-[12.5px] text-taupe-2">{f.open ? `due ${fmtRelative(f.due_at)}` : `completed ${fmtDate(f.completed_at)}`}</span>
            {canComplete && f.open && <Button size="sm" variant="secondary" loading={done.pending} onClick={async () => { const r = await done.run(f.id); if (r) q.setData(r) }}>Mark done</Button>}
          </div>
        )
      })}
    </div>
  )
}

export function LifecyclePanel({ refId, canChange, onChanged }: { refId: string; canChange: boolean; onChanged?: () => void }) {
  const q = useApi(() => complaints.lifecycle(refId), [refId])
  const [to, setTo] = useState('')
  const [reason, setReason] = useState('')
  const change = useAction((s: string, r: string) => complaints.changeStatus(refId, s, r || undefined))
  if (q.loading && !q.data) return <SkeletonRows rows={3} />
  if (q.error) return <ErrorState message={q.error} onRetry={q.refresh} />
  const d = q.data!
  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
      <ol className="relative flex flex-col gap-4 border-l border-line pl-5">
        {(d.history ?? []).length === 0 && <li className="text-[13.5px] text-taupe-2">No transitions recorded yet.</li>}
        {(d.history ?? []).map((h, i) => (
          <li key={i} className="relative">
            <span className="absolute -left-[26px] top-1.5 size-2.5 rounded-full border-2 border-espresso bg-cream" />
            <p className="text-[14px]">{h.from_status ? <><StatusBadge status={h.from_status} /> <span className="text-taupe-2">→</span> </> : null}<StatusBadge status={h.to_status} /></p>
            <p className="mt-1 text-[12.5px] text-taupe-2">{h.changed_by} · {fmtDate(h.at)}{h.reason ? ` · ${h.reason}` : ''}</p>
          </li>
        ))}
      </ol>
      {canChange && (
        <Card padding="sm" radius="md" tone="cream">
          <p className="eyebrow mb-3">Move to</p>
          {(d.available_actions ?? []).length === 0 ? <p className="text-[13px] text-taupe-2">No transition is available from <b>{humanise(d.status)}</b>.</p> : (
            <form className="flex flex-col gap-3" onSubmit={async (e) => { e.preventDefault(); const r = await change.run(to, reason); if (r) { q.setData(r); setTo(''); setReason(''); onChanged?.() } }}>
              <Select value={to} onChange={(e) => setTo(e.target.value)} required aria-label="Target status"><option value="">Choose a status…</option>{(d.available_actions ?? []).map((a) => <option key={a} value={a}>{humanise(a)}</option>)}</Select>
              <Textarea value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Reason (recorded in the audit trail)" rows={3} className="min-h-[80px]" />
              {change.error && <p role="alert" className="text-[13px] text-critical">{change.error}</p>}
              <Button type="submit" size="sm" loading={change.pending} disabled={!to}>Apply</Button>
            </form>
          )}
        </Card>
      )}
    </div>
  )
}

export function SlaPanel({ refId }: { refId: string }) {
  const q = useApi(() => review.sla(refId), [refId])
  if (q.loading && !q.data) return <SkeletonRows rows={2} />
  if (q.error) return <ErrorState message={q.error} onRetry={q.refresh} />
  const rows = q.data ?? []
  if (!rows.length) return <p className="text-[13.5px] text-taupe-2">No SLA policy applies to this complaint yet.</p>
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {rows.map((s) => (
        <Card key={s.event_type} padding="sm" radius="md">
          <div className="flex items-center justify-between"><span className="font-medium">{humanise(s.event_type)}</span><Badge tone={s.breached ? 'critical' : s.met_at ? 'verified' : s.at_risk ? 'warning' : 'neutral'}>{s.breached ? 'breached' : s.met_at ? 'met' : s.at_risk ? 'at risk' : 'on track'}</Badge></div>
          <KV className="mt-3" rows={[['Due', fmtDate(s.due_at)], ['Met', s.met_at ? fmtDate(s.met_at) : '—']]} />
        </Card>
      ))}
    </div>
  )
}

export function ReviewHistoryPanel({ refId }: { refId: string }) {
  const q = useApi(() => review.history(refId), [refId])
  if (q.loading && !q.data) return <SkeletonRows rows={3} />
  if (q.error) return <ErrorState message={q.error} onRetry={q.refresh} />
  const rows = q.data ?? []
  if (!rows.length) return <Empty title="No review actions yet" />
  return (
    <ol className="flex flex-col gap-3">
      {rows.map((h, i) => (
        <li key={i} className="rounded-[var(--radius-md)] border border-line bg-ivory px-4 py-3">
          <div className="flex flex-wrap items-center gap-2"><Badge tone={h.is_override ? 'warning' : 'neutral'}>{humanise(h.action)}</Badge>{h.is_override && <Badge tone="warning">override</Badge>}<span className="text-[12.5px] text-taupe-2">{h.actor_id ?? 'system'} · {fmtDate(h.at)}</span></div>
          {h.comment && <p className="mt-2 text-[13.5px]">{h.comment}</p>}
          <BeforeAfter before={h.before} after={h.after} />
        </li>
      ))}
    </ol>
  )
}

export function EscalationPanel({ refId }: { refId: string }) {
  const q = useApi(() => complaints.escalation(refId), [refId])
  if (q.loading && !q.data) return <SkeletonRows rows={2} />
  if (q.error) return <p className="text-[13.5px] text-taupe-2">{q.error}</p>
  const e = q.data!
  return (
    <Card tone={e.escalation_code && e.escalation_code !== 'NONE' ? 'sand' : 'ghost'}>
      <div className="flex flex-wrap items-center gap-2"><EscalationBadge code={e.escalation_code} /><span className="text-[13px] text-taupe-2">triggered by {humanise(e.triggered_by)}</span>{e.rule_ref && <Mono className="text-[12px]">{e.rule_ref}</Mono>}{e.acknowledged_at && <Badge tone="verified">acknowledged {fmtRelative(e.acknowledged_at)}</Badge>}</div>
      {e.reason && <p className="mt-2 text-[13.5px]">{e.reason}</p>}
      {e.notes ? <blockquote className="pencil mt-3 rounded-[var(--radius-md)] p-4 font-display italic text-[14.5px] leading-relaxed whitespace-pre-wrap">{e.notes}</blockquote> : e.note_available === false ? <p className="mt-2 text-[12.5px] text-taupe-2">No handover note on file. The escalation itself is recorded above; a note is written for complaints submitted live, and is skipped when the AI is unavailable or for bulk-processed datasets.</p> : null}
    </Card>
  )
}

export function AuditTrail({ entityType, entityId }: { entityType: string; entityId: string }) {
  const q = useApi(() => audit.trail(entityType, entityId), [entityType, entityId])
  if (q.loading && !q.data) return <SkeletonRows rows={4} />
  if (q.error) return <ErrorState message={q.error} onRetry={q.refresh} />
  const rows = q.data ?? []
  if (!rows.length) return <Empty title="No audit rows" body="Nothing has been recorded against this entity." />
  return (
    <ol className="flex flex-col gap-2">
      {rows.map((r) => (
        <li key={r.id} className="rounded-[var(--radius-md)] border border-line bg-ivory px-4 py-3">
          <div className="flex flex-wrap items-center gap-2 text-[13px]"><span className="font-medium text-espresso">{humanise(r.action)}</span><span className="text-taupe-2">{r.actor ?? 'system'}{r.actor_role ? ` (${r.actor_role})` : ''} · {fmtDate(r.at)}</span></div>
          {r.reason && <p className="mt-1.5 text-[13.5px]">{r.reason}</p>}
          <BeforeAfter before={r.before} after={r.after} />
        </li>
      ))}
    </ol>
  )
}

export function BeforeAfter({ before, after }: { before?: Record<string, unknown> | null; after?: Record<string, unknown> | null }) {
  if (!before && !after) return null
  const keys = Array.from(new Set([...Object.keys(before ?? {}), ...Object.keys(after ?? {})]))
  if (!keys.length) return null
  return (
    <dl className="mt-2 grid grid-cols-[max-content_1fr_1fr] gap-x-4 gap-y-1 text-[12.5px]">
      <dt className="eyebrow text-[9px]">What</dt><dt className="eyebrow text-[9px]">Before</dt><dt className="eyebrow text-[9px]">After</dt>
      {keys.map((k) => (
        <div key={k} className="contents"><dt className="text-taupe-2">{humanise(k)}</dt><dd className="pencil rounded px-1.5 py-0.5 [overflow-wrap:anywhere]">{fmtVal(before?.[k])}</dd><dd className="ink rounded px-1.5 py-0.5 [overflow-wrap:anywhere]">{fmtVal(after?.[k])}</dd></div>
      ))}
    </dl>
  )
}

/** A stored code as words: TECHNICAL_SUPPORT -> Technical support. P0, DOC-007 and ids stay as they are. */
const CODE = /^[A-Z][A-Z0-9]*(_[A-Z0-9]+)+$|^[A-Z]{4,}$/
export function plainCode(v: string): string {
  return CODE.test(v) ? humanise(v) : v
}

/** Any stored value as something a person reads: no JSON, no true/false, no SHOUTING_CODES. */
export function plainValue(v: unknown): string {
  if (v === undefined || v === null || v === '') return '—'
  if (typeof v === 'boolean') return v ? 'Yes' : 'No'
  if (typeof v === 'number') return v.toLocaleString()
  if (typeof v === 'string') return v.toLowerCase() === 'true' ? 'Yes' : v.toLowerCase() === 'false' ? 'No' : plainCode(v)
  if (Array.isArray(v)) return v.length ? v.map(plainValue).join(', ') : '—'
  if (typeof v === 'object') {
    const entries = Object.entries(v as Record<string, unknown>).filter(([, x]) => x !== null && x !== undefined && x !== '')
    return entries.length ? entries.map(([k, x]) => `${humanise(k)}: ${plainValue(x)}`).join('; ') : '—'
  }
  return String(v)
}

/** Replace codes inside a sentence: "GenAI derived DELIVERY" -> "GenAI derived Delivery". */
export function plainSentence(text?: string | null): string {
  if (!text) return ''
  return text
    .replace(/^(AGREED|GENAI_PYTHON_DISAGREEMENT|PYTHON_DOES_NOT_DERIVE|[A-Z_]{6,})\s+/, '')
    .replace(/\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b|\b[A-Z]{4,}\b/g, (m) => (m === 'GENAI' ? 'GenAI' : humanise(m)))
    .replace(/\bPython\b/g, 'the rules')
}

const fmtVal = plainValue

/* ------------------------------------------------------------------ review action form */

export function ReviewActionForm({ refId, taxonomy, onDone }: { refId: string; taxonomy?: S['TaxonomyOut'] | null; onDone?: (r: S['ReviewActionOut']) => void }) {
  const { user } = useAuth()
  const [form, setForm] = useState<S['ReviewActionRequest']>({ action: 'APPROVE' })
  const act = useAction((body: S['ReviewActionRequest']) => review.act(refId, body))
  const set = <K extends keyof S['ReviewActionRequest']>(k: K, v: S['ReviewActionRequest'][K]) => setForm((f) => ({ ...f, [k]: v }))
  const needs = {
    RECLASSIFY: ['category', 'subcategory', 'department'], MODIFY: ['urgency', 'priority'], REASSIGN: ['assign_to', 'department'], ESCALATE: ['escalation'], OVERRIDE: ['category', 'subcategory', 'department', 'urgency', 'priority', 'escalation'],
  }[form.action] ?? []
  const canAct = user && ['reviewer', 'manager', 'admin'].includes(user.role)
  if (!canAct) return <p className="text-[13.5px] text-taupe-2">Review actions are available to reviewers, managers and administrators.</p>
  const opts = (rows?: S['CodeOut'][]) => (rows ?? []).map((c) => <option key={c.code} value={c.code}>{c.code} — {c.name}</option>)
  return (
    <form className="flex flex-col gap-4" onSubmit={async (e) => { e.preventDefault(); const r = await act.run(form); if (r) { onDone?.(r); setForm({ action: 'APPROVE' }) } }}>
      <Field label="Action">{(id) => <Select id={id} value={form.action} onChange={(e) => set('action', e.target.value)}>{['APPROVE', 'REJECT', 'MODIFY', 'RECLASSIFY', 'REASSIGN', 'ESCALATE', 'REGENERATE', 'COMMENT', 'OVERRIDE'].map((a) => <option key={a} value={a}>{humanise(a)}</option>)}</Select>}</Field>
      <div className="grid gap-3 sm:grid-cols-2">
        {needs.includes('category') && <Field label="Category">{(id) => <Select id={id} value={form.category ?? ''} onChange={(e) => set('category', e.target.value || null)}><option value="">— keep —</option>{opts(taxonomy?.categories)}</Select>}</Field>}
        {needs.includes('subcategory') && <Field label="Subcategory">{(id) => <Select id={id} value={form.subcategory ?? ''} onChange={(e) => set('subcategory', e.target.value || null)}><option value="">— keep —</option>{opts(taxonomy?.subcategories)}</Select>}</Field>}
        {needs.includes('department') && <Field label="Department">{(id) => <Select id={id} value={form.department ?? ''} onChange={(e) => set('department', e.target.value || null)}><option value="">— keep —</option>{opts(taxonomy?.departments)}</Select>}</Field>}
        {needs.includes('urgency') && <Field label="Urgency">{(id) => <Select id={id} value={form.urgency ?? ''} onChange={(e) => set('urgency', e.target.value || null)}><option value="">— keep —</option>{['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'].map((u) => <option key={u} value={u}>{u}</option>)}</Select>}</Field>}
        {needs.includes('priority') && <Field label="Priority">{(id) => <Select id={id} value={form.priority ?? ''} onChange={(e) => set('priority', e.target.value || null)}><option value="">— keep —</option>{opts(taxonomy?.priority_levels)}</Select>}</Field>}
        {needs.includes('escalation') && <Field label="Escalation" hint="May be raised. The floor set by a mandatory rule cannot be lowered; the API will refuse and say why.">{(id) => <Select id={id} value={form.escalation ?? ''} onChange={(e) => set('escalation', e.target.value || null)}><option value="">— keep —</option>{opts(taxonomy?.escalation_levels)}</Select>}</Field>}
        {needs.includes('assign_to') && <Field label="Assign to (user id or email)">{(id) => <input id={id} className="h-11 w-full rounded-[var(--radius-md)] border border-line bg-ivory px-3.5 text-[14px]" value={form.assign_to ?? ''} onChange={(e) => set('assign_to', e.target.value || null)} />}</Field>}
      </div>
      <Field label="Comment" hint="Recorded with the action.">{(id) => <Textarea id={id} value={form.comment ?? ''} onChange={(e) => set('comment', e.target.value || null)} rows={3} className="min-h-[90px]" />}</Field>
      {act.error && <ErrorState title="The action was refused" message={act.error} />}
      <div><Button type="submit" loading={act.pending}>Record {humanise(form.action)}</Button></div>
    </form>
  )
}

export { Loading }
