// Server-only helpers for the session proxy.
//
// The backend issues a refresh token in the response body and expects it back
// in the body of /api/auth/refresh. A browser holding that token in JavaScript
// would be one XSS away from a permanent session, so the browser never sees
// it: these route handlers keep it in an httpOnly cookie scoped to
// /api/session and forward it on the browser's behalf. The access token,
// which is short-lived, is the only credential the client holds, in memory.

import 'server-only'
import { cookies, headers } from 'next/headers'
import { NextResponse } from 'next/server'

export const COOKIE = 'sn_refresh'
const THIRTY_DAYS = 60 * 60 * 24 * 30

export function backendUrl(): string {
  return process.env.API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'
}

/**
 * Forward the caller's address so the backend's per-IP login limit still
 * applies per person. On Vercel every sign-in reaches the backend from the
 * same few function IPs; the shared secret is how the backend knows this
 * address was vouched for by our proxy rather than typed by a client.
 */
export async function forwardedHeaders(extra: Record<string, string> = {}): Promise<Record<string, string>> {
  const h = await headers()
  const out: Record<string, string> = { 'Content-Type': 'application/json', ...extra }
  const ip = (h.get('x-forwarded-for') ?? h.get('x-real-ip') ?? '').split(',')[0].trim()
  if (ip) {
    out['X-Forwarded-For'] = ip
    const secret = process.env.SESSION_PROXY_SECRET
    if (secret) {
      out['X-SN-Client-IP'] = ip
      out['X-SN-Proxy-Secret'] = secret
    }
  }
  const ua = h.get('user-agent')
  if (ua) out['User-Agent'] = ua
  return out
}

/** A backend that cannot be reached answers 502 with a readable reason, not a bare 500. */
export async function backendFetch(path: string, init: RequestInit): Promise<Response> {
  try {
    return await fetch(`${backendUrl()}${path}`, { ...init, cache: 'no-store' })
  } catch {
    return Response.json(
      { error: { code: 'BACKEND_UNREACHABLE', message: 'The server could not be reached. Please try again in a moment.' } },
      { status: 502 },
    )
  }
}

export async function readRefreshCookie(): Promise<string | null> {
  const jar = await cookies()
  return jar.get(COOKIE)?.value ?? null
}

export function setRefreshCookie(res: NextResponse, token: string | null) {
  if (token) {
    res.cookies.set(COOKIE, token, {
      httpOnly: true,
      sameSite: 'lax',
      secure: process.env.NODE_ENV === 'production',
      path: '/api/session',
      maxAge: THIRTY_DAYS,
    })
  } else {
    res.cookies.set(COOKIE, '', { httpOnly: true, sameSite: 'lax', path: '/api/session', maxAge: 0 })
  }
}

type TokenBody = { access_token: string; refresh_token: string; expires_in: number; user: unknown }

/** Relay a token response to the browser without the refresh token. */
export function tokenResponse(body: TokenBody, status = 200): NextResponse {
  const res = NextResponse.json(
    { access_token: body.access_token, expires_in: body.expires_in, user: body.user },
    { status },
  )
  setRefreshCookie(res, body.refresh_token)
  return res
}

/** Relay a backend failure as-is, so the client reads the same `detail` it would have read directly. */
export async function relayError(upstream: Response): Promise<NextResponse> {
  let body: unknown = { detail: `Upstream ${upstream.status}` }
  try { body = await upstream.json() } catch {}
  const res = NextResponse.json(body, { status: upstream.status })
  const retry = upstream.headers.get('retry-after')
  if (retry) res.headers.set('Retry-After', retry)
  return res
}
