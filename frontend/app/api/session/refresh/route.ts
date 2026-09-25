import { NextResponse } from 'next/server'
import { backendUrl, forwardedHeaders, readRefreshCookie, relayError, setRefreshCookie, tokenResponse } from '@/lib/server/session'

export async function POST() {
  const refresh = await readRefreshCookie()
  if (!refresh) return NextResponse.json({ detail: 'No session.' }, { status: 401 })

  const upstream = await fetch(`${backendUrl()}/api/auth/refresh`, {
    method: 'POST',
    headers: await forwardedHeaders(),
    body: JSON.stringify({ refresh_token: refresh }),
    cache: 'no-store',
  })
  if (!upstream.ok) {
    // The token was rejected (expired, revoked or rotated away). Drop it so the
    // next visit does not retry a dead credential.
    const res = await relayError(upstream)
    setRefreshCookie(res, null)
    return res
  }
  return tokenResponse(await upstream.json())
}
