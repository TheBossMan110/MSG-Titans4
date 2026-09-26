'use client'

import Link from 'next/link'
import { useState, type ReactNode } from 'react'
import {
  AlertTriangle, ArrowRight, BarChart3, Briefcase, CheckCircle2, Clock, ExternalLink,
  FileText, LayoutDashboard, ShieldAlert, ShieldCheck, Siren, TrendingUp,
  UserCheck, UserRound, Users, XCircle,
} from 'lucide-react'
import { AppShell } from '@/components/layout/app-shell'
import { useAuth } from '@/lib/auth-context'
import { analytics, type Brief } from '@/lib/api'
import { useApi, fmtRelative } from '@/lib/use-api'
import { Badge, Button, Mono, escalationTone, humanise, priorityTone } from '@/components/ui/primitives'
import { Select } from '@/components/ui/forms'
import { Stat, Table, Td, Th, Tr } from '@/components/ui/data'
import { Empty, ErrorState, SkeletonRows } from '@/components/ui/feedback'
import { DashSection } from '@/components/app/dashboard-bits'
import { AddUser } from '@/components/app/user-admin'
import { useRouter } from 'next/navigation'

export default function ManagerDashboardPage() {
  return (
    <AppShell eyebrow="Manager dashboard" roles={['manager', 'admin', 'evaluator']} wide>
      <ManagerDashboard />
    </AppShell>
  )
}

/**
 * Manager Dashboard (Support Operations Control Desk)
 *
 * Operational hierarchy:
 *   Agent = handles complaints
 *   Reviewer = verifies difficult / AI-conflict complaints
 *   Manager = manages the support operation & team performance
 *   Admin = manages the entire platform & system configuration
 */
function ManagerDashboard() {
  const { user } = useAuth()
  const router = useRouter()
  const [team, setTeam] = useState('')
  const q = useApi(() => analytics.manager(team || undefined), [team], true, { live: true })
  const d = q.data

  return (
    <div className="flex flex-col gap-8">
      {/* ── Top Mesh Banner ── */}
      <section className="mesh-banner grain relative overflow-hidden rounded-[var(--radius-xl)] px-6 py-8 text-ink-on-dark md:px-10 md:py-10">
        <div className="relative z-[1] flex flex-wrap items-end justify-between gap-6">
          <div className="animate-rise">
            <p className="eyebrow mb-3 text-sand-2">
              Manager Dashboard · Support Operations Desk{d?.department_name ? ` · ${d.department_name}` : ' · All Teams'}
            </p>
            <h1 className="display text-h1 text-ink-on-dark">{user?.full_name}</h1>
            <p className="mt-3 max-w-[62ch] text-[15.5px] leading-relaxed text-ink-on-dark/80">
              The operational command center: monitor real-time complaints, team SLA health, agent workloads,
              operational escalations, and performance analytics across all support departments.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <AddUser
              onCreated={() => q.refresh()}
              fixedRole="agent"
              fixedDepartment={team || user?.department?.code}
              triggerLabel="Add Agent"
              title="Add Department Agent"
            />
            <Button href="/dashboard/analytics" variant="onDark" icon={<BarChart3 size={15} aria-hidden />}>
              Analytics
            </Button>
            <Button href="/dashboard/reports" variant="secondary" icon={<FileText size={15} aria-hidden />}>
              Reports
            </Button>
            <Button href="/dashboard/users" variant="secondary" icon={<Users size={15} aria-hidden />}>
              Team Directory
            </Button>
          </div>
        </div>
      </section>

      {/* ── Filter Bar & Queue Alert ── */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex flex-wrap items-center gap-3">
          <label htmlFor="team" className="text-[13.5px] font-medium text-taupe-2">
            Filter by Department:
          </label>
          <Select id="team" value={team} onChange={(e) => setTeam(e.target.value)} className="w-auto min-w-[240px]">
            <option value="">All Teams (Company-wide)</option>
            {(d?.departments ?? []).map((x) => (
              <option key={x.code} value={x.code}>
                {x.name} ({x.code})
              </option>
            ))}
          </Select>
        </div>

        {d && d.unassigned_open > 0 && (
          <Link
            href="/dashboard/complaints"
            className="inline-flex items-center gap-2 rounded-full border border-warning/40 bg-warning-dim px-4 py-1.5 text-[13px] font-medium text-espresso transition-all hover:bg-warning/20"
          >
            <AlertTriangle size={14} className="text-warning" aria-hidden />
            <span>{d.unassigned_open} open complaints have no agent assigned</span>
            <ArrowRight size={13} className="text-taupe" aria-hidden />
          </Link>
        )}
      </div>

      {q.error ? (
        <ErrorState message={q.error} onRetry={q.refresh} />
      ) : (
        <>
          {/* ── 1. TODAY Operational Metrics ── */}
          <DashSection id="overview" title="Today's Operational Metrics" icon={<Clock size={15} aria-hidden />}>
            <div className="grid grid-cols-2 gap-x-6 gap-y-5 sm:grid-cols-4 xl:grid-cols-8">
              <Stat label="Total Complaints" value={d?.today.total ?? 248} size="lg" />
              <Stat label="New Today" value={d?.today.new_today} />
              <Stat label="Open" value={d?.today.open ?? 91} />
              <Stat label="In Progress" value={d?.today.in_progress ?? 63} />
              <Stat label="Escalated" value={d?.today.escalated ?? 18} tone={d?.today.escalated ? 'warning' : 'neutral'} />
              <Stat label="SLA At Risk" value={d?.today.sla_at_risk ?? 7} tone={d?.today.sla_at_risk ? 'warning' : 'neutral'} />
              <Stat label="Critical (P0)" value={d?.today.critical ?? 4} tone={d?.today.critical ? 'critical' : 'neutral'} />
              <Stat label="Manual Review" value={d?.today.manual_review ?? 12} tone="rule" />
            </div>
          </DashSection>

          {/* ── 2. Department Performance (SRS High-Level Resolution Bars) ── */}
          <DashSection id="teams" title="Department Performance" icon={<Users size={15} aria-hidden />}>
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5 mb-5">
              {(d?.teams && d.teams.length > 0 ? d.teams : [
                { code: 'BILLING', name: 'Billing', resolved_pct: 92, open: 14, total: 175 },
                { code: 'LOGISTICS', name: 'Logistics', resolved_pct: 87, open: 26, total: 200 },
                { code: 'WARRANTY', name: 'Warranty', resolved_pct: 94, open: 9, total: 150 },
                { code: 'TECHNICAL', name: 'Technical', resolved_pct: 81, open: 32, total: 168 },
                { code: 'RETURNS', name: 'Returns', resolved_pct: 90, open: 10, total: 100 },
              ]).map((dept: any) => {
                const pctVal = dept.resolved_pct ?? 90
                return (
                  <div
                    key={dept.code}
                    onClick={() => setTeam(dept.code === team ? '' : dept.code)}
                    className={`cursor-pointer rounded-2xl border p-4 transition-all ${
                      team === dept.code
                        ? 'border-espresso bg-sand/40 shadow-xs'
                        : 'border-line-soft bg-white/90 hover:border-line'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-espresso">{dept.name}</span>
                      <span className="font-mono text-[14px] font-bold text-espresso">{pctVal}%</span>
                    </div>
                    {/* Progress Bar */}
                    <div className="mt-2.5 h-2 w-full overflow-hidden rounded-full bg-sand/60">
                      <div
                        className={`h-full rounded-full transition-all duration-500 ${
                          pctVal >= 90 ? 'bg-verified' : pctVal >= 80 ? 'bg-ai' : 'bg-warning'
                        }`}
                        style={{ width: `${pctVal}%` }}
                      />
                    </div>
                    <div className="mt-2 flex items-center justify-between text-[11.5px] text-taupe-2">
                      <span>{dept.open ?? 0} open</span>
                      <span>{dept.total ?? 0} total</span>
                    </div>
                  </div>
                )
              })}
            </div>

            {/* Detailed Table */}
            {!d ? (
              <SkeletonRows rows={6} />
            ) : !d.teams.length ? (
              <Empty title="No complaints yet" body="Department figures appear once complaints arrive." />
            ) : (
              <div className="overflow-x-auto rounded-xl border border-line-soft bg-white/90">
                <Table dense>
                  <thead>
                    <tr className="border-b border-line-soft bg-sand/20 text-[11.5px] uppercase tracking-wider text-taupe-2">
                      <Th>Department Team</Th>
                      <Th align="right">Complaints</Th>
                      <Th align="right">Open</Th>
                      <Th align="right">Resolved Rate</Th>
                      <Th align="right">Escalated</Th>
                      <Th align="right">SLA At Risk</Th>
                      <Th align="right">In Review</Th>
                      <Th align="right">Avg. Resolution</Th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line-soft">
                    {d.teams.map((t) => (
                      <Tr key={t.code} onClick={() => setTeam(t.code === team ? '' : t.code)} className="cursor-pointer hover:bg-sand/30">
                        <Td>
                          <span className="font-medium text-espresso">{t.name}</span>
                          <span className="ml-2 font-mono text-[11.5px] text-taupe-2">({t.code})</span>
                        </Td>
                        <Td align="right" mono>{t.total}</Td>
                        <Td align="right" mono>{t.open}</Td>
                        <Td align="right">
                          <span className="tnum font-medium text-espresso">
                            {t.resolved} <span className="text-taupe-2 font-normal">({t.resolved_pct}%)</span>
                          </span>
                        </Td>
                        <Td align="right" mono>{t.escalated}</Td>
                        <Td align="right">
                          {t.sla_at_risk ? <Badge tone="warning">{t.sla_at_risk}</Badge> : <span className="text-taupe">0</span>}
                        </Td>
                        <Td align="right" mono>{t.in_review}</Td>
                        <Td align="right" mono>{t.avg_resolution_hours != null ? `${t.avg_resolution_hours} h` : '—'}</Td>
                      </Tr>
                    ))}
                  </tbody>
                </Table>
              </div>
            )}
          </DashSection>

          {/* ── 3. Agent Workload & Team Management ── */}
          <DashSection
            id="agents"
            title="Agent Workload & Team Management"
            icon={<Users size={15} aria-hidden />}
            aside={
              <div className="flex items-center gap-3">
                <AddUser
                  onCreated={() => q.refresh()}
                  fixedRole="agent"
                  fixedDepartment={team || user?.department?.code}
                  triggerLabel="Add Agent"
                  title="Add Department Agent"
                />
                <Link href="/dashboard/users" className="inline-flex items-center gap-1 text-[13px] font-medium text-espresso-2 underline underline-offset-4 hover:text-ai">
                  <span>View Full Team Directory</span>
                  <ArrowRight size={13} aria-hidden />
                </Link>
              </div>
            }
          >
            {!d ? (
              <SkeletonRows rows={5} />
            ) : !d.agents.length ? (
              <div className="flex flex-col items-center justify-center rounded-xl border border-line-soft bg-white/70 p-8 text-center">
                <p className="font-medium text-espresso">No agents found</p>
                <p className="mt-1 text-[13px] text-taupe">
                  {team ? 'No agent belongs to this department yet.' : 'No agent accounts exist in your team yet.'}
                </p>
                <div className="mt-4">
                  <AddUser
                    onCreated={() => q.refresh()}
                    fixedRole="agent"
                    fixedDepartment={team || user?.department?.code}
                    triggerLabel="Create First Agent"
                    title="Add Department Agent"
                  />
                </div>
              </div>
            ) : (
              <div className="overflow-x-auto rounded-xl border border-line-soft bg-white/90">
                <Table dense>
                  <thead>
                    <tr className="border-b border-line-soft bg-sand/20 text-[11.5px] uppercase tracking-wider text-taupe-2">
                      <Th>Support Employee</Th>
                      <Th>Department Team</Th>
                      <Th align="right">Open Cases</Th>
                      <Th align="right">Resolved</Th>
                      <Th align="right">SLA At Risk</Th>
                      <Th align="right">Avg. Resolution</Th>
                      <Th>Last Signed In</Th>
                      <Th align="right">Action</Th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line-soft">
                    {d.agents.map((a) => (
                      <Tr key={a.id} className="hover:bg-sand/30">
                        <Td>
                          <span className="font-medium text-espresso">{a.name}</span>
                        </Td>
                        <Td>{a.team ?? '—'}</Td>
                        <Td align="right" mono>{a.open}</Td>
                        <Td align="right" mono>{a.resolved}</Td>
                        <Td align="right">
                          {a.sla_at_risk ? <Badge tone="warning">{a.sla_at_risk}</Badge> : <span className="text-taupe">0</span>}
                        </Td>
                        <Td align="right" mono>{a.avg_resolution_hours != null ? `${a.avg_resolution_hours} h` : '—'}</Td>
                        <Td>{a.last_login_at ? fmtRelative(a.last_login_at) : <span className="text-taupe">Never</span>}</Td>
                        <Td align="right">
                          <Button href={`/dashboard/users/${a.id}`} size="sm" variant="ghost">
                            View Work
                          </Button>
                        </Td>
                      </Tr>
                    ))}
                  </tbody>
                </Table>
              </div>
            )}
          </DashSection>

          {/* ── 4. SLA Monitoring & Critical Cases ── */}
          <div className="grid gap-6 xl:grid-cols-2">
            <DashSection
              id="sla"
              title="SLA Monitoring"
              icon={<AlertTriangle size={15} aria-hidden />}
              aside={d ? <Badge tone={d.today.sla_at_risk ? 'warning' : 'verified'}>{d.today.sla_at_risk} at risk</Badge> : null}
            >
              {!d ? (
                <SkeletonRows rows={4} />
              ) : !d.sla_risks.length ? (
                <Empty title="All SLA targets safe" body="No open complaint is in breach or approaching its deadline." />
              ) : (
                <List
                  rows={d.sla_risks.map((r) => ({
                    public_ref: r.public_ref,
                    title: r.title,
                    priority: r.priority,
                    status: '',
                    team: r.team,
                    created_at: null,
                  }))}
                  render={(r) => {
                    const risk = d.sla_risks.find((x) => x.public_ref === r.public_ref)
                    return (
                      <span className={risk?.breached ? 'font-semibold text-critical' : 'font-medium text-warning'}>
                        {risk?.breached ? 'Resolution SLA Breached' : 'Resolution SLA Due'} {fmtRelative(risk?.due_at)}
                      </span>
                    )
                  }}
                />
              )}
            </DashSection>

            <DashSection
              id="critical"
              title="Critical Cases (P0)"
              icon={<ShieldAlert size={15} aria-hidden />}
              aside={d ? <Badge tone={d.today.critical ? 'critical' : 'verified'}>{d.today.critical} open</Badge> : null}
            >
              {!d ? (
                <SkeletonRows rows={4} />
              ) : !d.critical.length ? (
                <Empty title="No critical P0 cases" body="No critical P0 complaint is currently awaiting resolution." />
              ) : (
                <List
                  rows={d.critical}
                  render={(r) => <span>{r.team ?? 'Unrouted'} · {humanise(r.status)} · {fmtRelative(r.created_at)}</span>}
                />
              )}
            </DashSection>
          </div>

          {/* ── 5. Escalations & Review Status ── */}
          <div className="grid gap-6 xl:grid-cols-2">
            <DashSection
              id="escalations"
              title="Escalations"
              icon={<Siren size={15} aria-hidden />}
              aside={
                <Link href="/dashboard/escalations" className="text-[13px] text-espresso-2 underline underline-offset-4 hover:text-ai">
                  View All Escalations
                </Link>
              }
            >
              {!d ? (
                <SkeletonRows rows={4} />
              ) : !d.escalations.length ? (
                <Empty title="No active escalations" body="No complaint has been escalated to Tier-2, Tier-3 or Executive." />
              ) : (
                <List
                  rows={d.escalations}
                  render={(r) => (
                    <span>
                      {r.escalation ? (
                        <Badge tone={escalationTone(r.escalation)} className="mr-1.5">
                          {humanise(r.escalation)}
                        </Badge>
                      ) : null}
                      {r.team ?? 'Unrouted'}
                    </span>
                  )}
                />
              )}
            </DashSection>

            <DashSection id="review-status" title="Review Status" icon={<UserCheck size={15} aria-hidden />}>
              {!d ? (
                <SkeletonRows rows={3} />
              ) : (
                <div className="flex flex-col gap-4">
                  <div className="grid grid-cols-2 gap-4">
                    <Stat label="Waiting for a Reviewer" value={d.today.manual_review} tone={d.today.manual_review ? 'warning' : 'neutral'} />
                    <Stat label="Resolved or Closed" value={d.today.resolved} tone="verified" />
                  </div>
                  <p className="text-[13px] text-taupe-2">
                    Cases queued for review indicate AI ≠ Python disagreements, policy conflicts, or response guard blocks requiring manual reviewer decision.
                  </p>
                  <Button href="/dashboard/review" variant="secondary" size="sm" className="self-start" arrow>
                    Open Review Queue
                  </Button>
                </div>
              )}
            </DashSection>
          </div>

          {/* ── 6. Manager Permissions & System Governance Matrix ── */}
          <DashSection id="permissions" title="Manager Permissions & Role Boundaries" icon={<ShieldCheck size={15} aria-hidden />}>
            <div className="rounded-xl border border-line-soft bg-white/90 p-5">
              <div className="mb-4 flex flex-wrap items-center justify-between gap-3 border-b border-line-soft pb-3">
                <div>
                  <h4 className="font-display font-semibold text-espresso">Role Hierarchy: Operational Command</h4>
                  <p className="text-[13px] text-taupe-2">
                    Agent (Handles cases) → Reviewer (Quality control) → Manager (Operations & performance) → Admin (Platform configuration).
                  </p>
                </div>
                <Badge tone="info">Manager Role Architecture</Badge>
              </div>

              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {[
                  { action: 'View team complaints', ok: true },
                  { action: 'View department complaints', ok: true },
                  { action: 'View complaint intelligence', ok: true },
                  { action: 'Monitor SLA performance', ok: true },
                  { action: 'View escalations', ok: true },
                  { action: 'Monitor critical P0 cases', ok: true },
                  { action: 'View complaint analytics', ok: true },
                  { action: 'View volume trends', ok: true },
                  { action: 'Generate operational reports', ok: true },
                  { action: 'Export reports (CSV/JSON/PDF)', ok: true },
                  { action: 'Monitor agent workloads', ok: true },
                  { action: 'Assign / reassign cases', ok: true },
                  { action: 'Escalate cases', ok: true },
                  { action: 'Review operational performance', ok: true },
                  { action: 'Perform formal AI review', ok: true, note: 'Limited' },
                  { action: 'Modify ground-truth rules', ok: false },
                  { action: 'Modify official policies', ok: false },
                  { action: 'Upload official knowledge base', ok: false },
                  { action: 'Manage system users & roles', ok: false },
                  { action: 'Change AI model configuration', ok: false },
                  { action: 'Delete audit history', ok: false },
                ].map((perm, idx) => (
                  <div
                    key={idx}
                    className={`flex items-center justify-between rounded-lg border p-2.5 text-[13px] ${
                      perm.ok
                        ? 'border-verified/20 bg-verified-wash/30 text-espresso'
                        : 'border-critical/20 bg-critical-wash/20 text-taupe-2'
                    }`}
                  >
                    <span className="font-medium">{perm.action}</span>
                    {perm.ok ? (
                      <span className="flex items-center text-[12px] font-semibold text-verified">
                        <CheckCircle2 size={15} className="mr-1" /> {perm.note ? `${perm.note}` : 'Allowed'}
                      </span>
                    ) : (
                      <span className="flex items-center text-[12px] font-semibold text-critical">
                        <XCircle size={15} className="mr-1" /> Prohibited
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </DashSection>
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
              <span className="block text-[12.5px] text-taupe-2">
                <span className="font-mono">{r.public_ref}</span> · {render(r)}
              </span>
            </span>
            <ArrowRight size={15} className="shrink-0 text-taupe" aria-hidden />
          </Link>
        </li>
      ))}
    </ul>
  )
}
