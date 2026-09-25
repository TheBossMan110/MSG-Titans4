'use client'

import { useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { Button, Wordmark, Eyebrow } from '@/components/ui/primitives'
import { Field, Input } from '@/components/ui/forms'
import { useAuth } from '@/lib/auth-context'

export default function TrackPage() {
  const [ref, setRef] = useState('')
  const router = useRouter()
  const { user } = useAuth()
  return (
    <main className="min-h-dvh px-[var(--gutter)] py-14">
      <div className="mx-auto max-w-[560px]">
        <Link href="/"><Wordmark /></Link>
        <Eyebrow className="mb-4 mt-12">Track a complaint</Eyebrow>
        <h1 className="display text-h1">Where is it now?</h1>
        <p className="mt-5 max-w-[48ch] text-[15px] text-espresso-2">
          Enter the reference from your confirmation. You will be asked to sign in: a
          reference alone is guessable, so the register checks that the complaint is yours
          before it shows you anything.
        </p>
        <form className="mt-8 flex flex-col gap-4" onSubmit={(e) => { e.preventDefault(); if (ref.trim()) router.push(`/track/${encodeURIComponent(ref.trim().toUpperCase())}`) }}>
          <Field label="Complaint reference" hint="For example CMP-000014">{(id) => <Input id={id} value={ref} onChange={(e) => setRef(e.target.value)} placeholder="CMP-000000" autoFocus className="font-mono uppercase" />}</Field>
          <div className="flex gap-2"><Button type="submit" disabled={!ref.trim()}>Track</Button>{!user && <Button href="/login?next=/track" variant="secondary">Sign in first</Button>}</div>
        </form>
        {user?.role === 'customer' && <p className="mt-8 text-[13.5px] text-taupe-2">Or see <Link href="/dashboard/my-complaints" className="text-espresso underline decoration-line underline-offset-4">all of your complaints</Link>.</p>}
      </div>
    </main>
  )
}
