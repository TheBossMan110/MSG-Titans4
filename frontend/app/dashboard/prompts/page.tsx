'use client'

import { useMemo, useState } from 'react'
import { AppShell } from '@/components/layout/app-shell'
import { useAuth } from '@/lib/auth-context'
import { admin, system } from '@/lib/api'
import { useApi, useAction } from '@/lib/use-api'
import { Badge, Button, Mono, humanise } from '@/components/ui/primitives'
import { Card, PanelHeader } from '@/components/ui/surfaces'
import { Input } from '@/components/ui/forms'
import { ErrorState, SkeletonRows, useToast } from '@/components/ui/feedback'
import { cn } from '@/lib/utils'

export default function PromptsPage() {
  return (
    <AppShell eyebrow="Prompts" roles={['admin', 'evaluator']}>
      <Prompts />
    </AppShell>
  )
}

/**
 * Prompt versions are data: named, versioned, checksummed. Exactly one
 * version of each prompt is active and every GenAI run records which. An
 * admin switches versions here with a reason; nothing is edited in place.
 */
function Prompts() {
  const { user } = useAuth()
  const toast = useToast()
  const q = useApi(() => admin.prompts())
  const version = useApi(() => system.version())
  const activate = useAction((name: string, v: string, reason?: string) => admin.activatePrompt(name, v, reason))
  const [reason, setReason] = useState('')
  const isAdmin = user?.role === 'admin'
  const groups = useMemo(() => {
    const m = new Map<string, NonNullable<typeof q.data>>()
    for (const p of q.data ?? []) m.set(p.name, [...(m.get(p.name) ?? []), p])
    return Array.from(m.entries())
  }, [q.data])

  return (
    <div className="flex flex-col gap-6">
      <div><p className="eyebrow mb-1">Pipeline 1 · configuration as data</p><h1 className="display text-h2">Prompt versions</h1><p className="mt-3 max-w-[60ch] text-[14.5px] text-espresso-2">Every model call records the prompt name and version it used, so a benchmark run can be reproduced. Switching a version is a configuration change, audited with a reason.</p></div>
      {version.data && <div className="flex flex-wrap gap-2 text-[13px] text-taupe-2"><span>Provider <Mono>{version.data.llm_primary_provider} · {version.data.llm_primary_model}</Mono></span>{version.data.llm_fallback_provider && <span>· fallback <Mono>{version.data.llm_fallback_provider}</Mono></span>}<span>· ruleset <Mono>{version.data.ruleset_version}</Mono></span></div>}
      {isAdmin && <div className="max-w-[520px]"><Input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Reason for switching (recorded in the audit trail)" aria-label="Reason" /></div>}
      {q.error ? <ErrorState message={q.error} onRetry={q.refresh} /> : q.loading && !q.data ? <SkeletonRows rows={5} /> : (
        <div className="grid gap-6 lg:grid-cols-2">
          {groups.map(([name, versions]) => (
            <Card key={name}>
              <PanelHeader title={humanise(name)} eyebrow={<Mono>{name}</Mono>} />
              <ul className="flex flex-col gap-2">
                {versions.map((p) => (
                  <li key={p.version} className={cn('flex flex-col gap-2 rounded-[var(--radius-md)] border px-4 py-3', p.is_active ? 'border-espresso bg-espresso text-ink-on-dark' : 'border-line bg-ivory')}>
                    <div className="flex flex-wrap items-center gap-3">
                      <Mono className="font-medium">{p.version}</Mono>
                      {p.is_active ? <Badge tone="neutral" className="bg-ink-on-dark/15 text-ink-on-dark border-transparent">active</Badge> : null}
                      {p.checksum && <Mono className={cn('text-[11px]', p.is_active ? 'text-sand-2' : 'text-taupe-2')}>{p.checksum.slice(0, 12)}</Mono>}
                      <span className={cn('flex flex-1 flex-wrap gap-1 text-[11.5px]', p.is_active ? 'text-sand-2' : 'text-taupe-2')}>{(p.variables ?? []).map((v) => <span key={v}>{`{${v}}`}</span>)}</span>
                      {isAdmin && !p.is_active && <Button size="sm" variant="secondary" loading={activate.pending} onClick={async () => { const r = await activate.run(name, p.version, reason || undefined); if (r) { toast('ok', `${name} now uses ${r.version}.`); q.refresh() } else if (activate.error) toast('err', activate.error) }}>Activate</Button>}
                    </div>
                    {p.template_text ? (
                      <details className="mt-1">
                        <summary className={cn('cursor-pointer text-[12px] font-medium hover:underline', p.is_active ? 'text-sand' : 'text-espresso')}>
                          View template source ({p.version})
                        </summary>
                        <pre className={cn('mt-2 max-h-80 overflow-auto rounded p-3 font-mono text-[11px] leading-relaxed whitespace-pre-wrap', p.is_active ? 'bg-ink text-sand-2' : 'bg-sand/40 text-espresso-2')}>
                          {p.template_text}
                        </pre>
                      </details>
                    ) : null}
                  </li>
                ))}
              </ul>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
