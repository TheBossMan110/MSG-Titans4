'use client'

import { useEffect, type ReactNode } from 'react'
import { usePathname, useRouter } from 'next/navigation'
import { useAuth } from '@/lib/auth-context'
import type { Role } from '@/lib/api'
import { Loading } from '@/components/ui/feedback'
import { Empty } from '@/components/ui/feedback'
import { Button } from '@/components/ui/primitives'

/**
 * Gate a page on a session, and optionally on a role.
 *
 * A missing session goes to sign-in with a return path. A wrong role gets a
 * plain page saying so -- not a redirect, because a reviewer who lands on an
 * admin page should learn that it exists and who may use it.
 */
export function AuthGuard({ children, roles }: { children: ReactNode; roles?: Role[] }) {
  const { user, loading } = useAuth()
  const router = useRouter()
  const pathname = usePathname()

  useEffect(() => {
    if (!loading && !user) router.replace(`/login?next=${encodeURIComponent(pathname)}`)
  }, [loading, user, router, pathname])

  if (loading || !user) return <Loading label="Checking your session" />

  if (roles && !roles.includes(user.role)) {
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
