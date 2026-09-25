'use client'

import { useCallback, useRef, useState } from 'react'
import {
  CheckCircle2, CircleDot, Clock, Download, FileText, ImageIcon, Mail, MessageSquareReply,
  Paperclip, Send, ShieldCheck, Sparkles, UploadCloud, Users, X,
} from 'lucide-react'
import { complaints, errorMessage, type S } from '@/lib/api'
import { fmtDate, fmtRelative } from '@/lib/use-api'
import { Badge, Button, Pulse } from '@/components/ui/primitives'
import { Card } from '@/components/ui/surfaces'
import { Textarea } from '@/components/ui/forms'
import { useToast } from '@/components/ui/feedback'
import { cn } from '@/lib/utils'

type Status = S['ComplaintStatusOut']

/* ------------------------------------------------------------------ timeline */

const MILESTONE_ICON: Record<string, typeof CircleDot> = {
  RECEIVED: CheckCircle2,
  UNDERSTOOD: Sparkles,
  CHECKED: ShieldCheck,
  WITH_TEAM: MessageSquareReply,
  RESOLVED: CheckCircle2,
}

/**
 * Where the complaint is, in the customer's words.
 *
 * Built from the milestones the server derives from the status history, so
 * it cannot drift from what actually happened. The AI step is blue and the
 * policy check forest — the same two colours the staff screens use for the
 * same two things.
 */
export function MilestoneTimeline({ milestones, orientation = 'vertical' }: { milestones: S['MilestoneOut'][]; orientation?: 'vertical' | 'horizontal' }) {
  if (!milestones.length) return null

  if (orientation === 'horizontal') {
    const reachedCount = milestones.filter((m) => m.reached).length
    return (
      <ol className="relative grid gap-4 sm:grid-cols-5" aria-label="Progress">
        <span aria-hidden className="absolute left-[18px] right-[18px] top-[17px] hidden h-[2px] rounded-full bg-sand sm:block" />
        <span
          aria-hidden
          className="absolute left-[18px] top-[17px] hidden h-[2px] rounded-full bg-gradient-to-r from-ai via-ai-2 to-rule-2 transition-[width] duration-1000 ease-[var(--ease-out-expo)] sm:block"
          style={{ width: `calc((100% - 36px) * ${Math.max(0, reachedCount - 1) / (milestones.length - 1)})` }}
        />
        {milestones.map((m) => {
          const Icon = MILESTONE_ICON[m.key] ?? CircleDot
          return (
            <li key={m.key} className="relative flex items-start gap-3 sm:flex-col sm:gap-2.5">
              <Dot reached={!!m.reached} current={!!m.current} kind={m.key}><Icon size={15} strokeWidth={2.2} aria-hidden /></Dot>
              <div className="min-w-0">
                <p className={cn('text-[14px] font-medium leading-tight', m.reached ? 'text-espresso' : m.current ? 'text-espresso-2' : 'text-taupe')}>{m.label}</p>
                <p className="mt-0.5 text-[12.5px] text-taupe">{m.at ? fmtRelative(m.at) : m.current ? 'In progress' : 'Pending'}</p>
              </div>
            </li>
          )
        })}
      </ol>
    )
  }

  return (
    <ol className="relative flex flex-col gap-5" aria-label="Progress">
      <span aria-hidden className="absolute bottom-3 left-[17px] top-3 w-[2px] rounded-full bg-sand" />
      {milestones.map((m) => {
        const Icon = MILESTONE_ICON[m.key] ?? CircleDot
        return (
          <li key={m.key} className="relative flex gap-4">
            <Dot reached={!!m.reached} current={!!m.current} kind={m.key}><Icon size={15} strokeWidth={2.2} aria-hidden /></Dot>
            <div className="min-w-0 pt-1.5">
              <p className={cn('text-[14.5px] font-medium leading-tight', m.reached ? 'text-espresso' : m.current ? 'text-espresso-2' : 'text-taupe')}>
                {m.label}
                {m.current && <Badge tone="ai" className="ml-2 align-middle">now</Badge>}
              </p>
              {m.detail && <p className="mt-1 text-[13px] leading-relaxed text-taupe">{m.detail}</p>}
              {m.at && <p className="mt-0.5 text-[12px] text-taupe">{fmtDate(m.at)}</p>}
            </div>
          </li>
        )
      })}
    </ol>
  )
}

function Dot({ reached, current, kind, children }: { reached: boolean; current: boolean; kind: string; children: React.ReactNode }) {
  const tone =
    kind === 'UNDERSTOOD' ? 'bg-ai text-white shadow-ai'
    : kind === 'CHECKED' ? 'bg-rule text-white shadow-rule'
    : 'bg-espresso text-ink-on-dark'
  return (
    <span
      className={cn(
        'relative z-[1] inline-flex size-9 shrink-0 items-center justify-center rounded-full ring-4 ring-cream transition-colors duration-500',
        reached ? tone : current ? 'border-2 border-ai bg-white text-ai' : 'border-2 border-line bg-white text-taupe',
      )}
    >
      {current && <span aria-hidden className="absolute inset-0 rounded-full border-2 border-ai animate-pulse-ring" />}
      {children}
    </span>
  )
}

/* ------------------------------------------------------------------ questions */

/**
 * The customer's side of "ask rather than invent".
 *
 * One small form per open question. Answered questions stay visible with the
 * reply, so the customer can see what they have already told us.
 */
export function QuestionsPanel({ refId, status, onUpdated }: { refId: string; status: Status; onUpdated: (s: Status) => void }) {
  const questions = status.questions ?? []
  if (!questions.length) return null
  const open = questions.filter((q) => !q.answered)

  return (
    <Card tone="glass" padding="lg" radius="xl" className={cn(open.length && 'ring-2 ring-warning-glow/40')}>
      <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="eyebrow mb-1.5 flex items-center gap-2">
            {open.length ? <><Pulse tone="warning" /> Customer action needed</> : 'Your answers'}
          </p>
          <h2 className="font-display text-h3 leading-tight">
            {open.length ? `We need ${open.length === 1 ? 'one thing' : `${open.length} things`} from you` : 'Thank you — everything we asked is answered'}
          </h2>
          <p className="mt-2 max-w-[56ch] text-[14px] text-taupe">
            We ask rather than guess. Your answer goes straight onto your complaint, and if you give
            us a reference number we attach it so the checks can use it.
          </p>
        </div>
        {open.length > 0 && <Badge tone="warning" pulse>{open.length} open</Badge>}
      </div>
      <ol className="flex flex-col gap-3">
        {questions.map((q, i) => (
          <QuestionItem key={q.id} refId={refId} q={q} index={i + 1} onUpdated={onUpdated} />
        ))}
      </ol>
    </Card>
  )
}

function QuestionItem({ refId, q, index, onUpdated }: { refId: string; q: S['CustomerQuestionOut']; index: number; onUpdated: (s: Status) => void }) {
  const toast = useToast()
  const [value, setValue] = useState('')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [editing, setEditing] = useState(false)

  const send = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!value.trim()) return
    setPending(true)
    setError(null)
    try {
      const r = await complaints.answer(refId, q.id, value.trim())
      onUpdated(r.status)
      setValue('')
      setEditing(false)
      const filled = Object.entries(r.filled ?? {}).map(([k, v]) => `${k === 'order_ref' ? 'consignment' : 'transaction'} ${v}`).join(', ')
      toast('ok', filled ? `Answer saved — we added ${filled} to your complaint.` : r.all_answered ? 'Thank you — that was the last question.' : 'Answer saved.')
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setPending(false)
    }
  }

  const answered = q.answered && !editing
  return (
    <li className={cn('rounded-2xl border p-4 transition-colors', answered ? 'border-verified/25 bg-verified-dim/50' : 'border-line-soft bg-white/80')}>
      <div className="flex items-start gap-3">
        <span className={cn('inline-flex size-7 shrink-0 items-center justify-center rounded-full text-[12px] font-semibold', answered ? 'bg-verified text-white' : 'bg-espresso text-ink-on-dark')}>
          {answered ? <CheckCircle2 size={14} aria-hidden /> : index}
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-[15px] font-medium leading-snug text-espresso">{q.question}</p>
          {answered ? (
            <div className="mt-2">
              <p className="whitespace-pre-wrap rounded-xl bg-white/80 px-3 py-2 text-[14px] text-espresso-2">{q.answer}</p>
              <div className="mt-1.5 flex items-center gap-3 text-[12px] text-taupe">
                <span>Answered {fmtRelative(q.answered_at)}</span>
                <button className="font-medium text-espresso underline decoration-line underline-offset-4" onClick={() => { setEditing(true); setValue(q.answer ?? '') }}>Change answer</button>
              </div>
            </div>
          ) : (
            <form onSubmit={send} className="mt-3 flex flex-col gap-2">
              <Textarea
                value={value}
                onChange={(e) => setValue(e.target.value)}
                rows={3}
                maxLength={2000}
                placeholder="Type your answer…"
                aria-label={`Answer to: ${q.question}`}
                className="min-h-[84px] bg-white"
              />
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-[12px] tnum text-taupe">{value.length} / 2000</span>
                <div className="flex gap-2">
                  {editing && <Button type="button" size="sm" variant="ghost" onClick={() => { setEditing(false); setValue('') }}>Cancel</Button>}
                  <Button type="submit" size="sm" loading={pending} disabled={!value.trim()} icon={<Send size={13} aria-hidden />}>Send answer</Button>
                </div>
              </div>
              {error && <p role="alert" className="text-[13px] text-critical">{error}</p>}
            </form>
          )}
        </div>
      </div>
    </li>
  )
}

/* ------------------------------------------------------------------ evidence */

type Upload = { id: string; name: string; size: number; progress: number; error?: string; done?: boolean }

const ACCEPT = '.pdf,.docx,.png,.jpg,.jpeg,.webp,.txt,application/pdf,image/png,image/jpeg,image/webp,text/plain'
const MAX_MB = 10

const kb = (n: number) => (n > 1024 * 1024 ? `${(n / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`)

/**
 * Drag, drop or choose. Each file uploads with its own progress bar; a file
 * the server refuses says why, in the server's words, and the others carry on.
 */
export function EvidencePanel({ refId, evidence, onUploaded, compact }: {
  refId: string
  evidence: S['EvidenceOut'][]
  onUploaded: () => void
  compact?: boolean
}) {
  const toast = useToast()
  const input = useRef<HTMLInputElement>(null)
  const [over, setOver] = useState(false)
  const [uploads, setUploads] = useState<Upload[]>([])

  const patch = (id: string, p: Partial<Upload>) => setUploads((all) => all.map((u) => (u.id === id ? { ...u, ...p } : u)))

  const start = useCallback(async (files: FileList | File[] | null) => {
    if (!files) return
    const list = Array.from(files)
    for (const file of list) {
      const id = `${file.name}-${file.size}-${Math.random().toString(36).slice(2, 7)}`
      if (file.size > MAX_MB * 1024 * 1024) {
        setUploads((u) => [...u, { id, name: file.name, size: file.size, progress: 0, error: `Larger than ${MAX_MB} MB.` }])
        continue
      }
      setUploads((u) => [...u, { id, name: file.name, size: file.size, progress: 0 }])
      try {
        await complaints.uploadEvidence(refId, file, (f) => patch(id, { progress: f }))
        patch(id, { progress: 1, done: true })
        onUploaded()
      } catch (err) {
        patch(id, { error: errorMessage(err) })
      }
    }
    if (list.length) toast('ok', list.length === 1 ? 'File uploaded.' : `${list.length} files processed.`)
  }, [refId, onUploaded, toast])

  return (
    <Card tone="glass" padding={compact ? 'md' : 'lg'} radius="xl">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <p className="eyebrow mb-1.5 flex items-center gap-1.5"><Paperclip size={12} aria-hidden /> Evidence</p>
          <h2 className="font-display text-h3 leading-tight">Photos, receipts, documents</h2>
          <p className="mt-2 max-w-[52ch] text-[14px] text-taupe">
            A photo of the damage or a copy of the receipt usually settles a complaint faster than
            a description of it. PDF, Word, PNG, JPEG, WEBP or text — up to {MAX_MB} MB each.
          </p>
        </div>
      </div>

      <div
        role="button"
        tabIndex={0}
        onClick={() => input.current?.click()}
        onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && input.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setOver(true) }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => { e.preventDefault(); setOver(false); void start(e.dataTransfer.files) }}
        className={cn(
          'group/drop flex cursor-pointer flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed px-6 py-8 text-center transition-[border-color,background-color,transform] duration-300',
          over ? 'scale-[1.01] border-ai bg-ai-soft/70' : 'border-line bg-white/50 hover:border-ai-line hover:bg-ai-soft/40',
        )}
      >
        <input ref={input} type="file" accept={ACCEPT} multiple hidden onChange={(e) => { void start(e.target.files); e.target.value = '' }} />
        <span className={cn('inline-flex size-12 items-center justify-center rounded-2xl bg-white text-ai shadow-card transition-transform duration-300', over ? '-translate-y-1' : 'group-hover/drop:-translate-y-0.5')}>
          <UploadCloud size={22} aria-hidden />
        </span>
        <p className="text-[15px] font-medium text-espresso">{over ? 'Drop to upload' : 'Drag files here, or click to choose'}</p>
        <p className="text-[12.5px] text-taupe">Files are checked by their contents, not their name.</p>
      </div>

      {(uploads.length > 0 || evidence.length > 0) && (
        <ul className="mt-4 flex flex-col gap-2">
          {uploads.filter((u) => !u.done).map((u) => (
            <li key={u.id} className={cn('flex items-center gap-3 rounded-xl border px-3 py-2.5', u.error ? 'border-critical/30 bg-critical-dim/50' : 'border-line-soft bg-white/80')}>
              <FileIcon name={u.name} />
              <div className="min-w-0 flex-1">
                <p className="truncate text-[13.5px] font-medium text-espresso">{u.name}</p>
                {u.error ? (
                  <p className="text-[12.5px] text-critical">{u.error}</p>
                ) : (
                  <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-sand">
                    <div className="h-full rounded-full bg-gradient-to-r from-ai to-ai-2 transition-[width] duration-200" style={{ width: `${Math.round(u.progress * 100)}%` }} />
                  </div>
                )}
              </div>
              <span className="text-[12px] tnum text-taupe">{u.error ? kb(u.size) : `${Math.round(u.progress * 100)}%`}</span>
              {u.error && (
                <button aria-label={`Dismiss ${u.name}`} className="text-taupe hover:text-espresso" onClick={() => setUploads((all) => all.filter((x) => x.id !== u.id))}>
                  <X size={15} aria-hidden />
                </button>
              )}
            </li>
          ))}
          {evidence.map((e) => (
            <li key={e.id} className="flex animate-rise items-center gap-3 rounded-xl border border-line-soft bg-white/80 px-3 py-2.5">
              <FileIcon name={e.file_name} mime={e.mime_type} />
              <div className="min-w-0 flex-1">
                <p className="truncate text-[13.5px] font-medium text-espresso">{e.file_name}</p>
                <p className="text-[12px] text-taupe">{kb(e.size_bytes)} · uploaded {fmtRelative(e.uploaded_at)}</p>
              </div>
              <Badge tone="verified" icon={<CheckCircle2 size={11} aria-hidden />}>Attached</Badge>
              <button
                className="inline-flex size-8 items-center justify-center rounded-full text-taupe-2 transition-colors hover:bg-sand/60 hover:text-espresso"
                aria-label={`Download ${e.file_name}`}
                onClick={() => complaints.downloadEvidence(refId, e.id, e.file_name).catch((err) => toast('err', errorMessage(err)))}
              >
                <Download size={15} aria-hidden />
              </button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}

function FileIcon({ name, mime }: { name: string; mime?: string }) {
  const image = (mime ?? '').startsWith('image/') || /\.(png|jpe?g|webp)$/i.test(name)
  return (
    <span className={cn('inline-flex size-9 shrink-0 items-center justify-center rounded-lg', image ? 'bg-ai-soft text-ai' : 'bg-sand text-espresso-2')}>
      {image ? <ImageIcon size={16} aria-hidden /> : <FileText size={16} aria-hidden />}
    </span>
  )
}

/* ------------------------------------------------------------------ handling team */

/**
 * Who has the complaint and how to reach them.
 *
 * The mailto link carries the reference in its subject, so a customer who
 * writes in lands on the right case without being asked for it.
 */
export function TeamCard({ department, publicRef, compact }: { department?: S['DepartmentContactOut'] | null; publicRef: string; compact?: boolean }) {
  if (!department) {
    return (
      <Card tone="glass" radius="xl" padding={compact ? 'sm' : 'md'}>
        <p className="eyebrow mb-1.5 flex items-center gap-1.5"><Users size={12} aria-hidden /> Handled by</p>
        <p className="text-[14px] text-taupe">A team is assigned as soon as the complaint has been checked against policy.</p>
      </Card>
    )
  }
  const subject = encodeURIComponent(`${publicRef} — my complaint`)
  return (
    <Card tone="glass" radius="xl" padding={compact ? 'sm' : 'md'}>
      <p className="eyebrow mb-2 flex items-center gap-1.5"><Users size={12} aria-hidden /> Handled by</p>
      <div className="flex items-start gap-3">
        <span className="inline-flex size-10 shrink-0 items-center justify-center rounded-xl bg-espresso text-[13px] font-semibold text-ink-on-dark">
          {department.name.split(/[\s&]+/).filter(Boolean).map((w) => w[0]).slice(0, 2).join('')}
        </span>
        <div className="min-w-0">
          <p className="font-display text-[19px] leading-tight text-espresso">{department.name}</p>
          {!compact && department.summary && <p className="mt-1.5 text-[13.5px] leading-relaxed text-taupe">{department.summary}</p>}
        </div>
      </div>
      {(department.email || department.support_hours) && (
        <div className="mt-4 flex flex-col gap-2 border-t border-line-soft pt-3.5 text-[13.5px]">
          {department.email && (
            <a href={`mailto:${department.email}?subject=${subject}`} className="group/mail flex items-center gap-2 text-espresso-2 transition-colors hover:text-ai">
              <Mail size={15} className="shrink-0 text-taupe group-hover/mail:text-ai" aria-hidden />
              <span className="truncate font-medium underline decoration-line underline-offset-4 group-hover/mail:decoration-ai">{department.email}</span>
            </a>
          )}
          {department.support_hours && (
            <p className="flex items-center gap-2 text-taupe"><Clock size={15} className="shrink-0" aria-hidden /> {department.support_hours}</p>
          )}
        </div>
      )}
    </Card>
  )
}
