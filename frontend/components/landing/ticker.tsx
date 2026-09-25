'use client'

import { Activity, BookOpen, Cpu, FileCheck2, ListChecks, ShieldCheck, Sparkles, type LucideIcon } from 'lucide-react'
import { system } from '@/lib/api'
import { useApi } from '@/lib/use-api'
import { cn } from '@/lib/utils'

type Item = { icon: LucideIcon; text: string; tone: 'ai' | 'rule' | 'plain'; live?: boolean }

/**
 * A slow ribbon of facts under the hero.
 *
 * The numbers are read from /api/health on load, so the ribbon says what this
 * deployment is running right now — not what a slide claimed. The rest are
 * structural facts about the architecture that are true by construction
 * (the verifier makes no model call; it is enforced by a test). Nothing here
 * is a performance claim, because performance is only quoted with its
 * denominator, on the benchmark page.
 *
 * Pure CSS transform animation, duplicated once for a seamless loop, paused
 * on hover and frozen under reduced motion.
 */
export function Ticker() {
  const health = useApi(() => system.health())
  const h = health.data

  const items: Item[] = [
    { icon: ListChecks, text: h ? `${h.active_rules.toLocaleString()} rules active` : 'Rules loading…', tone: 'rule', live: !!h },
    { icon: BookOpen, text: h ? `${h.knowledge_base_documents} policy documents indexed` : 'Policies loading…', tone: 'plain', live: !!h },
    { icon: Sparkles, text: h ? (h.llm_configured ? `AI provider: ${h.llm_primary}` : 'AI offline — rules deciding alone') : 'AI provider…', tone: 'ai', live: !!h },
    { icon: ShieldCheck, text: '0 model calls inside the verifier', tone: 'rule' },
    { icon: FileCheck2, text: 'Every citation resolved against the source', tone: 'plain' },
    { icon: Cpu, text: 'Two independent pipelines', tone: 'ai' },
    { icon: Activity, text: 'Escalation floors can be raised, never lowered', tone: 'rule' },
  ]

  const row = (hidden: boolean) => (
    <ul className="flex shrink-0 items-center gap-3 pr-3" aria-hidden={hidden || undefined}>
      {items.map((it, i) => {
        const Icon = it.icon
        return (
          <li
            key={`${i}-${hidden}`}
            className={cn(
              'inline-flex items-center gap-2 whitespace-nowrap rounded-full border px-4 py-2 text-[13.5px] font-medium',
              it.tone === 'ai' ? 'border-ai-line bg-ai-soft/80 text-ai'
                : it.tone === 'rule' ? 'border-rule-line bg-rule-soft/80 text-rule'
                  : 'border-line bg-white/80 text-espresso-2',
            )}
          >
            <Icon size={14} aria-hidden />
            {it.text}
            {it.live && <span className="ml-1 inline-flex items-center gap-1 text-[10.5px] font-semibold uppercase tracking-[0.12em] opacity-70"><span className="size-1.5 rounded-full bg-current" />live</span>}
          </li>
        )
      })}
    </ul>
  )

  return (
    <section aria-label="What this deployment is running" className="relative overflow-hidden border-y border-line-soft bg-cream/70 py-4 backdrop-blur-sm">
      <div className="pointer-events-none absolute inset-y-0 left-0 z-[1] w-24 bg-gradient-to-r from-cream to-transparent" />
      <div className="pointer-events-none absolute inset-y-0 right-0 z-[1] w-24 bg-gradient-to-l from-cream to-transparent" />
      <div className="flex w-max animate-marquee hover:[animation-play-state:paused] motion-reduce:animate-none">
        {row(false)}
        {row(true)}
      </div>
    </section>
  )
}
