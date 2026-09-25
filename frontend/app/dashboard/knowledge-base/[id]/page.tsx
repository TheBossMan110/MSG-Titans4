'use client'

import { use } from 'react'
import Link from 'next/link'
import { AppShell } from '@/components/layout/app-shell'
import { knowledge } from '@/lib/api'
import { useApi, fmtDate } from '@/lib/use-api'
import { Badge, Mono, humanise } from '@/components/ui/primitives'
import { Card } from '@/components/ui/surfaces'
import { KV, Table, Th, Td, Tr } from '@/components/ui/data'
import { ErrorState, Loading } from '@/components/ui/feedback'

export default function DocumentPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params)
  return (
    <AppShell eyebrow="Knowledge base / Document" roles={['agent', 'reviewer', 'manager', 'admin', 'evaluator']} wide>
      <Doc id={id} />
    </AppShell>
  )
}

function Doc({ id }: { id: string }) {
  const q = useApi(() => knowledge.get(id), [id])
  if (q.loading && !q.data) return <Loading label="Opening the document" />
  if (q.error) return <ErrorState message={q.error} onRetry={q.refresh} />
  const d = q.data!
  return (
    <div className="flex flex-col gap-6">
      <div>
        <p className="eyebrow mb-2"><Link href="/dashboard/knowledge-base" className="underline decoration-line underline-offset-4">Knowledge base</Link> / <Mono>{d.family_key}</Mono></p>
        <h1 className="display text-h2">{d.title}</h1>
        <div className="mt-3 flex flex-wrap gap-2"><Badge tone="ink">{humanise(d.doc_type)}</Badge>{d.department && <Badge tone="info">{d.department.name}</Badge>}{d.active_version ? <Badge tone="verified">active {d.active_version.version}</Badge> : <Badge tone="warning">no active version</Badge>}</div>
      </div>
      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        <Card padding="none">
          <Table>
            <thead><tr><Th>Version</Th><Th>Status</Th><Th>Format</Th><Th>Effective</Th><Th>Expiry</Th><Th align="right">Sections</Th><Th align="right">Chunks</Th><Th>Parse</Th><Th>Activated</Th><Th>Superseded</Th></tr></thead>
            <tbody>
              {(d.versions ?? []).map((v) => (
                <Tr key={v.id}>
                  <Td mono><Link href={`/dashboard/knowledge-base/versions/${v.id}`} className="underline decoration-line underline-offset-4">{v.version}</Link></Td>
                  <Td><Badge tone={v.status === 'ACTIVE' ? 'verified' : v.status === 'SUPERSEDED' || v.status === 'EXPIRED' ? 'neutral' : v.status === 'REJECTED' ? 'critical' : 'warning'}>{v.status}</Badge></Td>
                  <Td mono>{v.file_format.toUpperCase()}</Td>
                  <Td className="whitespace-nowrap">{fmtDate(v.effective_date, false)}</Td>
                  <Td className="whitespace-nowrap">{fmtDate(v.expiry_date, false)}</Td>
                  <Td align="right" mono>{v.section_count ?? '—'}</Td>
                  <Td align="right" mono>{v.chunk_count ?? '—'}</Td>
                  <Td><Badge tone={v.parse_status === 'PARSED' || v.parse_status === 'OK' ? 'verified' : 'critical'}>{humanise(v.parse_status)}</Badge>{!v.metadata_complete && <Badge tone="warning" className="ml-1">metadata incomplete</Badge>}</Td>
                  <Td className="whitespace-nowrap text-taupe-2">{fmtDate(v.activated_at)}</Td>
                  <Td className="whitespace-nowrap text-taupe-2">{fmtDate(v.superseded_at)}</Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        </Card>
        <Card>
          <p className="eyebrow mb-3">Family</p>
          <KV rows={[['Reference', <Mono key="r">{d.family_key}</Mono>], ['Created', fmtDate(d.created_at)], ['Versions', d.version_count ?? d.versions?.length ?? 0], ['Active file', d.active_version?.file_name ? <Mono key="f" className="break-all">{d.active_version.file_name}</Mono> : null]]} />
          <p className="mt-5 text-[12.5px] text-taupe-2">Exactly one version can be active. Activating another supersedes it and lists every open complaint whose citations now point at superseded text.</p>
        </Card>
      </div>
    </div>
  )
}
