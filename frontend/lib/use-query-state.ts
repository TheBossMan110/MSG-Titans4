'use client'

import { usePathname, useRouter, useSearchParams } from 'next/navigation'

/**
 * One value kept in the address bar's query string instead of in component
 * state, so that a sidebar link, a bookmark or a shared URL opens the page in
 * that state, and the page follows when only the query changes.
 *
 * That last part is why it exists. Two sidebar entries that lead to the same
 * page (Departments and Categories both open /dashboard/organisation) do not
 * remount it; a tab held in useState stayed where it was and the second link
 * appeared to do nothing. Read from the URL, the tab moves with the link.
 *
 * Setting the fallback removes the parameter, so the default state keeps the
 * plain URL. Callers must sit inside a <Suspense> boundary (useSearchParams).
 */
export function useQueryState(name: string, fallback = ''): [string, (value: string) => void] {
  const params = useSearchParams()
  const router = useRouter()
  const pathname = usePathname()
  const value = params.get(name) ?? fallback
  const set = (next: string) => {
    const query = new URLSearchParams(params.toString())
    if (next === fallback || next === '') query.delete(name)
    else query.set(name, next)
    const s = query.toString()
    router.replace(s ? `${pathname}?${s}` : pathname, { scroll: false })
  }
  return [value, set]
}

/** A page's tab as ``?tab=``; an unknown or missing value is the fallback tab. */
export function useTabParam<T extends string>(allowed: readonly T[], fallback: T): [T, (tab: T) => void] {
  const [raw, set] = useQueryState('tab', fallback)
  const tab = (allowed as readonly string[]).includes(raw) ? (raw as T) : fallback
  return [tab, set as (tab: T) => void]
}
