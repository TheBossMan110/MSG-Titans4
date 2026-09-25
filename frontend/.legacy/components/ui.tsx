'use client'
import React, { useState, useEffect, useCallback, useRef } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useAuth } from '@/lib/auth-context'
import {
  LayoutDashboard, MessageSquare, CheckSquare, BarChart3, Book,
  FlaskConical, Settings, LogOut, ChevronDown, Menu, X, Bell,
  Zap, Shield, Activity, AlertTriangle, TrendingUp, Users, Search,
  RefreshCw, Download, Upload, Eye, Play, ChevronRight,
  CheckCircle, XCircle, Clock, AlertCircle,
} from 'lucide-react'

// ─── Logo ───────────────────────────────────────────────────────────────────────
export function Logo({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" aria-hidden>
      <rect width="32" height="32" rx="8" fill="url(#logo-grad)" />
      <path d="M8 22L14 10l5 8 3-5 5 9" stroke="white" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
      <defs>
        <linearGradient id="logo-grad" x1="0" y1="0" x2="32" y2="32">
          <stop offset="0%" stopColor="#FF5722" />
          <stop offset="100%" stopColor="#FF8A50" />
        </linearGradient>
      </defs>
    </svg>
  )
}

// ─── Status pill ─────────────────────────────────────────────────────────────────
const STATUS_MAP: Record<string, string> = {
  SUBMITTED: 'pill-submitted', ANALYZING: 'pill-analyzing', ANALYZED: 'pill-analyzed',
  FAILED: 'pill-failed', ASSIGNED: 'pill-assigned', IN_PROGRESS: 'pill-in_progress',
  AWAITING_CUSTOMER: 'pill-awaiting_customer', RESOLVED: 'pill-resolved',
  CLOSED: 'pill-closed', ESCALATED: 'pill-escalated', REOPENED: 'pill-reopened',
  IN_REVIEW: 'pill-in_review',
}

export function StatusPill({ status }: { status: string }) {
  const cls = STATUS_MAP[status] ?? 'pill-submitted'
  const icon =
    status === 'RESOLVED' ? <CheckCircle size={10} /> :
    status === 'FAILED' || status === 'ESCALATED' ? <AlertCircle size={10} /> :
    status === 'ANALYZING' ? <Activity size={10} /> :
    <Clock size={10} />
  return (
    <span className={`pill ${cls}`}>
      {icon}
      {status.replace(/_/g, ' ')}
    </span>
  )
}

// ─── Priority badge ───────────────────────────────────────────────────────────────
export function PriorityBadge({ priority }: { priority: string }) {
  const cls = `badge badge-${priority.toLowerCase()}`
  return <span className={cls}>{priority}</span>
}

// ─── Verification outcome badge ───────────────────────────────────────────────────
export function VerificationBadge({ outcome }: { outcome?: string | null }) {
  if (!outcome) return <span className="badge badge-neutral">—</span>
  if (outcome === 'VERIFIED') return <span className="badge badge-verified"><CheckCircle size={10} /> VERIFIED</span>
  if (outcome === 'MISMATCH') return <span className="badge badge-mismatch"><AlertTriangle size={10} /> MISMATCH</span>
  if (outcome === 'CRITICAL') return <span className="badge badge-critical"><AlertCircle size={10} /> CRITICAL</span>
  return <span className="badge badge-neutral">{outcome}</span>
}

// ─── Confidence display (never hard-coded; null = "Not measured") ─────────────────
export function Confidence({ value }: { value?: number | null }) {
  if (value == null) return <span style={{ color: 'var(--text-4)', fontSize: 12 }}>Not measured</span>
  const pct = Math.round(value * 100)
  const color = pct >= 80 ? 'var(--verified)' : pct >= 60 ? 'var(--mismatch)' : 'var(--critical)'
  return (
    <span style={{ color, fontSize: 13, fontWeight: 700, fontFamily: 'DM Mono, monospace' }}>
      {pct}%
    </span>
  )
}

// ─── Loading spinner ───────────────────────────────────────────────────────────────
export function Spinner({ size = 20, color = 'var(--orange)' }: { size?: number; color?: string }) {
  return (
    <svg className="animate-spin" width={size} height={size} viewBox="0 0 24 24" fill="none" aria-label="Loading">
      <circle cx="12" cy="12" r="10" stroke={color} strokeOpacity="0.25" strokeWidth="3" />
      <path d="M12 2 a10 10 0 0 1 10 10" stroke={color} strokeWidth="3" strokeLinecap="round" />
    </svg>
  )
}

// ─── Empty state ─────────────────────────────────────────────────────────────────
export function Empty({ icon, title, body, action }: {
  icon?: React.ReactNode; title: string; body?: string
  action?: { label: string; onClick: () => void }
}) {
  return (
    <div className="empty">
      {icon ?? <Activity size={40} />}
      <div>
        <p style={{ fontWeight: 700, fontSize: 15, color: 'var(--text-2)', marginBottom: 4 }}>{title}</p>
        {body && <p style={{ fontSize: 13 }}>{body}</p>}
      </div>
      {action && (
        <button className="btn btn-ghost btn-sm" onClick={action.onClick}>{action.label}</button>
      )}
    </div>
  )
}

// ─── Error state ─────────────────────────────────────────────────────────────────
export function ErrorState({ error, retry }: { error: string; retry?: () => void }) {
  return (
    <div className="alert alert-error" style={{ borderRadius: 'var(--r-lg)', gap: 12, flexDirection: 'column', alignItems: 'flex-start' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <AlertCircle size={16} />
        <strong>Error</strong>
      </div>
      <p style={{ fontSize: 13, opacity: 0.85 }}>{error}</p>
      {retry && <button className="btn btn-ghost btn-sm" onClick={retry}><RefreshCw size={12} /> Retry</button>}
    </div>
  )
}

// ─── Skeleton rows ─────────────────────────────────────────────────────────────────
export function SkeletonRows({ rows = 6, cols = 5 }: { rows?: number; cols?: number }) {
  return (
    <>
      {Array.from({ length: rows }).map((_, r) => (
        <tr key={r}>
          {Array.from({ length: cols }).map((_, c) => (
            <td key={c} style={{ padding: '13px 16px' }}>
              <div className="skeleton" style={{ height: 14, width: c === 0 ? '80%' : '60%' }} />
            </td>
          ))}
        </tr>
      ))}
    </>
  )
}

// ─── Architecture Key ─────────────────────────────────────────────────────────────
export function ArchKey() {
  const items = [
    { color: '#6366F1', label: 'AI Engine' },
    { color: '#06B6D4', label: 'Python Verifier' },
    { color: '#22C55E', label: 'Verified' },
    { color: '#F59E0B', label: 'Mismatch' },
    { color: '#EF4444', label: 'Critical' },
  ]
  return (
    <div className="arch-key">
      {items.map((item) => (
        <span key={item.label} className="arch-key-item">
          <span className="arch-key-swatch" style={{ background: item.color }} />
          {item.label}
        </span>
      ))}
    </div>
  )
}

// ─── Two-Engine Compare Panel ────────────────────────────────────────────────────
interface EngineField {
  label: string
  ai?: string | number | boolean | null
  python?: string | number | boolean | null
}

export function TwoEnginePanel({ fields }: { fields: EngineField[] }) {
  return (
    <div className="pipeline-split">
      <div className="engine-block engine-block-ai">
        <div className="engine-label engine-label-ai">
          <Zap size={12} /> AI Engine
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {fields.map((f) => (
            <div key={f.label} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
              <span style={{ color: 'var(--text-3)' }}>{f.label}</span>
              <span style={{ color: 'var(--text)', fontWeight: 600, fontFamily: 'DM Mono, monospace', fontSize: 12 }}>
                {f.ai == null ? <span style={{ color: 'var(--text-4)' }}>—</span> : String(f.ai)}
              </span>
            </div>
          ))}
        </div>
      </div>
      <div className="engine-block engine-block-py">
        <div className="engine-label engine-label-py">
          <Shield size={12} /> Python Verifier
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {fields.map((f) => (
            <div key={f.label} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
              <span style={{ color: 'var(--text-3)' }}>{f.label}</span>
              <span style={{ color: 'var(--text)', fontWeight: 600, fontFamily: 'DM Mono, monospace', fontSize: 12 }}>
                {f.python == null ? <span style={{ color: 'var(--text-4)' }}>—</span> : String(f.python)}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// ─── Sidebar nav config ────────────────────────────────────────────────────────────
type NavItem = { href: string; label: string; icon: React.ReactNode; roles?: string[] }

const NAV: { section: string; items: NavItem[] }[] = [
  {
    section: 'Overview',
    items: [
      { href: '/dashboard', label: 'Dashboard', icon: <LayoutDashboard size={16} /> },
    ],
  },
  {
    section: 'Complaints',
    items: [
      { href: '/dashboard/complaints', label: 'All Complaints', icon: <MessageSquare size={16} /> },
      { href: '/dashboard/my-complaints', label: 'My Complaints', icon: <CheckSquare size={16} />, roles: ['customer'] },
    ],
  },
  {
    section: 'Operations',
    items: [
      { href: '/dashboard/review', label: 'Review Queue', icon: <Eye size={16} />, roles: ['reviewer', 'manager', 'admin'] },
      { href: '/dashboard/validation', label: 'Validation', icon: <Shield size={16} />, roles: ['reviewer', 'manager', 'admin', 'evaluator'] },
      { href: '/dashboard/analytics', label: 'Analytics', icon: <BarChart3 size={16} />, roles: ['manager', 'admin', 'evaluator'] },
      { href: '/dashboard/reports', label: 'Reports', icon: <Download size={16} />, roles: ['manager', 'admin', 'evaluator'] },
    ],
  },
  {
    section: 'Knowledge',
    items: [
      { href: '/dashboard/knowledge-base', label: 'Knowledge Base', icon: <Book size={16} />, roles: ['manager', 'admin', 'evaluator'] },
      { href: '/dashboard/benchmark', label: 'Benchmark', icon: <FlaskConical size={16} />, roles: ['admin', 'evaluator'] },
    ],
  },
  {
    section: 'System',
    items: [
      { href: '/dashboard/settings', label: 'Settings', icon: <Settings size={16} /> },
    ],
  },
]

// ─── Dashboard Shell ─────────────────────────────────────────────────────────────
export function DashboardShell({ children }: { children: React.ReactNode }) {
  const { user, logout } = useAuth()
  const pathname = usePathname()
  const [sidebarOpen, setSidebarOpen] = useState(false)

  const filteredNav = NAV.map((section) => ({
    ...section,
    items: section.items.filter((item) =>
      !item.roles || !user || item.roles.includes(user.role)
    ),
  })).filter((s) => s.items.length > 0)

  return (
    <div className="shell">
      {/* Top nav */}
      <nav className="nav">
        <button
          className="btn btn-ghost btn-sm"
          style={{ marginRight: 16, padding: '6px 8px' }}
          onClick={() => setSidebarOpen((v) => !v)}
          aria-label="Toggle sidebar"
        >
          {sidebarOpen ? <X size={18} /> : <Menu size={18} />}
        </button>

        <Link href="/dashboard" className="nav-brand" style={{ marginRight: 'auto' }}>
          <Logo size={26} />
          Support<span>Nova</span>
        </Link>

        {/* System status */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginRight: 20 }}>
          <span className="dot dot-verified dot-pulse" />
          <span style={{ fontSize: 12, color: 'var(--text-3)' }}>Systems Nominal</span>
        </div>

        {/* User menu */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{ textAlign: 'right', display: 'grid', lineHeight: 1.3 }}>
            <span style={{ fontSize: 13, fontWeight: 600 }}>{user?.display_name ?? user?.email}</span>
            <span style={{ fontSize: 11, color: 'var(--orange-2)', textTransform: 'capitalize' }}>{user?.role}</span>
          </div>
          <button
            className="btn btn-ghost btn-sm"
            onClick={logout}
            title="Sign out"
            style={{ padding: '6px 10px' }}
          >
            <LogOut size={15} />
          </button>
        </div>
      </nav>

      {/* Sidebar */}
      <aside className={`sidebar ${sidebarOpen ? 'open' : ''}`}>
        {filteredNav.map((section) => (
          <div key={section.section}>
            <div className="sidebar-label">{section.section}</div>
            {section.items.map((item) => {
              const active = pathname === item.href || (item.href !== '/dashboard' && pathname.startsWith(item.href))
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`sidebar-item ${active ? 'active' : ''}`}
                  onClick={() => setSidebarOpen(false)}
                >
                  {item.icon}
                  {item.label}
                </Link>
              )
            })}
          </div>
        ))}

        {/* Architecture key at bottom */}
        <div style={{ marginTop: 'auto', paddingTop: 16 }}>
          <div style={{ padding: '10px 8px', borderTop: '1px solid var(--border)' }}>
            <div className="sidebar-label" style={{ padding: '0 0 8px' }}>Dual-Engine</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
              {[
                { color: '#6366F1', label: 'AI Engine' },
                { color: '#06B6D4', label: 'Python Verifier' },
                { color: '#22C55E', label: 'Verified' },
                { color: '#F59E0B', label: 'Mismatch' },
                { color: '#EF4444', label: 'Critical' },
              ].map((item) => (
                <div key={item.label} style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 11, color: 'var(--text-4)' }}>
                  <span style={{ width: 8, height: 8, borderRadius: 2, background: item.color, flexShrink: 0 }} />
                  {item.label}
                </div>
              ))}
            </div>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <main className="main">
        {children}
      </main>
    </div>
  )
}

// ─── Stat card ────────────────────────────────────────────────────────────────────
export function StatCard({
  label, value, sub, accent, icon,
}: {
  label: string; value: React.ReactNode; sub?: React.ReactNode
  accent?: string; icon?: React.ReactNode
}) {
  return (
    <div className="stat-card" style={accent ? { borderColor: accent + '44', background: `${accent}08` } : undefined}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 10 }}>
        <div className="stat-label">{label}</div>
        {icon && <span style={{ color: accent ?? 'var(--text-4)', opacity: 0.7 }}>{icon}</span>}
      </div>
      <div className="stat-value" style={accent ? { color: accent } : undefined}>{value}</div>
      {sub && <div className="stat-sub">{sub}</div>}
    </div>
  )
}

// ─── Percent bar ──────────────────────────────────────────────────────────────────
export function PercentBar({ value, color = 'var(--orange)' }: { value: number | null; color?: string }) {
  if (value == null) return <span style={{ fontSize: 12, color: 'var(--text-4)' }}>Not measured</span>
  const pct = Math.max(0, Math.min(100, value))
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <div style={{ flex: 1, height: 6, background: 'var(--surface-3)', borderRadius: 99 }}>
        <div style={{ width: `${pct}%`, height: '100%', background: color, borderRadius: 99, transition: 'width 1s ease' }} />
      </div>
      <span style={{ fontSize: 12, fontFamily: 'DM Mono, monospace', fontWeight: 600, color }}>{pct}%</span>
    </div>
  )
}

// ─── Search bar ──────────────────────────────────────────────────────────────────
export function SearchBar({
  value, onChange, placeholder = 'Search…',
}: {
  value: string; onChange: (v: string) => void; placeholder?: string
}) {
  return (
    <div style={{ position: 'relative', flex: 1 }}>
      <Search size={15} style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-3)', pointerEvents: 'none' }} />
      <input
        className="input"
        style={{ paddingLeft: 36 }}
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        type="search"
        id="search-bar"
      />
    </div>
  )
}

// ─── Pagination ─────────────────────────────────────────────────────────────────
export function Pagination({
  page, pages, onPage,
}: {
  page: number; pages: number; onPage: (p: number) => void
}) {
  if (pages <= 1) return null
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, justifyContent: 'flex-end', padding: '12px 16px', borderTop: '1px solid var(--border)' }}>
      <button className="btn btn-ghost btn-sm" disabled={page <= 1} onClick={() => onPage(page - 1)}>← Prev</button>
      <span style={{ fontSize: 12, color: 'var(--text-3)', fontFamily: 'DM Mono, monospace' }}>
        {page} / {pages}
      </span>
      <button className="btn btn-ghost btn-sm" disabled={page >= pages} onClick={() => onPage(page + 1)}>Next →</button>
    </div>
  )
}

// ─── Filter select ─────────────────────────────────────────────────────────────
export function FilterSelect({
  label, value, onChange, options, id,
}: {
  label: string; value: string; onChange: (v: string) => void
  options: { value: string; label: string }[]; id: string
}) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <span style={{ fontSize: 12, color: 'var(--text-3)', whiteSpace: 'nowrap' }}>{label}</span>
      <select
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="input"
        style={{ width: 'auto', padding: '7px 12px', fontSize: 13 }}
      >
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </div>
  )
}

// ─── Checklist step ────────────────────────────────────────────────────────────
export function ChecklistItem({
  step, onConfirm, disabled,
}: {
  step: { step_id: string; title: string; description?: string; type: string; confirmed: boolean; confirmed_by?: string; confirmed_at?: string }
  onConfirm: (id: string) => void; disabled?: boolean
}) {
  return (
    <div style={{
      display: 'flex', alignItems: 'flex-start', gap: 12, padding: '12px 16px',
      borderBottom: '1px solid var(--border)', opacity: step.confirmed ? 0.7 : 1,
    }}>
      <button
        onClick={() => !step.confirmed && onConfirm(step.step_id)}
        disabled={disabled || step.confirmed}
        style={{
          width: 20, height: 20, border: '2px solid', borderRadius: 4, flexShrink: 0, cursor: 'pointer',
          background: step.confirmed ? 'var(--verified)' : 'transparent',
          borderColor: step.confirmed ? 'var(--verified)' : 'var(--border-3)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', marginTop: 2,
        }}
        aria-label={`Confirm step ${step.title}`}
      >
        {step.confirmed && <CheckCircle size={12} color="white" />}
      </button>
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: 13.5, fontWeight: 600, color: step.confirmed ? 'var(--text-3)' : 'var(--text)', textDecoration: step.confirmed ? 'line-through' : 'none' }}>
          {step.title}
          {step.type === 'RULE_REQUIRED' && (
            <span className="badge badge-critical" style={{ marginLeft: 8, fontSize: 9 }}>Required</span>
          )}
        </div>
        {step.description && <p style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 3 }}>{step.description}</p>}
        {step.confirmed && step.confirmed_by && (
          <p style={{ fontSize: 11, color: 'var(--text-4)', marginTop: 4 }}>
            Confirmed by {step.confirmed_by} · {step.confirmed_at ? new Date(step.confirmed_at).toLocaleString() : ''}
          </p>
        )}
      </div>
    </div>
  )
}

// ─── Timeline event ──────────────────────────────────────────────────────────────
export function TimelineEvent({ event, last }: {
  event: { event_type: string; from_status?: string; to_status?: string; actor?: string; note?: string; created_at: string }
  last?: boolean
}) {
  return (
    <div style={{ display: 'flex', gap: 12 }}>
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
        <div style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--orange)', marginTop: 5 }} />
        {!last && <div style={{ width: 1, flex: 1, background: 'var(--border)', marginTop: 4 }} />}
      </div>
      <div style={{ paddingBottom: 16, flex: 1 }}>
        <div style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--text)' }}>
          {event.event_type.replace(/_/g, ' ')}
          {event.from_status && event.to_status && (
            <span style={{ color: 'var(--text-3)', fontWeight: 400, marginLeft: 6 }}>
              {event.from_status} → {event.to_status}
            </span>
          )}
        </div>
        {event.note && <p style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 2 }}>{event.note}</p>}
        <div style={{ fontSize: 11, color: 'var(--text-4)', marginTop: 4 }}>
          {event.actor && <span>{event.actor} · </span>}
          {new Date(event.created_at).toLocaleString()}
        </div>
      </div>
    </div>
  )
}

// ─── SLA badge ───────────────────────────────────────────────────────────────────
export function SlaBadge({ breached, minutesRemaining, risk }: {
  breached?: boolean; minutesRemaining?: number; risk?: string
}) {
  if (breached) return <span className="badge badge-critical"><AlertCircle size={10} /> SLA Breached</span>
  if (risk === 'APPROACHING') return <span className="badge badge-mismatch"><Clock size={10} /> SLA At Risk</span>
  if (minutesRemaining != null) {
    const h = Math.floor(minutesRemaining / 60)
    const m = minutesRemaining % 60
    return <span className="badge badge-verified"><Clock size={10} /> {h > 0 ? `${h}h ` : ''}{m}m left</span>
  }
  return <span className="badge badge-neutral">—</span>
}

// ─── Kv row ───────────────────────────────────────────────────────────────────────
export function KvRow({ label, value, mono }: { label: string; value?: React.ReactNode; mono?: boolean }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 16, padding: '8px 0', borderBottom: '1px solid var(--border)' }}>
      <span style={{ fontSize: 12, color: 'var(--text-3)', whiteSpace: 'nowrap', flexShrink: 0 }}>{label}</span>
      <span style={{ fontSize: 13, color: 'var(--text)', fontFamily: mono ? 'DM Mono, monospace' : undefined, textAlign: 'right', wordBreak: 'break-word' }}>
        {value ?? <span style={{ color: 'var(--text-4)' }}>—</span>}
      </span>
    </div>
  )
}

// ─── Auth guard ───────────────────────────────────────────────────────────────────
export function AuthGuard({
  children, allowedRoles,
}: {
  children: React.ReactNode; allowedRoles?: string[]
}) {
  const { user, loading } = useAuth()
  const pathname = usePathname()

  useEffect(() => {
    if (!loading && !user) {
      window.location.href = `/login?redirect=${encodeURIComponent(pathname)}`
    }
  }, [user, loading, pathname])

  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100dvh' }}>
        <Spinner size={32} />
      </div>
    )
  }

  if (!user) return null

  if (allowedRoles && !allowedRoles.includes(user.role)) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100dvh', flexDirection: 'column', gap: 12 }}>
        <AlertCircle size={40} color="var(--critical)" />
        <p style={{ fontWeight: 700, fontSize: 18 }}>Access Denied</p>
        <p style={{ color: 'var(--text-3)' }}>You don't have permission to view this page.</p>
        <Link href="/dashboard" className="btn btn-ghost">Back to Dashboard</Link>
      </div>
    )
  }

  return <>{children}</>
}

// ─── Drag-and-drop file zone ────────────────────────────────────────────────────
export function DropZone({
  onFiles, accept = '*/*', label = 'Drop files here or click to browse',
}: {
  onFiles: (files: File[]) => void; accept?: string; label?: string
}) {
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragging(false)
    if (e.dataTransfer.files.length) onFiles(Array.from(e.dataTransfer.files))
  }, [onFiles])

  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
      onClick={() => inputRef.current?.click()}
      style={{
        border: `2px dashed ${dragging ? 'var(--orange)' : 'var(--border-2)'}`,
        borderRadius: 'var(--r-lg)',
        padding: '32px 20px',
        textAlign: 'center',
        cursor: 'pointer',
        transition: 'border-color 0.2s, background 0.2s',
        background: dragging ? 'var(--orange-dim)' : 'var(--surface-2)',
      }}
    >
      <Upload size={28} color="var(--text-3)" style={{ marginBottom: 10 }} />
      <p style={{ fontSize: 14, color: 'var(--text-2)', fontWeight: 500 }}>{label}</p>
      <p style={{ fontSize: 12, color: 'var(--text-4)', marginTop: 4 }}>Supported formats vary by section</p>
      <input ref={inputRef} type="file" accept={accept} multiple style={{ display: 'none' }} onChange={(e) => { if (e.target.files) onFiles(Array.from(e.target.files)) }} />
    </div>
  )
}

// ─── Expandable rule/explain accordion ───────────────────────────────────────────
export function RuleAccordion({
  rule,
}: {
  rule: { rule_id: string; description: string; outcome: string }
}) {
  const [open, setOpen] = useState(false)
  return (
    <div style={{ border: '1px solid var(--border)', borderRadius: 'var(--r-md)', overflow: 'hidden' }}>
      <button
        onClick={() => setOpen((v) => !v)}
        style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          width: '100%', padding: '10px 14px', background: 'transparent',
          border: 'none', cursor: 'pointer', color: 'var(--text)',
        }}
      >
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <span className="badge badge-neutral" style={{ fontFamily: 'DM Mono, monospace' }}>{rule.rule_id}</span>
          <span style={{ fontSize: 13.5, fontWeight: 500 }}>{rule.description}</span>
        </div>
        <ChevronDown size={14} style={{ transform: open ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s', flexShrink: 0 }} />
      </button>
      {open && (
        <div style={{ padding: '0 14px 12px', borderTop: '1px solid var(--border)', background: 'var(--surface-2)' }}>
          <p style={{ fontSize: 12.5, color: 'var(--text-3)', marginTop: 10 }}>
            <strong style={{ color: 'var(--text-2)' }}>Outcome: </strong>{rule.outcome}
          </p>
        </div>
      )}
    </div>
  )
}

// ─── Trend arrow ────────────────────────────────────────────────────────────────
export function TrendArrow({ direction, pct }: { direction: 'UP' | 'DOWN' | 'STABLE'; pct: number | null }) {
  if (pct == null) return <span style={{ fontSize: 11, color: 'var(--text-4)' }}>Not measured</span>
  const color = direction === 'UP' ? 'var(--verified)' : direction === 'DOWN' ? 'var(--critical)' : 'var(--text-3)'
  const arrow = direction === 'UP' ? '↑' : direction === 'DOWN' ? '↓' : '→'
  return (
    <span style={{ fontSize: 12, color, fontWeight: 700, fontFamily: 'DM Mono, monospace' }}>
      {arrow} {Math.abs(pct).toFixed(1)}%
    </span>
  )
}

// ─── Simple bar chart (pure CSS) ────────────────────────────────────────────────
export function BarChart({
  data, color = 'var(--orange)', height = 160,
}: {
  data: { label: string; value: number }[]; color?: string; height?: number
}) {
  if (!data.length) return <Empty title="No data" />
  const max = Math.max(...data.map((d) => d.value), 1)
  return (
    <div style={{ display: 'flex', gap: 4, alignItems: 'flex-end', height }}>
      {data.map((d) => (
        <div key={d.label} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
          <span style={{ fontSize: 10, color: 'var(--text-3)', fontFamily: 'DM Mono, monospace' }}>{d.value}</span>
          <div
            style={{
              width: '100%', background: color, opacity: 0.8,
              borderRadius: '4px 4px 0 0',
              height: `${(d.value / max) * (height - 30)}px`,
              transition: 'height 0.6s ease',
              minHeight: 4,
            }}
          />
          <span style={{ fontSize: 9, color: 'var(--text-4)', textAlign: 'center', lineHeight: 1.2 }}>{d.label}</span>
        </div>
      ))}
    </div>
  )
}

// ─── Landing nav ────────────────────────────────────────────────────────────────
export function LandingNav() {
  const [scrolled, setScrolled] = useState(false)
  useEffect(() => {
    const handler = () => setScrolled(window.scrollY > 20)
    window.addEventListener('scroll', handler)
    return () => window.removeEventListener('scroll', handler)
  }, [])

  return (
    <nav className="nav" style={{
      background: scrolled ? 'rgba(7,8,13,0.95)' : 'transparent',
      borderBottom: scrolled ? '1px solid var(--border)' : '1px solid transparent',
    }}>
      <Link href="/" className="nav-brand" style={{ marginRight: 'auto' }}>
        <Logo size={26} />
        Support<span>Nova</span>
      </Link>

      <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
        <Link href="/features" className="btn btn-ghost btn-sm">Features</Link>
        <Link href="/how-it-works" className="btn btn-ghost btn-sm">How it Works</Link>
        <Link href="/about" className="btn btn-ghost btn-sm">About</Link>
        <Link href="/login" className="btn btn-orange btn-sm">Sign in</Link>
      </div>
    </nav>
  )
}
