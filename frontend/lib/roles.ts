import type { Role } from '@/lib/api'

/**
 * The five role experiences (FR ii). One application, one sign-in; each role
 * gets its own dashboard and its own navigation. The server enforces every
 * permission regardless -- these decide only what is offered.
 */
export type View = 'customer' | 'agent' | 'reviewer' | 'manager' | 'admin' | 'platform'

export const VIEW_LABEL: Record<View, string> = {
  customer: 'Customer',
  agent: 'Agent',
  reviewer: 'Reviewer',
  manager: 'Manager',
  admin: 'Administrator',
  platform: 'Platform',
}

export const HOME: Record<View, string> = {
  customer: '/dashboard/my-complaints',
  agent: '/dashboard/agent',
  reviewer: '/dashboard/reviewer',
  manager: '/dashboard/manager',
  admin: '/dashboard',
  platform: '/dashboard/platform',
}

/**
 * A role's own view. Evaluators are judges: they see the administrator's view,
 * read-only on the server. The super administrator sees the platform: every
 * company's totals and the shared template, never one company's data.
 */
export function viewOf(role?: Role | string | null): View {
  switch (role) {
    case 'customer': return 'customer'
    case 'agent': return 'agent'
    case 'reviewer': return 'reviewer'
    case 'manager': return 'manager'
    case 'superadmin': return 'platform'
    default: return 'admin'
  }
}

/**
 * Who may change the shared template (rules, prompts, configuration, lexicon,
 * SLA ladders): the super administrators, and the administrators of the
 * reference company whose dataset defined it. Everyone else reads it; the API
 * refuses their edits regardless.
 */
export function canEditTemplate(user: { role?: string; organisation?: { owns_template?: boolean } | null } | null | undefined): boolean {
  if (!user) return false
  return user.role === 'superadmin' || (user.role === 'admin' && Boolean(user.organisation?.owns_template))
}

export function homeFor(role?: Role | string | null): string {
  return HOME[viewOf(role)]
}

/**
 * Other dashboards a role may open to see the work as that role does. An
 * administrator can look through every staff role's eyes; a manager through
 * an agent's. Nobody else switches.
 */
export const SWITCHABLE: Partial<Record<Role, View[]>> = {
  admin: ['manager', 'reviewer', 'agent'],
  evaluator: ['manager', 'reviewer', 'agent'],
  manager: ['agent'],
}

/**
 * The work an organisation's administrator can give or withhold per role
 * (backend: src/core/permissions.py). `/api/auth/me` lists what the signed-in
 * user holds; the API checks the same on every request.
 */
export type Permission =
  | 'analytics.view' | 'reports.export' | 'review.queue' | 'review.decide' | 'complaints.reanalyse'
  | 'documents.manage' | 'users.manage' | 'audit.view' | 'benchmark.run'

export function can(user: { permissions?: string[] | null } | null | undefined, permission: Permission): boolean {
  return Boolean(user?.permissions?.includes(permission))
}

/** Which dashboard route belongs to which view, for the switcher. */
export function viewForPath(pathname: string): View | null {
  if (pathname === '/dashboard') return 'admin'
  if (pathname.startsWith('/dashboard/manager')) return 'manager'
  if (pathname.startsWith('/dashboard/reviewer')) return 'reviewer'
  if (pathname.startsWith('/dashboard/agent')) return 'agent'
  return null
}
