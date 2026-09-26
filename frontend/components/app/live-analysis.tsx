'use client'

import { useEffect, useState } from 'react'
import {
  BookOpen, Check, CheckCircle2, Cpu, FileText, Hash, History, ListChecks,
  Loader2, MinusCircle, Scale, Send, ShieldAlert, ShieldCheck, Sparkles,
  Terminal, XCircle, Zap,
} from 'lucide-react'
import type { ProgressStep } from '@/lib/api'
import { AiBadge, Badge, Mono, Pulse, RuleBadge } from '@/components/ui/primitives'
import { Card } from '@/components/ui/surfaces'
import { cn } from '@/lib/utils'

type Kind = 'ai' | 'rule' | 'plain'

export interface StepView {
  state: ProgressStep['state']
  detail: string | null
  log: string[]
  at_ms: number
}

export type StepMap = Record<string, StepView>

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

/** The backend's step ids with metadata */
const STEPS: Array<{ id: string; label: string; kind: Kind; icon: typeof FileText }> = [
  { id: 'read', label: 'Reading raw complaint bytes', kind: 'plain', icon: FileText },
  { id: 'safety', label: 'Scanning for injection & safety anomalies', kind: 'rule', icon: ShieldCheck },
  { id: 'details', label: 'Regex entity & PII scrubber pass', kind: 'plain', icon: ListChecks },
  { id: 'history', label: 'Checking customer & duplicate history', kind: 'plain', icon: History },
  { id: 'saved', label: 'Generating immutable complaint reference', kind: 'plain', icon: Hash },
  { id: 'rules', label: 'Deterministic business rules evaluation (precedence 1-10)', kind: 'rule', icon: Scale },
  { id: 'policy', label: 'Semantic policy retrieval & citation mapping (RAG)', kind: 'ai', icon: BookOpen },
  { id: 'ai', label: 'Gemini reasoning pass (intent, sentiment, multi-issues)', kind: 'ai', icon: Sparkles },
  { id: 'verify', label: 'Cross-pipeline verification & reconciliation gate', kind: 'rule', icon: ShieldCheck },
  { id: 'route', label: 'Routing to department & SLA deadline calculation', kind: 'plain', icon: Send },
]

export function LiveAnalysis({ steps, finished = false }: { steps: StepMap; finished?: boolean }) {
  const [elapsed, setElapsed] = useState(0)
  const [viewMode, setViewMode] = useState<'race' | 'timeline'>('race')

  useEffect(() => {
    if (finished) return
    const start = Date.now()
    const id = window.setInterval(() => setElapsed((Date.now() - start) / 1000), 50)
    return () => clearInterval(id)
  }, [finished])

  const closed = STEPS.filter((s) => steps[s.id]?.state === 'done' || steps[s.id]?.state === 'skipped').length
  const current = STEPS.find((s) => steps[s.id]?.state === 'active')
  const ref = steps.saved?.state === 'done' ? steps.saved.detail : null

  // GenAI Lane Steps
  const aiSteps = [
    {
      id: 'ai-prompt',
      name: 'Structured Prompt Assembly',
      desc: 'Injecting role constraints, few-shot examples & delimiters',
      active: steps.read?.state === 'active' || steps.read?.state === 'done',
      done: Boolean(steps.read?.state === 'done'),
    },
    {
      id: 'ai-reason',
      name: 'Gemini LLM Intent & Emotion Derivation',
      desc: steps.ai?.detail || 'Inferring primary intent, emotion indicators & sentiment score',
      active: steps.ai?.state === 'active',
      done: Boolean(steps.ai?.state === 'done'),
    },
    {
      id: 'ai-rag',
      name: 'RAG Semantic Policy Retrieval',
      desc: steps.policy?.detail || 'Searching policy vector embeddings & chunk citations',
      active: steps.policy?.state === 'active',
      done: Boolean(steps.policy?.state === 'done'),
    },
    {
      id: 'ai-draft',
      name: 'Suggested Action & Draft Synthesis',
      desc: 'Formulating resolution proposal & multi-issue breakdown',
      active: steps.ai?.state === 'done' && !finished,
      done: finished,
    },
  ]

  // Python Validation Lane Checks
  const pyChecks = [
    {
      id: 'py-pii',
      name: 'PII Regex Scrubber & Normalizer',
      desc: 'Detects CNIC, phone & payment cards; normalizes Unicode text',
      active: steps.details?.state === 'active',
      done: Boolean(steps.details?.state === 'done'),
      status: 'verified',
    },
    {
      id: 'py-inject',
      name: 'Prompt Injection Neutralization',
      desc: '28 heuristic patterns; strips delimiter escapes & isolates untrusted input',
      active: steps.safety?.state === 'active',
      done: Boolean(steps.safety?.state === 'done'),
      status: steps.safety?.log.some((l) => /injection/i.test(l)) ? 'flagged' : 'verified',
    },
    {
      id: 'py-rules',
      name: 'Precedence Rule Matrix (1-10)',
      desc: steps.rules?.detail || 'Strict deterministic validation rules overrule model hallucinations',
      active: steps.rules?.state === 'active',
      done: Boolean(steps.rules?.state === 'done'),
      status: 'verified',
    },
    {
      id: 'py-safety',
      name: 'Mandatory Safety & Escalation Floor',
      desc: 'Independent of sentiment: checks life-safety, fire hazard & regulatory codes',
      active: steps.verify?.state === 'active',
      done: Boolean(steps.verify?.state === 'done'),
      status: 'verified',
    },
    {
      id: 'py-reconcile',
      name: 'Agreement Scoring & Discrepancy Gate',
      desc: 'Calculates verification score; routes to human review if agreement < 70%',
      active: steps.verify?.state === 'active' || steps.route?.state === 'active',
      done: finished,
      status: 'verified',
    },
  ]

  return (
    <div className="mx-auto flex w-full max-w-[1140px] flex-col gap-6 py-4 md:py-6">
      {/* ── Race Header ── */}
      <div className="animate-rise text-center">
        <div className="mb-2 flex items-center justify-center gap-2">
          <Badge tone={finished ? 'verified' : 'ai'} pulse={!finished} className="px-3 py-1 font-mono text-[12px] uppercase tracking-wider">
            {finished ? 'Dual Pipeline Reconciliation Complete' : 'Split-Screen Pipeline Race Live'}
          </Badge>
          <span className="font-mono text-[13px] font-semibold text-taupe tnum">
            {elapsed.toFixed(2)}s
          </span>
        </div>
        <h1 className="display text-h1 text-espresso">
          {finished ? 'Decided & Reconciled.' : 'Live Dual-Pipeline Execution'}
        </h1>
        <p className="mx-auto mt-2 max-w-[68ch] text-[15px] leading-relaxed text-taupe-2">
          {current ? (
            <>
              Currently executing: <span className="font-medium text-espresso">{steps[current.id]?.log.at(-1) ?? current.label}</span>
            </>
          ) : finished ? (
            'Both GenAI and Python Validation pipelines have concluded. Agreement score computed.'
          ) : (
            'Simultaneously streaming GenAI reasoning and executing deterministic Python validation checks.'
          )}
        </p>

        {/* View toggle */}
        <div className="mt-4 flex items-center justify-center gap-2">
          <button
            type="button"
            onClick={() => setViewMode('race')}
            className={cn(
              'rounded-full px-3.5 py-1 text-[12.5px] font-medium transition-all',
              viewMode === 'race'
                ? 'bg-espresso text-white shadow-xs'
                : 'border border-line bg-white/70 text-espresso-2 hover:bg-white',
            )}
          >
            ⚡ Split-Screen Race View
          </button>
          <button
            type="button"
            onClick={() => setViewMode('timeline')}
            className={cn(
              'rounded-full px-3.5 py-1 text-[12.5px] font-medium transition-all',
              viewMode === 'timeline'
                ? 'bg-espresso text-white shadow-xs'
                : 'border border-line bg-white/70 text-espresso-2 hover:bg-white',
            )}
          >
            📋 Step Timeline View
          </button>
        </div>
      </div>

      {viewMode === 'race' ? (
        /* ══════════════════════════════════════════════════════════════
           SPLIT-SCREEN PIPELINE RACE VIEW
        ══════════════════════════════════════════════════════════════ */
        <div className="grid gap-6 lg:grid-cols-2">
          {/* ── LEFT COLUMN: GenAI Pipeline ── */}
          <div className="flex flex-col gap-4">
            <Card
              tone="glass"
              radius="xl"
              className="border-ai/30 shadow-sm relative overflow-hidden bg-gradient-to-b from-white/95 to-ai/[0.03]"
            >
              <div className="mb-4 flex items-center justify-between border-b border-line-soft pb-3">
                <div className="flex items-center gap-2">
                  <div className="flex size-7 items-center justify-center rounded-lg bg-ai text-white shadow-xs">
                    <Sparkles size={16} aria-hidden />
                  </div>
                  <div>
                    <h2 className="font-display text-[17px] font-medium text-espresso">
                      Pipeline 1 · GenAI Engine
                    </h2>
                    <p className="text-[11.5px] text-taupe">Gemini 2.5 LLM · Probabilistic & Creative</p>
                  </div>
                </div>
                <Badge tone="ai" className="font-mono text-[11px]">
                  {steps.ai?.state === 'active' ? 'GENERATING TOKENS…' : steps.ai?.state === 'done' ? 'PASSED' : 'STANDBY'}
                </Badge>
              </div>

              {/* Streaming Output Simulation Box */}
              <div className="mb-4 rounded-xl border border-line-soft bg-espresso p-3.5 font-mono text-[12px] text-white/90 shadow-inner">
                <div className="mb-2 flex items-center justify-between text-[11px] text-white/50 border-b border-white/10 pb-1.5">
                  <span className="flex items-center gap-1.5">
                    <Terminal size={12} aria-hidden /> Streaming Reasoner Tokens
                  </span>
                  <span>temp: 0.1 · Top-P: 0.95</span>
                </div>
                <div className="min-h-[88px] whitespace-pre-wrap leading-relaxed">
                  {steps.ai?.log && steps.ai.log.length > 0 ? (
                    <span className="text-sand-2">
                      &gt; {steps.ai.log.join('\n&gt; ')}
                    </span>
                  ) : steps.read?.state === 'active' ? (
                    <span className="text-white/60 animate-pulse">&gt; Parsing complaint tokens into context window…</span>
                  ) : steps.policy?.state === 'active' ? (
                    <span className="text-sand-2">&gt; Semantic similarity search over company policy corpus…</span>
                  ) : finished ? (
                    <span className="text-verified-2">&gt; Decision payload formed: Primary Category, SLA priority & suggested resolution generated.</span>
                  ) : (
                    <span className="text-white/40">&gt; Awaiting prompt assembly trigger…</span>
                  )}
                </div>
              </div>

              {/* Step Lane */}
              <div className="flex flex-col gap-2.5">
                {aiSteps.map((st, idx) => (
                  <div
                    key={st.id}
                    className={cn(
                      'flex items-start gap-3 rounded-xl border p-3 transition-all',
                      st.active
                        ? 'border-ai/50 bg-white/90 shadow-xs'
                        : st.done
                        ? 'border-line-soft bg-sand/30'
                        : 'border-transparent bg-sand/15 opacity-60',
                    )}
                  >
                    <div className="mt-0.5 shrink-0">
                      {st.done ? (
                        <div className="flex size-6 items-center justify-center rounded-full bg-ai text-white">
                          <Check size={13} strokeWidth={3} />
                        </div>
                      ) : st.active ? (
                        <div className="flex size-6 items-center justify-center rounded-full border-2 border-ai bg-white text-ai">
                          <Loader2 size={13} className="animate-spin" />
                        </div>
                      ) : (
                        <div className="flex size-6 items-center justify-center rounded-full border border-line bg-white/60 text-[11px] font-mono text-taupe">
                          {idx + 1}
                        </div>
                      )}
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-[13.5px] font-medium text-espresso">{st.name}</p>
                      <p className="text-[12px] text-taupe-2">{st.desc}</p>
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          </div>

          {/* ── RIGHT COLUMN: Python Validation Pipeline ── */}
          <div className="flex flex-col gap-4">
            <Card
              tone="glass"
              radius="xl"
              className="border-rule/30 shadow-sm relative overflow-hidden bg-gradient-to-b from-white/95 to-rule/[0.03]"
            >
              <div className="mb-4 flex items-center justify-between border-b border-line-soft pb-3">
                <div className="flex items-center gap-2">
                  <div className="flex size-7 items-center justify-center rounded-lg bg-rule text-white shadow-xs">
                    <Scale size={16} aria-hidden />
                  </div>
                  <div>
                    <h2 className="font-display text-[17px] font-medium text-espresso">
                      Pipeline 2 · Python Validation
                    </h2>
                    <p className="text-[11.5px] text-taupe">Deterministic Precedence Engine · Guardrails</p>
                  </div>
                </div>
                <Badge tone="rule" className="font-mono text-[11px]">
                  {steps.rules?.state === 'active' || steps.verify?.state === 'active'
                    ? 'EVALUATING RULES…'
                    : finished
                    ? 'VERIFIED'
                    : 'ARMED'}
                </Badge>
              </div>

              {/* Python Rules Status Monitor */}
              <div className="mb-4 rounded-xl border border-line-soft bg-espresso p-3.5 font-mono text-[12px] text-white/90 shadow-inner">
                <div className="mb-2 flex items-center justify-between text-[11px] text-white/50 border-b border-white/10 pb-1.5">
                  <span className="flex items-center gap-1.5">
                    <Cpu size={12} aria-hidden /> Python Precedence & Safety Guard
                  </span>
                  <span>Precedence: P1 &gt; P2 &gt; P3</span>
                </div>
                <div className="min-h-[88px] whitespace-pre-wrap leading-relaxed">
                  {steps.safety?.detail ? (
                    <span className="text-warning">&gt; [DEFENSE] {steps.safety.detail}</span>
                  ) : steps.rules?.detail ? (
                    <span className="text-verified-2">&gt; [RULE ENGINE] {steps.rules.detail}</span>
                  ) : steps.verify?.detail ? (
                    <span className="text-sand-2">&gt; [RECONCILIATION] {steps.verify.detail}</span>
                  ) : finished ? (
                    <span className="text-verified-2">&gt; Zero hallucinated promises allowed. Mandatory precedence floor upheld.</span>
                  ) : (
                    <span className="text-white/40">&gt; Deterministic engine standing by for payload verification…</span>
                  )}
                </div>
              </div>

              {/* Checks Lane */}
              <div className="flex flex-col gap-2.5">
                {pyChecks.map((ch, idx) => (
                  <div
                    key={ch.id}
                    className={cn(
                      'flex items-start gap-3 rounded-xl border p-3 transition-all',
                      ch.active
                        ? 'border-rule/50 bg-white/90 shadow-xs'
                        : ch.done
                        ? 'border-line-soft bg-sand/30'
                        : 'border-transparent bg-sand/15 opacity-60',
                    )}
                  >
                    <div className="mt-0.5 shrink-0">
                      {ch.done ? (
                        <div className="flex size-6 items-center justify-center rounded-full bg-rule text-white">
                          <Check size={13} strokeWidth={3} />
                        </div>
                      ) : ch.active ? (
                        <div className="flex size-6 items-center justify-center rounded-full border-2 border-rule bg-white text-rule">
                          <Loader2 size={13} className="animate-spin" />
                        </div>
                      ) : (
                        <div className="flex size-6 items-center justify-center rounded-full border border-line bg-white/60 text-[11px] font-mono text-taupe">
                          {idx + 1}
                        </div>
                      )}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <p className="text-[13.5px] font-medium text-espresso">{ch.name}</p>
                        {ch.done && (
                          <span className="rounded bg-verified/10 px-1.5 py-0.2 text-[10.5px] font-mono text-verified font-medium">
                            TICKED
                          </span>
                        )}
                      </div>
                      <p className="text-[12px] text-taupe-2">{ch.desc}</p>
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          </div>
        </div>
      ) : (
        /* ══════════════════════════════════════════════════════════════
           SEQUENTIAL TIMELINE VIEW
        ══════════════════════════════════════════════════════════════ */
        <Card tone="glass" padding="lg" radius="xl">
          <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
            <p className="text-[13px] text-taupe">
              {ref ? (
                <>
                  Reference <span className="font-mono font-medium text-espresso">{ref}</span>
                </>
              ) : (
                'Your reference appears once it is saved'
              )}
            </p>
            <p className="font-mono text-[13px] tnum text-taupe" aria-live="off">
              {finished ? '' : `${elapsed.toFixed(1)} s`}
            </p>
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
                      state === 'done' &&
                        (s.kind === 'ai'
                          ? 'border-ai bg-ai text-white'
                          : s.kind === 'rule'
                          ? 'border-rule bg-rule text-white'
                          : 'border-espresso bg-espresso text-ink-on-dark'),
                      state === 'active' && 'border-ai bg-white text-ai',
                      state === 'skipped' && 'border-line bg-sand/60 text-taupe',
                      state === 'pending' && 'border-line bg-white text-taupe/70',
                    )}
                  >
                    {state === 'active' && (
                      <span aria-hidden className="absolute inset-0 rounded-full border-2 border-ai animate-pulse-ring" />
                    )}
                    {state === 'done' ? (
                      <CheckCircle2 size={15} aria-hidden />
                    ) : state === 'active' ? (
                      <Loader2 size={14} className="animate-spin" aria-hidden />
                    ) : state === 'skipped' ? (
                      <MinusCircle size={14} aria-hidden />
                    ) : (
                      <Icon size={14} aria-hidden />
                    )}
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
                              j === v.log.length - 1
                                ? 'text-espresso-2'
                                : 'text-taupe line-through decoration-taupe/40',
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
                    {v && state !== 'active' && (
                      <span className="font-mono text-[11.5px] tnum text-taupe">
                        {(v.at_ms / 1000).toFixed(1)}s
                      </span>
                    )}
                  </div>
                </li>
              )
            })}
          </ol>
        </Card>
      )}

      {/* Progress Bar Footer */}
      <div className="rounded-xl border border-line-soft bg-white/70 p-4">
        <div className="flex items-center justify-between text-[12.5px] text-taupe-2 mb-2">
          <span>Overall Pipeline Progress</span>
          <span className="font-mono tnum font-semibold text-espresso">{closed} of {STEPS.length} stages completed</span>
        </div>
        <div className="h-2 overflow-hidden rounded-full bg-sand/80" role="progressbar">
          <div
            className="h-full rounded-full bg-gradient-to-r from-ai via-espresso to-rule transition-[width] duration-500"
            style={{ width: `${finished ? 100 : (closed / STEPS.length) * 100}%` }}
          />
        </div>
      </div>
    </div>
  )
}
