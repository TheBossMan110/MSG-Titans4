'use client'

import { useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { ArrowRight, Clock } from 'lucide-react'
import { Badge, Button, Wordmark, Eyebrow, humanise, statusTone } from '@/components/ui/primitives'
import { Field, Input } from '@/components/ui/forms'
import { useAuth } from '@/lib/auth-context'
import { complaints } from '@/lib/api'
import { useApi, fmtRelative } from '@/lib/use-api'

export default function TrackPage() {
  const [ref, setRef] = useState('')
  const router = useRouter()
  const { user } = useAuth()
  const myComplaints = useApi(() => complaints.mine(1, 10), [], Boolean(user))

  return (
    <main className="min-h-dvh px-[var(--gutter)] py-14">
      <div className="mx-auto max-w-[620px]">
        <Link href="/"><Wordmark /></Link>
        <Eyebrow className="mb-4 mt-12">Complaint Details</Eyebrow>
        <h1 className="display text-h1">Track your complaint</h1>
        <p className="mt-5 max-w-[50ch] text-[15px] text-espresso-2">
          Enter the complaint reference from your confirmation to view full status, milestones, answers, and evidence.
        </p>

        <form className="mt-8 flex flex-col gap-4" onSubmit={(e) => { e.preventDefault(); if (ref.trim()) router.push(`/track/${encodeURIComponent(ref.trim().toUpperCase())}`) }}>
          <Field label="Complaint reference" hint="For example CMP-000014">
            {(id) => (
              <Input
                id={id}
                value={ref}
                onChange={(e) => setRef(e.target.value)}
                placeholder="CMP-000000"
                autoFocus
                className="font-mono uppercase"
              />
            )}
          </Field>
          <div className="flex gap-2">
            <Button type="submit" disabled={!ref.trim()}>View Details</Button>
            {!user && <Button href="/login?next=/track" variant="secondary">Sign in first</Button>}
          </div>
        </form>

        {user && myComplaints.data?.items && myComplaints.data.items.length > 0 && (
          <div className="mt-10 rounded-2xl border border-line-soft bg-white/80 p-5 shadow-card">
            <h2 className="text-[13px] font-semibold uppercase tracking-[0.1em] text-taupe-2">Or select from your active complaints</h2>
            <ul className="mt-3 flex flex-col divide-y divide-line-soft">
              {myComplaints.data.items.map((c) => (
                <li key={c.public_ref}>
                  <Link
                    href={`/track/${encodeURIComponent(c.public_ref)}`}
                    className="flex items-center justify-between gap-3 py-3 transition hover:text-espresso"
                  >
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-[13px] font-medium text-espresso">{c.public_ref}</span>
                        <Badge tone={statusTone(c.status)} dot>{humanise(c.status)}</Badge>
                      </div>
                      <p className="mt-0.5 truncate text-[14px] text-espresso-2">{c.title}</p>
                      <p className="mt-0.5 flex items-center gap-1 text-[11.5px] text-taupe-2">
                        <Clock size={11} /> Updated {fmtRelative(c.last_updated)}
                      </p>
                    </div>
                    <ArrowRight size={16} className="shrink-0 text-taupe" />
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        )}

        {user?.role === 'customer' && (
          <p className="mt-8 text-[13.5px] text-taupe-2">
            Back to <Link href="/dashboard/my-complaints" className="text-espresso underline decoration-line underline-offset-4">Customer Dashboard</Link>.
          </p>
        )}
      </div>
    </main>
  )
}
