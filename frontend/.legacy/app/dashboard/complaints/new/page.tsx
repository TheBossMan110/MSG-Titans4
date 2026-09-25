'use client'
import { useState, FormEvent } from 'react'
import { useRouter } from 'next/navigation'
import { ArrowLeft, MessageSquare, AlertCircle, CheckCircle } from 'lucide-react'
import Link from 'next/link'
import { DashboardShell, AuthGuard, Spinner } from '@/components/ui'
import { complaints as complaintsApi } from '@/lib/api'

export default function NewComplaintPage() {
  return (
    <AuthGuard>
      <NewComplaintForm />
    </AuthGuard>
  )
}

function NewComplaintForm() {
  const router = useRouter()
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [orderRef, setOrderRef] = useState('')
  const [product, setProduct] = useState('')
  const [amount, setAmount] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<{ ref: string; public_ref: string; validation_findings?: string[] } | null>(null)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!title.trim() || !description.trim()) {
      setError('Title and description are required.')
      return
    }
    setError(null)
    setSubmitting(true)
    try {
      const res = await complaintsApi.create({
        title: title.trim(),
        description: description.trim(),
        order_ref: orderRef.trim() || undefined,
        product: product.trim() || undefined,
        amount: amount ? parseFloat(amount) : undefined,
      })
      setResult(res)
    } catch (e: unknown) {
      setError((e as Error).message)
    } finally {
      setSubmitting(false)
    }
  }

  if (result) {
    return (
      <DashboardShell>
        <div style={{ maxWidth: 560, margin: '40px auto', textAlign: 'center' }}>
          <div style={{ width: 64, height: 64, borderRadius: '50%', background: 'var(--verified-dim)', border: '1px solid var(--verified-border)', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 20px' }}>
            <CheckCircle size={28} color="var(--verified)" />
          </div>
          <h1 style={{ fontSize: 24, fontWeight: 900, marginBottom: 8 }}>Complaint Submitted</h1>
          <p style={{ color: 'var(--text-3)', marginBottom: 20 }}>
            Your complaint is being processed by our dual-engine pipeline.
          </p>
          <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--r-lg)', padding: '20px', marginBottom: 24 }}>
            <p style={{ fontSize: 12, color: 'var(--text-4)', marginBottom: 4 }}>Reference Number</p>
            <p style={{ fontFamily: 'DM Mono, monospace', fontSize: 22, fontWeight: 800, color: 'var(--orange-2)' }}>
              {result.public_ref}
            </p>
          </div>
          {result.validation_findings && result.validation_findings.length > 0 && (
            <div className="alert alert-warning" style={{ marginBottom: 20, textAlign: 'left' }}>
              <AlertCircle size={14} />
              <div>
                <strong>Validation notes:</strong>
                <ul style={{ marginTop: 6, paddingLeft: 16 }}>
                  {result.validation_findings.map((f, i) => <li key={i} style={{ fontSize: 12, marginTop: 4 }}>{f}</li>)}
                </ul>
              </div>
            </div>
          )}
          <div style={{ display: 'flex', gap: 10, justifyContent: 'center' }}>
            <Link href={`/dashboard/complaints/${result.ref}`} className="btn btn-orange">View Complaint</Link>
            <Link href="/dashboard/complaints" className="btn btn-ghost">All Complaints</Link>
          </div>
        </div>
      </DashboardShell>
    )
  }

  return (
    <DashboardShell>
      <div style={{ maxWidth: 660, margin: '0 auto' }}>
        <div style={{ marginBottom: 20 }}>
          <Link href="/dashboard/complaints" className="btn btn-ghost btn-sm">
            <ArrowLeft size={14} /> Back
          </Link>
        </div>

        <div className="page-header">
          <div>
            <h1 className="page-title">Submit New Complaint</h1>
            <p className="page-subtitle">Describe your issue in detail so our AI pipeline can classify it accurately.</p>
          </div>
        </div>

        <div className="card" style={{ padding: '28px' }}>
          {error && (
            <div className="alert alert-error" style={{ marginBottom: 20 }}>
              <AlertCircle size={14} /> {error}
            </div>
          )}

          <form onSubmit={handleSubmit}>
            <div style={{ marginBottom: 18 }}>
              <label className="label" htmlFor="complaint-title">Title <span style={{ color: 'var(--critical)' }}>*</span></label>
              <input
                id="complaint-title"
                className="input"
                placeholder="Brief summary of your issue"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                maxLength={200}
                required
              />
              <p style={{ fontSize: 11, color: 'var(--text-4)', marginTop: 4 }}>{title.length}/200 characters</p>
            </div>

            <div style={{ marginBottom: 18 }}>
              <label className="label" htmlFor="complaint-description">Description <span style={{ color: 'var(--critical)' }}>*</span></label>
              <textarea
                id="complaint-description"
                className="input"
                placeholder="Please provide as much detail as possible about your experience, what happened, and what resolution you expect."
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                style={{ minHeight: 140 }}
                required
              />
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 18 }}>
              <div>
                <label className="label" htmlFor="complaint-order">Order Reference (optional)</label>
                <input
                  id="complaint-order"
                  className="input"
                  placeholder="ORD-12345"
                  value={orderRef}
                  onChange={(e) => setOrderRef(e.target.value)}
                />
              </div>
              <div>
                <label className="label" htmlFor="complaint-product">Product (optional)</label>
                <input
                  id="complaint-product"
                  className="input"
                  placeholder="Product name"
                  value={product}
                  onChange={(e) => setProduct(e.target.value)}
                />
              </div>
            </div>

            <div style={{ marginBottom: 28 }}>
              <label className="label" htmlFor="complaint-amount">Amount Disputed (£, optional)</label>
              <input
                id="complaint-amount"
                className="input"
                type="number"
                min="0"
                step="0.01"
                placeholder="0.00"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                style={{ maxWidth: 180 }}
              />
            </div>

            {/* What happens next */}
            <div style={{ background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 'var(--r-md)', padding: '14px 16px', marginBottom: 24 }}>
              <p style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-3)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.05em' }}>What happens next</p>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {[
                  { color: '#6366F1', text: 'AI Engine analyses your complaint' },
                  { color: '#06B6D4', text: 'Python Verifier cross-checks the classification' },
                  { color: '#22C55E', text: 'Matched outcome is routed to the right team' },
                  { color: '#F59E0B', text: 'Discrepancies go to human reviewer for resolution' },
                ].map((s) => (
                  <div key={s.text} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12.5, color: 'var(--text-2)' }}>
                    <span style={{ width: 7, height: 7, borderRadius: '50%', background: s.color, flexShrink: 0 }} />
                    {s.text}
                  </div>
                ))}
              </div>
            </div>

            <button
              id="submit-complaint"
              type="submit"
              className="btn btn-orange"
              disabled={submitting}
              style={{ width: '100%', justifyContent: 'center' }}
            >
              {submitting ? <><Spinner size={16} color="#fff" /> Submitting…</> : <><MessageSquare size={16} /> Submit Complaint</>}
            </button>
          </form>
        </div>
      </div>
    </DashboardShell>
  )
}
