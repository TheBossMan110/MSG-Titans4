'use client'

import { Suspense, useMemo } from 'react'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'
import { AppShell } from '@/components/layout/app-shell'
import { complaints, admin, COMPLAINT_STATUSES, URGENCIES, PRIORITIES, VERIFICATION_OUTCOMES } from '@/lib/api'
import { useApi } from '@/lib/use-api'
import { useAuth } from '@/lib/auth-context'
import { Button, humanise } from '@/components/ui/primitives'
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

function Register() {
  const { user } = useAuth()
  const f = useFilters()
  const oversight = user && ['manager', 'admin', 'evaluator'].includes(user.role)
  const taxonomy = useApi(() => admin.taxonomy(), [], Boolean(oversight))
  const filters = useMemo(() => ({
    page: f.page, size: 25, status: f.get('status'), category: f.get('category'), department: f.get('department'),
    urgency: f.get('urgency'), priority: f.get('priority'), verification_outcome: f.get('verification_outcome'),
    requires_review: f.get('requires_review') === '1' ? true : undefined, dataset_tag: f.get('dataset_tag'), search: f.get('search'),
  }), [f]) // eslint-disable-line react-hooks/exhaustive-deps
  const q = useApi(() => complaints.list(filters), [JSON.stringify(filters)])

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div><p className="eyebrow mb-1">Register</p><h1 className="display text-h2">Complaints</h1></div>
        <Button href="/dashboard/complaints/new">Submit a complaint</Button>
      </div>

      <div className="glass grid gap-2 rounded-[var(--radius-xl)] p-3 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-6">
        <SearchBox value={f.get('search')} onChange={(v) => f.set({ search: v })} placeholder="Search text or reference" className="sm:col-span-2 lg:col-span-3 2xl:col-span-6" />
        <Select value={f.get('status')} onChange={(e) => f.set({ status: e.target.value })} aria-label="Status"><option value="">Any status</option>{COMPLAINT_STATUSES.map((s) => <option key={s} value={s}>{humanise(s)}</option>)}</Select>
        <Select value={f.get('category')} onChange={(e) => f.set({ category: e.target.value })} aria-label="Category"><option value="">Any category</option>{(taxonomy.data?.categories ?? []).map((c) => <option key={c.code} value={c.code}>{c.name}</option>)}</Select>
        <Select value={f.get('department')} onChange={(e) => f.set({ department: e.target.value })} aria-label="Department"><option value="">Any department</option>{(taxonomy.data?.departments ?? []).map((c) => <option key={c.code} value={c.code}>{c.name}</option>)}</Select>
        <Select value={f.get('urgency')} onChange={(e) => f.set({ urgency: e.target.value })} aria-label="Urgency"><option value="">Any urgency</option>{URGENCIES.map((u) => <option key={u} value={u}>{humanise(u)}</option>)}</Select>
        <Select value={f.get('priority')} onChange={(e) => f.set({ priority: e.target.value })} aria-label="Priority"><option value="">Any priority</option>{PRIORITIES.map((p) => <option key={p} value={p}>{p}</option>)}</Select>
        <Select value={f.get('verification_outcome')} onChange={(e) => f.set({ verification_outcome: e.target.value })} aria-label="Verification"><option value="">Any verification</option>{VERIFICATION_OUTCOMES.map((v) => <option key={v} value={v}>{humanise(v)}</option>)}</Select>
        <div className="flex flex-wrap items-center gap-4 px-1 sm:col-span-2 lg:col-span-3 2xl:col-span-6">
          <Checkbox label="Needs review only" checked={f.get('requires_review') === '1'} onChange={(e) => f.set({ requires_review: e.target.checked ? '1' : '' })} />
          <input value={f.get('dataset_tag')} onChange={(e) => f.set({ dataset_tag: e.target.value })} placeholder="Dataset tag" aria-label="Dataset tag" className="h-9 rounded-[var(--radius-md)] border border-line bg-ivory px-3 text-[13px]" />
          {(f.get('search') || f.get('status') || f.get('category') || f.get('department') || f.get('urgency') || f.get('priority') || f.get('verification_outcome') || f.get('requires_review') || f.get('dataset_tag')) && <button className="text-[13px] text-taupe-2 underline underline-offset-4" onClick={() => f.set({ search: '', status: '', category: '', department: '', urgency: '', priority: '', verification_outcome: '', requires_review: '', dataset_tag: '' })}>Clear</button>}
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
