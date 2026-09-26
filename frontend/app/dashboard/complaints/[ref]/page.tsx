'use client'
// SupportNova complaint detail view (Turbopack fresh)

import { use, useState } from 'react'
import Link from 'next/link'
import { AppShell } from '@/components/layout/app-shell'
import { useAuth } from '@/lib/auth-context'
import { complaints, admin, type S } from '@/lib/api'
import { useApi, useAction, fmtDate } from '@/lib/use-api'
import { useToast } from '@/components/ui/feedback'
import { Badge, Button, Mono, humanise } from '@/components/ui/primitives'
import { Card, PanelHeader } from '@/components/ui/surfaces'
import { KV } from '@/components/ui/data'
import { ErrorState, Loading, Tabs } from '@/components/ui/feedback'
import {
  StatusBadge, OutcomeBadge, PriorityBadge, UrgencyBadge, EscalationBadge, VerificationCard, ComparisonTable, RuleHits, PolicyTrace,
  Conflicts, GenAIRuns, ResolutionSteps, Eligibility, Guidance, Entities, Links, ChecklistPanel, FollowUpsPanel, LifecyclePanel,
  SlaPanel, ReviewHistoryPanel, EscalationPanel, AuditTrail, ReviewActionForm, Clarifications, SuggestedResponsePanel,
  VerificationMeterBadge, ComplaintTextCard, ExplainabilityPanel,
} from '@/components/app/complaint-bits'
import { EvidencePanel } from '@/components/app/customer'
import { AssignControl } from '@/components/app/assign-control'

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
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <Mono className="text-[13px] text-taupe-2">{c.public_ref}</Mono>
            <StatusBadge status={c.status} />
            <OutcomeBadge outcome={c.verification_outcome} />
            <VerificationMeterBadge score={(c as any).agreement_score ?? c.verification?.agreement_score ?? null} outcome={c.verification_outcome} />
            {c.injection_suspected && <Badge tone="critical">injection suspected</Badge>}
            {c.is_duplicate && <Badge tone="warning">duplicate</Badge>}
            {(c.repeat_count ?? 0) > 1 && <Badge>repeat ×{c.repeat_count}</Badge>}
          </div>
          <h1 className="display text-h2">{c.title}</h1>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            {c.category && <Badge tone="ink">Category: {humanise(c.category)}</Badge>}
            {c.subcategory && <Badge tone="neutral">Subcategory: {humanise(c.subcategory)}</Badge>}
            {c.department && <Badge tone="info">Department: {humanise(c.department)}</Badge>}
            <UrgencyBadge u={c.urgency} />
            <PriorityBadge code={c.priority_code} />
            <EscalationBadge code={c.escalation_code} />
            {c.sentiment && <Badge>Sentiment: {humanise(c.sentiment)}</Badge>}
          </div>
          <div className="mt-3"><AssignControl complaint={c} onChanged={q.refresh} /></div>
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
            <ComplaintTextCard raw={c.description_raw} clean={c.description_clean} />
            <ExplainabilityPanel complaint={c} explain={explain.data} />
            <Card tone="cream">
              <PanelHeader title="Summary & Issues" eyebrow="AI, verified" />
              {c.summary && <p className="text-[15px] leading-relaxed mb-4">{c.summary}</p>}
              <KV rows={[
                ['Primary issue', c.primary_issue || <span className="text-taupe">—</span>],
                ['Secondary issue', c.secondary_issue || <span className="text-taupe">—</span>],
              ]} />
            </Card>
            <VerificationCard v={c.verification} />
            {(c.validation_issues ?? []).length > 0 && <Card tone="sand"><PanelHeader title="Intake findings" /><ul className="flex flex-col gap-1.5 text-[13.5px]">{c.validation_issues!.map((v, i) => <li key={i} className="flex gap-2"><Badge tone={v.severity === 'ERROR' || v.severity === 'CRITICAL' ? 'critical' : 'warning'}>{v.code}</Badge><span>{v.message}</span></li>)}</ul></Card>}
          </div>
          <div className="flex flex-col gap-6">
            <Card>
              <PanelHeader title="Facts" />
              <KV rows={[
                ['Received', fmtDate(c.created_at)],
                ['Analysed', fmtDate(c.analyzed_at)],
                ['Validated', fmtDate(c.validated_at)],
                ['Channel', c.channel ? humanise(c.channel) : null],
                ['Product', c.product],
                ['Order ref', c.order_ref ? <Mono>{c.order_ref}</Mono> : null],
                ['Transaction', c.transaction_ref ? <Mono>{c.transaction_ref}</Mono> : null],
                ['Amount', c.amount != null ? `${c.currency ?? ''} ${c.amount.toLocaleString()}` : null],
                ['Customer', c.customer_ref ? <Link href={`/dashboard/users/${encodeURIComponent(c.customer_ref)}`} className="underline decoration-line underline-offset-4 hover:text-espresso"><Mono>{c.customer_ref}</Mono></Link> : null],
                ['Supporting department', c.support_department ? humanise(c.support_department) : null],
              ]} />
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
            <WhySummary rows={explain.data!.comparisons ?? []} floor={explain.data!.escalation_floor} />
            <section><PanelHeader title="AI answer against the rules" eyebrow="Field by field" /><ComparisonTable rows={explain.data!.comparisons} /></section>
            <Conflicts rows={explain.data!.policy_conflicts} />
            <div className="grid gap-6 lg:grid-cols-2">
              <section><PanelHeader title="Rules that fired" eyebrow="Pipeline 2" /><RuleHits hits={explain.data!.rule_hits} floor={explain.data!.escalation_floor} /></section>
              <section><PanelHeader title="Policy trace" eyebrow="Every citation, resolved" /><PolicyTrace rows={explain.data!.policy_trace} /></section>
            </div>
            {/* The machinery -- model calls, versions, the raw decision record --
                is for whoever debugs the system, not for reading a complaint. */}
            <details className="group rounded-[var(--radius-lg)] border border-line bg-ivory/70 p-4">
              <summary className="cursor-pointer list-none text-[14px] font-medium text-espresso-2">
                <span className="mr-2 inline-block transition-transform group-open:rotate-90" aria-hidden>›</span>
                Technical details <span className="font-normal text-taupe-2">— AI calls, versions and the raw decision record, for troubleshooting</span>
              </summary>
              <div className="mt-4 flex flex-col gap-5">
                <p className="flex flex-wrap items-center gap-2 text-[13px] text-taupe-2">
                  <span>Rules version <Mono>{explain.data!.ruleset_version ?? '—'}</Mono></span><span>·</span><span>Policy library <Mono>{explain.data!.knowledge_base_version ?? '—'}</Mono></span>
                  {(explain.data!.reason_codes ?? []).length > 0 && <><span>·</span><span>Review reasons: {explain.data!.reason_codes!.map((r) => humanise(r)).join(', ')}</span></>}
                </p>
                <section><PanelHeader title="AI calls" eyebrow="Every attempt, including failed ones" /><GenAIRuns runs={explain.data!.genai_runs} /></section>
                {explain.data!.reconciled && Object.keys(explain.data!.reconciled).length > 0 && (
                  <section><p className="eyebrow mb-2">Raw decision record</p><pre className="overflow-x-auto rounded-[var(--radius-md)] bg-espresso p-4 font-mono text-[12px] text-ink-on-dark">{JSON.stringify(explain.data!.reconciled, null, 2)}</pre></section>
                )}
              </div>
            </details>
          </div>
        )
      )}

      {tab === 'resolution' && (
        <div className="grid gap-6 lg:grid-cols-[1.2fr_1fr]">
          <div className="flex flex-col gap-6">
            <section><PanelHeader title="Checklist" eyebrow="Required steps, confirmed by a person" /><ChecklistPanel refId={refId} canConfirm={Boolean(canAct)} /></section>
            <section><PanelHeader title="Resolution steps" eyebrow="Proposed and verified" /><ResolutionSteps steps={c.resolution_steps} /></section>
            <section><SuggestedResponsePanel refId={refId} canAct={Boolean(canAct)} /></section>
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

      {tab === 'audit' && <section><PanelHeader title="Audit trail" eyebrow="This complaint" />{oversight || user?.role === 'reviewer' ? <AuditTrail entityType="complaint" entityId={c.id} /> : <p className="text-[13.5px] text-taupe-2">A complaint's audit trail is visible to reviewers, managers and administrators.</p>}</section>}
    </div>
  )
}

/** The comparison in one paragraph, before the table that backs it up. */
function WhySummary({ rows, floor }: { rows: S['ComparisonOut'][]; floor?: string | null }) {
  if (!rows.length) return null
  const compared = rows.filter((r) => r.genai_value != null && r.python_value != null)
  const agreed = compared.filter((r) => r.status === 'MATCH' || r.status === 'AGREED').length
  const corrected = compared.filter((r) => r.status === 'MISMATCH' || r.status === 'CONFLICT')
  return (
    <Card tone="glass" radius="xl">
      <p className="text-[15px] leading-relaxed text-espresso-2">
        The AI and the company&rsquo;s rules each decided this complaint on their own.
        {' '}They <strong className="font-medium text-espresso">agreed on {agreed} of {compared.length}</strong> fields they both answered.
        {corrected.length > 0 && <> Where they differed ({corrected.map((r) => humanise(r.field).toLowerCase()).join(', ')}), <strong className="font-medium text-espresso">the rules&rsquo; answer was used</strong> and the complaint went to a person to check.</>}
        {floor && floor !== 'NONE' && <> A mandatory rule sets the lowest allowed escalation at <strong className="font-medium text-espresso">{humanise(floor)}</strong>; nobody can lower it.</>}
      </p>
    </Card>
  )
}
