import { NextResponse } from 'next/server'
import { backendFetch, forwardedHeaders, readRefreshCookie, relayError, setRefreshCookie, tokenResponse } from '@/lib/server/session'

export async function POST() {
  const refresh = await readRefreshCookie()
  if (!refresh) return NextResponse.json({ detail: 'No session.' }, { status: 401 })

  const upstream = await backendFetch('/api/auth/refresh', {
    method: 'POST',
    headers: await forwardedHeaders(),
    body: JSON.stringify({ refresh_token: refresh }),
  })
  if (upstream.status === 401 || upstream.status === 403) {
    // The token was rejected (expired, revoked or rotated away). Drop it so the
    // next visit does not retry a dead credential.
    const res = await relayError(upstream)
    setRefreshCookie(res, null)
    return res
  }
  // Anything else -- the backend restarting, a rate limit, a database blip --
  // says nothing about the session, which is still good: keep the cookie.
  if (!upstream.ok) return relayError(upstream)
  return tokenResponse(await upstream.json())
}
