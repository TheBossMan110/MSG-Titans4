'use client'

import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import {
  BarChart3, BookOpen, Briefcase, Building2, ChevronDown, ClipboardCheck, Download, FileSearch, FileText, FlaskConical, Gauge, Headset, Inbox, Info, LayoutDashboard, ListChecks, LogOut, type LucideIcon, Mail, MessageCircle, MessageSquareReply, Plus, ScrollText, Settings, ShieldAlert, Siren, Sparkles, Target, TrendingUp, UserCheck, UserRound, Users,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { useAuth } from '@/lib/auth-context'
import type { Role } from '@/lib/api'
import { Button, Wordmark } from '@/components/ui/primitives'
import { ADMIN_SECTIONS, AGENT_SECTIONS, MANAGER_SECTIONS, REVIEWER_SECTIONS, USER_SECTIONS } from '@/components/app/dashboard-bits'
import { HOME, SWITCHABLE, VIEW_LABEL, type View, viewForPath, viewOf } from '@/lib/roles'
import { getLenis } from '@/components/motion/smooth-scroll'
import { AuthGuard } from './auth-guard'
import { LiveIndicator } from './live-indicator'

const OVERSIGHT: Role[] = ['manager', 'admin', 'evaluator']

type Item = { href: string; label: string; icon: LucideIcon; exact?: boolean }
type Group = { title: string; items: Item[] }

const ACCOUNT: Group = {
  title: 'Account',
  items: [
    { href: '/dashboard/profile', label: 'Profile & security', icon: UserRound },
    { href: '/dashboard/settings', label: 'Settings', icon: Settings },
  ],
}

/** Read-only reference every member of staff works from. Only an administrator changes it. */
const REFERENCE: Group = {
  title: 'Knowledge (read only)',
  items: [
    { href: '/dashboard/knowledge-base', label: 'Policies', icon: BookOpen },
    { href: '/dashboard/knowledge-base/search', label: 'Search & trace', icon: FileSearch },
    { href: '/dashboard/rules', label: 'Rule matrix', icon: ListChecks },
    { href: '/dashboard/organisation', label: 'Organisation', icon: Building2 },
  ],
}

/**
 * Five role experiences (FR ii). Each role sees its own work, not the others'
 * menus: the customer their complaints; the agent their team's cases; the
 * reviewer the review desk; the manager the operation; the administrator the
 * platform. The API enforces the same boundaries on every request.
 */
const NAV: Record<View, Group[]> = {
  customer: [
    {
      title: 'My SupportNova',
      items: [
        { href: '/dashboard/my-complaints', label: 'Overview', icon: LayoutDashboard },
        { href: '/dashboard/complaints/new', label: 'Submit a complaint', icon: Plus },
        { href: '/dashboard/assistant', label: 'Chat with Nova', icon: MessageCircle },
        { href: '/dashboard/my-emails', label: 'Messages & updates', icon: Mail },
      ],
    },
    ACCOUNT,
  ],
  agent: [
    {
      title: 'My work',
      items: [
        { href: '/dashboard/agent', label: 'Agent dashboard', icon: Headset },
        { href: '/dashboard/complaints', label: 'Team complaints', icon: Inbox, exact: true },
        { href: '/dashboard/follow-ups', label: 'Follow-ups', icon: MessageSquareReply },
        { href: '/dashboard/escalations', label: 'Escalations', icon: Siren },
        { href: '/dashboard/email', label: 'Customer email', icon: Mail },
        { href: '/dashboard/complaints/new', label: 'New complaint', icon: Plus },
      ],
    },
    REFERENCE,
    ACCOUNT,
  ],
  reviewer: [
    {
      title: 'Review desk',
      items: [
        { href: '/dashboard/reviewer', label: 'Reviewer dashboard', icon: ClipboardCheck },
        { href: '/dashboard/review', label: 'Review queue', icon: UserCheck },
        { href: '/dashboard/complaints', label: 'Complaints', icon: Inbox, exact: true },
        { href: '/dashboard/escalations', label: 'Escalations', icon: Siren },
      ],
    },
    REFERENCE,
    ACCOUNT,
  ],
  manager: [
    {
      title: 'Operations',
      items: [
        { href: '/dashboard/manager', label: 'Manager dashboard', icon: Briefcase },
        { href: '/dashboard/complaints', label: 'Complaints', icon: Inbox, exact: true },
        { href: '/dashboard/review', label: 'Review queue', icon: UserCheck },
        { href: '/dashboard/escalations', label: 'Escalations', icon: Siren },
        { href: '/dashboard/follow-ups', label: 'Follow-ups', icon: MessageSquareReply },
        { href: '/dashboard/email', label: 'Email', icon: Mail },
        { href: '/dashboard/users', label: 'Team', icon: Users },
      ],
    },
    {
      title: 'Insight',
      items: [
        { href: '/dashboard/analytics', label: 'Analytics', icon: BarChart3 },
        { href: '/dashboard/analytics/trends', label: 'Trends', icon: TrendingUp },
        { href: '/dashboard/reports', label: 'Reports', icon: FileText },
        { href: '/dashboard/exports', label: 'Exports', icon: Download },
      ],
    },
    { ...REFERENCE, items: [...REFERENCE.items, { href: '/dashboard/rules/sandbox', label: 'Rule sandbox', icon: FlaskConical }] },
    ACCOUNT,
  ],
  admin: [
    {
      title: 'Overview',
      items: [
        { href: '/dashboard', label: 'Admin dashboard', icon: LayoutDashboard, exact: true },
        { href: '/dashboard/complaints', label: 'Complaints', icon: Inbox, exact: true },
        { href: '/dashboard/review', label: 'Review queue', icon: UserCheck },
        { href: '/dashboard/escalations', label: 'Escalations', icon: Siren },
        { href: '/dashboard/follow-ups', label: 'Follow-ups', icon: MessageSquareReply },
        { href: '/dashboard/email', label: 'Email', icon: Mail },
      ],
    },
    {
      title: 'Platform',
      items: [
        { href: '/dashboard/users', label: 'Users & roles', icon: Users },
        { href: '/dashboard/organisation', label: 'Departments & categories', icon: Building2 },
        { href: '/dashboard/knowledge-base', label: 'Knowledge base', icon: BookOpen },
        { href: '/dashboard/knowledge-base/search', label: 'Search & trace', icon: FileSearch },
        { href: '/dashboard/rules', label: 'Rule matrix', icon: ListChecks },
        { href: '/dashboard/rules/sandbox', label: 'Rule sandbox', icon: FlaskConical },
        { href: '/dashboard/prompts', label: 'Prompts', icon: Sparkles },
      ],
    },
    {
      title: 'Insight',
      items: [
        { href: '/dashboard/analytics', label: 'Analytics', icon: BarChart3 },
        { href: '/dashboard/analytics/trends', label: 'Trends', icon: TrendingUp },
        { href: '/dashboard/reports', label: 'Reports', icon: FileText },
        { href: '/dashboard/exports', label: 'Exports', icon: Download },
        { href: '/dashboard/benchmark', label: 'Benchmark', icon: Target },
      ],
    },
    {
      title: 'Trust',
      items: [
        { href: '/dashboard/security', label: 'Security', icon: ShieldAlert },
        { href: '/dashboard/audit', label: 'Audit trail', icon: ScrollText },
      ],
    },
    ACCOUNT,
  ],
}


/** What each dashboard contains, as the SRS lists it; shown under the active item. */
const VIEW_KEY = 'sn-view'

const SECTIONS: Record<string, Array<[string, string]>> = {
  '/dashboard': ADMIN_SECTIONS,
  '/dashboard/agent': AGENT_SECTIONS,
  '/dashboard/reviewer': REVIEWER_SECTIONS,
  '/dashboard/manager': MANAGER_SECTIONS,
  '/dashboard/my-complaints': USER_SECTIONS,
}

/**
 * Links to each section of the current dashboard. A click scrolls to it and
 * briefly highlights it; while reading, the section in view is marked.
 */
function SectionLinks({ sections }: { sections: Array<[string, string]> }) {
  const [current, setCurrent] = useState<string | null>(null)
  useEffect(() => {
    const els = sections.map(([id]) => document.getElementById(id)).filter((e): e is HTMLElement => Boolean(e))
    if (!els.length) return
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries.filter((e) => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)
        if (visible[0]) setCurrent(visible[0].target.id)
      },
      { rootMargin: '-80px 0px -55% 0px' },
    )
    els.forEach((e) => observer.observe(e))
    return () => observer.disconnect()
  })
  const go = (id: string) => {
    const el = document.getElementById(id)
    if (!el) return
    const lenis = getLenis()
    if (lenis) lenis.scrollTo(el, { offset: -88 })
    else el.scrollIntoView({ behavior: 'smooth', block: 'start' })
    el.dataset.flash = 'true'
    window.setTimeout(() => { el.dataset.flash = 'false' }, 1600)
    setCurrent(id)
  }
  return (
    <ul className="mb-1 ml-[22px] mt-1 flex flex-col border-l border-line-soft pl-2.5" aria-label="On this dashboard">
      {sections.map(([id, label]) => (
        <li key={id}>
          <button type="button" onClick={() => go(id)} aria-current={current === id ? 'location' : undefined}
            className={cn('w-full rounded-lg px-2 py-1 text-left text-[12.5px] transition-colors', current === id ? 'bg-white/80 font-medium text-espresso' : 'text-taupe-2 hover:text-espresso')}>
            {label}
          </button>
        </li>
      ))}
    </ul>
  )
}

/**
 * One sentence per page on what it is for, shown above the page. Staff pages
 * are dense by necessity; the sentence tells a newcomer which question the
 * page answers before they have to work it out from the tables.
 */
const PAGE_HELP: Array<[RegExp, string]> = [
  [/^\/dashboard\/manager$/, 'The manager view: the whole operation today — each team’s load and SLA, each agent’s workload, critical cases and escalations. Pick one team to focus on it.'],
  [/^\/dashboard\/reviewer$/, 'The reviewer view: cases the system will not settle alone, grouped by why a person is needed, and your own review decisions.'],
  [/^\/dashboard\/users$/, 'Every account in the database. Open one to see their details, each complaint they raised with its full history, their sign-ins and emails. New sign-ups appear here on their own.'],
  [/^\/dashboard\/users\//, 'One account: who they are, when they joined and signed in, and every complaint with each status change and when it happened.'],
  [/^\/dashboard$/, 'The admin view: totals, where complaints go, how urgent they are, SLA risks, AI-versus-rules mismatches and cases waiting on a person.'],
  [/^\/dashboard\/agent/, 'The agent view: your complaints with the AI recommendation, what the rules confirmed, a suggested reply and any escalation warning.'],
  [/^\/dashboard\/complaints$/, 'Every complaint in the register. Filter it, then open one to see what the AI proposed and what the rules decided.'],
  [/^\/dashboard\/complaints\/new$/, 'Submit a complaint on a customer’s behalf. Each step of the analysis appears as it happens.'],
  [/^\/dashboard\/complaints\/[^/]+$/, 'One complaint. Overview is what happened; Why shows the AI and the rules side by side; the other tabs are the work still to do.'],
  [/^\/dashboard\/assistant/, ''],
  [/^\/dashboard\/email/, 'Complaints that arrive by email, and the replies the system sent. Each complaint email is registered and analysed like any other.'],
  [/^\/dashboard\/follow-ups/, 'Promises the system made to customers, with due dates. Mark each one done when it is done.'],
  [/^\/dashboard\/review/, 'Complaints a person must check: the AI and the rules disagreed, a rule escalated it, or something looked unsafe.'],
  [/^\/dashboard\/escalations/, 'Complaints the rules sent above the normal team. The level can be raised, never lowered.'],
  [/^\/dashboard\/organisation/, 'The company as the dataset defines it: teams, categories, service levels, reply templates and the loaded datasets.'],
  [/^\/dashboard\/knowledge-base\/search/, 'Search the policy library the way the AI does, and trace any citation back to the exact paragraph.'],
  [/^\/dashboard\/knowledge-base/, 'The company policies the AI may cite. Only the active version of each can back a decision.'],
  [/^\/dashboard\/rules\/sandbox/, 'Try any complaint text against the rules without saving anything, and see which rules fire and why.'],
  [/^\/dashboard\/rules/, 'The rules that make the final decision. Each one cites the policy it comes from.'],
  [/^\/dashboard\/prompts/, 'The instructions the AI is given, versioned. Changing the active version changes how every new complaint is read.'],
  [/^\/dashboard\/analytics\/trends/, 'Which categories and teams are rising or falling between snapshots, with unusual jumps flagged.'],
  [/^\/dashboard\/analytics/, 'Volumes, categories, team load, and how often the rules had to correct the AI.'],
  [/^\/dashboard\/reports/, 'Ready-made reports on the live register. Pick one on the left; managers and admins can download it.'],
  [/^\/dashboard\/exports/, 'Every report that has been downloaded, by whom and when.'],
  [/^\/dashboard\/benchmark/, 'How accurate the AI and the rules are against a labelled dataset, field by field.'],
  [/^\/dashboard\/security/, 'Attempts to trick the AI, and the safety checks that stop bad replies before a customer sees them.'],
  [/^\/dashboard\/audit/, 'Who changed what, and when. Every change in the system is recorded here and cannot be edited.'],
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

  // Each role has its own navigation. An administrator (or a manager) who
  // opens another role's dashboard sees the app as that role does -- its
  // sidebar, its pages -- until they go back to their own dashboard. Kept for
  // the tab's session, so moving between that role's pages keeps the view.
  const own: View = viewOf(user?.role)
  const switchable = (user && SWITCHABLE[user.role]) || []
  const oversight = Boolean(user && OVERSIGHT.includes(user.role))
  const [view, setView] = useState<View>(own)
  useEffect(() => {
    if (!switchable.length) { setView(own); return }
    const target = viewForPath(pathname)
    let next: View = own
    try {
      if (target && target !== own && switchable.includes(target)) { sessionStorage.setItem(VIEW_KEY, target); next = target }
      else if (target === own) sessionStorage.removeItem(VIEW_KEY)
      else {
        const stored = sessionStorage.getItem(VIEW_KEY) as View | null
        const inStored = stored && switchable.includes(stored) && NAV[stored].some((g) => g.items.some((i) => pathname === i.href || pathname.startsWith(i.href + '/')))
        if (inStored) next = stored as View
        else sessionStorage.removeItem(VIEW_KEY)
      }
    } catch {
      if (target && switchable.includes(target)) next = target
    }
    setView(next)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname, own, switchable.join()])
  const viewing = view !== own

  const visible = NAV[view]
  const flat = visible.flatMap((g) => g.items)
  const signOut = async () => { await logout(); router.replace('/login') }
  const help = PAGE_HELP.find(([pattern]) => pattern.test(pathname))?.[1]

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
                    <Icon size={16} strokeWidth={1.9} className={cn('shrink-0 transition-transform duration-300 group-hover/nav:scale-110', active ? 'text-[#9cc7e6]' : 'text-taupe')} aria-hidden />
                    <span className="truncate">{i.label}</span>
                  </Link>
                  {active && SECTIONS[i.href] && <SectionLinks sections={SECTIONS[i.href]} />}
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
            {viewing && (
              <Link href={HOME[own]} className="hidden items-center gap-1.5 rounded-full border border-ai-line bg-ai-soft px-3 py-1 text-[12px] font-medium text-ai transition-colors hover:bg-white sm:inline-flex" title={`Leave the ${VIEW_LABEL[view].toLowerCase()} view`}>
                <Headset size={13} aria-hidden /> {VIEW_LABEL[view]} view
              </Link>
            )}
            {user && user.role !== 'customer' && <LiveIndicator oversight={oversight} />}
            {user && <UserMenu user={user} onLogout={signOut} view={view} own={own} switchable={switchable} />}
          </div>
        </header>

        {drawer && (
          <div className="glass border-x-0 border-t-0 px-[var(--gutter)] py-5 lg:hidden">
            {nav}
            <div className="mt-5"><UserCard user={user} onLogout={signOut} /></div>
          </div>
        )}

        <main className={cn('flex-1 px-[var(--gutter)] py-8 lg:px-10 lg:py-10', !wide && 'mx-auto w-full max-w-[1320px]')}>
          {help && user && user.role !== 'customer' && (
            <p className="mb-6 flex items-start gap-2 text-[13.5px] leading-relaxed text-taupe-2">
              <Info size={15} className="mt-0.5 shrink-0 text-taupe" aria-hidden />
              <span>{help}</span>
            </p>
          )}
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

/**
 * Who is signed in, in the corner where people look for it, and the way to
 * their profile, settings and sign-out. A real menu: Escape and a click
 * outside close it, and it is announced as one.
 */
const DASH_ICON: Record<View, LucideIcon> = {
  customer: LayoutDashboard, agent: Headset, reviewer: ClipboardCheck, manager: Briefcase, admin: LayoutDashboard,
}

function UserMenu({ user, onLogout, view, own, switchable }: { user: NonNullable<ReturnType<typeof useAuth>['user']>; onLogout: () => void; view: View; own: View; switchable: View[] }) {
  const [open, setOpen] = useState(false)
  const box = useRef<HTMLDivElement>(null)
  const pathname = usePathname()
  useEffect(() => setOpen(false), [pathname])
  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) setOpen(false) }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('mousedown', onDown); document.removeEventListener('keydown', onKey) }
  }, [open])

  const name = user.full_name || user.email
  const initials = name.split(/\s+/).map((w) => w[0]).slice(0, 2).join('').toUpperCase()
  const item = 'flex w-full items-center gap-2.5 rounded-xl px-3 py-2 text-left text-[14px] text-espresso-2 transition-colors hover:bg-sand/60 hover:text-espresso focus-visible:bg-sand/60 focus-visible:outline-none'

  return (
    <div ref={box} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
        className="flex items-center gap-2 rounded-full border border-line-soft bg-white/80 py-1 pl-1 pr-2.5 transition-colors hover:bg-white sm:pr-3"
      >
        <span className="inline-flex size-8 items-center justify-center rounded-full bg-espresso text-[12px] font-semibold text-ink-on-dark" aria-hidden>{initials}</span>
        <span className="hidden max-w-[160px] flex-col text-left leading-tight sm:flex">
          <span className="truncate text-[13px] font-medium text-espresso">{name}</span>
          <span className="truncate text-[11.5px] capitalize text-taupe-2">{user.role}</span>
        </span>
        <ChevronDown size={14} className={cn('text-taupe transition-transform', open && 'rotate-180')} aria-hidden />
        <span className="sr-only">Account menu</span>
      </button>
      {open && (
        <div role="menu" className="absolute right-0 top-[calc(100%+8px)] z-50 w-[272px] animate-rise rounded-2xl border border-line-soft bg-ivory p-2 shadow-[0_24px_60px_-24px_rgba(42,31,23,0.45)]">
          <div className="flex items-center gap-3 border-b border-line-soft px-2.5 pb-3 pt-1.5">
            <span className="inline-flex size-10 shrink-0 items-center justify-center rounded-full bg-espresso text-[13px] font-semibold text-ink-on-dark" aria-hidden>{initials}</span>
            <div className="min-w-0">
              <p className="truncate text-[14px] font-medium text-espresso">{name}</p>
              <p className="truncate text-[12.5px] text-taupe-2">{user.email}</p>
              <p className="mt-0.5 text-[11.5px] capitalize text-taupe">{user.role}{user.department ? ` · ${user.department.name}` : ''}</p>
            </div>
          </div>
          <div className="flex flex-col gap-0.5 pt-2">
            {switchable.length > 0 && (
              <>
                <p className="px-3 pb-1 pt-1 text-[11px] font-medium uppercase tracking-[0.12em] text-taupe">Switch dashboard</p>
                {[own, ...switchable].map((v) => {
                  const Icon = DASH_ICON[v]
                  return (
                    <Link key={v} role="menuitem" href={HOME[v]} aria-current={v === view ? 'page' : undefined}
                      className={cn(item, v === view ? 'bg-sand/60 font-medium text-espresso' : 'text-espresso-2')}>
                      <Icon size={16} className="text-taupe" aria-hidden /> {VIEW_LABEL[v]} dashboard
                    </Link>
                  )
                })}
                <span className="mx-2 my-1 block border-t border-line-soft" aria-hidden />
              </>
            )}
            <Link role="menuitem" href="/dashboard/profile" className={item}><UserRound size={16} className="text-taupe" aria-hidden /> Profile &amp; security</Link>
            <Link role="menuitem" href="/dashboard/settings" className={item}><Settings size={16} className="text-taupe" aria-hidden /> Settings</Link>
            <button role="menuitem" type="button" onClick={onLogout} className={cn(item, 'text-critical hover:text-critical')}><LogOut size={16} aria-hidden /> Sign out</button>
          </div>
        </div>
      )}
    </div>
  )
}
