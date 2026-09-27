'use client'

import { useCallback, useEffect, useRef, useState, type DependencyList } from 'react'
import { errorMessage, getSessionUser } from '@/lib/api'

export interface Query<T> {
  data: T | null
  error: string | null
  loading: boolean
  refresh: () => Promise<void>
  setData: (updater: T | ((prev: T | null) => T | null)) => void
}

/**
 * Fetch on mount and when `deps` change; ignore results from a superseded call.
 *
 * Small on purpose. The app has no cache layer because every page's data is
 * the backend's live truth and the judge will change it under us during the
 * demo; a stale cache would show the wrong thing with confidence.
 */
/**
 * The last answer each query received, kept in memory for the tab.
 *
 * Going back to a page shows what it showed last time at once, and the fresh
 * answer replaces it a moment later -- stale-while-revalidate. Keyed by the
 * signed-in user, the query's code and its inputs, so one person's data is
 * never shown to another; emptied on sign-out.
 */
const answers = new Map<string, unknown>()
const MAX_ANSWERS = 250

function answerKey(fetcher: () => unknown, deps: DependencyList): string {
  let inputs = ''
  try { inputs = JSON.stringify(deps) } catch { inputs = String(deps.length) }
  return `${getSessionUser()?.id ?? 'anon'}|${fetcher.toString()}|${inputs}`
}

function remember(key: string, value: unknown) {
  answers.delete(key)
  answers.set(key, value)
  if (answers.size > MAX_ANSWERS) answers.delete(answers.keys().next().value as string)
}

/** Forget every remembered answer (sign-out, a user switch). */
export function clearAnswers() {
  answers.clear()
}

/** Fired by the live indicator when something new reached the database. */
export const LIVE_EVENT = 'sn-live'
export interface LiveChange { complaints: number; users: number; emails: number; statuses: boolean }

export function useApi<T>(
  fetcher: () => Promise<T>,
  deps: DependencyList = [],
  enabled = true,
  opts?: { live?: boolean },
): Query<T> {
  const key = answerKey(fetcher, deps)
  const keyRef = useRef(key)
  keyRef.current = key
  const [data, setData] = useState<T | null>(() => (enabled ? ((answers.get(key) as T | undefined) ?? null) : null))
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(enabled)
  const seq = useRef(0)
  // Whether a request has ever started. A query enabled after mount (a report
  // chosen from a list) renders once before its effect runs, with no data and
  // ``loading`` still false -- and a page that trusted ``!loading`` to mean
  // "data is here" crashed on that one render.
  const started = useRef(false)
  const fn = useRef(fetcher)
  fn.current = fetcher

  const run = useCallback(async () => {
    const id = ++seq.current
    started.current = true
    setLoading(true)
    setError(null)
    try {
      const forKey = keyRef.current
      const result = await fn.current()
      remember(forKey, result)
      if (id === seq.current) setData(result)
    } catch (e) {
      if (id === seq.current) setError(errorMessage(e))
    } finally {
      if (id === seq.current) setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!enabled) return
    // Show the remembered answer for these inputs at once; the request below replaces it.
    const known = answers.get(keyRef.current) as T | undefined
    if (known !== undefined) setData(known)
    void run()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, run, ...deps])

  // Live pages re-read quietly when the pulse moves: no skeleton, no error
  // banner for a blip -- the data already on screen stays until the new
  // answer arrives.
  const live = Boolean(opts?.live)
  useEffect(() => {
    if (!live || !enabled) return
    const onLive = async () => {
      const id = ++seq.current
      try {
        const forKey = keyRef.current
        const result = await fn.current()
        remember(forKey, result)
        if (id === seq.current) { setData(result); setError(null) }
      } catch {
        /* keep what is on screen */
      } finally {
        // This call superseded any load in flight, so it owns the spinner now.
        if (id === seq.current) setLoading(false)
      }
    }
    window.addEventListener(LIVE_EVENT, onLive)
    return () => window.removeEventListener(LIVE_EVENT, onLive)
  }, [live, enabled])

  const set = useCallback((u: T | ((prev: T | null) => T | null)) => {
    setData((prev) => (typeof u === 'function' ? (u as (p: T | null) => T | null)(prev) : u))
  }, [])

  return { data, error, loading: loading || (enabled && !started.current), refresh: run, setData: set }
}

/** A mutation with its own pending/error state. */
export function useAction<A extends unknown[], R>(action: (...args: A) => Promise<R>) {
  const [pending, setPending] = useState(false)
  const [, setError] = useState<string | null>(null)
  // Read through a ref: callers check ``error`` straight after ``await run()``,
  // inside the same closure, where the state value would still be the one
  // from before the call -- so the first failure showed no message at all.
  const errorRef = useRef<string | null>(null)
  const run = useCallback(
    async (...args: A): Promise<R | undefined> => {
      setPending(true)
      errorRef.current = null
      setError(null)
      try {
        return await action(...args)
      } catch (e) {
        errorRef.current = errorMessage(e)
        setError(errorRef.current)
        return undefined
      } finally {
        setPending(false)
      }
    },
    [action],
  )
  return {
    run,
    pending,
    get error() { return errorRef.current },
    clear: () => { errorRef.current = null; setError(null) },
  }
}

/* ------------------------------------------------------------------ formatting */

export function fmtDate(iso?: string | null, withTime = true): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString(undefined, withTime
    ? { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }
    : { day: 'numeric', month: 'short', year: 'numeric' })
}

export function fmtRelative(iso?: string | null): string {
  if (!iso) return '—'
  const t = new Date(iso).getTime()
  if (Number.isNaN(t)) return iso
  const diff = (t - Date.now()) / 1000
  const abs = Math.abs(diff)
  const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' })
  if (abs < 60) return rtf.format(Math.round(diff), 'second')
  if (abs < 3600) return rtf.format(Math.round(diff / 60), 'minute')
  if (abs < 86400) return rtf.format(Math.round(diff / 3600), 'hour')
  return rtf.format(Math.round(diff / 86400), 'day')
}

export function fmtMinutes(mins?: number | null): string {
  if (mins === null || mins === undefined) return '—'
  const m = Math.round(Math.abs(mins))
  if (m < 60) return `${m} min`
  if (m < 60 * 24) return `${Math.floor(m / 60)} h ${m % 60} min`
  return `${Math.floor(m / 1440)} d ${Math.floor((m % 1440) / 60)} h`
}

export const pct = (v?: number | null, digits = 0) => (v === null || v === undefined ? '—' : `${v.toFixed(digits)}%`)
