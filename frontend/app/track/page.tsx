'use client'
import { useState, FormEvent } from 'react'
import { ArrowLeft, Search, Clock, CheckCircle, AlertCircle, MessageSquare, Zap, Shield } from 'lucide-react'
import Link from 'next/link'
import { LandingNav, Logo, StatusPill, Spinner } from '@/components/ui'
import { complaints as complaintsApi } from '@/lib/api'
import type { ComplaintStatus } from '@/lib/api'

export default function TrackComplaintPage() {
  const [ref, setRef] = useState('')
  const [result, setResult] = useState<{
    public_ref: string; status: ComplaintStatus; category?: string
    summary?: string; specialist_involved?: boolean; outstanding_questions?: string[]
  } | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSearch = async (e: FormEvent) => {
    e.preventDefault()
    if (!ref.trim()) return
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const data = await complaintsApi.status(ref.trim().toUpperCase())
      setResult(data)
    } catch (err: unknown) {
      setError('Complaint not found or you do not have access to view it.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <>
      <div className="ambient-bg" />
      <div className="grid-overlay" />
      <LandingNav />

      <div style={{
        minHeight: '100dvh', display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: '100px 24px 60px',
      }}>
        <div style={{ width: '100%', maxWidth: 560 }}>
          <div style={{ textAlign: 'center', marginBottom: 36 }}>
            <div className="hero-badge" style={{ display: 'inline-flex', marginBottom: 16 }}>
              <Search size={13} /> Track Your Complaint
            </div>
            <h1 style={{ fontSize: 'clamp(28px, 4vw, 40px)', fontWeight: 900, letterSpacing: '-0.03em', marginBottom: 12 }}>
              Complaint Status
            </h1>
            <p style={{ color: 'var(--text-3)', fontSize: 14 }}>
              Enter your complaint reference number to see the current status.
            </p>
          </div>

          <div className="card" style={{ padding: '28px' }}>
            <form onSubmit={handleSearch}>
              <label className="label" htmlFor="track-ref">Reference Number</label>
              <div style={{ display: 'flex', gap: 10, marginBottom: 8 }}>
                <input
                  id="track-ref"
                  className="input"
                  placeholder="e.g. SN-2024-001234"
                  value={ref}
                  onChange={(e) => setRef(e.target.value)}
                  style={{ flex: 1, letterSpacing: '0.05em', fontFamily: 'DM Mono, monospace' }}
                />
                <button className="btn btn-orange" type="submit" disabled={loading || !ref.trim()}>
                  {loading ? <Spinner size={14} color="#fff" /> : <Search size={14} />}
                  Track
                </button>
              </div>
              <p style={{ fontSize: 12, color: 'var(--text-4)' }}>
                You received this reference when you submitted your complaint.
              </p>
            </form>

            {error && (
              <div className="alert alert-error" style={{ marginTop: 20 }}>
                <AlertCircle size={14} /> {error}
              </div>
            )}

            {result && (
              <div style={{ marginTop: 24, borderTop: '1px solid var(--border)', paddingTop: 24 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                  <div>
                    <p style={{ fontSize: 12, color: 'var(--text-4)', marginBottom: 4 }}>Reference</p>
                    <p style={{ fontFamily: 'DM Mono, monospace', fontWeight: 800, color: 'var(--orange-2)', fontSize: 18 }}>
                      {result.public_ref}
                    </p>
                  </div>
                  <StatusPill status={result.status} />
                </div>

                {result.category && (
                  <div style={{ marginBottom: 12, padding: '8px 12px', background: 'var(--surface-2)', borderRadius: 'var(--r-md)', fontSize: 13, color: 'var(--text-2)' }}>
                    Category: <strong>{result.category}</strong>
                  </div>
                )}

                {result.summary && (
                  <div style={{ marginBottom: 12, padding: '12px 14px', background: 'var(--ai-dim)', border: '1px solid var(--ai-border)', borderRadius: 'var(--r-md)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                      <Zap size={12} color="#a5b4fc" />
                      <span style={{ fontSize: 10, fontWeight: 700, color: '#a5b4fc', textTransform: 'uppercase', letterSpacing: '0.08em' }}>Status Summary</span>
                    </div>
                    <p style={{ fontSize: 13.5, color: 'var(--text-2)', lineHeight: 1.6 }}>{result.summary}</p>
                  </div>
                )}

                {result.specialist_involved && (
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center', padding: '8px 12px', background: 'var(--py-dim)', border: '1px solid var(--py-border)', borderRadius: 'var(--r-md)', marginBottom: 12, fontSize: 13, color: '#67e8f9' }}>
                    <Shield size={13} />
                    A specialist is involved in reviewing your complaint.
                  </div>
                )}

                {result.outstanding_questions && result.outstanding_questions.length > 0 && (
                  <div style={{ background: 'var(--mismatch-dim)', border: '1px solid var(--mismatch-border)', borderRadius: 'var(--r-md)', padding: '12px 14px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
                      <AlertCircle size={12} color="var(--mismatch)" />
                      <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--mismatch)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                        Action Required
                      </span>
                    </div>
                    <ul style={{ paddingLeft: 16, margin: 0 }}>
                      {result.outstanding_questions.map((q, i) => (
                        <li key={i} style={{ fontSize: 13, color: 'var(--text-2)', marginBottom: 4 }}>{q}</li>
                      ))}
                    </ul>
                    <p style={{ fontSize: 12, color: 'var(--text-4)', marginTop: 8 }}>
                      Please log in to respond to these questions.
                    </p>
                  </div>
                )}

                <div style={{ marginTop: 16, display: 'flex', gap: 10 }}>
                  <Link href="/login" className="btn btn-ghost btn-sm">
                    Log in for full details →
                  </Link>
                </div>
              </div>
            )}
          </div>

          <div style={{ textAlign: 'center', marginTop: 24 }}>
            <Link href="/" style={{ fontSize: 12, color: 'var(--text-4)' }}>← Back to home</Link>
          </div>
        </div>
      </div>
    </>
  )
}
