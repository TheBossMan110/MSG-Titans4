'use client'

import { useRef, useState } from 'react'
import Link from 'next/link'
import { AppShell } from '@/components/layout/app-shell'
import { knowledge, admin, type S } from '@/lib/api'
import { useApi, useAction } from '@/lib/use-api'
import { Badge, Button, Mono } from '@/components/ui/primitives'
import { Card } from '@/components/ui/surfaces'
import { Field, Select, Checkbox } from '@/components/ui/forms'
import { ErrorState } from '@/components/ui/feedback'
import { cn } from '@/lib/utils'

const ACCEPT = '.pdf,.docx'

export default function UploadPage() {
  return (
    <AppShell eyebrow="Knowledge base / Upload" roles={['admin']}>
      <Upload />
    </AppShell>
  )
}

function Upload() {
  const [files, setFiles] = useState<File[]>([])
  const [dept, setDept] = useState('')
  const [activate, setActivate] = useState(true)
  const [over, setOver] = useState(false)
  const [result, setResult] = useState<S['UploadResponse'] | null>(null)
  const input = useRef<HTMLInputElement>(null)
  const taxonomy = useApi(() => admin.taxonomy())
  const up = useAction((fs: File[]) => knowledge.upload(fs, { department_code: dept || undefined, activate }))

  const add = (list: FileList | null) => {
    if (!list) return
    const next = Array.from(list).filter((f) => /\.(pdf|docx)$/i.test(f.name))
    setFiles((prev) => [...prev, ...next.filter((n) => !prev.some((p) => p.name === n.name && p.size === n.size))].slice(0, 25))
  }

  return (
    <div className="mx-auto max-w-[820px] flex flex-col gap-6">
      <div><p className="eyebrow mb-1">Ingest</p><h1 className="display text-h2">Upload policy documents</h1><p className="mt-3 max-w-[60ch] text-[14.5px] text-espresso-2">PDF and DOCX. The file name or its metadata should carry the reference and version, for example <Mono>DOC-003_v2.1.pdf</Mono>. Each file is parsed into sections and chunks, validated, and, if you choose, activated, superseding the previous version of the same document.</p></div>

      <div
        onDragOver={(e) => { e.preventDefault(); setOver(true) }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => { e.preventDefault(); setOver(false); add(e.dataTransfer.files) }}
        onClick={() => input.current?.click()}
        role="button" tabIndex={0} onKeyDown={(e) => e.key === 'Enter' && input.current?.click()}
        className={cn('cursor-pointer rounded-[var(--radius-xl)] border-2 border-dashed px-6 py-14 text-center transition-colors', over ? 'border-espresso bg-sand/50' : 'border-line bg-ivory hover:border-taupe')}
      >
        <input ref={input} type="file" accept={ACCEPT} multiple hidden onChange={(e) => { add(e.target.files); e.target.value = '' }} />
        <p className="font-display text-h3">Drop files here</p>
        <p className="mt-1 text-[13.5px] text-taupe-2">or click to choose · up to 25 files</p>
      </div>

      {files.length > 0 && (
        <ul className="divide-y divide-line-soft rounded-[var(--radius-lg)] border border-line bg-ivory">
          {files.map((f) => <li key={f.name + f.size} className="flex items-center gap-3 px-4 py-2.5 text-[13.5px]"><Mono className="flex-1 truncate">{f.name}</Mono><span className="text-taupe-2">{(f.size / 1024).toFixed(0)} KB</span><button className="text-taupe-2 hover:text-critical" onClick={() => setFiles((p) => p.filter((x) => x !== f))} aria-label={`Remove ${f.name}`}>×</button></li>)}
        </ul>
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Department (optional)">{(id) => <Select id={id} value={dept} onChange={(e) => setDept(e.target.value)}><option value="">Infer from the document</option>{(taxonomy.data?.departments ?? []).map((d) => <option key={d.code} value={d.code}>{d.name}</option>)}</Select>}</Field>
        <div className="flex items-end pb-3"><Checkbox label="Activate on success (supersedes the previous version)" checked={activate} onChange={(e) => setActivate(e.target.checked)} /></div>
      </div>

      {up.error && <ErrorState title="Upload failed" message={up.error} />}
      <div><Button size="lg" loading={up.pending} disabled={!files.length} onClick={async () => { const r = await up.run(files); if (r) { setResult(r); setFiles([]) } }}>Upload {files.length ? `${files.length} file${files.length > 1 ? 's' : ''}` : ''}</Button></div>

      {result && (
        <Card>
          <div className="mb-4 flex flex-wrap gap-2"><Badge tone="verified">{result.accepted} accepted</Badge><Badge tone="warning">{result.requires_review} need review</Badge><Badge tone="critical">{result.rejected} rejected</Badge><span className="text-[13px] text-taupe-2">of {result.uploaded}</span></div>
          <ul className="flex flex-col gap-3">
            {result.results.map((r) => (
              <li key={r.file_name} className={cn('rounded-[var(--radius-md)] border px-4 py-3', r.accepted ? (r.requires_review ? 'border-warning/30 bg-warning-dim/40' : 'border-verified/30 bg-verified-dim/40') : 'border-critical/30 bg-critical-dim/40')}>
                <div className="flex flex-wrap items-center gap-2 text-[13.5px]"><Mono className="font-medium">{r.file_name}</Mono>{r.doc_ref && <Badge>{r.doc_ref} {r.version}</Badge>}{r.status && <Badge tone={r.status === 'ACTIVE' ? 'verified' : 'neutral'}>{r.status}</Badge>}{r.superseded_version && <span className="text-taupe-2">superseded {r.superseded_version}</span>}</div>
                <p className="mt-1 text-[13px] text-espresso-2">{r.message}</p>
                {(r.section_count != null || r.chunk_count != null) && <p className="mt-1 text-[12px] text-taupe-2">{r.section_count ?? 0} sections · {r.chunk_count ?? 0} chunks · {r.embedded_count ?? 0} embedded</p>}
                {(r.issues ?? []).length > 0 && <ul className="mt-2 flex flex-col gap-1 text-[12.5px]">{r.issues!.map((i, k) => <li key={k} className="flex gap-2"><Badge tone={i.fatal ? 'critical' : 'warning'}>{i.code}</Badge><span>{i.message}{i.detail ? ` — ${i.detail}` : ''}</span></li>)}</ul>}
                {r.document_version_id && <Link href={`/dashboard/knowledge-base/versions/${r.document_version_id}`} className="mt-2 inline-block text-[12.5px] underline decoration-line underline-offset-4">Open version</Link>}
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  )
}
