'use client'

import { Suspense, useEffect, useState } from 'react'
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { useAuth } from '@/lib/auth-context'
import { errorMessage, type User } from '@/lib/api'
import { Button, Wordmark, Eyebrow } from '@/components/ui/primitives'
import { Field, Input } from '@/components/ui/forms'

export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <Login />
    </Suspense>
  )
}

const homeFor = (u: User) => (u.role === 'customer' ? '/dashboard/my-complaints' : '/dashboard')

function Login() {
  const { user, login, loading } = useAuth()
  const router = useRouter()
  const params = useSearchParams()
  const next = params.get('next')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  useEffect(() => {
    if (!loading && user) router.replace(next && next.startsWith('/') ? next : homeFor(user))
  }, [loading, user, next, router])

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setPending(true)
    setError(null)
    try {
      const u = await login(email.trim(), password)
      router.replace(next && next.startsWith('/') ? next : homeFor(u))
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setPending(false)
    }
  }

  return (
    <main className="grid min-h-dvh lg:grid-cols-[1.1fr_1fr]">
      <section className="section-dark grain relative hidden flex-col justify-between p-12 lg:flex">
        <Link href="/"><Wordmark dark /></Link>
        <div>
          <Eyebrow className="mb-6 text-sand-2">Sign in</Eyebrow>
          <h1 className="display text-h1 text-ink-on-dark">
            The AI writes in pencil.
            <span className="display-italic block text-sand-2">The rules confirm in ink.</span>
          </h1>
          <p className="mt-6 max-w-[42ch] text-[15px] text-sand-2">
            Six roles, one register. What you can see and do is decided by the server for
            every request, not by which buttons this page shows you.
          </p>
        </div>
        <p className="text-[12.5px] text-sand-2">RaftarXpress Logistics (Pvt) Ltd · synthetic data only</p>
      </section>

      <section className="flex items-center justify-center px-[var(--gutter)] py-16">
        <div className="w-full max-w-[400px]">
          <Link href="/" className="mb-10 block lg:hidden"><Wordmark /></Link>
          <h2 className="font-display text-h2 leading-none">Welcome back.</h2>
          <p className="mt-3 text-[14px] text-taupe-2">Use the account your administrator provisioned.</p>

          <form onSubmit={submit} className="mt-8 flex flex-col gap-4" noValidate>
            <Field label="Email" required>{(id) => <Input id={id} type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus />}</Field>
            <Field label="Password" required>{(id) => <Input id={id} type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />}</Field>
            {error && <p role="alert" className="rounded-[var(--radius-md)] border border-critical/30 bg-critical-dim px-3.5 py-2.5 text-[13.5px] text-espresso">{error}</p>}
            <Button type="submit" size="lg" loading={pending} className="mt-2 w-full">Sign in</Button>
          </form>

          <div className="mt-8 rounded-[var(--radius-lg)] border border-line bg-ivory p-5 text-[13px] text-taupe-2">
            <p className="eyebrow mb-2">Evaluation accounts</p>
            <p>The seeded staff accounts, one per role, are listed in the backend README with the published demo password. Use <span className="font-mono text-[12px] text-espresso">admin@raftarxpress.com</span> to reach the rule matrix, knowledge base and audit trail.</p>
          </div>

          <p className="mt-6 text-[13px] text-taupe-2">
            No account?{' '}
            <Link href="/register" className="text-espresso underline decoration-line underline-offset-4">Create one</Link>
            {' '}&mdash; sign-up creates a customer account.
          </p>
        </div>
      </section>
    </main>
  )
}
