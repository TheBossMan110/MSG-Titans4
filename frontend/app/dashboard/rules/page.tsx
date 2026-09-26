'use client'

import { useMemo, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { ShieldCheck } from 'lucide-react'
import { AppShell } from '@/components/layout/app-shell'
import { useAuth } from '@/lib/auth-context'
import { admin, type S } from '@/lib/api'
import { useApi, useAction } from '@/lib/use-api'
import { Badge, Button, Mono, humanise, escalationTone, priorityTone, urgencyTone } from '@/components/ui/primitives'
import { Card } from '@/components/ui/surfaces'
import { Select, SearchBox, Checkbox } from '@/components/ui/forms'
import { Table, Th, Td, Tr, Stat } from '@/components/ui/data'
import { Empty, ErrorState, SkeletonRows, Tabs, useToast } from '@/components/ui/feedback'
import { cn } from '@/lib/utils'

const OVERSIGHT = ['manager', 'admin', 'evaluator'] as const

export default function RulesPage() {
  return (
    <AppShell eyebrow="Rules" roles={['agent', 'reviewer', 'manager', 'admin', 'evaluator']} wide>
      <Matrix />
    </AppShell>
  )
}

/**
 * The rule matrix: every rule the engine loads, filterable, with the taxonomy
 * it maps onto. Configuration-as-data made visible: nothing here is in code.
 */
function Matrix() {
  const router = useRouter()
  const { user } = useAuth()
  const toast = useToast()
  const [tab, setTab] = useState<'rules' | 'taxonomy'>('rules')
  const [type, setType] = useState('')
  const [search, setSearch] = useState('')
  const [mandatory, setMandatory] = useState(false)
  const [inactive, setInactive] = useState(false)
  const rules = useApi(() => admin.rules({ rule_type: type || undefined, search: search || undefined, mandatory: mandatory || undefined, active: inactive ? undefined : true }), [type, search, mandatory, inactive])
  const taxonomy = useApi(() => admin.taxonomy())
  const reload = useAction(() => admin.reloadRules())
  const isAdmin = user?.role === 'admin'

  const all = rules.data ?? []
  const counts = useMemo(() => ({
    total: all.length, mandatory: all.filter((r) => r.is_mandatory_escalation).length, catchAll: all.filter((r) => r.is_catch_all).length,
    types: Array.from(new Set(all.map((r) => r.rule_type))).sort(),
  }), [all])

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div><p className="eyebrow mb-1">Pipeline 2 · configuration as data</p><h1 className="display text-h2">Rule matrix</h1></div>
        <div className="flex gap-2">
          <Button href="/dashboard/rules/sandbox" variant="secondary">Sandbox</Button>
          {isAdmin && <Button loading={reload.pending} onClick={async () => { const r = await reload.run(); if (r) { toast('ok', `Reloaded from YAML: ${Object.entries(r.reloaded ?? {}).map(([k, v]) => `${k} ${v}`).join(', ')} · ruleset ${r.ruleset_version}`); rules.refresh() } else if (reload.error) toast('err', reload.error) }}>Reload from YAML</Button>}
        </div>
      </div>

      <div className="grid gap-x-8 gap-y-6 rounded-[var(--radius-xl)] border border-line bg-ivory p-6 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Rules shown" value={rules.data ? counts.total : undefined} evidence={inactive ? 'including inactive' : 'active only'} />
        <Stat label="Mandatory escalations" value={rules.data ? counts.mandatory : undefined} tone="critical" evidence="floors that cannot be lowered" />
        <Stat label="Catch-all" value={rules.data ? counts.catchAll : undefined} evidence="what fires when nothing else does" />
        <Stat label="Rule types" value={rules.data ? counts.types.length : undefined} evidence={counts.types.map((t) => humanise(t)).join(' · ')} />
      </div>

      <Tabs value={tab} onChange={setTab} tabs={[{ id: 'rules', label: 'Rules', count: rules.data?.length ?? null }, { id: 'taxonomy', label: 'Taxonomy' }]} />

      {tab === 'rules' && (
        <>
          <div className="flex flex-wrap items-center gap-3">
            <SearchBox value={search} onChange={setSearch} placeholder="Reference, name or rationale" className="w-full sm:w-[320px]" />
            <Select value={type} onChange={(e) => setType(e.target.value)} aria-label="Rule type" className="w-auto"><option value="">All types</option>{['CLASSIFICATION', 'ROUTING', 'ESCALATION', 'ELIGIBILITY', 'RESOLUTION', 'PRIORITY'].map((t) => <option key={t} value={t}>{humanise(t)}</option>)}</Select>
            <Checkbox label="Mandatory only" checked={mandatory} onChange={(e) => setMandatory(e.target.checked)} />
            <Checkbox label="Show inactive" checked={inactive} onChange={(e) => setInactive(e.target.checked)} />
          </div>
          {rules.error ? <ErrorState message={rules.error} onRetry={rules.refresh} /> : rules.loading && !rules.data ? <SkeletonRows rows={10} /> : !all.length ? <Empty title="No rules match" /> : (
            <Table>
              <thead><tr><Th>Rule</Th><Th>Type</Th><Th align="right">Precedence</Th><Th>Outcome</Th><Th>Flags</Th><Th align="right">Version</Th></tr></thead>
              <tbody>
                {all.map((r) => (
                  <Tr key={r.rule_ref} onClick={() => router.push(`/dashboard/rules/${encodeURIComponent(r.rule_ref)}`)} className={cn(!r.is_active && 'opacity-55')}>
                    <Td className="max-w-[420px]">
                      <Link href={`/dashboard/rules/${encodeURIComponent(r.rule_ref)}`} onClick={(e) => e.stopPropagation()} className="font-mono text-[12.5px] text-taupe transition-colors hover:text-ai">{r.rule_ref}</Link>
                      <span className="mt-0.5 block truncate font-medium text-espresso">{r.name}</span>
                    </Td>
                    <Td><Badge tone="rule">{humanise(r.rule_type)}</Badge></Td>
                    <Td align="right" mono>{r.precedence}</Td>
                    <Td>
                      <span className="flex flex-wrap gap-1.5">
                        {r.outcome_escalation_code && <Badge tone={escalationTone(r.outcome_escalation_code)}>{humanise(r.outcome_escalation_code)}</Badge>}
                        {r.outcome_urgency && <Badge tone={urgencyTone(r.outcome_urgency)}>{humanise(r.outcome_urgency)}</Badge>}
                        {r.outcome_priority_code && <Badge tone={priorityTone(r.outcome_priority_code)} pulse={r.outcome_priority_code === 'P0'}>{r.outcome_priority_code}</Badge>}
                        {!r.outcome_escalation_code && !r.outcome_urgency && !r.outcome_priority_code && <span className="text-[13px] text-taupe">Classification only</span>}
                      </span>
                    </Td>
                    <Td>
                      <span className="flex flex-wrap gap-1.5">
                        {r.is_mandatory_escalation && <Badge tone="critical" icon={<ShieldCheck size={11} aria-hidden />}>Mandatory floor</Badge>}
                        {r.is_catch_all && <Badge tone="info">Catch-all</Badge>}
                        {!r.is_active && <Badge>Inactive</Badge>}
                        {r.can_deactivate === false && r.is_active && <Badge tone="warning">Locked</Badge>}
                      </span>
                    </Td>
                    <Td align="right" mono>v{r.version}</Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
          )}
        </>
      )}

      {tab === 'taxonomy' && (taxonomy.error ? <ErrorState message={taxonomy.error} onRetry={taxonomy.refresh} /> : taxonomy.loading && !taxonomy.data ? <SkeletonRows rows={6} /> : <TaxonomyView t={taxonomy.data!} />)}
    </div>
  )
}

function TaxonomyView({ t }: { t: S['TaxonomyOut'] }) {
  const groups: Array<[string, S['CodeOut'][] | undefined]> = [['Categories', t.categories], ['Subcategories', t.subcategories], ['Departments', t.departments], ['Priority levels', t.priority_levels], ['Escalation levels', t.escalation_levels]]
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      {groups.map(([title, rows]) => (
        <Card key={title} padding="sm">
          <p className="eyebrow mb-3 px-1">{title} <Mono className="ml-1 text-taupe-2">{rows?.length ?? 0}</Mono></p>
          <ul className="max-h-[420px] divide-y divide-line-soft overflow-y-auto">
            {(rows ?? []).map((c) => <li key={c.code} className="flex items-baseline gap-3 px-1 py-2 text-[13.5px]"><Mono className="w-[220px] shrink-0 truncate text-[12px] text-taupe-2">{c.code}</Mono><span className="flex-1">{c.name}</span>{c.rank != null && <Mono className="text-[11px] text-taupe">#{c.rank}</Mono>}</li>)}
          </ul>
        </Card>
      ))}
    </div>
  )
}
