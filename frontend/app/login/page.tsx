'use client'
import { useState, useEffect, FormEvent } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import Link from 'next/link'
import { Eye, EyeOff, AlertCircle, Zap, Shield } from 'lucide-react'
import { useAuth } from '@/lib/auth-context'
import { Logo, Spinner } from '@/components/ui'

export default function LoginPage() {
  const { login, user, loading, error } = useAuth()
  const router = useRouter()
  const params = useSearchParams()
  const redirect = params.get('redirect') ?? '/dashboard'

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPw, setShowPw] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [localError, setLocalError] = useState<string | null>(null)

  useEffect(() => {
    if (!loading && user) router.replace(redirect)
  }, [user, loading, redirect, router])

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setLocalError(null)
    if (!email || !password) { setLocalError('Please enter email and password.'); return }
    setSubmitting(true)
    try {
      await login(email, password)
      router.replace(redirect)
    } catch (err: unknown) {
      setLocalError((err as Error).message)
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return (
      <div style={{ display: 'flex', height: '100dvh', alignItems: 'center', justifyContent: 'center' }}>
        <Spinner size={32} />
      </div>
    )
  }

  return (
    <div style={{
      display: 'flex', minHeight: '100dvh', alignItems: 'center', justifyContent: 'center',
      padding: 24, background: 'var(--bg)',
    }}>
      <div className="ambient-bg" />
      <div className="grid-overlay" />

      {/* Glow orb */}
      <div style={{
        position: 'fixed', width: 600, height: 600, borderRadius: '50%',
        background: 'radial-gradient(circle, rgba(255,87,34,0.1) 0%, transparent 70%)',
        top: '50%', left: '50%', transform: 'translate(-50%, -50%)', pointerEvents: 'none',
      }} />

      <div style={{ width: '100%', maxWidth: 420, position: 'relative', zIndex: 1 }}>
        {/* Brand */}
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <Link href="/" style={{ display: 'inline-flex', flexDirection: 'column', alignItems: 'center', gap: 12 }}>
            <Logo size={40} />
            <div style={{ fontSize: 22, fontWeight: 900, fontFamily: 'Manrope, sans-serif', letterSpacing: '-0.03em' }}>
              Support<span style={{ color: 'var(--orange)' }}>Nova</span>
            </div>
          </Link>
          <p style={{ marginTop: 8, fontSize: 13, color: 'var(--text-3)' }}>
            ResponseX Intelligence Platform
          </p>
        </div>

        {/* Card */}
        <div className="card" style={{ padding: '32px 28px', borderColor: 'var(--border-2)' }}>
          <h1 style={{ fontSize: 20, fontWeight: 800, marginBottom: 4, textAlign: 'center' }}>Sign In</h1>
          <p style={{ fontSize: 13, color: 'var(--text-3)', textAlign: 'center', marginBottom: 24 }}>
            Enter your credentials to access your dashboard
          </p>

          {(localError || error) && (
            <div className="alert alert-error" style={{ marginBottom: 20 }}>
              <AlertCircle size={14} />
              {localError ?? error}
            </div>
          )}

          <form onSubmit={handleSubmit} noValidate>
            <div style={{ marginBottom: 16 }}>
              <label className="label" htmlFor="login-email">Email</label>
              <input
                id="login-email"
                type="email"
                className="input"
                placeholder="you@company.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
                required
              />
            </div>

            <div style={{ marginBottom: 24, position: 'relative' }}>
              <label className="label" htmlFor="login-password">Password</label>
              <input
                id="login-password"
                type={showPw ? 'text' : 'password'}
                className="input"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                required
                style={{ paddingRight: 44 }}
              />
              <button
                type="button"
                onClick={() => setShowPw((v) => !v)}
                style={{
                  position: 'absolute', right: 12, bottom: 10, background: 'none', border: 'none',
                  cursor: 'pointer', color: 'var(--text-3)', padding: 0,
                }}
                aria-label={showPw ? 'Hide password' : 'Show password'}
              >
                {showPw ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>

            <button
              id="login-submit"
              type="submit"
              className="btn btn-orange"
              disabled={submitting}
              style={{ width: '100%', justifyContent: 'center' }}
            >
              {submitting ? <><Spinner size={16} color="#fff" /> Signing in…</> : 'Sign In'}
            </button>
          </form>
        </div>

        {/* Dual-engine indicator */}
        <div style={{
          marginTop: 24, display: 'flex', gap: 16, justifyContent: 'center', fontSize: 12,
        }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: 5, color: '#a5b4fc' }}>
            <Zap size={12} /> AI Engine
          </span>
          <span style={{ color: 'var(--border-3)' }}>+</span>
          <span style={{ display: 'flex', alignItems: 'center', gap: 5, color: '#67e8f9' }}>
            <Shield size={12} /> Python Verifier
          </span>
          <span style={{ color: 'var(--border-3)' }}>→</span>
          <span style={{ color: 'var(--text-4)' }}>Always cross-checked</span>
        </div>

        <div style={{ textAlign: 'center', marginTop: 20 }}>
          <Link href="/" style={{ fontSize: 12, color: 'var(--text-4)' }}>← Back to home</Link>
        </div>
      </div>
    </div>
  )
}
