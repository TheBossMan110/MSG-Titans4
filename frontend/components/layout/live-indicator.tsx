'use client'

import { useEffect, useRef, useState } from 'react'
import { Activity } from 'lucide-react'
import { live, type S } from '@/lib/api'
import { LIVE_EVENT, type LiveChange } from '@/lib/use-api'
import { useToast } from '@/components/ui/feedback'
import { cn } from '@/lib/utils'

const EVERY_MS = 8000

/**
 * "Live data", made true. Polls the pulse every few seconds while the tab is
 * visible; when a counter moves -- a complaint filed through the form, the
 * chat or email, a new account, an email, any status change -- it says what
 * arrived and tells every open page to refresh itself (pages opt in with
 * ``useApi(..., { live: true })``). Nothing is cached: the page re-reads the
 * database, so what it shows is what is stored.
 */
export function LiveIndicator({ oversight }: { oversight: boolean }) {
  const toast = useToast()
  const last = useRef<S['Pulse'] | null>(null)
  const [state, setState] = useState<'live' | 'offline'>('live')
  const [flash, setFlash] = useState(false)
  const [checkedAt, setCheckedAt] = useState<number | null>(null)
  const [, tick] = useState(0)

  useEffect(() => {
    let stopped = false
    let timer: ReturnType<typeof setTimeout> | undefined

    const check = async () => {
      if (stopped) return
      if (document.visibilityState === 'visible') {
        try {
          const now = await live.pulse()
          const before = last.current
          last.current = now
          setState('live')
          setCheckedAt(Date.now())
          if (before) {
            const change: LiveChange = {
              complaints: now.complaints - before.complaints,
              users: now.users - before.users,
              emails: now.emails_in - before.emails_in,
              statuses: now.status_changes !== before.status_changes,
            }
            if (change.complaints || change.users || change.emails || change.statuses) {
              window.dispatchEvent(new CustomEvent<LiveChange>(LIVE_EVENT, { detail: change }))
              setFlash(true)
              setTimeout(() => setFlash(false), 1600)
              if (change.complaints > 0) {
                toast('ok', change.complaints === 1 && now.latest_complaint_ref ? `New complaint ${now.latest_complaint_ref} received.` : `${change.complaints} new complaints received.`)
              }
              if (oversight && change.users > 0) {
                toast('ok', change.users === 1 && now.latest_user_name ? `New account: ${now.latest_user_name}.` : `${change.users} new accounts.`)
              }
              if (change.emails > 0) {
                toast('ok', change.emails === 1 && now.latest_email_from ? `New email from ${now.latest_email_from}.` : `${change.emails} new emails.`)
              }
            }
          }
        } catch {
          setState('offline')
        }
      }
      timer = setTimeout(check, EVERY_MS)
    }

    void check()
    const onVisible = () => { if (document.visibilityState === 'visible') { clearTimeout(timer); void check() } }
    document.addEventListener('visibilitychange', onVisible)
    const clock = setInterval(() => tick((n) => n + 1), 5000)
    return () => { stopped = true; clearTimeout(timer); clearInterval(clock); document.removeEventListener('visibilitychange', onVisible) }
  }, [oversight, toast])

  const seconds = checkedAt ? Math.max(0, Math.round((Date.now() - checkedAt) / 1000)) : null
  const label = state === 'offline' ? 'Reconnecting' : seconds === null ? 'Live data' : seconds < 10 ? 'Live · just now' : `Live · ${seconds}s ago`

  return (
    <span
      className={cn(
        'hidden items-center gap-2 rounded-full border px-3 py-1 text-[12px] transition-colors duration-500 md:inline-flex',
        flash ? 'border-verified/40 bg-verified-dim text-verified' : 'border-line-soft bg-white/70 text-taupe-2',
      )}
      title="Checks for new complaints, accounts and emails every few seconds, and refreshes this page when something arrives."
    >
      <span className="relative inline-flex size-2" aria-hidden>
        {state === 'live' && <span className="absolute inline-flex size-full animate-ping rounded-full bg-verified/60 [.reduce-motion_&]:hidden" />}
        <span className={cn('relative inline-flex size-2 rounded-full', state === 'live' ? 'bg-verified' : 'bg-warning')} />
      </span>
      <Activity size={13} className={state === 'live' ? 'text-verified' : 'text-warning'} aria-hidden />
      {label}
    </span>
  )
}
