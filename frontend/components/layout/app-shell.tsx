'use client'

import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { useEffect, useState, type ReactNode } from 'react'
import {
  Activity, BarChart3, BookOpen, Download, FileSearch, FileText, FlaskConical, Gauge,
  Inbox, LayoutDashboard, ListChecks, LogOut, MessageSquareReply, Plus, ScrollText,
  Settings, ShieldAlert, Siren, Sparkles, Target, TrendingUp, UserCheck, type LucideIcon,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useAuth } from '@/lib/auth-context'
import type { Role } from '@/lib/api'
import { Badge, Button, Wordmark } from '@/components/ui/primitives'
import { AuthGuard } from './auth-guard'

type Item = { href: string; label: string; icon: LucideIcon; roles?: Role[]; exact?: boolean }
type Group = { title: string; items: Item[] }

const STAFF: Role[] = ['agent', 'reviewer', 'manager', 'admin', 'evaluator']
const OVERSIGHT: Role[] = ['manager', 'admin', 'evaluator']
const REVIEWERS: Role[] = ['reviewer', 'manager', 'admin']

const groups: Group[] = [
  {
    title: 'Work',
    items: [
      { href: '/dashboard', label: 'Overview', icon: LayoutDashboard, exact: true, roles: STAFF },
      { href: '/dashboard/my-complaints', label: 'My complaints', icon: Inbox, roles: ['customer'] },
      { href: '/dashboard/complaints/new', label: 'New complaint', icon: Plus, roles: ['customer'] },
      { href: '/dashboard/complaints', label: 'Complaints', icon: Inbox, roles: STAFF },
      { href: '/dashboard/follow-ups', label: 'Follow-ups', icon: MessageSquareReply, roles: STAFF },
      { href: '/dashboard/review', label: 'Review queue', icon: UserCheck, roles: [...REVIEWERS, 'evaluator', 'agent'] },
      { href: '/dashboard/escalations', label: 'Escalations', icon: Siren, roles: STAFF },
    ],
  },
  {
    title: 'Knowledge',
    items: [
      { href: '/dashboard/knowledge-base', label: 'Policies', icon: BookOpen, roles: STAFF },
      { href: '/dashboard/knowledge-base/search', label: 'Search & trace', icon: FileSearch, roles: STAFF },
      { href: '/dashboard/rules', label: 'Rule matrix', icon: ListChecks, roles: OVERSIGHT },
      { href: '/dashboard/rules/sandbox', label: 'Rule sandbox', icon: FlaskConical, roles: OVERSIGHT },
      { href: '/dashboard/prompts', label: 'Prompts', icon: Sparkles, roles: OVERSIGHT },
    ],
  },
  {
    title: 'Insight',
    items: [
      { href: '/dashboard/analytics', label: 'Analytics', icon: BarChart3, roles: OVERSIGHT },
      { href: '/dashboard/analytics/trends', label: 'Trends', icon: TrendingUp, roles: OVERSIGHT },
      { href: '/dashboard/reports', label: 'Reports', icon: FileText, roles: OVERSIGHT },
      { href: '/dashboard/exports', label: 'Exports', icon: Download, roles: OVERSIGHT },
      { href: '/dashboard/benchmark', label: 'Benchmark', icon: Target, roles: OVERSIGHT },
    ],
  },
  {
    title: 'Trust',
    items: [
      { href: '/dashboard/security', label: 'Security', icon: ShieldAlert, roles: OVERSIGHT },
      { href: '/dashboard/audit', label: 'Audit trail', icon: ScrollText, roles: OVERSIGHT },
      { href: '/dashboard/settings', label: 'Settings', icon: Settings },
    ],
  },
]

/**
 * The application frame: a frosted sidebar over a quiet gradient mesh, a
 * glass top bar, the page.
 *
 * Navigation is filtered by role so that what is offered is what will be
 * accepted — an interface that offers a page the API refuses teaches people
 * to distrust it. The server still authorises every request regardless.
 */
export function AppShell({
  children,
  title,
  eyebrow,
  actions,
  roles,
  wide,
}: {
  children: ReactNode
  title?: ReactNode
  eyebrow?: ReactNode
  actions?: ReactNode
  roles?: Role[]
  wide?: boolean
}) {
  return (
    <div className="mesh-app min-h-dvh">
      <AuthGuard roles={roles}>
        <Frame title={title} eyebrow={eyebrow} actions={actions} wide={wide}>
          {children}
        </Frame>
      </AuthGuard>
    </div>
  )
}

function isActive(pathname: string, item: Item, all: Item[]) {
  if (item.exact) return pathname === item.href
  if (pathname === item.href) return true
  if (!pathname.startsWith(item.href + '/')) return false
  // A longer sibling route claims its own subtree: /rules/sandbox is not /rules.
  return !all.some((o) => o !== item && o.href.startsWith(item.href + '/') && (pathname === o.href || pathname.startsWith(o.href + '/')))
}

function Frame({ children, title, eyebrow, actions, wide }: { children: ReactNode; title?: ReactNode; eyebrow?: ReactNode; actions?: ReactNode; wide?: boolean }) {
  const { user, logout } = useAuth()
  const pathname = usePathname()
  const router = useRouter()
  const [drawer, setDrawer] = useState(false)

  useEffect(() => setDrawer(false), [pathname])

  const visible = groups
    .map((g) => ({ ...g, items: g.items.filter((i) => !i.roles || (user && i.roles.includes(user.role))) }))
    .filter((g) => g.items.length)
  const flat = visible.flatMap((g) => g.items)
  const signOut = async () => { await logout(); router.replace('/login') }

  const nav = (
    <nav aria-label="Application" className="flex flex-col gap-6">
      {visible.map((g) => (
        <div key={g.title}>
          <p className="eyebrow mb-2 px-3 text-[10px]">{g.title}</p>
          <ul className="flex flex-col gap-0.5">
            {g.items.map((i) => {
              const active = isActive(pathname, i, flat)
              const Icon = i.icon
              return (
                <li key={i.href}>
                  <Link
                    href={i.href}
                    aria-current={active ? 'page' : undefined}
                    className={cn(
                      'group/nav relative flex items-center gap-2.5 rounded-xl px-3 py-2 text-[14px] transition-[background-color,color,box-shadow] duration-200',
                      active
                        ? 'bg-espresso text-ink-on-dark shadow-[0_8px_20px_-10px_rgba(42,31,23,0.6)]'
                        : 'text-espresso-2 hover:bg-white/70 hover:text-espresso',
                    )}
                  >
                    <Icon size={16} strokeWidth={1.9} className={cn('shrink-0 transition-transform duration-300 group-hover/nav:scale-110', active ? 'text-[#b7adff]' : 'text-taupe')} aria-hidden />
                    <span className="truncate">{i.label}</span>
                  </Link>
                </li>
              )
            })}
          </ul>
        </div>
      ))}
    </nav>
  )

  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[260px_1fr]">
      <aside
        className="glass sticky top-0 hidden h-dvh flex-col rounded-none border-y-0 border-l-0 border-r border-line-soft px-4 py-5 lg:flex"
        style={{ paddingTop: 'max(20px, env(safe-area-inset-top))' }}
      >
        <Link href="/" className="mb-7 px-3"><Wordmark /></Link>
        <div className="-mr-2 flex-1 overflow-y-auto pr-2" data-lenis-prevent>{nav}</div>
        <UserCard user={user} onLogout={signOut} />
      </aside>

      <div className="flex min-w-0 flex-col">
        <header
          className="sticky top-0 z-30 flex h-16 items-center justify-between gap-3 border-b border-white/60 bg-cream/60 px-[var(--gutter)] backdrop-blur-xl lg:px-8"
          style={{ top: 'env(safe-area-inset-top, 0px)' }}
        >
          <div className="flex min-w-0 items-center gap-3">
            <button
              className="inline-flex size-10 items-center justify-center rounded-full border border-line bg-white/80 lg:hidden"
              aria-label="Menu"
              aria-expanded={drawer}
              onClick={() => setDrawer((d) => !d)}
            >
              <span className="block h-[1.5px] w-4 bg-espresso shadow-[0_5px_0_var(--color-espresso),0_-5px_0_var(--color-espresso)]" />
            </button>
            <div className="min-w-0 truncate text-[13.5px] text-taupe">
              {eyebrow ?? <span className="lg:hidden"><Wordmark /></span>}
            </div>
          </div>
          <div className="flex items-center gap-2">
            {actions}
            <span className="hidden items-center gap-2 rounded-full border border-line-soft bg-white/70 px-3 py-1 text-[12px] text-taupe-2 md:inline-flex">
              <Activity size={13} className="text-verified" aria-hidden /> Live data
            </span>
            {user && <Badge tone="ink" className="hidden capitalize sm:inline-flex">{user.role}</Badge>}
          </div>
        </header>

        {drawer && (
          <div className="glass border-x-0 border-t-0 px-[var(--gutter)] py-5 lg:hidden">
            {nav}
            <div className="mt-5"><UserCard user={user} onLogout={signOut} /></div>
          </div>
        )}

        <main className={cn('flex-1 px-[var(--gutter)] py-8 lg:px-10 lg:py-10', !wide && 'mx-auto w-full max-w-[1320px]')}>
          {title && (
            <div className="mb-7 flex flex-wrap items-end justify-between gap-4">
              <h1 className="font-display text-h2 leading-none">{title}</h1>
            </div>
          )}
          {children}
        </main>
      </div>
    </div>
  )
}

function UserCard({ user, onLogout }: { user: ReturnType<typeof useAuth>['user']; onLogout: () => void }) {
  if (!user) return null
  const initials = (user.full_name || user.email).split(/\s+/).map((w) => w[0]).slice(0, 2).join('').toUpperCase()
  return (
    <div className="rounded-2xl border border-white/70 bg-white/70 p-3 shadow-card">
      <div className="flex items-center gap-3">
        <span className="inline-flex size-9 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-espresso to-espresso-2 text-[12px] font-semibold text-ink-on-dark ring-2 ring-white">
          {initials}
        </span>
        <div className="min-w-0">
          <p className="truncate text-[13.5px] font-medium text-espresso">{user.full_name || user.email}</p>
          <p className="flex items-center gap-1.5 text-[12px] capitalize text-taupe"><Gauge size={11} aria-hidden /> {user.role}</p>
        </div>
      </div>
      <Button variant="secondary" size="sm" className="mt-3 w-full" onClick={onLogout} icon={<LogOut size={13} aria-hidden />}>Sign out</Button>
    </div>
  )
}
