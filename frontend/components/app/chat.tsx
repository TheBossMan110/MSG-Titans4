'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { ArrowUp, CheckCircle2, FileText, Loader2, MessageCircle, Pencil, Sparkles, X } from 'lucide-react'
import { useAuth } from '@/lib/auth-context'
import { assistant, errorMessage, submitWithProgress, type ProgressStep, type S } from '@/lib/api'
import { Button } from '@/components/ui/primitives'
import { cn } from '@/lib/utils'

type Draft = S['DraftOut']
type Status = S['StatusBrief']

interface Msg {
  role: 'user' | 'assistant'
  content: string
  draft?: Draft | null
  statuses?: Status[]
  signIn?: boolean
  filing?: { steps: ProgressStep[]; ref?: string; done?: boolean; error?: string }
}

const STORE = 'nova-chat-v1'
const GREETING: Msg = {
  role: 'assistant',
  content: "Hi, I'm Nova from RaftarXpress support. Tell me what went wrong and I'll help you raise a complaint — or ask me about one you already raised.",
}
const STARTERS = ['My parcel is late', 'My parcel arrived damaged', 'Check my complaint status', 'How does this work?']

function load(): Msg[] {
  try {
    const raw = sessionStorage.getItem(STORE)
    const parsed = raw ? (JSON.parse(raw) as Msg[]) : null
    return parsed?.length ? parsed : [GREETING]
  } catch {
    return [GREETING]
  }
}

/**
 * The conversation with Nova. Nova only talks; filing happens when the
 * customer presses "File this complaint", which sends the draft through the
 * same live intake as the form (channel CHAT) and narrates it here.
 */
export function ChatPanel({ onClose, className }: { onClose?: () => void; className?: string }) {
  const { user } = useAuth()
  const [messages, setMessages] = useState<Msg[]>([GREETING])
  const [input, setInput] = useState('')
  const [pending, setPending] = useState(false)
  const list = useRef<HTMLDivElement>(null)
  const field = useRef<HTMLTextAreaElement>(null)

  useEffect(() => { setMessages(load()) }, [])
  useEffect(() => {
    try { sessionStorage.setItem(STORE, JSON.stringify(messages.slice(-40))) } catch {}
    list.current?.scrollTo({ top: list.current.scrollHeight, behavior: 'smooth' })
  }, [messages])
  useEffect(() => { field.current?.focus() }, [])

  const send = useCallback(async (text: string) => {
    const content = text.trim()
    if (!content || pending) return
    const next: Msg[] = [...messages, { role: 'user', content }]
    setMessages(next)
    setInput('')
    setPending(true)
    try {
      const history = next
        .filter((m) => !m.filing)
        .map((m) => ({ role: m.role, content: m.content }))
      const r = await assistant.chat(history)
      setMessages((m) => [...m, { role: 'assistant', content: r.reply, draft: r.draft ?? null, statuses: r.statuses ?? [], signIn: r.needs_sign_in }])
    } catch (e) {
      setMessages((m) => [...m, { role: 'assistant', content: `Sorry, I couldn't reply just now (${errorMessage(e)}). You can still use the complaint form.` }])
    } finally {
      setPending(false)
      field.current?.focus()
    }
  }, [messages, pending])

  const file = useCallback(async (draft: Draft) => {
    setMessages((m) => [...m, { role: 'assistant', content: 'Filing your complaint now — you can watch each step.', filing: { steps: [] } }])
    const update = (fn: (f: NonNullable<Msg['filing']>) => NonNullable<Msg['filing']>) =>
      setMessages((m) => {
        const copy = [...m]
        for (let i = copy.length - 1; i >= 0; i--) if (copy[i].filing) { copy[i] = { ...copy[i], filing: fn(copy[i].filing!) }; break }
        return copy
      })
    try {
      const body: S['ComplaintCreate'] = {
        title: draft.title, description: draft.description, channel: 'CHAT',
        order_ref: draft.order_ref ?? undefined, product: draft.product ?? undefined,
        requested_resolution: draft.requested_resolution ?? undefined,
      }
      const result = await submitWithProgress(body, true, (step) => update((f) => ({ ...f, steps: [...f.steps.filter((s) => !(s.step === step.step && s.state === 'active')), step] })))
      update((f) => ({ ...f, ref: result.public_ref, done: true }))
      const team = result.customer_view?.department?.name
      setMessages((m) => [...m, {
        role: 'assistant',
        content: `Done — your complaint is ${result.public_ref}.${team ? ` It's with the ${team} team.` : ''} Keep that reference; you can follow every step, answer questions and add photos from its tracking page.`,
        statuses: result.customer_view ? [{ public_ref: result.public_ref, title: result.customer_view.title, status_label: result.customer_view.action_needed ? 'Waiting for you' : 'Checked against policy', team: team ?? null, action_needed: Boolean(result.customer_view.action_needed) }] : [],
      }])
    } catch (e) {
      update((f) => ({ ...f, error: errorMessage(e) }))
    }
  }, [])

  const reset = () => { setMessages([GREETING]); try { sessionStorage.removeItem(STORE) } catch {} }
  const started = messages.length > 1

  return (
    <div className={cn('flex min-h-0 flex-col bg-ivory', className)}>
      <header className="flex items-center gap-3 border-b border-line-soft bg-espresso px-4 py-3 text-ink-on-dark">
        <span className="relative inline-flex size-9 items-center justify-center rounded-full bg-ink-on-dark/15"><Sparkles size={16} aria-hidden /><span className="absolute -bottom-0.5 -right-0.5 size-2.5 rounded-full border-2 border-espresso bg-verified-dim" aria-hidden /></span>
        <div className="min-w-0 flex-1">
          <p className="text-[14.5px] font-medium leading-tight">Nova</p>
          <p className="text-[12px] text-ink-on-dark/70">RaftarXpress support · usually replies in seconds</p>
        </div>
        {started && <button type="button" onClick={reset} className="rounded-full px-2.5 py-1 text-[12px] text-ink-on-dark/80 hover:bg-ink-on-dark/10">New chat</button>}
        {onClose && <button type="button" onClick={onClose} aria-label="Close chat" className="inline-flex size-8 items-center justify-center rounded-full hover:bg-ink-on-dark/10"><X size={17} aria-hidden /></button>}
      </header>

      <div ref={list} data-lenis-prevent className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto px-4 py-4" aria-live="polite">
        {messages.map((m, i) => <Bubble key={i} m={m} signedIn={Boolean(user)} onFile={file} onEdit={() => field.current?.focus()} />)}
        {pending && (
          <div className="flex items-center gap-2 text-[13px] text-taupe-2"><Loader2 size={14} className="animate-spin" aria-hidden /> Nova is typing…</div>
        )}
        {!started && (
          <div className="mt-1 flex flex-wrap gap-2">
            {STARTERS.map((s) => <button key={s} type="button" onClick={() => void send(s)} className="rounded-full border border-line bg-white px-3 py-1.5 text-[13px] text-espresso-2 transition-colors hover:border-espresso/40 hover:text-espresso">{s}</button>)}
          </div>
        )}
      </div>

      <form
        onSubmit={(e) => { e.preventDefault(); void send(input) }}
        className="flex items-end gap-2 border-t border-line-soft bg-white/80 p-3"
      >
        <label className="sr-only" htmlFor="nova-input">Message Nova</label>
        <textarea
          id="nova-input"
          ref={field}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void send(input) } }}
          rows={1}
          maxLength={2000}
          placeholder="Type your message…"
          className="max-h-32 min-h-[44px] flex-1 resize-none rounded-2xl border border-line bg-ivory px-3.5 py-2.5 text-[14px] text-espresso placeholder:text-taupe focus:border-espresso focus:outline-none"
        />
        <button type="submit" disabled={!input.trim() || pending} aria-label="Send" className="inline-flex size-11 shrink-0 items-center justify-center rounded-full bg-espresso text-ink-on-dark transition-opacity disabled:opacity-40">
          <ArrowUp size={18} aria-hidden />
        </button>
      </form>
      <p className="bg-white/80 px-4 pb-3 text-[11.5px] text-taupe-2">Nova only helps with RaftarXpress deliveries and complaints. Nothing is filed until you press “File this complaint”.</p>
    </div>
  )
}

function Bubble({ m, signedIn, onFile, onEdit }: { m: Msg; signedIn: boolean; onFile: (d: Draft) => void; onEdit: () => void }) {
  const mine = m.role === 'user'
  return (
    <div className={cn('flex flex-col gap-2', mine ? 'items-end' : 'items-start')}>
      <p className={cn('max-w-[88%] whitespace-pre-wrap rounded-2xl px-3.5 py-2.5 text-[14px] leading-relaxed', mine ? 'rounded-br-md bg-espresso text-ink-on-dark' : 'rounded-bl-md border border-line-soft bg-white text-espresso-2')}>
        {m.content}
      </p>

      {m.draft && (
        <div className="w-full max-w-[92%] rounded-2xl border border-line bg-white p-3.5 shadow-card">
          <p className="mb-2 flex items-center gap-1.5 text-[11.5px] font-semibold uppercase tracking-[0.12em] text-taupe-2"><FileText size={13} aria-hidden /> Your complaint</p>
          <p className="text-[14px] font-medium text-espresso">{m.draft.title}</p>
          <p className="mt-1 text-[13px] leading-relaxed text-espresso-2">{m.draft.description}</p>
          <dl className="mt-2 grid grid-cols-[max-content_1fr] gap-x-3 gap-y-0.5 text-[12.5px]">
            {m.draft.order_ref && <><dt className="text-taupe-2">Reference</dt><dd className="font-mono text-espresso">{m.draft.order_ref}</dd></>}
            {m.draft.requested_resolution && <><dt className="text-taupe-2">You'd like</dt><dd className="text-espresso">{m.draft.requested_resolution}</dd></>}
          </dl>
          {signedIn ? (
            <div className="mt-3 flex flex-wrap gap-2">
              <Button size="sm" onClick={() => onFile(m.draft!)} icon={<CheckCircle2 size={14} aria-hidden />}>File this complaint</Button>
              <Button size="sm" variant="ghost" onClick={onEdit} icon={<Pencil size={13} aria-hidden />}>Change something</Button>
            </div>
          ) : (
            <div className="mt-3 flex flex-wrap gap-2">
              <Button size="sm" href={`/login?next=${encodeURIComponent('/dashboard/assistant')}`}>Sign in to file</Button>
              <Button size="sm" variant="secondary" href="/register">Create account</Button>
            </div>
          )}
        </div>
      )}

      {m.signIn && !m.draft && !signedIn && (
        <div className="flex flex-wrap gap-2">
          <Button size="sm" href={`/login?next=${encodeURIComponent('/dashboard/assistant')}`}>Sign in</Button>
          <Button size="sm" variant="secondary" href="/register">Create account</Button>
        </div>
      )}

      {m.statuses && m.statuses.length > 0 && (
        <ul className="flex w-full max-w-[92%] flex-col gap-2">
          {m.statuses.map((s) => (
            <li key={s.public_ref}>
              <Link href={`/track/${encodeURIComponent(s.public_ref)}`} className="block rounded-2xl border border-line bg-white px-3.5 py-3 transition-colors hover:border-espresso/40">
                <span className="flex items-center justify-between gap-2"><span className="font-mono text-[12.5px] text-taupe-2">{s.public_ref}</span><span className={cn('rounded-full px-2 py-0.5 text-[11.5px]', s.action_needed ? 'bg-warning-dim text-warning' : 'bg-sand/70 text-espresso-2')}>{s.status_label}</span></span>
                <span className="mt-1 block truncate text-[14px] font-medium text-espresso">{s.title}</span>
                {s.team && <span className="block text-[12.5px] text-taupe-2">With the {s.team} team</span>}
              </Link>
            </li>
          ))}
        </ul>
      )}

      {m.filing && (
        <ol className="w-full max-w-[92%] rounded-2xl border border-line-soft bg-white p-3 text-[13px]">
          {m.filing.steps.map((s, i) => (
            <li key={`${s.step}-${i}`} className="flex items-start gap-2 py-0.5">
              {s.state === 'active' ? <Loader2 size={14} className="mt-0.5 shrink-0 animate-spin text-ai" aria-hidden /> : <CheckCircle2 size={14} className={cn('mt-0.5 shrink-0', s.state === 'skipped' ? 'text-taupe' : 'text-verified')} aria-hidden />}
              <span className="min-w-0"><span className="text-espresso">{s.label}</span>{s.detail && <span className="text-taupe-2"> — {s.detail}</span>}</span>
            </li>
          ))}
          {!m.filing.done && !m.filing.error && m.filing.steps.length === 0 && <li className="flex items-center gap-2 text-taupe-2"><Loader2 size={14} className="animate-spin" aria-hidden /> Starting…</li>}
          {m.filing.error && <li className="mt-1 text-critical">{m.filing.error}</li>}
        </ol>
      )}
    </div>
  )
}

/**
 * The floating way in, on the public site and customer pages. Staff work in
 * the register and do not see it; neither do the sign-in pages.
 */
export function ChatLauncher() {
  const { user } = useAuth()
  const pathname = usePathname()
  const [open, setOpen] = useState(false)
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open])

  const hidden =
    (user && user.role !== 'customer') ||
    pathname.startsWith('/login') || pathname.startsWith('/register') ||
    pathname.startsWith('/dashboard/assistant') || pathname.startsWith('/dashboard/complaints/new')
  if (hidden) return null

  return (
    <>
      {open && (
        <div role="dialog" aria-label="Chat with Nova" className="fixed inset-0 z-[80] flex flex-col sm:inset-auto sm:bottom-24 sm:right-6 sm:h-[min(640px,calc(100dvh-140px))] sm:w-[400px] sm:overflow-hidden sm:rounded-3xl sm:border sm:border-line sm:shadow-[0_30px_80px_-30px_rgba(42,31,23,0.55)]">
          <ChatPanel onClose={() => setOpen(false)} className="h-full" />
        </div>
      )}
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-label={open ? 'Close chat' : 'Chat with Nova'}
        className={cn(
          'fixed bottom-5 right-5 z-[79] flex items-center gap-2 rounded-full bg-espresso px-4 py-3.5 text-ink-on-dark shadow-[0_18px_40px_-16px_rgba(42,31,23,0.7)] transition-transform hover:-translate-y-0.5 sm:bottom-6 sm:right-6',
          open && 'hidden sm:flex',
        )}
      >
        {open ? <X size={20} aria-hidden /> : <MessageCircle size={20} aria-hidden />}
        <span className="hidden text-[14px] font-medium sm:inline">{open ? 'Close' : 'Chat with Nova'}</span>
      </button>
    </>
  )
}
