import { NextResponse } from 'next/server'
import { backendUrl, forwardedHeaders, relayError, tokenResponse } from '@/lib/server/session'

export async function POST(req: Request) {
  let payload: unknown
  try { payload = await req.json() } catch { return NextResponse.json({ detail: 'Malformed request.' }, { status: 400 }) }

  const upstream = await fetch(`${backendUrl()}/api/auth/login`, {
    method: 'POST',
    headers: await forwardedHeaders(),
    body: JSON.stringify(payload),
    cache: 'no-store',
  })
  if (!upstream.ok) return relayError(upstream)
  return tokenResponse(await upstream.json())
}
