'use client'

import Link from 'next/link'
import { useState, type ReactNode } from 'react'
import { AlertTriangle, ArrowRight, Briefcase, Clock, Siren, UserCheck, Users } from 'lucide-react'
import { AppShell } from '@/components/layout/app-shell'
import { useAuth } from '@/lib/auth-context'
import { analytics, type Brief } from '@/lib/api'
import { useApi, fmtRelative } from '@/lib/use-api'
import { Badge, Button, escalationTone, humanise, priorityTone } from '@/components/ui/primitives'
import { Select } from '@/components/ui/forms'
import { Stat, Table, Td, Th, Tr } from '@/components/ui/data'
import { Empty, ErrorState, SkeletonRows } from '@/components/ui/feedback'
import { DashSection } from '@/components/app/dashboard-bits'
import { useRouter } from 'next/navigation'

export default function ManagerDashboardPage() {
  return (
    <AppShell eyebrow="Manager dashboard" roles={['manager', 'admin', 'evaluator']} wide>
      <ManagerDashboard />
    </AppShell>
  )
}

/**
 * The support manager runs the operation: every team's load and SLA, which
 * agent holds what, and where to step in -- critical cases, escalations, the
 * review queue. They watch and intervene; configuring the platform is the
 * administrator's job.
 */
function ManagerDashboard() {
  const { user } = useAuth()
  const router = useRouter()
  const [team, setTeam] = useState('')
  const q = useApi(() => analytics.manager(team || undefined), [team], true, { live: true })
  const d = q.data

  return (
    <div className="flex flex-col gap-8">
      <section className="mesh-banner grain relative overflow-hidden rounded-[var(--radius-xl)] px-6 py-8 text-ink-on-dark md:px-10 md:py-10">
        <div className="relative z-[1] flex flex-wrap items-end justify-between gap-6">
          <div className="animate-rise">
            <p className="eyebrow mb-3 text-sand-2">Manager dashboard{d?.department_name ? ` · ${d.department_name}` : ' · all teams'}</p>
            <h1 className="display text-h1 text-ink-on-dark">{user?.full_name}</h1>
            <p className="mt-3 max-w-[58ch] text-[15.5px] text-ink-on-dark/80">
              The support operation today: how much is open, how each team and agent is doing, what is close to its deadline, and where to step in.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button href="/dashboard/reports" variant="onDark" icon={<Briefcase size={15} aria-hidden />}>Reports</Button>
          </div>
        </div>
      </section>

      <div className="flex flex-wrap items-center gap-3">
        <label htmlFor="team" className="text-[13.5px] text-taupe-2">Showing</label>
        <Select id="team" value={team} onChange={(e) => setTeam(e.target.value)} className="w-auto min-w-[240px]">
          <option value="">All teams</option>
          {(d?.departments ?? []).map((x) => <option key={x.code} value={x.code}>{x.name}</option>)}
        </Select>
        {d && d.unassigned_open > 0 && (
          <Link href="/dashboard/complaints" className="inline-flex items-center gap-1.5 rounded-full border border-warning/40 bg-warning-dim px-3 py-1 text-[12.5px] text-espresso">
            <AlertTriangle size={13} className="text-warning" aria-hidden /> {d.unassigned_open} open complaints have no one assigned
          </Link>
        )}
      </div>

      {q.error ? <ErrorState message={q.error} onRetry={q.refresh} /> : (
        <>
          <DashSection id="today" title="Today" icon={<Clock size={15} aria-hidden />}>
            <div className="grid grid-cols-2 gap-x-6 gap-y-5 sm:grid-cols-4 xl:grid-cols-8">
              <Stat label="Total complaints" value={d?.today.total} size="lg" />
              <Stat label="New today" value={d?.today.new_today} />
              <Stat label="Open" value={d?.today.open} />
              <Stat label="In progress" value={d?.today.in_progress} />
              <Stat label="Escalated" value={d?.today.escalated} tone={d?.today.escalated ? 'warning' : 'neutral'} />
              <Stat label="SLA at risk" value={d?.today.sla_at_risk} tone={d?.today.sla_at_risk ? 'warning' : 'neutral'} />
              <Stat label="Critical (P0)" value={d?.today.critical} tone={d?.today.critical ? 'critical' : 'neutral'} />
              <Stat label="Manual review" value={d?.today.manual_review} />
            </div>
          </DashSection>

          <DashSection id="teams" title="Team performance" icon={<Users size={15} aria-hidden />}>
            {!d ? <SkeletonRows rows={6} /> : !d.teams.length ? <Empty title="No complaints yet" body="Team figures appear once complaints arrive." /> : (
              <Table dense>
                <thead><tr><Th>Team</Th><Th align="right">Complaints</Th><Th align="right">Open</Th><Th align="right">Resolved</Th><Th align="right">Escalated</Th><Th align="right">SLA at risk</Th><Th align="right">In review</Th><Th align="right">Avg. resolution</Th></tr></thead>
                <tbody>
                  {d.teams.map((t) => (
                    <Tr key={t.code} onClick={() => setTeam(t.code)}>
                      <Td><span className="font-medium text-espresso">{t.name}</span></Td>
                      <Td align="right" mono>{t.total}</Td>
                      <Td align="right" mono>{t.open}</Td>
                      <Td align="right"><span className="tnum">{t.resolved} <span className="text-taupe-2">({t.resolved_pct}%)</span></span></Td>
                      <Td align="right" mono>{t.escalated}</Td>
                      <Td align="right">{t.sla_at_risk ? <Badge tone="warning">{t.sla_at_risk}</Badge> : <span className="text-taupe">0</span>}</Td>
                      <Td align="right" mono>{t.in_review}</Td>
                      <Td align="right" mono>{t.avg_resolution_hours != null ? `${t.avg_resolution_hours} h` : '—'}</Td>
                    </Tr>
                  ))}
                </tbody>
              </Table>
            )}
          </DashSection>

          <DashSection id="agents" title="Agent workload" icon={<Users size={15} aria-hidden />}
            aside={<Link href="/dashboard/users" className="text-[13px] text-espresso-2 underline underline-offset-4">See the team</Link>}>
            {!d ? <SkeletonRows rows={5} /> : !d.agents.length ? <Empty title="No agents" body={team ? 'No agent belongs to this team yet.' : 'No agent accounts exist yet.'} /> : (
              <Table dense>
                <thead><tr><Th>Agent</Th><Th>Team</Th><Th align="right">Open cases</Th><Th align="right">Resolved</Th><Th align="right">SLA at risk</Th><Th align="right">Avg. resolution</Th><Th>Last signed in</Th></tr></thead>
                <tbody>
                  {d.agents.map((a) => (
                    <Tr key={a.id} onClick={() => router.push(`/dashboard/users/${a.id}`)}>
                      <Td><span className="font-medium text-espresso">{a.name}</span></Td>
                      <Td>{a.team ?? '—'}</Td>
                      <Td align="right" mono>{a.open}</Td>
                      <Td align="right" mono>{a.resolved}</Td>
                      <Td align="right">{a.sla_at_risk ? <Badge tone="warning">{a.sla_at_risk}</Badge> : <span className="text-taupe">0</span>}</Td>
                      <Td align="right" mono>{a.avg_resolution_hours != null ? `${a.avg_resolution_hours} h` : '—'}</Td>
                      <Td>{a.last_login_at ? fmtRelative(a.last_login_at) : <span className="text-taupe">Never</span>}</Td>
                    </Tr>
                  ))}
                </tbody>
              </Table>
            )}
          </DashSection>

          <div className="grid gap-6 xl:grid-cols-2">
            <DashSection id="sla" title="SLA monitoring" icon={<AlertTriangle size={15} aria-hidden />}
              aside={d ? <Badge tone={d.today.sla_at_risk ? 'warning' : 'verified'}>{d.today.sla_at_risk} at risk</Badge> : null}>
              {!d ? <SkeletonRows rows={4} /> : !d.sla_risks.length ? <Empty title="All clear" body="No open complaint is near its deadline." /> : (
                <List rows={d.sla_risks.map((r) => ({ public_ref: r.public_ref, title: r.title, priority: r.priority, status: '', team: r.team, created_at: null }))}
                  render={(r) => {
                    const risk = d.sla_risks.find((x) => x.public_ref === r.public_ref)
                    return <span className={risk?.breached ? 'text-critical' : 'text-warning'}>{risk?.breached ? 'Breached' : 'Due'} {fmtRelative(risk?.due_at)}</span>
                  }} />
              )}
            </DashSection>
            <DashSection id="critical" title="Critical cases" icon={<Siren size={15} aria-hidden />}
              aside={d ? <Badge tone={d.today.critical ? 'critical' : 'verified'}>{d.today.critical} open</Badge> : null}>
              {!d ? <SkeletonRows rows={4} /> : !d.critical.length ? <Empty title="None open" body="No P0 complaint is open." /> : (
                <List rows={d.critical} render={(r) => <span>{r.team ?? 'Unrouted'} · {humanise(r.status)} · {fmtRelative(r.created_at)}</span>} />
              )}
            </DashSection>
          </div>

          <div className="grid gap-6 xl:grid-cols-2">
            <DashSection id="escalations" title="Escalations" icon={<Siren size={15} aria-hidden />}
              aside={<Link href="/dashboard/escalations" className="text-[13px] text-espresso-2 underline underline-offset-4">All escalations</Link>}>
              {!d ? <SkeletonRows rows={4} /> : !d.escalations.length ? <Empty title="None open" body="Nothing is escalated right now." /> : (
                <List rows={d.escalations} render={(r) => <span>{r.escalation ? <Badge tone={escalationTone(r.escalation)} className="mr-1.5">{humanise(r.escalation)}</Badge> : null}{r.team ?? 'Unrouted'}</span>} />
              )}
            </DashSection>
            <DashSection id="review-status" title="Review status" icon={<UserCheck size={15} aria-hidden />}>
              {!d ? <SkeletonRows rows={3} /> : (
                <div className="flex flex-col gap-4">
                  <div className="grid grid-cols-2 gap-4">
                    <Stat label="Waiting for a reviewer" value={d.today.manual_review} tone={d.today.manual_review ? 'warning' : 'neutral'} />
                    <Stat label="Resolved or closed" value={d.today.resolved} tone="verified" />
                  </div>
                  <Button href="/dashboard/review" variant="secondary" size="sm" className="self-start" arrow>Open the review queue</Button>
                </div>
              )}
            </DashSection>
          </div>
        </>
      )}
    </div>
  )
}

function List({ rows, render }: { rows: Brief[]; render: (r: Brief) => ReactNode }) {
  return (
    <ul className="divide-y divide-line-soft">
      {rows.map((r) => (
        <li key={r.public_ref}>
          <Link href={`/dashboard/complaints/${encodeURIComponent(r.public_ref)}`} className="flex items-center gap-3 py-2.5 hover:bg-white/50">
            {r.priority ? <Badge tone={priorityTone(r.priority)}>{r.priority}</Badge> : null}
            <span className="min-w-0 flex-1">
              <span className="block truncate text-[14px] font-medium text-espresso">{r.title}</span>
              <span className="block text-[12.5px] text-taupe-2"><span className="font-mono">{r.public_ref}</span> · {render(r)}</span>
            </span>
            <ArrowRight size={15} className="shrink-0 text-taupe" aria-hidden />
          </Link>
        </li>
      ))}
    </ul>
  )
}
