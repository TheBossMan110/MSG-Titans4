'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { AlertCircle, CheckCircle, Eye, EyeOff } from 'lucide-react'
import { DashboardShell, AuthGuard, Spinner } from '@/components/ui'
import { auth } from '@/lib/api'
import { useAuth } from '@/lib/auth-context'

export default function SettingsPage() {
  return (
    <AuthGuard>
      <SettingsContent />
    </AuthGuard>
  )
}

function SettingsContent() {
  const { user, logout } = useAuth()
  const router = useRouter()
  const [current, setCurrent] = useState('')
  const [newPw, setNewPw] = useState('')
  const [confirm, setConfirm] = useState('')
  const [showPw, setShowPw] = useState(false)
  const [saving, setSaving] = useState(false)
  const [success, setSuccess] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setSuccess(false)
    if (!current || !newPw || !confirm) { setError('All fields are required.'); return }
    if (newPw !== confirm) { setError('New passwords do not match.'); return }
    if (newPw.length < 8) { setError('Password must be at least 8 characters.'); return }
    setSaving(true)
    try {
      await auth.changePassword(current, newPw)
      setSuccess(true)
      setCurrent(''); setNewPw(''); setConfirm('')
    } catch (e: unknown) {
      setError((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  const handleLogout = async () => {
    await logout()
    router.push('/login')
  }

  return (
    <DashboardShell>
      <h1 className="page-title" style={{ marginBottom: 24 }}>Settings</h1>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, maxWidth: 900 }}>
        {/* Profile info */}
        <div className="card" style={{ padding: '24px' }}>
          <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 16 }}>Your Profile</h2>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div style={{ padding: '10px 14px', background: 'var(--surface-2)', borderRadius: 'var(--r-md)', border: '1px solid var(--border)' }}>
              <p style={{ fontSize: 11, color: 'var(--text-4)', marginBottom: 2 }}>EMAIL</p>
              <p style={{ fontSize: 14, fontWeight: 500 }}>{user?.email}</p>
            </div>
            <div style={{ padding: '10px 14px', background: 'var(--surface-2)', borderRadius: 'var(--r-md)', border: '1px solid var(--border)' }}>
              <p style={{ fontSize: 11, color: 'var(--text-4)', marginBottom: 2 }}>ROLE</p>
              <p style={{ fontSize: 14, fontWeight: 500, textTransform: 'capitalize', color: 'var(--orange-2)' }}>{user?.role}</p>
            </div>
            {user?.department && (
              <div style={{ padding: '10px 14px', background: 'var(--surface-2)', borderRadius: 'var(--r-md)', border: '1px solid var(--border)' }}>
                <p style={{ fontSize: 11, color: 'var(--text-4)', marginBottom: 2 }}>DEPARTMENT</p>
                <p style={{ fontSize: 14, fontWeight: 500 }}>{user.department}</p>
              </div>
            )}
          </div>

          <div style={{ borderTop: '1px solid var(--border)', marginTop: 24, paddingTop: 20 }}>
            <button className="btn btn-ghost btn-sm" onClick={handleLogout} style={{ color: 'var(--critical)', borderColor: 'var(--critical-border)' }}>
              Sign Out of All Sessions
            </button>
          </div>
        </div>

        {/* Change password */}
        <div className="card" style={{ padding: '24px' }}>
          <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 16 }}>Change Password</h2>

          {success && (
            <div className="alert alert-success" style={{ marginBottom: 16 }}>
              <CheckCircle size={14} /> Password updated successfully.
            </div>
          )}
          {error && (
            <div className="alert alert-error" style={{ marginBottom: 16 }}>
              <AlertCircle size={14} /> {error}
            </div>
          )}

          <form onSubmit={handleChangePassword}>
            {[
              { id: 'current-password', label: 'Current Password', value: current, setter: setCurrent },
              { id: 'new-password', label: 'New Password', value: newPw, setter: setNewPw },
              { id: 'confirm-password', label: 'Confirm New Password', value: confirm, setter: setConfirm },
            ].map((f) => (
              <div key={f.id} style={{ marginBottom: 14, position: 'relative' }}>
                <label className="label" htmlFor={f.id}>{f.label}</label>
                <input
                  id={f.id}
                  type={showPw ? 'text' : 'password'}
                  className="input"
                  value={f.value}
                  onChange={(e) => f.setter(e.target.value)}
                  required
                />
              </div>
            ))}

            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 20 }}>
              <input
                type="checkbox"
                id="show-passwords"
                checked={showPw}
                onChange={(e) => setShowPw(e.target.checked)}
                style={{ accentColor: 'var(--orange)' }}
              />
              <label htmlFor="show-passwords" style={{ fontSize: 13, color: 'var(--text-3)', cursor: 'pointer' }}>
                Show passwords
              </label>
            </div>

            <button
              id="save-password"
              type="submit"
              className="btn btn-orange"
              disabled={saving}
              style={{ width: '100%', justifyContent: 'center' }}
            >
              {saving ? <><Spinner size={14} color="#fff" /> Saving…</> : 'Update Password'}
            </button>
          </form>
        </div>
      </div>

      {/* System info */}
      <div className="card" style={{ padding: '20px', maxWidth: 900, marginTop: 16 }}>
        <h2 style={{ fontSize: 15, fontWeight: 700, marginBottom: 12 }}>System Architecture</h2>
        <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
          {[
            { color: '#6366F1', label: 'Engine 1: AI — Generative Reasoning', desc: 'Natural language classification, sentiment, entity extraction' },
            { color: '#06B6D4', label: 'Engine 2: Python — Deterministic Verifier', desc: 'Rule-matrix, business policy, SLA enforcement, ground-truth' },
          ].map((e) => (
            <div key={e.label} style={{ flex: 1, minWidth: 240, padding: '14px 16px', background: 'var(--surface-2)', border: `1px solid ${e.color}30`, borderRadius: 'var(--r-md)', borderLeft: `3px solid ${e.color}` }}>
              <p style={{ fontSize: 13, fontWeight: 700, color: e.color, marginBottom: 4 }}>{e.label}</p>
              <p style={{ fontSize: 12, color: 'var(--text-3)' }}>{e.desc}</p>
            </div>
          ))}
        </div>
        <p style={{ fontSize: 12, color: 'var(--text-4)', marginTop: 12 }}>
          SUPABASE_SERVICE_ROLE_KEY is never transmitted to or exposed in the frontend.
        </p>
      </div>
    </DashboardShell>
  )
}
