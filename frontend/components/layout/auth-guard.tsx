'use client'

import { useEffect, type ReactNode } from 'react'
import { usePathname, useRouter } from 'next/navigation'
import { useAuth } from '@/lib/auth-context'
import type { Role } from '@/lib/api'
import { can, type Permission } from '@/lib/roles'
import { Loading } from '@/components/ui/feedback'
import { Empty } from '@/components/ui/feedback'
import { Button } from '@/components/ui/primitives'

/**
 * Gate a page on a session, and optionally on a role or a permission.
 *
 * A missing session goes to sign-in with a return path. A wrong role gets a
 * plain page saying so -- not a redirect, because a reviewer who lands on an
 * admin page should learn that it exists and who may use it.
 *
 * With `permission`, the organisation's access policy decides instead of the
 * role list: a manager whose company withheld analytics is refused, an agent
 * whose company granted it is let in.
 */
export function AuthGuard({ children, roles, permission }: { children: ReactNode; roles?: Role[]; permission?: Permission }) {
  const { user, loading } = useAuth()
  const router = useRouter()
  const pathname = usePathname()

  useEffect(() => {
    if (!loading && !user) router.replace(`/login?next=${encodeURIComponent(pathname)}`)
  }, [loading, user, router, pathname])

  if (loading || !user) return <Loading label="Checking your session" />

  if (permission && !can(user, permission)) {
    return (
      <Empty
        title="Your company has not given your role this access"
        body={`You are signed in as ${user.role}${user.organisation ? ` at ${user.organisation.name}` : ''}. An administrator can grant it on the Company & Access page.`}
        action={<Button href="/dashboard" variant="secondary">Back to the dashboard</Button>}
        className="m-8"
      />
    )
  }

  if (!permission && roles && !roles.includes(user.role)) {
    return (
      <Empty
        title="This page is for another role"
        body={`You are signed in as ${user.role}. This area is available to ${roles.join(', ')}.`}
        action={<Button href="/dashboard" variant="secondary">Back to the dashboard</Button>}
        className="m-8"
      />
    )
  }

  return <>{children}</>
}
