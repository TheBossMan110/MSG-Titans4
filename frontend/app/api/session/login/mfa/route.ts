import { NextResponse } from 'next/server'
import { backendFetch, forwardedHeaders, relayError, tokenResponse } from '@/lib/server/session'

/** The second step of a two-step sign-in; on success the refresh token becomes the cookie. */
export async function POST(req: Request) {
  let payload: unknown
  try { payload = await req.json() } catch { return NextResponse.json({ detail: 'Malformed request.' }, { status: 400 }) }

  const upstream = await backendFetch('/api/auth/login/mfa', {
    method: 'POST',
    headers: await forwardedHeaders(),
    body: JSON.stringify(payload),
  })
  if (!upstream.ok) return relayError(upstream)
  return tokenResponse(await upstream.json())
}
