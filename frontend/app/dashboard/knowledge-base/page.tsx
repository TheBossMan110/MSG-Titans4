'use client'

import { useState } from 'react'
import Link from 'next/link'
import { AppShell } from '@/components/layout/app-shell'
import { useAuth } from '@/lib/auth-context'
import { knowledge } from '@/lib/api'
import { useApi, fmtDate } from '@/lib/use-api'
import { Badge, Button, Mono, humanise } from '@/components/ui/primitives'
import { Card, PanelHeader } from '@/components/ui/surfaces'
import { Select, SearchBox } from '@/components/ui/forms'
import { Table, Th, Td, Tr, Pagination, Stat, Ratio } from '@/components/ui/data'
import { Empty, ErrorState, SkeletonRows, Tabs } from '@/components/ui/feedback'

const STAFF = ['agent', 'reviewer', 'manager', 'admin', 'evaluator'] as const

export default function KnowledgeBasePage() {
  return (
    <AppShell eyebrow="Knowledge base" roles={[...STAFF]} wide>
      <Library />
    </AppShell>
  )
}

function Library() {
  const { user } = useAuth()
  const [tab, setTab] = useState<'documents' | 'findings'>('documents')
  const coverage = useApi(() => knowledge.coverage())
  const cov = coverage.data
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div><p className="eyebrow mb-1">Policies and procedures</p><h1 className="display text-h2">Knowledge base</h1></div>
        <div className="flex gap-2"><Button href="/dashboard/knowledge-base/search" variant="secondary">Search &amp; trace</Button>{user?.role === 'admin' && <Button href="/dashboard/knowledge-base/upload">Upload documents</Button>}</div>
      </div>

      <div className="grid gap-x-8 gap-y-6 rounded-[var(--radius-xl)] border border-line bg-ivory p-6 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Active documents" value={cov ? cov.active_documents : coverage.error ? null : undefined} evidence={cov ? `knowledge base ${cov.knowledge_base_version}` : coverage.error ?? undefined} />
        <Stat label="Chunks indexed" value={cov ? cov.chunks : undefined} />
        <div className="flex flex-col justify-end">{cov ? <Ratio numerator={cov.embedded_chunks} denominator={cov.chunks} label="Embedded for semantic search" tone={cov.semantic_search_available ? 'verified' : 'warning'} /> : <SkeletonRows rows={1} />}</div>
        <Stat label="Semantic search" value={cov ? (cov.semantic_search_available ? 'Available' : 'Lexical only') : undefined} tone={cov?.semantic_search_available ? 'verified' : 'warning'} evidence={cov && !cov.semantic_search_available ? `${cov.unembedded_chunks} chunks without embeddings` : undefined} />
      </div>

      <Tabs value={tab} onChange={setTab} tabs={[{ id: 'documents', label: 'Documents' }, { id: 'findings', label: 'Validation findings' }]} />
      {tab === 'documents' ? <Documents /> : <Findings />}
    </div>
  )
}

function Documents() {
  const [page, setPage] = useState(1)
  const [qText, setQText] = useState('')
  const [docType, setDocType] = useState('')
  const [status, setStatus] = useState('')
  const q = useApi(() => knowledge.list({ page, page_size: 25, q: qText || undefined, doc_type: docType || undefined, status: status || undefined }), [page, qText, docType, status])
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap gap-2">
        <SearchBox value={qText} onChange={(v) => { setQText(v); setPage(1) }} placeholder="Title or reference" className="w-full sm:w-[320px]" />
        <Select value={docType} onChange={(e) => { setDocType(e.target.value); setPage(1) }} aria-label="Type" className="w-auto"><option value="">Any type</option>{['POLICY', 'SOP', 'FAQ', 'TERMS', 'GUIDE', 'NOTICE'].map((t) => <option key={t} value={t}>{humanise(t)}</option>)}</Select>
        <Select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1) }} aria-label="Status" className="w-auto"><option value="">Any status</option>{['ACTIVE', 'DRAFT', 'SUPERSEDED', 'EXPIRED', 'REJECTED'].map((t) => <option key={t} value={t}>{humanise(t)}</option>)}</Select>
      </div>
      {q.error ? <ErrorState message={q.error} onRetry={q.refresh} /> : q.loading && !q.data ? <SkeletonRows rows={8} /> : !q.data!.items.length ? <Empty title="No documents" body="Upload PDF or DOCX policies to build the knowledge base." /> : (
        <>
          <Table>
            <thead><tr><Th>Reference</Th><Th>Title</Th><Th>Type</Th><Th>Department</Th><Th>Active version</Th><Th>Format</Th><Th>Effective</Th><Th>Parse</Th><Th align="right">Versions</Th></tr></thead>
            <tbody>
              {q.data!.items.map((d) => {
                const v = d.active_version
                return (
                  <Tr key={d.id}>
                    <Td mono><Link href={`/dashboard/knowledge-base/${d.id}`} className="underline decoration-line underline-offset-4">{d.family_key}</Link></Td>
                    <Td className="max-w-[360px]"><span className="line-clamp-1">{d.title}</span></Td>
                    <Td>{humanise(d.doc_type)}</Td>
                    <Td>{d.department?.name ?? '—'}</Td>
                    <Td>{v ? <span className="flex items-center gap-1.5"><Mono>{v.version}</Mono><Badge tone={v.status === 'ACTIVE' ? 'verified' : 'neutral'}>{v.status}</Badge></span> : <Badge tone="warning">none active</Badge>}</Td>
                    <Td mono>{v?.file_format?.toUpperCase() ?? '—'}</Td>
                    <Td className="whitespace-nowrap">{fmtDate(v?.effective_date, false)}</Td>
                    <Td>{v ? <Badge tone={v.parse_status === 'PARSED' || v.parse_status === 'OK' ? 'verified' : 'critical'}>{humanise(v.parse_status)}</Badge> : '—'}</Td>
                    <Td align="right" mono>{d.version_count ?? 0}</Td>
                  </Tr>
                )
              })}
            </tbody>
          </Table>
          <Pagination page={page} size={25} total={q.data!.total} onPage={setPage} />
        </>
      )}
    </div>
  )
}

function Findings() {
  const [page, setPage] = useState(1)
  const [outcome, setOutcome] = useState('')
  const q = useApi(() => knowledge.validationIssues({ page, page_size: 25, outcome: outcome || undefined }), [page, outcome])
  return (
    <div className="flex flex-col gap-4">
      <Card tone="cream" padding="sm"><p className="text-[13.5px] text-espresso-2">Every uploaded file is checked for metadata (reference, version, effective date), duplicate versions, parse quality and contradictions with active policy. Findings are kept even when the file was accepted.</p></Card>
      <Select value={outcome} onChange={(e) => { setOutcome(e.target.value); setPage(1) }} aria-label="Outcome" className="w-auto"><option value="">Any outcome</option>{['ACCEPTED', 'ACCEPTED_WITH_WARNINGS', 'REQUIRES_REVIEW', 'REJECTED'].map((o) => <option key={o} value={o}>{humanise(o)}</option>)}</Select>
      {q.error ? <ErrorState message={q.error} onRetry={q.refresh} /> : q.loading && !q.data ? <SkeletonRows rows={6} /> : !q.data!.items.length ? <Empty title="No findings" /> : (
        <>
          <Table dense>
            <thead><tr><Th>When</Th><Th>File</Th><Th>Code</Th><Th>Severity</Th><Th>Outcome</Th><Th>Message</Th><Th>Version</Th></tr></thead>
            <tbody>
              {q.data!.items.map((i) => (
                <Tr key={i.id}>
                  <Td className="whitespace-nowrap text-taupe-2">{fmtDate(i.created_at)}</Td>
                  <Td mono className="max-w-[220px] truncate">{i.file_name}</Td>
                  <Td mono>{i.issue_code}</Td>
                  <Td><Badge tone={i.severity === 'ERROR' || i.severity === 'CRITICAL' ? 'critical' : i.severity === 'WARNING' ? 'warning' : 'neutral'}>{i.severity}</Badge></Td>
                  <Td><Badge tone={i.outcome === 'REJECTED' ? 'critical' : i.outcome === 'ACCEPTED' ? 'verified' : 'warning'}>{humanise(i.outcome)}</Badge></Td>
                  <Td className="max-w-[420px] text-[12.5px]">{i.message}{i.detail && <span className="block text-taupe-2">{i.detail}</span>}</Td>
                  <Td>{i.document_version_id ? <Link href={`/dashboard/knowledge-base/versions/${i.document_version_id}`} className="text-[12.5px] underline decoration-line underline-offset-4">open</Link> : '—'}</Td>
                </Tr>
              ))}
            </tbody>
          </Table>
          <Pagination page={page} size={25} total={q.data!.total} onPage={setPage} />
        </>
      )}
    </div>
  )
}
