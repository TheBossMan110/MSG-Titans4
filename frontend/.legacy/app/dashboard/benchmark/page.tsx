'use client'
import { useState, useEffect } from 'react'
import { RefreshCw, Play, Trash2, Upload, ChevronRight } from 'lucide-react'
import Link from 'next/link'
import {
  DashboardShell, AuthGuard, StatCard, PercentBar, Spinner, ErrorState, Empty, DropZone,
} from '@/components/ui'
import { benchmark } from '@/lib/api'
import type { BenchmarkDataset, BenchmarkRun } from '@/lib/api'

export default function BenchmarkPage() {
  return (
    <AuthGuard allowedRoles={['admin', 'evaluator']}>
      <BenchmarkContent />
    </AuthGuard>
  )
}

function BenchmarkContent() {
  const [datasets, setDatasets] = useState<BenchmarkDataset[]>([])
  const [runs, setRuns] = useState<BenchmarkRun[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [running, setRunning] = useState<string | null>(null)
  const [uploading, setUploading] = useState<string | null>(null)
  const [importTag, setImportTag] = useState('')

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const [d, r] = await Promise.all([benchmark.datasets(), benchmark.runs()])
      setDatasets(d)
      setRuns(r)
    } catch (e: unknown) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  const run = async (tag: string) => {
    setRunning(tag)
    try {
      await benchmark.run(tag)
      await load()
    } catch (e: unknown) {
      alert((e as Error).message)
    } finally {
      setRunning(null)
    }
  }

  const deleteDataset = async (tag: string) => {
    if (!confirm(`Delete dataset "${tag}"? This cannot be undone.`)) return
    try {
      await benchmark.deleteDataset(tag)
      await load()
    } catch (e: unknown) {
      alert((e as Error).message)
    }
  }

  const importFile = async (files: File[]) => {
    if (!importTag.trim()) { alert('Enter a dataset tag first.'); return }
    setUploading(importTag)
    try {
      const res = await benchmark.importDataset(importTag.trim(), files[0])
      alert(`Imported ${res.imported} records (${res.labelled} labelled, ${res.rejected} rejected)`)
      await load()
    } catch (e: unknown) {
      alert((e as Error).message)
    } finally {
      setUploading(null)
    }
  }

  useEffect(() => { load() }, [])

  const latestRun = runs[0]

  return (
    <DashboardShell>
      <div className="page-header">
        <div>
          <h1 className="page-title">Benchmark</h1>
          <p className="page-subtitle">Evaluate pipeline accuracy against labelled datasets</p>
        </div>
        <button className="btn btn-ghost btn-sm" onClick={load} disabled={loading}>
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
        </button>
      </div>

      {latestRun && (
        <div className="stats-grid" style={{ marginBottom: 20 }}>
          <StatCard
            label="Latest Run Accuracy"
            value={latestRun.overall_accuracy != null ? `${(latestRun.overall_accuracy * 100).toFixed(1)}%` : 'Not measured'}
            accent={latestRun.overall_accuracy != null ? (latestRun.overall_accuracy > 0.85 ? 'var(--verified)' : 'var(--mismatch)') : undefined}
            sub={latestRun.dataset_tag}
          />
          <StatCard
            label="Guard Compliance"
            value={latestRun.guard_compliance != null ? `${(latestRun.guard_compliance * 100).toFixed(1)}%` : 'Not measured'}
            sub="Policy guard pass rate"
          />
          <StatCard
            label="Run Status"
            value={latestRun.status}
            accent={latestRun.status === 'COMPLETED' ? 'var(--verified)' : latestRun.status === 'FAILED' ? 'var(--critical)' : 'var(--mismatch)'}
            sub={latestRun.completed_at ? new Date(latestRun.completed_at).toLocaleDateString() : 'Running…'}
          />
        </div>
      )}

      {error && <ErrorState error={error} retry={load} />}

      {loading ? (
        <div style={{ display: 'flex', justifyContent: 'center', padding: '60px 0' }}><Spinner size={28} /></div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          {/* Datasets */}
          <div>
            <h3 style={{ fontSize: 14, fontWeight: 700, marginBottom: 12, color: 'var(--text-2)' }}>Datasets</h3>

            {/* Import */}
            <div className="card" style={{ padding: '18px', marginBottom: 14 }}>
              <h4 style={{ fontSize: 13, fontWeight: 600, marginBottom: 10 }}>Import New Dataset</h4>
              <input
                id="import-tag"
                className="input"
                placeholder="Dataset tag (e.g. v1_labelled)"
                value={importTag}
                onChange={(e) => setImportTag(e.target.value)}
                style={{ marginBottom: 10 }}
              />
              <DropZone
                onFiles={importFile}
                accept=".csv,.json,.jsonl"
                label="Drop CSV/JSON dataset file"
              />
              {uploading && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 10, color: 'var(--text-3)', fontSize: 13 }}>
                  <Spinner size={14} /> Importing…
                </div>
              )}
            </div>

            {datasets.length === 0 ? (
              <Empty title="No datasets" body="Import a labelled dataset to begin benchmarking." />
            ) : (
              datasets.map((d) => (
                <div key={d.tag} className="card" style={{ padding: '16px', marginBottom: 10 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                    <span style={{ fontFamily: 'DM Mono, monospace', fontSize: 13, fontWeight: 700, color: 'var(--orange-2)' }}>{d.tag}</span>
                    <div style={{ display: 'flex', gap: 8 }}>
                      <button
                        className="btn btn-orange btn-sm"
                        onClick={() => run(d.tag)}
                        disabled={!d.scoreable || running === d.tag}
                        title={!d.scoreable ? 'Dataset has no labelled records' : 'Run benchmark'}
                        id={`run-${d.tag}`}
                      >
                        {running === d.tag ? <Spinner size={12} color="#fff" /> : <Play size={12} />}
                        Run
                      </button>
                      <button
                        className="btn btn-ghost btn-sm"
                        onClick={() => deleteDataset(d.tag)}
                        style={{ color: 'var(--critical)' }}
                        id={`delete-${d.tag}`}
                      >
                        <Trash2 size={12} />
                      </button>
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: 12, fontSize: 12, color: 'var(--text-3)' }}>
                    <span>{d.total_count} total</span>
                    <span>{d.labelled_count} labelled</span>
                    <span className={`badge ${d.scoreable ? 'badge-verified' : 'badge-neutral'}`} style={{ fontSize: 10 }}>
                      {d.scoreable ? 'Scoreable' : 'No labels'}
                    </span>
                  </div>
                </div>
              ))
            )}
          </div>

          {/* Runs */}
          <div>
            <h3 style={{ fontSize: 14, fontWeight: 700, marginBottom: 12, color: 'var(--text-2)' }}>Benchmark Runs</h3>
            {runs.length === 0 ? (
              <Empty title="No runs yet" body="Run a benchmark against a dataset to see results here." />
            ) : (
              runs.map((r) => (
                <Link key={r.id} href={`/dashboard/benchmark/${r.id}`} style={{ display: 'block', marginBottom: 10 }}>
                  <div className="card" style={{ padding: '16px', cursor: 'pointer' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                      <span style={{ fontFamily: 'DM Mono, monospace', fontSize: 12, color: 'var(--orange-2)' }}>{r.dataset_tag}</span>
                      <span className={`badge ${r.status === 'COMPLETED' ? 'badge-verified' : r.status === 'FAILED' ? 'badge-critical' : 'badge-mismatch'}`}>
                        {r.status}
                      </span>
                    </div>
                    {r.overall_accuracy != null && (
                      <div style={{ marginBottom: 4 }}>
                        <PercentBar
                          value={Math.round(r.overall_accuracy * 100)}
                          color={r.overall_accuracy > 0.85 ? 'var(--verified)' : 'var(--mismatch)'}
                        />
                      </div>
                    )}
                    {r.overall_accuracy == null && r.status === 'COMPLETED' && (
                      <p style={{ fontSize: 12, color: 'var(--text-4)' }}>Accuracy: Not measured</p>
                    )}
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--text-4)', fontFamily: 'DM Mono, monospace', marginTop: 6 }}>
                      <span>{new Date(r.started_at).toLocaleString()}</span>
                      <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>View details <ChevronRight size={10} /></span>
                    </div>
                  </div>
                </Link>
              ))
            )}
          </div>
        </div>
      )}
    </DashboardShell>
  )
}
