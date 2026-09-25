'use client'

import { use, useState } from 'react'
import { AppShell } from '@/components/layout/app-shell'
import { useAuth } from '@/lib/auth-context'
import { complaints, admin } from '@/lib/api'
import { useApi, useAction, fmtDate } from '@/lib/use-api'
import { useToast } from '@/components/ui/feedback'
import { Badge, Button, Mono, humanise } from '@/components/ui/primitives'
import { Card, PanelHeader } from '@/components/ui/surfaces'
import { KV } from '@/components/ui/data'
import { ErrorState, Loading, Tabs } from '@/components/ui/feedback'
import {
  StatusBadge, OutcomeBadge, PriorityBadge, UrgencyBadge, EscalationBadge, VerificationCard, ComparisonTable, RuleHits, PolicyTrace,
  Conflicts, GenAIRuns, ResolutionSteps, Eligibility, Guidance, Entities, Links, ChecklistPanel, FollowUpsPanel, LifecyclePanel,
  SlaPanel, ReviewHistoryPanel, EscalationPanel, AuditTrail, ReviewActionForm, Clarifications,
} from '@/components/app/complaint-bits'
import { EvidencePanel } from '@/components/app/customer'

const STAFF = ['agent', 'reviewer', 'manager', 'admin', 'evaluator'] as const
type Tab = 'overview' | 'why' | 'resolution' | 'followups' | 'lifecycle' | 'review' | 'audit'

export default function ComplaintPage({ params }: { params: Promise<{ ref: string }> }) {
  const { ref } = use(params)
  const refId = decodeURIComponent(ref)
  return (
    <AppShell eyebrow={<span>Complaints / <Mono>{refId}</Mono></span>} roles={[...STAFF]} wide>
      <Detail refId={refId} />
    </AppShell>
  )
}

function Detail({ refId }: { refId: string }) {
  const { user } = useAuth()
  const toast = useToast()
  const [tab, setTab] = useState<Tab>('overview')
  const q = useApi(() => complaints.get(refId), [refId])
  const explain = useApi(() => complaints.explain(refId), [refId])
  const oversight = user && ['manager', 'admin', 'evaluator'].includes(user.role)
  const canReanalyse = user && ['manager', 'admin'].includes(user.role)
  const canAct = user && ['agent', 'reviewer', 'manager', 'admin'].includes(user.role)
  const taxonomy = useApi(() => admin.taxonomy(), [], Boolean(oversight))
  const reanalyse = useAction((genai: boolean) => complaints.reanalyse(refId, genai))

  if (q.loading && !q.data) return <Loading label="Opening the complaint" />
  if (q.error) return <ErrorState message={q.error} onRetry={q.refresh} />
  const c = q.data!

  const onReanalyse = async (genai: boolean) => {
    const r = await reanalyse.run(genai)
    if (r) {
      const changed = Object.keys(r.changed ?? {})
      toast('ok', changed.length ? `Re-analysed. Changed: ${changed.join(', ')}` : 'Re-analysed. Nothing changed.')
      q.refresh(); explain.refresh()
    } else if (reanalyse.error) toast('err', reanalyse.error)
  }

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="mb-2 flex flex-wrap items-center gap-2"><Mono className="text-[13px] text-taupe-2">{c.public_ref}</Mono><StatusBadge status={c.status} /><OutcomeBadge outcome={c.verification_outcome} />{c.injection_suspected && <Badge tone="critical">injection suspected</Badge>}{c.is_duplicate && <Badge tone="warning">duplicate</Badge>}{(c.repeat_count ?? 0) > 1 && <Badge>repeat ×{c.repeat_count}</Badge>}</div>
          <h1 className="display text-h2">{c.title}</h1>
          <div className="mt-3 flex flex-wrap items-center gap-2">{c.category && <Badge tone="ink">{humanise(c.category)}</Badge>}{c.subcategory && <Badge>{humanise(c.subcategory)}</Badge>}{c.department && <Badge tone="info">{humanise(c.department)}</Badge>}<UrgencyBadge u={c.urgency} /><PriorityBadge code={c.priority_code} /><EscalationBadge code={c.escalation_code} />{c.sentiment && <Badge>{humanise(c.sentiment)}</Badge>}</div>
        </div>
        {canReanalyse && (
          <div className="flex gap-2">
            <Button variant="secondary" size="sm" loading={reanalyse.pending} onClick={() => onReanalyse(true)}>Re-run both pipelines</Button>
            <Button variant="ghost" size="sm" loading={reanalyse.pending} onClick={() => onReanalyse(false)}>Rules only</Button>
          </div>
        )}
      </header>

      <Tabs<Tab>
        value={tab}
        onChange={setTab}
        tabs={[
          { id: 'overview', label: 'Overview' }, { id: 'why', label: 'Why', count: explain.data?.comparisons?.length ?? null }, { id: 'resolution', label: 'Resolution' },
          { id: 'followups', label: 'Follow-ups' }, { id: 'lifecycle', label: 'Lifecycle' }, { id: 'review', label: 'Review' }, { id: 'audit', label: 'Audit' },
        ]}
      />

      {tab === 'overview' && (
        <div className="grid gap-6 lg:grid-cols-[1.3fr_1fr]">
          <div className="flex flex-col gap-6">
            <Card>
              <PanelHeader title="The complaint" eyebrow="As written" />
              <p className="whitespace-pre-wrap font-display text-[17px] leading-relaxed">{c.description_raw}</p>
              {c.description_clean !== c.description_raw && <details className="mt-4 text-[13px] text-taupe-2"><summary className="cursor-pointer">Normalised text used by the pipelines</summary><p className="mt-2 whitespace-pre-wrap">{c.description_clean}</p></details>}
            </Card>
            {c.summary && <Card tone="cream"><PanelHeader title="Summary" eyebrow="AI, verified" /><p className="text-[15px] leading-relaxed">{c.summary}</p>{(c.primary_issue || c.secondary_issue) && <KV className="mt-4" rows={[['Primary issue', c.primary_issue], ['Secondary issue', c.secondary_issue]]} />}</Card>}
            <VerificationCard v={c.verification} />
            {(c.validation_issues ?? []).length > 0 && <Card tone="sand"><PanelHeader title="Intake findings" /><ul className="flex flex-col gap-1.5 text-[13.5px]">{c.validation_issues!.map((v, i) => <li key={i} className="flex gap-2"><Badge tone={v.severity === 'ERROR' || v.severity === 'CRITICAL' ? 'critical' : 'warning'}>{v.code}</Badge><span>{v.message}</span></li>)}</ul></Card>}
          </div>
          <div className="flex flex-col gap-6">
            <Card>
              <PanelHeader title="Facts" />
              <KV rows={[['Received', fmtDate(c.created_at)], ['Analysed', fmtDate(c.analyzed_at)], ['Validated', fmtDate(c.validated_at)], ['Channel', c.channel ? humanise(c.channel) : null], ['Product', c.product], ['Order ref', c.order_ref ? <Mono>{c.order_ref}</Mono> : null], ['Transaction', c.transaction_ref ? <Mono>{c.transaction_ref}</Mono> : null], ['Amount', c.amount != null ? `${c.currency ?? ''} ${c.amount.toLocaleString()}` : null], ['Customer', c.customer_ref ? <Mono>{c.customer_ref}</Mono> : null], ['Support dept', c.support_department ? humanise(c.support_department) : null]]} />
            </Card>
            <Card><PanelHeader title="Entities" /><Entities rows={c.entities} /></Card>
            {(c.emotion_indicators ?? []).length > 0 && <Card><PanelHeader title="Emotion indicators" /><div className="flex flex-wrap gap-1.5">{(c.emotion_indicators as unknown[]).map((e, i) => <Badge key={i}>{String(e)}</Badge>)}</div></Card>}
            {(c.missing_information ?? []).length > 0 && <Card tone="sand"><PanelHeader title="Missing information" /><ul className="list-disc pl-5 text-[13.5px]">{(c.missing_information as unknown[]).map((m, i) => <li key={i}>{String(m)}</li>)}</ul></Card>}
            {(c.clarifications ?? []).length > 0 && <Card><PanelHeader title="Clarifying questions" eyebrow="Asked instead of guessed" /><Clarifications rows={c.clarifications} /></Card>}
            <EvidencePanel refId={c.public_ref} evidence={c.evidence ?? []} onUploaded={() => void q.refresh()} compact />
            {(c.links ?? []).length > 0 && <Card><PanelHeader title="Related complaints" /><Links rows={c.links} /></Card>}
            <EscalationPanel refId={refId} />
          </div>
        </div>
      )}

      {tab === 'why' && (
        explain.loading && !explain.data ? <Loading label="Explaining" /> : explain.error ? <ErrorState message={explain.error} onRetry={explain.refresh} /> : (
          <div className="flex flex-col gap-6">
            <div className="flex flex-wrap items-center gap-3 text-[13px] text-taupe-2">
              <span>Ruleset <Mono>{explain.data!.ruleset_version ?? '—'}</Mono></span><span>·</span><span>Knowledge base <Mono>{explain.data!.knowledge_base_version ?? '—'}</Mono></span>
              {explain.data!.escalation_floor && <><span>·</span><span>Floor <EscalationBadge code={explain.data!.escalation_floor} /></span></>}
              {(explain.data!.reason_codes ?? []).length > 0 && <><span>·</span><span className="flex flex-wrap gap-1">{explain.data!.reason_codes!.map((r) => <Badge key={r}><Mono>{r}</Mono></Badge>)}</span></>}
            </div>
            <section><PanelHeader title="Pencil against ink" eyebrow="Field by field" /><ComparisonTable rows={explain.data!.comparisons} /></section>
            <Conflicts rows={explain.data!.policy_conflicts} />
            <div className="grid gap-6 lg:grid-cols-2">
              <section><PanelHeader title="Rules that fired" eyebrow="Pipeline 2" /><RuleHits hits={explain.data!.rule_hits} floor={explain.data!.escalation_floor} /></section>
              <section><PanelHeader title="Policy trace" eyebrow="Every citation, resolved" /><PolicyTrace rows={explain.data!.policy_trace} /></section>
            </div>
            <section><PanelHeader title="GenAI runs" eyebrow="Pipeline 1" /><GenAIRuns runs={explain.data!.genai_runs} /></section>
            {explain.data!.reconciled && Object.keys(explain.data!.reconciled).length > 0 && (
              <details className="text-[13px]"><summary className="cursor-pointer text-taupe-2">Reconciled record (raw)</summary><pre className="mt-2 overflow-x-auto rounded-[var(--radius-md)] bg-espresso p-4 font-mono text-[12px] text-ink-on-dark">{JSON.stringify(explain.data!.reconciled, null, 2)}</pre></details>
            )}
          </div>
        )
      )}

      {tab === 'resolution' && (
        <div className="grid gap-6 lg:grid-cols-[1.2fr_1fr]">
          <div className="flex flex-col gap-6">
            <section><PanelHeader title="Checklist" eyebrow="Required steps, confirmed by a person" /><ChecklistPanel refId={refId} canConfirm={Boolean(canAct)} /></section>
            <section><PanelHeader title="Resolution steps" eyebrow="Proposed and verified" /><ResolutionSteps steps={c.resolution_steps} /></section>
          </div>
          <div className="flex flex-col gap-6">
            <section><PanelHeader title="Eligibility" /><Eligibility rows={c.eligibility} /></section>
            {(c.guidance ?? []).length > 0 && <section><PanelHeader title="Guidance" eyebrow="Required and prohibited" /><Guidance rows={c.guidance} /></section>}
            <section><PanelHeader title="SLA" /><SlaPanel refId={refId} /></section>
          </div>
        </div>
      )}

      {tab === 'followups' && <section><PanelHeader title="Follow-ups" eyebrow="Commitments with due dates" /><FollowUpsPanel refId={refId} canComplete={Boolean(canAct)} /></section>}

      {tab === 'lifecycle' && <section><PanelHeader title="Lifecycle" eyebrow="Every transition, who and why" /><LifecyclePanel refId={refId} canChange={Boolean(canAct)} onChanged={() => q.refresh()} /></section>}

      {tab === 'review' && (
        <div className="grid gap-6 lg:grid-cols-2">
          <section><PanelHeader title="Review history" /><ReviewHistoryPanel refId={refId} /></section>
          <section><PanelHeader title="Record an action" eyebrow="Reviewers, managers, admins" /><Card><ReviewActionForm refId={refId} taxonomy={taxonomy.data} onDone={(r) => { toast('ok', `${humanise(r.action)} recorded${r.is_override ? ' as an override' : ''}.`); q.refresh(); explain.refresh() }} /></Card></section>
        </div>
      )}

      {tab === 'audit' && <section><PanelHeader title="Audit trail" eyebrow="This complaint" />{oversight ? <AuditTrail entityType="complaint" entityId={c.id} /> : <p className="text-[13.5px] text-taupe-2">The audit trail is visible to managers, administrators and evaluators.</p>}</section>}
    </div>
  )
}
