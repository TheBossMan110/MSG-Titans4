import { NextResponse } from 'next/server'
import { backendFetch, forwardedHeaders, relayError, tokenResponse } from '@/lib/server/session'

export async function POST(req: Request) {
  let payload: unknown
  try { payload = await req.json() } catch { return NextResponse.json({ detail: 'Malformed request.' }, { status: 400 }) }

  const upstream = await backendFetch('/api/auth/login', {
    method: 'POST',
    headers: await forwardedHeaders(),
    body: JSON.stringify(payload),
  })
  if (!upstream.ok) return relayError(upstream)
  const body = await upstream.json()
  // Two-step sign-in: no tokens yet, so no cookie. The browser gets the
  // short-lived step token and finishes at /api/session/login/mfa.
  if (body.mfa_required) return NextResponse.json({ mfa_required: true, mfa_token: body.mfa_token })
  return tokenResponse(body)
}
