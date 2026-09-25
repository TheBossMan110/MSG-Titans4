'use client'

import { Suspense, useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { useAuth } from '@/lib/auth-context'
import { errorMessage } from '@/lib/api'
import { Badge, Button, Eyebrow, Wordmark } from '@/components/ui/primitives'
import { Field, Input, PasswordInput } from '@/components/ui/forms'
import { cn } from '@/lib/utils'

const MIN_PASSWORD = 12

export default function RegisterPage() {
  return (
    <Suspense fallback={null}>
      <Register />
    </Suspense>
  )
}

function Register() {
  const { user, register, loading } = useAuth()
  const router = useRouter()
  const params = useSearchParams()
  const next = params.get('next')

  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [touched, setTouched] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  useEffect(() => {
    if (!loading && user) router.replace(next && next.startsWith('/') ? next : '/dashboard/my-complaints')
  }, [loading, user, next, router])

  const tooShort = password.length > 0 && password.length < MIN_PASSWORD
  const mismatch = confirm.length > 0 && confirm !== password
  const ready = fullName.trim().length >= 2 && email.includes('@') && password.length >= MIN_PASSWORD && confirm === password

  const strength = useMemo(() => {
    let score = 0
    if (password.length >= MIN_PASSWORD) score++
    if (password.length >= 16) score++
    if (/[^a-zA-Z0-9]/.test(password)) score++
    if (/\d/.test(password) && /[a-zA-Z]/.test(password)) score++
    return score
  }, [password])

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setTouched(true)
    if (!ready) return
    setPending(true)
    setError(null)
    try {
      await register(email.trim(), fullName.trim(), password)
      router.replace(next && next.startsWith('/') ? next : '/dashboard/my-complaints')
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setPending(false)
    }
  }

  return (
    <main className="grid min-h-dvh lg:grid-cols-[1fr_1.1fr]">
      <section className="flex items-center justify-center px-[var(--gutter)] py-14">
        <div className="w-full max-w-[420px]">
          <Link href="/" className="mb-10 block"><Wordmark /></Link>

          <Eyebrow className="mb-4">Create an account</Eyebrow>
          <h1 className="display text-h2">Track your complaint from the inside.</h1>
          <p className="mt-3 text-[14.5px] text-taupe-2">
            Sign up to submit a complaint and follow every step the system takes on it.
          </p>

          <form onSubmit={submit} className="mt-8 flex flex-col gap-4" noValidate>
            <Field label="Full name" required error={touched && fullName.trim().length < 2 ? 'Please give your name.' : null}>
              {(id) => <Input id={id} value={fullName} onChange={(e) => setFullName(e.target.value)} autoComplete="name" required autoFocus />}
            </Field>

            <Field label="Email" required error={touched && !email.includes('@') ? 'Please give a valid email address.' : null}>
              {(id) => <Input id={id} type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" required />}
            </Field>

            <Field
              label="Password"
              required
              error={tooShort ? `At least ${MIN_PASSWORD} characters.` : null}
              hint={!tooShort ? `At least ${MIN_PASSWORD} characters. A passphrase beats a short complicated word.` : undefined}
            >
              {(id) => <PasswordInput id={id} value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" required minLength={MIN_PASSWORD} />}
            </Field>

            {password.length > 0 && (
              <div className="-mt-1 flex items-center gap-2" aria-hidden>
                {[0, 1, 2, 3].map((i) => (
                  <span
                    key={i}
                    className={cn(
                      'h-1 flex-1 rounded-full transition-colors duration-300',
                      i < strength ? (strength <= 1 ? 'bg-critical' : strength === 2 ? 'bg-warning' : 'bg-verified') : 'bg-sand',
                    )}
                  />
                ))}
                <span className="w-16 text-right text-[11.5px] text-taupe-2">
                  {strength <= 1 ? 'weak' : strength === 2 ? 'fair' : strength === 3 ? 'good' : 'strong'}
                </span>
              </div>
            )}

            <Field label="Repeat password" required error={mismatch ? 'The two passwords do not match.' : null}>
              {(id) => <PasswordInput id={id} value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="new-password" required />}
            </Field>

            {error && (
              <p role="alert" className="rounded-[var(--radius-md)] border border-critical/30 bg-critical-dim px-3.5 py-2.5 text-[13.5px] text-espresso">
                {error}
              </p>
            )}

            <Button type="submit" size="lg" loading={pending} disabled={!ready} className="mt-2 w-full">
              Create account
            </Button>
          </form>

          <p className="mt-6 text-[13px] text-taupe-2">
            Already have one?{' '}
            <Link href="/login" className="text-espresso underline decoration-line underline-offset-4">Sign in</Link>
          </p>
        </div>
      </section>

      <section className="section-dark grain relative hidden flex-col justify-center px-[clamp(40px,5vw,80px)] py-14 lg:flex">
        <Eyebrow className="mb-6 text-sand-2">What this account can do</Eyebrow>
        <h2 className="display text-h2 text-ink-on-dark">
          A customer account,
          <span className="display-italic block text-sand-2">and only a customer account.</span>
        </h2>
        <p className="mt-6 max-w-[46ch] text-[15px] text-sand-2">
          Signing up creates a <b className="text-ink-on-dark">customer</b>. You can submit
          complaints and read your own &mdash; nothing else. Agent, reviewer, manager,
          administrator and evaluator accounts are created by an administrator, because a
          form that let you pick your own authority would make every permission check in
          the system decorative.
        </p>

        <ul className="mt-10 flex flex-col gap-3 text-[14px] text-ink-on-dark/90">
          {[
            'Submit a complaint and watch both pipelines run on it',
            'Track its status, category and escalation as they change',
            'See the questions the system needs answered',
            'Read the resolution once the rules have confirmed it',
          ].map((t) => (
            <li key={t} className="flex items-start gap-3">
              <span aria-hidden className="mt-[7px] size-1.5 shrink-0 rounded-full bg-sand-2" />
              {t}
            </li>
          ))}
        </ul>

        <div className="mt-10 border-t border-ink-on-dark/15 pt-6">
          <p className="eyebrow mb-3 text-sand-2">Evaluating this project?</p>
          <p className="max-w-[46ch] text-[13.5px] text-sand-2">
            The seeded staff accounts, one per role, are listed in the backend README with
            their published demo password. Use those to reach the dashboard, rule matrix
            and audit trail.
          </p>
          <div className="mt-4 flex flex-wrap gap-1.5">
            {['customer', 'agent', 'reviewer', 'manager', 'admin', 'evaluator'].map((r) => (
              <Badge key={r} tone={r === 'customer' ? 'verified' : 'neutral'} className="border-ink-on-dark/20 bg-ink-on-dark/10 text-ink-on-dark">{r}</Badge>
            ))}
          </div>
        </div>
      </section>
    </main>
  )
}
