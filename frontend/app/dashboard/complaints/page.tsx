'use client'

import { Suspense, useMemo } from 'react'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'
import { AppShell } from '@/components/layout/app-shell'
import { complaints, organisation, COMPLAINT_STATUSES, URGENCIES, PRIORITIES, VERIFICATION_OUTCOMES } from '@/lib/api'
import { useApi } from '@/lib/use-api'
import { humanise } from '@/components/ui/primitives'
import { Select, SearchBox, Checkbox } from '@/components/ui/forms'
import { Pagination } from '@/components/ui/data'
import { ErrorState, SkeletonRows } from '@/components/ui/feedback'
import { ComplaintTable } from '@/components/app/complaint-bits'

const STAFF = ['agent', 'reviewer', 'manager', 'admin', 'evaluator'] as const

export default function ComplaintsPage() {
  return (
    <AppShell eyebrow="Complaints" roles={[...STAFF]} wide>
      <Suspense fallback={<SkeletonRows rows={8} />}>
        <Register />
      </Suspense>
    </AppShell>
  )
}

/** Filters live in the URL so a view can be shared and the back button works. */
function useFilters() {
  const params = useSearchParams()
  const router = useRouter()
  const pathname = usePathname()
  const get = (k: string) => params.get(k) ?? ''
  const set = (patch: Record<string, string | boolean | number | undefined>) => {
    const next = new URLSearchParams(params.toString())
    for (const [k, v] of Object.entries(patch)) {
      if (v === undefined || v === '' || v === false) next.delete(k)
      else next.set(k, String(v))
    }
    if (!('page' in patch)) next.delete('page')
    router.replace(`${pathname}?${next.toString()}`)
  }
  return { get, set, page: Number(params.get('page') || 1) }
}

// Every filter the register understands; "Clear" resets exactly these.
const FILTER_KEYS = [
  'search', 'status', 'category', 'department', 'urgency', 'priority',
  'verification_outcome', 'requires_review', 'dataset_tag', 'customer_type',
  'sentiment', 'escalation', 'date_from', 'date_to',
] as const

function Register() {
  const f = useFilters()
  // Categories, teams, customer types and datasets for the dropdowns. Readable
  // by every staff role -- the admin taxonomy endpoint left agents and
  // reviewers with empty lists.
  const org = useApi(() => organisation.get())
  const filters = useMemo(() => ({
    page: f.page, size: 25, status: f.get('status'), category: f.get('category'), department: f.get('department'),
    urgency: f.get('urgency'), priority: f.get('priority'), verification_outcome: f.get('verification_outcome'),
    requires_review: f.get('requires_review') === '1' ? true : undefined, dataset_tag: f.get('dataset_tag'),
    customer_type: f.get('customer_type'), sentiment: f.get('sentiment'), escalation: f.get('escalation'),
    date_from: f.get('date_from'), date_to: f.get('date_to'), search: f.get('search'),
  }), [f]) // eslint-disable-line react-hooks/exhaustive-deps
  const q = useApi(() => complaints.list(filters), [JSON.stringify(filters)], true, { live: true })

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div><p className="eyebrow mb-1">Register</p><h1 className="display text-h2">Complaints</h1></div>
        {q.data && <p className="text-[14px] text-taupe"><span className="font-medium tnum text-espresso">{q.data.total.toLocaleString()}</span> {q.data.total === 1 ? 'complaint' : 'complaints'}{FILTER_KEYS.some((k) => f.get(k)) ? ' match these filters' : ' in total'}</p>}
      </div>

      <div className="glass grid gap-2 rounded-[var(--radius-xl)] p-3 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-6">
        <SearchBox value={f.get('search')} onChange={(v) => f.set({ search: v })} placeholder="Search: complaint ID, customer or order reference, or any words" className="sm:col-span-2 lg:col-span-3 2xl:col-span-6" />
        <Select value={f.get('status')} onChange={(e) => f.set({ status: e.target.value })} aria-label="Status"><option value="">Any status</option>{COMPLAINT_STATUSES.map((s) => <option key={s} value={s}>{humanise(s)}</option>)}</Select>
        <Select value={f.get('category')} onChange={(e) => f.set({ category: e.target.value })} aria-label="Category"><option value="">Any category</option>{(org.data?.categories ?? []).map((c) => <option key={c.code} value={c.code}>{c.name}</option>)}</Select>
        <Select value={f.get('department')} onChange={(e) => f.set({ department: e.target.value })} aria-label="Department"><option value="">Any department</option>{(org.data?.departments ?? []).map((c) => <option key={c.code} value={c.code}>{c.name}</option>)}</Select>
        <Select value={f.get('urgency')} onChange={(e) => f.set({ urgency: e.target.value })} aria-label="Urgency"><option value="">Any urgency</option>{URGENCIES.map((u) => <option key={u} value={u}>{humanise(u)}</option>)}</Select>
        <Select value={f.get('priority')} onChange={(e) => f.set({ priority: e.target.value })} aria-label="Priority"><option value="">Any priority</option>{PRIORITIES.map((p) => <option key={p} value={p}>{p}</option>)}</Select>
        <Select value={f.get('verification_outcome')} onChange={(e) => f.set({ verification_outcome: e.target.value })} aria-label="Verification"><option value="">Any verification</option>{VERIFICATION_OUTCOMES.map((v) => <option key={v} value={v}>{humanise(v)}</option>)}</Select>
        <Select value={f.get('customer_type')} onChange={(e) => f.set({ customer_type: e.target.value })} aria-label="Customer type" className="sm:col-span-1 lg:col-span-1 2xl:col-span-3"><option value="">Any customer type</option>{(org.data?.profile.customer_types ?? []).map((t) => <option key={t} value={t}>{t}</option>)}</Select>
        <Select value={f.get('dataset_tag')} onChange={(e) => f.set({ dataset_tag: e.target.value })} aria-label="Dataset" className="sm:col-span-1 lg:col-span-2 2xl:col-span-3"><option value="">Any source</option>{(org.data?.datasets ?? []).map((d) => <option key={d.dataset_tag} value={d.dataset_tag}>{humanise(d.dataset_tag)} dataset ({d.total})</option>)}</Select>
        <Select value={f.get('sentiment')} onChange={(e) => f.set({ sentiment: e.target.value })} aria-label="Sentiment"><option value="">Any sentiment</option>{['STRONGLY_NEGATIVE', 'NEGATIVE', 'NEUTRAL', 'POSITIVE'].map((v) => <option key={v} value={v}>{humanise(v)}</option>)}</Select>
        <Select value={f.get('escalation')} onChange={(e) => f.set({ escalation: e.target.value })} aria-label="Escalation"><option value="">Any escalation</option><option value="ANY">Escalated</option><option value="NONE">Not escalated</option>{['SUPERVISOR', 'SPECIALIST', 'DEPT_MANAGER', 'COMPLIANCE_REVIEW', 'CRITICAL_MGMT'].map((v) => <option key={v} value={v}>{humanise(v)}</option>)}</Select>
        <label className="flex items-center gap-2 text-[13px] text-taupe-2">From<input type="date" value={f.get('date_from')} onChange={(e) => f.set({ date_from: e.target.value })} aria-label="Received from" className="h-11 flex-1 rounded-[var(--radius-md)] border border-line bg-ivory px-3 text-[14px] text-espresso" /></label>
        <label className="flex items-center gap-2 text-[13px] text-taupe-2">To<input type="date" value={f.get('date_to')} onChange={(e) => f.set({ date_to: e.target.value })} aria-label="Received to" className="h-11 flex-1 rounded-[var(--radius-md)] border border-line bg-ivory px-3 text-[14px] text-espresso" /></label>
        <div className="flex flex-wrap items-center gap-4 px-1 sm:col-span-2 lg:col-span-3 2xl:col-span-6">
          <Checkbox label="Needs review only" checked={f.get('requires_review') === '1'} onChange={(e) => f.set({ requires_review: e.target.checked ? '1' : '' })} />
          {FILTER_KEYS.some((k) => f.get(k)) && <button className="text-[13px] text-taupe-2 underline underline-offset-4" onClick={() => f.set(Object.fromEntries(FILTER_KEYS.map((k) => [k, ''])))}>Clear filters</button>}
        </div>
      </div>

      {q.error ? <ErrorState message={q.error} onRetry={q.refresh} /> : q.loading && !q.data ? <SkeletonRows rows={10} /> : (
        <>
          <ComplaintTable items={q.data!.items} />
          <Pagination page={f.page} size={25} total={q.data!.total} onPage={(p) => f.set({ page: p })} />
        </>
      )}
    </div>
  )
}
