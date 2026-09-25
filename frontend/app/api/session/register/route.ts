import { NextResponse } from 'next/server'
import { backendUrl, forwardedHeaders, relayError, tokenResponse } from '@/lib/server/session'

/**
 * Sign-up, proxied for the same reason login is: the refresh token the
 * backend returns must become an httpOnly cookie rather than a value this
 * page's JavaScript can read.
 *
 * The body is passed through untouched. It is the backend that decides the
 * new account is a customer — this route must not be the thing enforcing it.
 */
export async function POST(req: Request) {
  let payload: unknown
  try { payload = await req.json() } catch { return NextResponse.json({ error: { message: 'Malformed request.' } }, { status: 400 }) }

  const upstream = await fetch(`${backendUrl()}/api/auth/register`, {
    method: 'POST',
    headers: await forwardedHeaders(),
    body: JSON.stringify(payload),
    cache: 'no-store',
  })
  if (!upstream.ok) return relayError(upstream)
  return tokenResponse(await upstream.json(), 201)
}
