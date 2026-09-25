'use client'

import { use, useRef, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { AppShell } from '@/components/layout/app-shell'
import { useAuth } from '@/lib/auth-context'
import { benchmark, complaints, type S } from '@/lib/api'
import { useApi, useAction } from '@/lib/use-api'
import { Badge, Button, Mono } from '@/components/ui/primitives'
import { Card, PanelHeader } from '@/components/ui/surfaces'
import { Field, Input, Checkbox } from '@/components/ui/forms'
import { Stat, Ratio } from '@/components/ui/data'
import { ErrorState, Modal, SkeletonRows, useToast } from '@/components/ui/feedback'
import { ComplaintTable } from '@/components/app/complaint-bits'
import { cn } from '@/lib/utils'

export default function DatasetPage({ params }: { params: Promise<{ tag: string }> }) {
  const { tag } = use(params)
  const t = decodeURIComponent(tag)
  return (
    <AppShell eyebrow={<span>Benchmark / Dataset / <Mono>{t}</Mono></span>} roles={['manager', 'admin', 'evaluator']} wide>
      {t === 'new' ? <NewDataset /> : <Dataset tag={t} />}
    </AppShell>
  )
}

/**
 * One labelled dataset: its counts, an import form (evaluator/admin), the
 * delete control (admin, with confirmation, because it removes the
 * complaints that carry the tag), and the complaints themselves.
 */
function Dataset({ tag }: { tag: string }) {
  const { user } = useAuth()
  const toast = useToast()
  const router = useRouter()
  const q = useApi(() => benchmark.dataset(tag), [tag])
  const [page, setPage] = useState(1)
  const rows = useApi(() => complaints.list({ dataset_tag: tag, page, size: 25 }), [tag, page])
  const del = useAction(() => benchmark.deleteDataset(tag))
  const [confirming, setConfirming] = useState(false)
  const isAdmin = user?.role === 'admin'
  const operator = user && ['evaluator', 'admin'].includes(user.role)
  const d = q.data

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div><p className="eyebrow mb-2"><Link href="/dashboard/benchmark" className="underline decoration-line underline-offset-4">Benchmark</Link> / dataset</p><h1 className="display text-h2"><Mono>{tag}</Mono></h1></div>
        <div className="flex gap-2">{operator && <Button href={`/dashboard/benchmark?dataset=${encodeURIComponent(tag)}`} variant="secondary" size="sm">Start a run</Button>}{isAdmin && <Button variant="danger" size="sm" onClick={() => setConfirming(true)}>Delete dataset</Button>}</div>
      </div>

      {q.error ? <ErrorState message={q.error} onRetry={q.refresh} /> : (
        <div className="grid gap-x-8 gap-y-6 rounded-[var(--radius-xl)] border border-line bg-ivory p-6 sm:grid-cols-2 lg:grid-cols-4">
          <Stat label="Complaints" value={d ? d.total ?? 0 : undefined} />
          <Stat label="Labelled" value={d ? d.labelled ?? 0 : undefined} evidence={d ? `${d.unlabelled ?? 0} unlabelled` : undefined} />
          <div className="flex flex-col justify-end">{d ? <Ratio numerator={d.analysed ?? 0} denominator={d.total ?? 0} label="Analysed" /> : <SkeletonRows rows={1} />}</div>
          <Stat label="Pending analysis" value={d ? d.pending_analysis ?? 0 : undefined} tone={d && (d.pending_analysis ?? 0) > 0 ? 'warning' : 'neutral'} />
        </div>
      )}

      {operator && <ImportForm tag={tag} onDone={() => { q.refresh(); rows.refresh() }} />}

      <section>
        <PanelHeader title="Complaints in this dataset" />
        {rows.error ? <ErrorState message={rows.error} onRetry={rows.refresh} /> : rows.loading && !rows.data ? <SkeletonRows rows={8} /> : <><ComplaintTable items={rows.data!.items} />{rows.data!.total > 25 && <div className="mt-3 flex justify-end gap-2"><Button size="sm" variant="secondary" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Previous</Button><Button size="sm" variant="secondary" disabled={page * 25 >= rows.data!.total} onClick={() => setPage((p) => p + 1)}>Next</Button></div>}</>}
      </section>

      <Modal open={confirming} onClose={() => setConfirming(false)} title={<>Delete <Mono>{tag}</Mono>?</>} footer={<><Button variant="secondary" onClick={() => setConfirming(false)}>Keep it</Button><Button variant="danger" loading={del.pending} onClick={async () => { const r = await del.run(); if (r) { toast('warn', `Deleted: ${Object.entries(r).map(([k, v]) => `${k} ${v}`).join(', ')}`); router.replace('/dashboard/benchmark') } else if (del.error) { toast('err', del.error); setConfirming(false) } }}>Delete</Button></>}>
        <p>This removes every complaint carrying the tag, their analyses and their labels. Benchmark runs already recorded keep their metrics. This cannot be undone.</p>
      </Modal>
    </div>
  )
}

function ImportForm({ tag, onDone }: { tag: string; onDone?: (r: S['ImportResultOut']) => void }) {
  const toast = useToast()
  const [file, setFile] = useState<File | null>(null)
  const [replace, setReplace] = useState(false)
  const [result, setResult] = useState<S['ImportResultOut'] | null>(null)
  const input = useRef<HTMLInputElement>(null)
  const imp = useAction((f: File, r: boolean) => benchmark.importDataset(tag, f, r))
  return (
    <Card>
      <PanelHeader title="Import labelled complaints" eyebrow="CSV with expected_* columns" />
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex-1 min-w-[240px]"><Field label="CSV file">{(id) => <input id={id} ref={input} type="file" accept=".csv,text/csv" onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="block w-full text-[13.5px] file:mr-3 file:rounded-full file:border file:border-line file:bg-ivory file:px-3 file:py-1.5 file:text-[13px]" />}</Field></div>
        <Checkbox label="Replace existing rows with this tag" checked={replace} onChange={(e) => setReplace(e.target.checked)} className="pb-3" />
        <Button loading={imp.pending} disabled={!file} onClick={async () => { if (!file) return; const r = await imp.run(file, replace); if (r) { setResult(r); toast(r.error_count ? 'warn' : 'ok', `Imported ${r.imported ?? 0}, skipped ${r.skipped ?? 0}, ${r.error_count ?? 0} errors.`); onDone?.(r); setFile(null); if (input.current) input.current.value = '' } else if (imp.error) toast('err', imp.error) }}>Import</Button>
      </div>
      {imp.error && <p className="mt-3 text-[13px] text-critical">{imp.error}</p>}
      {result && (
        <div className="mt-4 flex flex-col gap-2 text-[13px]">
          <div className="flex flex-wrap gap-2"><Badge tone="verified">{result.imported ?? 0} imported</Badge><Badge>{result.labelled ?? 0} labelled</Badge><Badge>{result.unlabelled ?? 0} unlabelled</Badge><Badge tone="neutral">{result.skipped ?? 0} skipped</Badge><Badge tone={result.error_count ? 'critical' : 'neutral'}>{result.error_count ?? 0} errors</Badge></div>
          {(result.errors ?? []).length > 0 && <ul className={cn('max-h-[220px] overflow-y-auto rounded-[var(--radius-md)] border border-critical/30 bg-critical-dim/40 p-3 font-mono text-[11.5px]')}>{result.errors!.slice(0, 50).map((e, i) => <li key={i}>{JSON.stringify(e)}</li>)}</ul>}
        </div>
      )}
    </Card>
  )
}

function NewDataset() {
  const router = useRouter()
  const [tag, setTag] = useState('')
  return (
    <div className="mx-auto max-w-[560px] flex flex-col gap-5">
      <div><p className="eyebrow mb-1">Benchmark</p><h1 className="display text-h2">New dataset</h1><p className="mt-3 text-[14.5px] text-espresso-2">Choose a tag; the import form is on the dataset's page. The tag is stamped on every complaint imported under it.</p></div>
      <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (tag.trim()) router.push(`/dashboard/benchmark/datasets/${encodeURIComponent(tag.trim())}`) }}>
        <Input value={tag} onChange={(e) => setTag(e.target.value.replace(/[^a-zA-Z0-9_.-]/g, '-'))} placeholder="e.g. raftarxpress-v1" className="font-mono" autoFocus />
        <Button type="submit" disabled={!tag.trim()}>Continue</Button>
      </form>
    </div>
  )
}
