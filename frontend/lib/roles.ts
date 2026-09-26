import type { Role } from '@/lib/api'

/**
 * The five role experiences (FR ii). One application, one sign-in; each role
 * gets its own dashboard and its own navigation. The server enforces every
 * permission regardless -- these decide only what is offered.
 */
export type View = 'customer' | 'agent' | 'reviewer' | 'manager' | 'admin'

export const VIEW_LABEL: Record<View, string> = {
  customer: 'Customer',
  agent: 'Agent',
  reviewer: 'Reviewer',
  manager: 'Manager',
  admin: 'Administrator',
}

export const HOME: Record<View, string> = {
  customer: '/dashboard/my-complaints',
  agent: '/dashboard/agent',
  reviewer: '/dashboard/reviewer',
  manager: '/dashboard/manager',
  admin: '/dashboard',
}

/** A role's own view. Evaluators are judges: they see the administrator's view, read-only on the server. */
export function viewOf(role?: Role | string | null): View {
  switch (role) {
    case 'customer': return 'customer'
    case 'agent': return 'agent'
    case 'reviewer': return 'reviewer'
    case 'manager': return 'manager'
    default: return 'admin'
  }
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

/** Which dashboard route belongs to which view, for the switcher. */
export function viewForPath(pathname: string): View | null {
  if (pathname === '/dashboard') return 'admin'
  if (pathname.startsWith('/dashboard/manager')) return 'manager'
  if (pathname.startsWith('/dashboard/reviewer')) return 'reviewer'
  if (pathname.startsWith('/dashboard/agent')) return 'agent'
  return null
}
