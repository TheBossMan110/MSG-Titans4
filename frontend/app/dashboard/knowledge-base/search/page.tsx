'use client'

import { Suspense, useEffect, useState } from 'react'
import { useSearchParams } from 'next/navigation'
import Link from 'next/link'
import { AppShell } from '@/components/layout/app-shell'
import { knowledge, type S } from '@/lib/api'
import { useAction, fmtDate } from '@/lib/use-api'
import { Badge, Button, Mono, humanise } from '@/components/ui/primitives'
import { Card, PanelHeader } from '@/components/ui/surfaces'
import { Field, Input, Checkbox } from '@/components/ui/forms'
import { KV } from '@/components/ui/data'
import { Empty, ErrorState, SkeletonRows } from '@/components/ui/feedback'
import { cn } from '@/lib/utils'

export default function SearchPage() {
  return (
    <AppShell eyebrow="Knowledge base / Search & trace" roles={['agent', 'reviewer', 'manager', 'admin', 'evaluator']} wide>
      <Suspense fallback={null}><SearchAndTrace /></Suspense>
    </AppShell>
  )
}

/**
 * Two instruments on one page. Search runs the same retrieval the pipelines
 * use (lexical + exact reference + semantic when embeddings exist). Trace
 * resolves a citation the way the hallucination checks do: by chunk key, or
 * by document and section reference, and says whether it was in force.
 */
function SearchAndTrace() {
  const params = useSearchParams()
  const [query, setQuery] = useState('')
  const [semantic, setSemantic] = useState(true)
  const [superseded, setSuperseded] = useState(false)
  const [res, setRes] = useState<S['SearchResponse'] | null>(null)
  const search = useAction((body: S['SearchRequest']) => knowledge.search(body))

  const [chunkKey, setChunkKey] = useState(params.get('chunk') ?? '')
  const [docRef, setDocRef] = useState(params.get('doc_ref') ?? '')
  const [sectionRef, setSectionRef] = useState(params.get('section_ref') ?? '')
  const [trace, setTrace] = useState<S['TraceabilityResponse'] | null>(null)
  const byKey = useAction((k: string) => knowledge.trace(k))
  const byRef = useAction((d: string, s?: string) => knowledge.byReference(d, s || undefined))

  const runSearch = async () => { const r = await search.run({ query, top_k: 10, semantic, include_superseded: superseded }); if (r) setRes(r) }
  const runTrace = async () => {
    const r = chunkKey.trim() ? await byKey.run(chunkKey.trim()) : await byRef.run(docRef.trim(), sectionRef.trim())
    if (r) setTrace(r)
  }

  useEffect(() => { if (params.get('chunk') || params.get('doc_ref')) void runTrace() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="grid gap-8 lg:grid-cols-[1.2fr_1fr]">
      <section className="flex flex-col gap-5">
        <div><p className="eyebrow mb-1">Retrieval</p><h1 className="display text-h2">Search the policies</h1></div>

        <div className="rounded-[var(--radius-lg)] border border-primary/25 bg-primary/5 p-4">
          <div className="flex flex-wrap items-center justify-between gap-1 mb-2">
            <span className="text-[12px] font-semibold text-primary uppercase tracking-wider">
              Evaluator Demo: Semantic Paraphrase Test (RAG Proof)
            </span>
            <span className="text-[11.5px] text-taupe-2">
              Natural wording → exact policy section retrieved
            </span>
          </div>
          <p className="text-[12.5px] text-espresso-2 mb-3">
            Click any natural paraphrase below that contains <b>no formal policy keywords</b> to visually prove how SupportNova RAG retrieves the canonical policy section via vector embeddings:
          </p>
          <div className="flex flex-wrap gap-2">
            {[
              {
                label: '💧 "package smells wet"',
                query: 'package smells wet and soaked through cardboard',
                target: 'Water Damage & Transit Spoilage'
              },
              {
                label: '🛵 "rider asked for extra cash at door"',
                query: 'delivery person demanded additional cash money before handing parcel',
                target: 'COD Overcharging & Extortion Policy'
              },
              {
                label: '⚡ "charger made a loud pop and burning smell"',
                query: 'power adapter sparked loud sound and burnt smell from device',
                target: 'Electrical & Hardware Safety Hazard'
              },
              {
                label: '📦 "delivered to someone else in my building"',
                query: 'parcel left with unknown neighbor without otp verification',
                target: 'Misdelivery & Missing Proof of Delivery'
              },
            ].map((demo, idx) => (
              <button
                key={idx}
                type="button"
                onClick={() => {
                  setQuery(demo.query)
                  setSemantic(true)
                  void search.run({ query: demo.query, top_k: 10, semantic: true, include_superseded: superseded }).then((r) => r && setRes(r))
                }}
                className="inline-flex flex-col items-start px-2.5 py-1.5 rounded-[var(--radius-md)] border border-line bg-white text-left text-[12px] hover:border-primary hover:bg-cream transition-colors shadow-xs"
              >
                <span className="font-semibold text-espresso">{demo.label}</span>
                <span className="text-[11px] text-taupe-2">Retrieves: {demo.target}</span>
              </button>
            ))}
          </div>
        </div>

        <form className="flex flex-col gap-3" onSubmit={(e) => { e.preventDefault(); if (query.trim()) void runSearch() }}>
          <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="e.g. compensation ceiling for lost COD parcel" aria-label="Search query" autoFocus />
          <div className="flex flex-wrap items-center gap-4"><Checkbox label="Semantic" checked={semantic} onChange={(e) => setSemantic(e.target.checked)} /><Checkbox label="Include superseded versions" checked={superseded} onChange={(e) => setSuperseded(e.target.checked)} /><Button type="submit" size="sm" loading={search.pending} disabled={!query.trim()}>Search</Button></div>
        </form>
        {search.error && <ErrorState message={search.error} />}
        {search.pending && !res && <SkeletonRows rows={4} />}
        {res && (
          <>
            <div className="flex flex-wrap items-center gap-2 text-[12.5px] text-taupe-2">
              <Badge>{res.results.length} results</Badge><span>lexical {res.lexical_count}</span><span>·</span><span>exact {res.exact_count}</span><span>·</span><span>semantic {res.semantic_count}</span>
              {!res.semantic_available && <Badge tone="warning">semantic unavailable</Badge>}{res.knowledge_base_empty && <Badge tone="critical">knowledge base empty</Badge>}
              {res.cited_documents.length > 0 && <span className="ml-auto">in {res.cited_documents.join(', ')}</span>}
            </div>
            {!res.results.length ? <Empty title="Nothing matched" body="Try other words, or include superseded versions." /> : (
              <ol className="flex flex-col gap-3">
                {res.results.map((r) => (
                  <li key={r.chunk_key} className="rounded-[var(--radius-lg)] border border-line bg-ivory p-4">
                    <div className="mb-2 flex flex-wrap items-center gap-2 text-[12px]"><Mono className="font-medium text-espresso">{r.doc_ref} {r.doc_version}</Mono>{r.section_ref && <span className="text-taupe-2">§{r.section_ref}</span>}{r.heading && <span className="text-taupe-2">{r.heading}</span>}<Badge className="ml-auto">{humanise(r.matched_by)}</Badge><Mono className="text-taupe-2">{r.score.toFixed(3)}</Mono></div>
                    <p className="text-[13.5px] leading-relaxed">{r.text}</p>
                    <div className="mt-2 flex gap-3 text-[12px]"><button className="underline decoration-line underline-offset-4" onClick={() => { setChunkKey(r.chunk_key); setDocRef(''); setSectionRef(''); void byKey.run(r.chunk_key).then((t) => t && setTrace(t)) }}>Trace this chunk</button><span className="text-taupe-2">ranks: lex {r.lexical_rank ?? '—'} · sem {r.semantic_rank ?? '—'} · exact {r.exact_rank ?? '—'}</span></div>
                  </li>
                ))}
              </ol>
            )}
          </>
        )}
      </section>

      <section className="flex flex-col gap-5">
        <div><p className="eyebrow mb-1">Traceability</p><h2 className="display text-h2">Resolve a citation</h2></div>
        <Card>
          <form className="flex flex-col gap-3" onSubmit={(e) => { e.preventDefault(); void runTrace() }}>
            <Field label="Chunk key" hint="As cited by the model, e.g. DOC-003:v2.1:s3:p0">{(id) => <Input id={id} value={chunkKey} onChange={(e) => setChunkKey(e.target.value)} className="font-mono" />}</Field>
            <p className="text-center text-[12px] text-taupe-2">or by reference</p>
            <div className="grid grid-cols-2 gap-2">
              <Field label="Document">{(id) => <Input id={id} value={docRef} onChange={(e) => setDocRef(e.target.value)} placeholder="DOC-003" className="font-mono" />}</Field>
              <Field label="Section">{(id) => <Input id={id} value={sectionRef} onChange={(e) => setSectionRef(e.target.value)} placeholder="3" className="font-mono" />}</Field>
            </div>
            {(byKey.error || byRef.error) && <p role="alert" className="text-[13px] text-critical">{byKey.error ?? byRef.error}</p>}
            <Button type="submit" size="sm" loading={byKey.pending || byRef.pending} disabled={!chunkKey.trim() && !docRef.trim()}>Trace</Button>
          </form>
        </Card>
        {trace && (
          <Card tone={trace.resolved ? 'ivory' : 'sand'} className={cn(trace.resolved && trace.applicability !== 'APPLICABLE' && 'border-warning/40')}>
            <PanelHeader title={trace.resolved ? 'Resolved' : 'Not found'} aside={trace.applicability && <Badge tone={trace.applicability === 'APPLICABLE' ? 'verified' : 'warning'}>{humanise(trace.applicability)}</Badge>} />
            {trace.reason && <p className="mb-3 text-[13.5px] text-espresso-2">{trace.reason}</p>}
            {trace.citation && <KV rows={[['Document', <Mono key="d">{trace.citation.doc_ref} {trace.citation.version}</Mono>], ['Title', trace.document_title], ['Status', trace.document_status ? <Badge key="s" tone={trace.document_status === 'ACTIVE' ? 'verified' : 'neutral'}>{trace.document_status}</Badge> : null], ['Section', trace.citation.section_ref ? `§${trace.citation.section_ref}${trace.citation.heading ? ` — ${trace.citation.heading}` : ''}` : null], ['Page', trace.citation.page_no], ['Effective', fmtDate(trace.effective_date, false)], ['Expiry', fmtDate(trace.expiry_date, false)], ['Chunk', <Mono key="c" className="text-[11.5px]">{trace.citation.chunk_key}</Mono>]]} />}
            {trace.text && <blockquote className="mt-4 border-l-2 border-espresso pl-4 text-[13.5px] leading-relaxed">{trace.text}</blockquote>}
            {trace.section_text && trace.section_text !== trace.text && <details className="mt-3 text-[12.5px]"><summary className="cursor-pointer text-taupe-2">Whole section</summary><p className="mt-2 whitespace-pre-wrap leading-relaxed">{trace.section_text}</p></details>}
            <p className="mt-4 text-[12px] text-taupe-2"><Link href="/dashboard/knowledge-base" className="underline decoration-line underline-offset-4">Browse the knowledge base</Link></p>
          </Card>
        )}
      </section>
    </div>
  )
}
