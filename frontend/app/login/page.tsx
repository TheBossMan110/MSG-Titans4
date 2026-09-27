'use client'

import { Suspense, useEffect, useState } from 'react'
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { useAuth } from '@/lib/auth-context'
import { errorMessage, type User } from '@/lib/api'
import { ShieldCheck } from 'lucide-react'
import { BrandMark, Button, Wordmark, Eyebrow } from '@/components/ui/primitives'
import { Field, Input, PasswordInput } from '@/components/ui/forms'
import { homeFor as roleHome } from '@/lib/roles'

export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <Login />
    </Suspense>
  )
}

// Each of the five roles lands on its own dashboard (lib/roles.ts).
const homeFor = (u: User) => roleHome(u.role)

function Login() {
  const { user, login, completeMfa, loading } = useAuth()
  const router = useRouter()
  const params = useSearchParams()
  const next = params.get('next')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  // Set once the password is accepted on an account with two-step sign-in.
  const [mfaToken, setMfaToken] = useState<string | null>(null)
  const [code, setCode] = useState('')

  useEffect(() => {
    if (!loading && user) router.replace(next && next.startsWith('/') ? next : homeFor(user))
  }, [loading, user, next, router])

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setPending(true)
    setError(null)
    try {
      const u = mfaToken ? await completeMfa(mfaToken, code.trim()) : await login(email.trim(), password)
      if ('mfaToken' in u) {
        setMfaToken(u.mfaToken)
        return
      }
      router.replace(next && next.startsWith('/') ? next : homeFor(u))
    } catch (err) {
      // A step token lasts five minutes; after that the password is needed again.
      if (mfaToken && /took too long/i.test(errorMessage(err))) { setMfaToken(null); setCode('') }
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
          <BrandMark size={72} className="mb-7 hidden lg:block" />
          <h2 className="font-display text-h2 leading-none">Welcome back.</h2>
          <p className="mt-3 text-[14px] text-taupe-2">Use the account your administrator provisioned.</p>

          <form onSubmit={submit} className="mt-8 flex flex-col gap-4" noValidate>
            {mfaToken ? (
              <>
                <div className="flex items-start gap-3 rounded-[var(--radius-lg)] border border-line bg-ivory p-4">
                  <ShieldCheck size={20} className="mt-0.5 shrink-0 text-rule" aria-hidden />
                  <p className="text-[13.5px] leading-relaxed text-espresso-2">
                    Your password was right. Now enter the 6-digit code from your authenticator app, or one of your recovery codes.
                  </p>
                </div>
                <Field label="Verification code" required>{(id) => (
                  <Input id={id} inputMode="numeric" autoComplete="one-time-code" value={code} onChange={(e) => setCode(e.target.value)} required autoFocus maxLength={16} className="text-center font-mono text-[20px] tracking-[0.3em]" placeholder="000000" />
                )}</Field>
              </>
            ) : (
              <>
                <Field label="Email" required>{(id) => <Input id={id} type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus />}</Field>
                <Field label="Password" required>{(id) => <PasswordInput id={id} autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />}</Field>
              </>
            )}
            {error && <p role="alert" className="rounded-[var(--radius-md)] border border-critical/30 bg-critical-dim px-3.5 py-2.5 text-[13.5px] text-espresso">{error}</p>}
            <Button type="submit" size="lg" loading={pending} className="mt-2 w-full">{mfaToken ? 'Verify and sign in' : 'Sign in'}</Button>
            {mfaToken && <button type="button" onClick={() => { setMfaToken(null); setCode(''); setError(null) }} className="text-[13px] text-taupe-2 underline underline-offset-4">Use a different account</button>}
          </form>

          <p className="mt-8 text-[13px] text-taupe-2">
            No account?{' '}
            <Link href="/register" className="text-espresso underline decoration-line underline-offset-4">Create one</Link>
            {' '}&mdash; sign-up creates a customer account.
          </p>
        </div>
      </section>
    </main>
  )
}
