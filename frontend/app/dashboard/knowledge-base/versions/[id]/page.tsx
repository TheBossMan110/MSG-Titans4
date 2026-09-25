'use client'

import { use, useState } from 'react'
import Link from 'next/link'
import { AppShell } from '@/components/layout/app-shell'
import { useAuth } from '@/lib/auth-context'
import { knowledge, type S } from '@/lib/api'
import { useApi, useAction, fmtDate } from '@/lib/use-api'
import { Badge, Button, Mono, humanise } from '@/components/ui/primitives'
import { Card, PanelHeader } from '@/components/ui/surfaces'
import { KV, Table, Th, Td, Tr } from '@/components/ui/data'
import { Empty, ErrorState, Loading, Modal, Tabs, useToast } from '@/components/ui/feedback'
import { StatusBadge } from '@/components/app/complaint-bits'

export default function VersionPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params)
  return (
    <AppShell eyebrow="Knowledge base / Version" roles={['agent', 'reviewer', 'manager', 'admin', 'evaluator']} wide>
      <Version id={id} />
    </AppShell>
  )
}

/**
 * One version of one document: its sections, its chunks, and, for an admin,
 * the activate / deactivate controls with the impact report the backend
 * returns -- which complaints cited the version being superseded.
 */
function Version({ id }: { id: string }) {
  const { user } = useAuth()
  const toast = useToast()
  const [tab, setTab] = useState<'sections' | 'chunks' | 'issues' | 'impact'>('sections')
  const q = useApi(() => knowledge.version(id), [id])
  const chunks = useApi(() => knowledge.chunks(id), [id], tab === 'chunks')
  const impact = useApi(() => knowledge.impact(id), [id], tab === 'impact')
  const [activation, setActivation] = useState<S['ActivationResponse'] | null>(null)
  const activate = useAction(() => knowledge.activate(id))
  const deactivate = useAction(() => knowledge.deactivate(id))
  const isAdmin = user?.role === 'admin'

  if (q.loading && !q.data) return <Loading label="Opening the version" />
  if (q.error) return <ErrorState message={q.error} onRetry={q.refresh} />
  const v = q.data!

  const onActivate = async () => { const r = await activate.run(); if (r) { setActivation(r); q.refresh() } else if (activate.error) toast('err', activate.error) }
  const onDeactivate = async () => { const r = await deactivate.run(); if (r) { toast('warn', r.message); q.refresh() } else if (deactivate.error) toast('err', deactivate.error) }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="eyebrow mb-2"><Link href="/dashboard/knowledge-base" className="underline decoration-line underline-offset-4">Knowledge base</Link> / <Mono>{v.doc_ref}</Mono> / <Mono>{v.version}</Mono></p>
          <h1 className="display text-h2">{v.title ?? v.doc_ref}</h1>
          <div className="mt-3 flex flex-wrap gap-2"><Badge tone={v.status === 'ACTIVE' ? 'verified' : v.status === 'REJECTED' ? 'critical' : v.status === 'SUPERSEDED' || v.status === 'EXPIRED' ? 'neutral' : 'warning'}>{v.status}</Badge><Badge>{v.file_format.toUpperCase()}</Badge><Badge tone={v.parse_status === 'PARSED' || v.parse_status === 'OK' ? 'verified' : 'critical'}>{humanise(v.parse_status)}</Badge>{!v.metadata_complete && <Badge tone="warning">metadata incomplete</Badge>}</div>
        </div>
        {isAdmin && (
          <div className="flex gap-2">
            {v.status !== 'ACTIVE' && <Button loading={activate.pending} onClick={onActivate}>Activate this version</Button>}
            {v.status === 'ACTIVE' && <Button variant="danger" loading={deactivate.pending} onClick={onDeactivate}>Deactivate</Button>}
          </div>
        )}
      </div>

      {v.parse_error && <ErrorState title="This file did not parse cleanly" message={v.parse_error} />}

      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        <div className="flex flex-col gap-4">
          <Tabs value={tab} onChange={setTab} tabs={[{ id: 'sections', label: 'Sections', count: v.section_count ?? v.sections?.length ?? null }, { id: 'chunks', label: 'Chunks', count: v.chunk_count ?? null }, { id: 'issues', label: 'Findings', count: v.validation_issues?.length ?? null }, { id: 'impact', label: 'Impact' }]} />

          {tab === 'sections' && (!v.sections?.length ? <Empty title="No sections" body="The parser found no headings in this file." /> : (
            <ol className="flex flex-col gap-3">
              {v.sections.map((s) => (
                <li key={s.id} id={`s-${s.section_ref}`} className="rounded-[var(--radius-lg)] border border-line bg-ivory p-5">
                  <div className="mb-2 flex flex-wrap items-center gap-2"><Mono className="text-[12px] text-taupe-2">§{s.section_ref}</Mono>{s.heading && <h3 className="font-display text-[18px]" style={{ marginLeft: `${Math.max(0, s.level - 1) * 12}px` }}>{s.heading}</h3>}{s.page_no != null && <span className="text-[12px] text-taupe-2">p.{s.page_no}</span>}</div>
                  <p className="whitespace-pre-wrap text-[14px] leading-relaxed text-espresso-2">{s.text}</p>
                </li>
              ))}
            </ol>
          ))}

          {tab === 'chunks' && (chunks.loading && !chunks.data ? <Loading /> : chunks.error ? <ErrorState message={chunks.error} onRetry={chunks.refresh} /> : !chunks.data?.length ? <Empty title="No chunks" /> : (
            <ol className="flex flex-col gap-2">
              {chunks.data.map((c) => (
                <li key={c.chunk_key} className="rounded-[var(--radius-md)] border border-line bg-ivory px-4 py-3">
                  <div className="mb-1 flex flex-wrap items-center gap-2 text-[12px] text-taupe-2"><Link href={`/dashboard/knowledge-base/search?chunk=${encodeURIComponent(c.chunk_key)}`}><Mono className="underline decoration-line underline-offset-4">{c.chunk_key}</Mono></Link>{c.section_ref && <span>§{c.section_ref}</span>}{c.heading && <span>{c.heading}</span>}{c.page_no != null && <span>p.{c.page_no}</span>}</div>
                  <p className="text-[13.5px] leading-relaxed">{c.text}</p>
                </li>
              ))}
            </ol>
          ))}

          {tab === 'issues' && (!v.validation_issues?.length ? <Empty title="No findings" body="This version passed every ingest check." /> : (
            <Table dense>
              <thead><tr><Th>Code</Th><Th>Severity</Th><Th>Outcome</Th><Th>Message</Th></tr></thead>
              <tbody>{v.validation_issues.map((i) => <Tr key={i.id}><Td mono>{i.issue_code}</Td><Td><Badge tone={i.severity === 'ERROR' || i.severity === 'CRITICAL' ? 'critical' : 'warning'}>{i.severity}</Badge></Td><Td>{humanise(i.outcome)}</Td><Td className="text-[12.5px]">{i.message}{i.detail && <span className="block text-taupe-2">{i.detail}</span>}</Td></Tr>)}</tbody>
            </Table>
          ))}

          {tab === 'impact' && <ImpactView q={impact} />}
        </div>

        <Card>
          <PanelHeader title="Metadata" />
          <KV rows={[['File', <Mono key="f" className="break-all text-[12px]">{v.file_name}</Mono>], ['Size', v.file_size_bytes != null ? `${(v.file_size_bytes / 1024).toFixed(0)} KB` : null], ['Pages', v.page_count], ['Effective', fmtDate(v.effective_date, false)], ['Expiry', fmtDate(v.expiry_date, false)], ['Uploaded', fmtDate(v.created_at)], ['Activated', fmtDate(v.activated_at)], ['Superseded', fmtDate(v.superseded_at)]]} />
          {v.metadata_json && Object.keys(v.metadata_json).length > 0 && <details className="mt-4 text-[12.5px]"><summary className="cursor-pointer text-taupe-2">Extracted metadata</summary><pre className="mt-2 overflow-x-auto rounded bg-cream p-3 font-mono text-[11.5px]">{JSON.stringify(v.metadata_json, null, 2)}</pre></details>}
        </Card>
      </div>

      <Modal open={Boolean(activation)} onClose={() => setActivation(null)} title="Version activated" width={640} footer={<Button onClick={() => setActivation(null)}>Close</Button>}>
        {activation && (
          <div className="flex flex-col gap-4">
            <p>{activation.message}</p>
            <div className="flex flex-wrap gap-2"><Badge tone="verified">{activation.doc_ref} {activation.version} is now {activation.status}</Badge>{activation.superseded_version && <Badge>superseded {activation.superseded_version}</Badge>}</div>
            {activation.impact && <ImpactBody i={activation.impact} />}
          </div>
        )}
      </Modal>
    </div>
  )
}

function ImpactView({ q }: { q: ReturnType<typeof useApi<S['PolicyImpactOut']>> }) {
  if (q.loading && !q.data) return <Loading label="Assessing impact" />
  if (q.error) return <ErrorState message={q.error} onRetry={q.refresh} />
  if (!q.data) return null
  return <ImpactBody i={q.data} />
}

function ImpactBody({ i }: { i: S['PolicyImpactOut'] }) {
  return (
    <div className="flex flex-col gap-3">
      <p className="text-[13.5px] text-espresso-2">{i.affected_total ?? 0} complaint{i.affected_total === 1 ? '' : 's'} cited <Mono>{i.doc_ref}</Mono>{i.superseded_version ? <> {i.superseded_version}</> : null}; <b>{i.affected_open ?? 0}</b> of them still open. Their citations now point at superseded text and should be re-analysed against {i.active_version ?? 'the active version'}.</p>
      {(i.complaints ?? []).length > 0 && (
        <Table dense>
          <thead><tr><Th>Complaint</Th><Th>Status</Th><Th>Cited</Th><Th>Analysed</Th></tr></thead>
          <tbody>{i.complaints!.map((c) => <Tr key={c.public_ref + c.section_ref}><Td mono><Link href={`/dashboard/complaints/${c.public_ref}`} className="underline decoration-line underline-offset-4">{c.public_ref}</Link></Td><Td><StatusBadge status={c.status} /></Td><Td mono>{c.doc_ref}{c.section_ref ? ` §${c.section_ref}` : ''}{c.cited_version ? ` ${c.cited_version}` : ''}</Td><Td className="text-taupe-2">{fmtDate(c.analyzed_at)}</Td></Tr>)}</tbody>
        </Table>
      )}
    </div>
  )
}
