'use client'
import { useState, useEffect } from 'react'
import Link from 'next/link'
import { RefreshCw, Download, BarChart3 } from 'lucide-react'
import { DashboardShell, AuthGuard, Spinner, ErrorState, Empty } from '@/components/ui'
import { analytics } from '@/lib/api'
import type { Report, ExportRecord } from '@/lib/api'

export default function ReportsPage() {
  return (
    <AuthGuard allowedRoles={['manager', 'admin', 'evaluator']}>
      <ReportsContent />
    </AuthGuard>
  )
}

function ReportsContent() {
  const [reports, setReports] = useState<Report[]>([])
  const [exports, setExports] = useState<ExportRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [previewType, setPreviewType] = useState<string | null>(null)
  const [previewData, setPreviewData] = useState<unknown[] | null>(null)
  const [previewing, setPreviewing] = useState(false)

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const [r, e] = await Promise.all([analytics.reports(), analytics.exports()])
      setReports(r)
      setExports(e)
    } catch (e: unknown) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  const preview = async (type: string) => {
    setPreviewType(type)
    setPreviewing(true)
    try {
      const data = await analytics.report(type)
      setPreviewData(data.data)
    } catch (e: unknown) {
      setError((e as Error).message)
    } finally {
      setPreviewing(false)
    }
  }

  useEffect(() => { load() }, [])

  return (
    <DashboardShell>
      <div className="page-header">
        <div>
          <h1 className="page-title">Reports</h1>
          <p className="page-subtitle">Export and preview operational data reports</p>
        </div>
        <button className="btn btn-ghost btn-sm" onClick={load} disabled={loading}>
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
        </button>
      </div>

      {error && <ErrorState error={error} retry={load} />}

      {loading ? (
        <div style={{ display: 'flex', justifyContent: 'center', padding: '60px 0' }}><Spinner size={28} /></div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          {/* Available reports */}
          <div>
            <h3 style={{ fontSize: 14, fontWeight: 700, marginBottom: 12 }}>Available Reports</h3>
            {reports.length === 0 ? (
              <Empty icon={<BarChart3 size={36} />} title="No reports available" />
            ) : (
              reports.map((r) => (
                <div key={r.type} className="card" style={{ padding: '16px', marginBottom: 10 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 6 }}>
                    <div>
                      <h4 style={{ fontSize: 14, fontWeight: 700 }}>{r.label}</h4>
                      {r.description && <p style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 2 }}>{r.description}</p>}
                      <p style={{ fontSize: 11, color: 'var(--text-4)', marginTop: 4, fontFamily: 'DM Mono, monospace' }}>
                        {r.row_count.toLocaleString()} records
                      </p>
                    </div>
                    <div style={{ display: 'flex', gap: 8, flexShrink: 0 }}>
                      <button
                        className="btn btn-ghost btn-sm"
                        onClick={() => preview(r.type)}
                        disabled={previewing && previewType === r.type}
                        id={`preview-${r.type}`}
                      >
                        {previewing && previewType === r.type ? <Spinner size={12} /> : <BarChart3 size={12} />}
                        Preview
                      </button>
                      <a
                        href={analytics.reportExportUrl(r.type)}
                        className="btn btn-orange btn-sm"
                        target="_blank"
                        rel="noreferrer"
                        id={`export-${r.type}`}
                      >
                        <Download size={12} /> Export
                      </a>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>

          {/* Preview panel or exports */}
          <div>
            {previewData ? (
              <>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                  <h3 style={{ fontSize: 14, fontWeight: 700 }}>Preview: {previewType}</h3>
                  <button className="btn btn-ghost btn-sm" onClick={() => { setPreviewData(null); setPreviewType(null) }}>
                    ✕ Close
                  </button>
                </div>
                <div className="table-wrap">
                  {previewData.length === 0 ? (
                    <Empty title="No rows" body="This report has no data." />
                  ) : (
                    <table className="table">
                      <thead>
                        <tr>
                          {Object.keys(previewData[0] as object).slice(0, 6).map((k) => (
                            <th key={k} style={{ textTransform: 'none' }}>{k}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {(previewData as Record<string, unknown>[]).slice(0, 20).map((row, i) => (
                          <tr key={i}>
                            {Object.values(row).slice(0, 6).map((v, j) => (
                              <td key={j} style={{ fontSize: 12, fontFamily: 'DM Mono, monospace' }}>
                                {v == null ? '—' : String(v)}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                  {previewData.length > 20 && (
                    <p style={{ padding: '10px 16px', fontSize: 12, color: 'var(--text-4)' }}>
                      Showing 20 of {previewData.length} rows. Export CSV for full data.
                    </p>
                  )}
                </div>
              </>
            ) : (
              <>
                <h3 style={{ fontSize: 14, fontWeight: 700, marginBottom: 12 }}>Export History</h3>
                {exports.length === 0 ? (
                  <Empty title="No exports yet" body="Export a report to see the download history here." />
                ) : (
                  exports.map((e) => (
                    <div key={e.id} className="card" style={{ padding: '12px 16px', marginBottom: 8 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
                        <div>
                          <span style={{ fontWeight: 600 }}>{e.type}</span>
                          <span style={{ marginLeft: 8, fontSize: 11, color: 'var(--text-4)', fontFamily: 'DM Mono, monospace' }}>.{e.format}</span>
                        </div>
                        {e.file_size_bytes != null && (
                          <span style={{ fontSize: 11, color: 'var(--text-4)' }}>
                            {(e.file_size_bytes / 1024).toFixed(1)} KB
                          </span>
                        )}
                      </div>
                      <div style={{ fontSize: 11, color: 'var(--text-4)', marginTop: 4 }}>
                        {e.requested_by} · {new Date(e.requested_at).toLocaleString()}
                      </div>
                    </div>
                  ))
                )}
              </>
            )}
          </div>
        </div>
      )}
    </DashboardShell>
  )
}
