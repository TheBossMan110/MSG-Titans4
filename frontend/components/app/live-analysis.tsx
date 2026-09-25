'use client'

import { useEffect, useState } from 'react'
import {
  BookOpen, CheckCircle2, FileText, Hash, History, ListChecks, Loader2, MinusCircle,
  Scale, Send, ShieldCheck, Sparkles,
} from 'lucide-react'
import type { ProgressStep } from '@/lib/api'
import { AiBadge, Pulse, RuleBadge } from '@/components/ui/primitives'
import { Card } from '@/components/ui/surfaces'
import { cn } from '@/lib/utils'

type Kind = 'ai' | 'rule' | 'plain'

/** The backend's step ids, in pipeline order, with how each is drawn. */
const STEPS: Array<{ id: string; label: string; kind: Kind; icon: typeof FileText }> = [
  { id: 'read', label: 'Reading your complaint', kind: 'plain', icon: FileText },
  { id: 'safety', label: 'Checking it is safe to process', kind: 'rule', icon: ShieldCheck },
  { id: 'details', label: 'Checking the details you gave', kind: 'plain', icon: ListChecks },
  { id: 'history', label: 'Looking for earlier complaints', kind: 'plain', icon: History },
  { id: 'saved', label: 'Saving it with a reference', kind: 'plain', icon: Hash },
  { id: 'rules', label: 'Company rules are classifying it', kind: 'rule', icon: Scale },
  { id: 'policy', label: 'Finding the policies that apply', kind: 'ai', icon: BookOpen },
  { id: 'ai', label: 'AI is analysing your complaint', kind: 'ai', icon: Sparkles },
  { id: 'verify', label: 'Checking the AI against the rules', kind: 'rule', icon: ShieldCheck },
  { id: 'route', label: 'Sending it to the right team', kind: 'plain', icon: Send },
]

export interface StepView {
  state: ProgressStep['state']
  detail: string | null
  /** Every message the step has reported, oldest first — the AI step can have several. */
  log: string[]
  at_ms: number
}

export type StepMap = Record<string, StepView>

/** Fold one server event into the step map. */
export function applyStep(map: StepMap, e: ProgressStep): StepMap {
  const prev = map[e.step]
  const log = prev?.log ?? []
  return {
    ...map,
    [e.step]: {
      state: e.state,
      detail: e.detail ?? prev?.detail ?? null,
      log: e.detail && log[log.length - 1] !== e.detail ? [...log, e.detail] : log,
      at_ms: e.elapsed_ms,
    },
  }
}

/**
 * The analysis as it happens. Every line on this screen is a message the
 * pipeline sent at the moment the step ran — nothing advances on a timer.
 */
export function LiveAnalysis({ steps, finished = false }: { steps: StepMap; finished?: boolean }) {
  const [elapsed, setElapsed] = useState(0)
  useEffect(() => {
    if (finished) return
    const start = Date.now()
    const id = window.setInterval(() => setElapsed((Date.now() - start) / 1000), 100)
    return () => clearInterval(id)
  }, [finished])

  const closed = STEPS.filter((s) => steps[s.id]?.state === 'done' || steps[s.id]?.state === 'skipped').length
  const current = STEPS.find((s) => steps[s.id]?.state === 'active')
  const ref = steps.saved?.state === 'done' ? steps.saved.detail : null

  return (
    <div className="mx-auto flex w-full max-w-[760px] flex-col gap-6 py-4 md:py-6">
      <div className="animate-rise text-center">
        <p className="eyebrow mb-3 flex items-center justify-center gap-2">
          {finished ? <CheckCircle2 size={13} className="text-verified" aria-hidden /> : <Pulse tone="ai" />}
          {finished ? 'Finished' : 'Live'}
        </p>
        <h1 className="display text-h2">{finished ? 'All checked.' : 'Working on your complaint'}</h1>
        <p className="mx-auto mt-3 max-w-[54ch] text-[15px] leading-relaxed text-taupe">
          {current
            ? <>Right now: <span className="font-medium text-espresso">{steps[current.id]?.log.at(-1) ?? current.label}</span></>
            : finished ? 'Every step below has run. Your result is ready.' : 'Starting…'}
        </p>
      </div>

      <Card tone="glass" padding="lg" radius="xl">
        <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
          <p className="text-[13px] text-taupe">
            {ref ? <>Reference <span className="font-mono font-medium text-espresso">{ref}</span></> : 'Your reference appears once it is saved'}
          </p>
          <p className="font-mono text-[13px] tnum text-taupe" aria-live="off">{finished ? '' : `${elapsed.toFixed(1)} s`}</p>
        </div>

        <ol className="flex flex-col gap-1" aria-live="polite">
          {STEPS.map((s, i) => {
            const v = steps[s.id]
            const state = (v?.state ?? 'pending') as ProgressStep['state'] | 'pending'
            const Icon = s.icon
            return (
              <li
                key={s.id}
                className={cn(
                  'grid grid-cols-[auto_1fr_auto] items-start gap-3 rounded-2xl px-2 py-2.5 transition-colors duration-300 sm:gap-4 sm:px-3',
                  state === 'active' && 'bg-white/85 shadow-sm',
                )}
              >
                <span
                  className={cn(
                    'relative mt-0.5 inline-flex size-8 shrink-0 items-center justify-center rounded-full border-2 transition-colors duration-300',
                    state === 'done' && (s.kind === 'ai' ? 'border-ai bg-ai text-white' : s.kind === 'rule' ? 'border-rule bg-rule text-white' : 'border-espresso bg-espresso text-ink-on-dark'),
                    state === 'active' && 'border-ai bg-white text-ai',
                    state === 'skipped' && 'border-line bg-sand/60 text-taupe',
                    state === 'pending' && 'border-line bg-white text-taupe/70',
                  )}
                >
                  {state === 'active' && <span aria-hidden className="absolute inset-0 rounded-full border-2 border-ai animate-pulse-ring" />}
                  {state === 'done' ? <CheckCircle2 size={15} aria-hidden />
                    : state === 'active' ? <Loader2 size={14} className="animate-spin" aria-hidden />
                    : state === 'skipped' ? <MinusCircle size={14} aria-hidden />
                    : <Icon size={14} aria-hidden />}
                </span>

                <div className="min-w-0">
                  <p className={cn('text-[15px] font-medium leading-snug', state === 'pending' ? 'text-taupe' : 'text-espresso')}>
                    <span className="mr-2 font-mono text-[11.5px] text-taupe">{String(i + 1).padStart(2, '0')}</span>
                    {s.label}
                  </p>
                  {v && v.log.length > 0 && (
                    <ul className="mt-1 flex flex-col gap-0.5">
                      {v.log.map((line, j) => (
                        <li
                          key={j}
                          className={cn(
                            'animate-rise break-words text-[13px] leading-relaxed',
                            j === v.log.length - 1 ? 'text-espresso-2' : 'text-taupe line-through decoration-taupe/40',
                          )}
                        >
                          {line}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>

                <div className="flex flex-col items-end gap-1 pt-0.5">
                  {s.kind === 'ai' && <AiBadge>AI</AiBadge>}
                  {s.kind === 'rule' && <RuleBadge>rules</RuleBadge>}
                  {v && state !== 'active' && <span className="font-mono text-[11.5px] tnum text-taupe">{(v.at_ms / 1000).toFixed(1)}s</span>}
                </div>
              </li>
            )
          })}
        </ol>

        <div className="mt-5 h-1.5 overflow-hidden rounded-full bg-sand/80" role="progressbar" aria-valuemin={0} aria-valuemax={STEPS.length} aria-valuenow={closed}>
          <div
            className="h-full rounded-full bg-gradient-to-r from-ai to-rule-2 transition-[width] duration-500"
            style={{ width: `${finished ? 100 : (closed / STEPS.length) * 100}%` }}
          />
        </div>
        <p className="mt-2 text-center text-[12.5px] tnum text-taupe">{closed} of {STEPS.length} steps</p>
      </Card>
    </div>
  )
}
