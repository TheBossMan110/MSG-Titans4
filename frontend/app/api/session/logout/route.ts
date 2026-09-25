import { NextResponse } from 'next/server'
import { backendUrl, forwardedHeaders, readRefreshCookie, setRefreshCookie } from '@/lib/server/session'

export async function POST(req: Request) {
  const refresh = await readRefreshCookie()
  const authz = req.headers.get('authorization')
  if (refresh && authz) {
    // Best effort: revoke server-side. The cookie is cleared regardless.
    try {
      await fetch(`${backendUrl()}/api/auth/logout`, {
        method: 'POST',
        headers: await forwardedHeaders({ Authorization: authz }),
        body: JSON.stringify({ refresh_token: refresh }),
        cache: 'no-store',
      })
    } catch {}
  }
  const res = NextResponse.json({ message: 'Signed out.' })
  setRefreshCookie(res, null)
  return res
}
