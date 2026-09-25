'use client'
import { useState, useEffect } from 'react'
import { RefreshCw, Download, TrendingUp, TrendingDown, Activity } from 'lucide-react'
import {
  DashboardShell, AuthGuard, StatCard, BarChart, PercentBar,
  Spinner, ErrorState, TrendArrow, Empty,
} from '@/components/ui'
import { analytics } from '@/lib/api'
import type {
  AnalyticsDashboard, VolumeData, CategoryData, DepartmentData, PipelineData, TrendItem,
} from '@/lib/api'

export default function AnalyticsPage() {
  return (
    <AuthGuard allowedRoles={['manager', 'admin', 'evaluator']}>
      <AnalyticsContent />
    </AuthGuard>
  )
}

function AnalyticsContent() {
  const [dash, setDash] = useState<AnalyticsDashboard | null>(null)
  const [volume, setVolume] = useState<VolumeData[]>([])
  const [categories, setCategories] = useState<CategoryData[]>([])
  const [departments, setDepartments] = useState<DepartmentData[]>([])
  const [pipeline, setPipeline] = useState<PipelineData | null>(null)
  const [trends, setTrends] = useState<TrendItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [volumePeriod, setVolumePeriod] = useState('daily')

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const [d, v, c, dep, p, t] = await Promise.all([
        analytics.dashboard(),
        analytics.volume({ period: volumePeriod }),
        analytics.categories(),
        analytics.departments(),
        analytics.pipelines(),
        analytics.trends(),
      ])
      setDash(d)
      setVolume(v)
      setCategories(c)
      setDepartments(dep)
      setPipeline(p)
      setTrends(t)
    } catch (e: unknown) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [volumePeriod])

  return (
    <DashboardShell>
      <div className="page-header">
        <div>
          <h1 className="page-title">Analytics</h1>
          <p className="page-subtitle">Live operational metrics — all figures traced to database records</p>
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          <select
            className="input"
            style={{ width: 'auto', padding: '7px 12px', fontSize: 13 }}
            value={volumePeriod}
            onChange={(e) => setVolumePeriod(e.target.value)}
            id="volume-period"
          >
            <option value="daily">Daily</option>
            <option value="weekly">Weekly</option>
            <option value="monthly">Monthly</option>
          </select>
          <button className="btn btn-ghost btn-sm" onClick={load} disabled={loading}>
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {error && <ErrorState error={error} retry={load} />}

      {loading && (
        <div style={{ display: 'flex', justifyContent: 'center', padding: '80px 0' }}>
          <Spinner size={28} />
        </div>
      )}

      {!loading && !error && dash && (
        <>
          {/* KPI row */}
          <div className="stats-grid">
            <StatCard
              label="Total Complaints"
              value={dash.total_complaints.toLocaleString()}
              icon={<Activity size={18} />}
              sub={`${dash.resolved_count} resolved`}
            />
            <StatCard
              label="Pipeline Agreement"
              value={dash.pipeline_agreement_rate != null ? `${Math.round(dash.pipeline_agreement_rate * 100)}%` : 'Not measured'}
              accent={dash.pipeline_agreement_rate != null ? (dash.pipeline_agreement_rate > 0.85 ? 'var(--verified)' : 'var(--mismatch)') : undefined}
              sub="AI ↔ Python match rate"
            />
            <StatCard
              label="Escalated"
              value={dash.escalated_count.toLocaleString()}
              accent={dash.escalated_count > 0 ? 'var(--critical)' : undefined}
              sub="Critical priority"
            />
            <StatCard
              label="Avg Resolution"
              value={dash.avg_resolution_hours != null ? `${dash.avg_resolution_hours.toFixed(1)}h` : 'Not measured'}
              sub="Across resolved cases"
            />
          </div>

          {/* Volume chart */}
          <div className="card" style={{ padding: '24px', marginBottom: 16 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
              <h3 style={{ fontSize: 15, fontWeight: 700 }}>Volume Over Time</h3>
              <a
                href={analytics.reportExportUrl('volume')}
                className="btn btn-ghost btn-sm"
                target="_blank"
                rel="noreferrer"
              >
                <Download size={13} /> Export
              </a>
            </div>
            {volume.length === 0 ? (
              <Empty title="No volume data" />
            ) : (
              <BarChart
                data={volume.slice(-20).map((v) => ({ label: v.period.slice(-5), value: v.count }))}
                color="var(--orange)"
                height={180}
              />
            )}
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 16 }}>
            {/* Categories */}
            <div className="card" style={{ padding: '20px' }}>
              <h3 style={{ fontSize: 15, fontWeight: 700, marginBottom: 16 }}>By Category</h3>
              {categories.length === 0 ? (
                <Empty title="No category data" />
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                  {categories.slice(0, 8).map((c) => (
                    <div key={c.category}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12.5, marginBottom: 4 }}>
                        <span style={{ color: 'var(--text-2)', fontWeight: 500 }}>{c.category}</span>
                        <span style={{ color: 'var(--text-3)', fontFamily: 'DM Mono, monospace' }}>
                          {c.count} {c.percentage != null ? `· ${c.percentage.toFixed(1)}%` : ''}
                        </span>
                      </div>
                      <PercentBar value={c.percentage} color="var(--ai)" />
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Pipeline per-field */}
            {pipeline && (
              <div className="card" style={{ padding: '20px' }}>
                <h3 style={{ fontSize: 15, fontWeight: 700, marginBottom: 4 }}>Pipeline Agreement by Field</h3>
                <p style={{ fontSize: 12, color: 'var(--text-3)', marginBottom: 16 }}>
                  Total: {pipeline.total} · Agreement: {pipeline.agreement_count} · Mismatch: {pipeline.mismatch_count}
                </p>
                {pipeline.by_field.map((f) => (
                  <div key={f.field} style={{ marginBottom: 10 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12.5, marginBottom: 4 }}>
                      <span style={{ color: 'var(--text-2)', fontWeight: 500, textTransform: 'capitalize' }}>{f.field}</span>
                    </div>
                    <PercentBar
                      value={f.agreement_rate != null ? Math.round(f.agreement_rate * 100) : null}
                      color={f.agreement_rate != null ? (f.agreement_rate > 0.85 ? 'var(--verified)' : f.agreement_rate > 0.7 ? 'var(--mismatch)' : 'var(--critical)') : 'var(--text-4)'}
                    />
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Departments */}
          {departments.length > 0 && (
            <div className="table-wrap" style={{ marginBottom: 16 }}>
              <div style={{ padding: '16px 16px 0' }}>
                <h3 style={{ fontSize: 15, fontWeight: 700 }}>By Department</h3>
              </div>
              <table className="table" style={{ marginTop: 8 }}>
                <thead>
                  <tr>
                    <th>Department</th>
                    <th>Total</th>
                    <th>Resolved</th>
                    <th>Pending</th>
                    <th>Resolution Rate</th>
                  </tr>
                </thead>
                <tbody>
                  {departments.map((d) => {
                    const rate = d.count > 0 ? Math.round((d.resolved / d.count) * 100) : null
                    return (
                      <tr key={d.department}>
                        <td style={{ fontWeight: 600 }}>{d.department}</td>
                        <td style={{ fontFamily: 'DM Mono, monospace', fontSize: 13 }}>{d.count}</td>
                        <td style={{ fontFamily: 'DM Mono, monospace', fontSize: 13, color: 'var(--verified)' }}>{d.resolved}</td>
                        <td style={{ fontFamily: 'DM Mono, monospace', fontSize: 13 }}>{d.pending}</td>
                        <td>
                          <PercentBar value={rate} color="var(--verified)" />
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}

          {/* Trends */}
          {trends.length > 0 && (
            <div className="card" style={{ padding: '20px' }}>
              <h3 style={{ fontSize: 15, fontWeight: 700, marginBottom: 16 }}>Trends</h3>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 12 }}>
                {trends.map((t) => (
                  <div key={t.id} style={{ background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 'var(--r-md)', padding: '14px 16px' }}>
                    <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-4)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 6 }}>
                      {t.metric}
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      {t.direction === 'UP' ? <TrendingUp size={16} color="var(--verified)" /> : t.direction === 'DOWN' ? <TrendingDown size={16} color="var(--critical)" /> : <Activity size={16} color="var(--text-3)" />}
                      <TrendArrow direction={t.direction} pct={t.change_pct} />
                    </div>
                    {t.description && <p style={{ fontSize: 11.5, color: 'var(--text-3)', marginTop: 6 }}>{t.description}</p>}
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </DashboardShell>
  )
}
