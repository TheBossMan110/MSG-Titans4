'use client'

import { useState } from 'react'
import { AppShell } from '@/components/layout/app-shell'
import { audit } from '@/lib/api'
import { useApi, fmtDate } from '@/lib/use-api'
import { Badge, Button, Mono, humanise } from '@/components/ui/primitives'
import { Card } from '@/components/ui/surfaces'
import { Input, Select } from '@/components/ui/forms'
import { Pagination } from '@/components/ui/data'
import { Empty, ErrorState, SkeletonRows } from '@/components/ui/feedback'
import { BeforeAfter } from '@/components/app/complaint-bits'
import { Bars } from '@/components/app/charts'

const ENTITY_TYPES = ['complaint', 'review', 'rule', 'config', 'lexicon', 'sla_policy', 'prompt', 'document', 'document_version', 'auth', 'benchmark', 'dataset', 'export']

export default function AuditPage() {
  return (
    <AppShell eyebrow="Audit trail" roles={['manager', 'admin', 'evaluator']} wide>
      <Trail />
    </AppShell>
  )
}

/**
 * The organisation's trail, newest first, filterable by entity, action and
 * actor. Each row shows before and after in pencil and ink. This is the page
 * that makes "every action is audited" a thing you can scroll.
 */
function Trail() {
  const [page, setPage] = useState(1)
  const [entityType, setEntityType] = useState('')
  const [action, setAction] = useState('')
  const [actor, setActor] = useState('')
  const [entityId, setEntityId] = useState('')
  const q = useApi(() => audit.list({ page, size: 30, entity_type: entityType || undefined, action: action || undefined, actor: actor || undefined, entity_id: entityId || undefined }), [page, entityType, action, actor, entityId])
  const actions = useApi(() => audit.actions())

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div><p className="eyebrow mb-1">Trust</p><h1 className="display text-h2">Audit trail</h1></div>
        <Button variant="secondary" size="sm" onClick={() => { q.refresh(); actions.refresh() }}>Refresh</Button>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        <div className="flex flex-col gap-4">
          <div className="grid gap-2 rounded-[var(--radius-lg)] border border-line bg-ivory p-3 sm:grid-cols-4">
            <Select value={entityType} onChange={(e) => { setEntityType(e.target.value); setPage(1) }} aria-label="Entity type"><option value="">Any entity</option>{ENTITY_TYPES.map((t) => <option key={t} value={t}>{humanise(t)}</option>)}</Select>
            <Select value={action} onChange={(e) => { setAction(e.target.value); setPage(1) }} aria-label="Action"><option value="">Any action</option>{(actions.data ?? []).map((a) => <option key={a.action} value={a.action}>{a.action} ({a.count})</option>)}</Select>
            <Input value={actor} onChange={(e) => { setActor(e.target.value); setPage(1) }} placeholder="Actor (email or id)" aria-label="Actor" />
            <Input value={entityId} onChange={(e) => { setEntityId(e.target.value); setPage(1) }} placeholder="Entity id / reference" aria-label="Entity id" className="font-mono" />
          </div>
          {q.error ? <ErrorState message={q.error} onRetry={q.refresh} /> : q.loading && !q.data ? <SkeletonRows rows={10} /> : !q.data!.items.length ? <Empty title="No rows" body="Nothing matches these filters." /> : (
            <>
              <ol className="flex flex-col gap-2">
                {q.data!.items.map((r) => (
                  <li key={r.id} className="rounded-[var(--radius-md)] border border-line bg-ivory px-4 py-3">
                    <div className="flex flex-wrap items-center gap-2 text-[13px]">
                      <Mono className="font-medium">{r.action}</Mono>
                      <Badge>{humanise(r.entity_type)}</Badge>
                      <button className="font-mono text-[12px] text-taupe-2 underline decoration-line underline-offset-4" onClick={() => { setEntityId(r.entity_id); setEntityType(r.entity_type); setPage(1) }}>{r.entity_id}</button>
                      <span className="ml-auto text-[12.5px] text-taupe-2">{r.actor ?? 'system'}{r.actor_role ? ` (${r.actor_role})` : ''} · {fmtDate(r.at)}</span>
                    </div>
                    {r.reason && <p className="mt-1.5 text-[13.5px]">{r.reason}</p>}
                    <BeforeAfter before={r.before} after={r.after} />
                    {r.request_id && <p className="mt-1.5 font-mono text-[10.5px] text-taupe">{r.request_id}</p>}
                  </li>
                ))}
              </ol>
              <Pagination page={page} size={30} total={q.data!.total} onPage={setPage} />
            </>
          )}
        </div>
        <Card className="self-start">
          <p className="eyebrow mb-3">Actions recorded</p>
          {actions.loading && !actions.data ? <SkeletonRows rows={6} /> : actions.error ? <p className="text-[13px] text-critical">{actions.error}</p> : <Bars rows={(actions.data ?? []).slice(0, 20).map((a) => ({ label: a.action, value: a.count }))} tone="taupe" />}
        </Card>
      </div>
    </div>
  )
}
