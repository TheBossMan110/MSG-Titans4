'use client'

import { useEffect, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import QRCode from 'qrcode'
import {
  AlertTriangle, CheckCircle2, Copy, Download, KeyRound, Laptop, LogOut, Monitor, ShieldCheck,
  ShieldOff, Smartphone, UserRound, XCircle,
} from 'lucide-react'
import { AppShell } from '@/components/layout/app-shell'
import { useAuth } from '@/lib/auth-context'
import { auth, type S } from '@/lib/api'
import { useAction, useApi, fmtDate, fmtRelative } from '@/lib/use-api'
import { Badge, Button, Mono, humanise } from '@/components/ui/primitives'
import { Card, PanelHeader } from '@/components/ui/surfaces'
import { Field, Input, PasswordInput } from '@/components/ui/forms'
import { ErrorState, SkeletonRows, useToast } from '@/components/ui/feedback'
import { cn } from '@/lib/utils'

export default function ProfilePage() {
  return (
    <AppShell eyebrow="Profile & security">
      <Profile />
    </AppShell>
  )
}

function Profile() {
  const { user } = useAuth()
  const security = useApi(() => auth.security())
  if (!user) return null
  const s = security.data

  return (
    <div className="flex min-w-0 flex-col gap-6">
      <Identity />

      <section aria-label="Security at a glance" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Glance
          ok={s ? s.mfa_enabled : undefined}
          title="Two-step sign-in"
          value={s ? (s.mfa_enabled ? 'On' : 'Off') : undefined}
          note={s ? (s.mfa_enabled ? `${s.recovery_codes_left} recovery codes left` : 'Recommended: turn it on below') : undefined}
        />
        <Glance ok={s ? true : undefined} title="Password" value={s ? (s.password_changed_at ? `Changed ${fmtRelative(s.password_changed_at)}` : 'Set at sign-up') : undefined} note="At least 12 characters" />
        <Glance ok={s ? s.active_sessions <= 3 : undefined} title="Signed in on" value={s ? `${s.active_sessions} ${s.active_sessions === 1 ? 'device' : 'devices'}` : undefined} note="Review them below" />
        <Glance ok={s ? !s.locked_until : undefined} title="Last sign-in" value={s ? fmtRelative(s.last_login_at) : undefined} note="Locks after 5 wrong passwords" />
      </section>

      <div className="grid gap-6 xl:grid-cols-2">
        <TwoStep overview={s ?? undefined} onChange={security.refresh} />
        <Password onChange={security.refresh} />
      </div>
      <Sessions onChange={security.refresh} />
      <Activity />
    </div>
  )
}

function Glance({ ok, title, value, note }: { ok?: boolean; title: string; value?: string; note?: string }) {
  return (
    <Card tone="glass" padding="sm" radius="lg" className="flex items-start gap-3">
      <span className={cn('mt-0.5 inline-flex size-9 shrink-0 items-center justify-center rounded-full', ok === undefined ? 'bg-sand' : ok ? 'bg-verified-dim text-verified' : 'bg-warning-dim text-warning')}>
        {ok === false ? <AlertTriangle size={17} aria-hidden /> : <ShieldCheck size={17} aria-hidden />}
      </span>
      <div className="min-w-0">
        <p className="eyebrow">{title}</p>
        <p className="mt-1 text-[15px] font-medium text-espresso">{value ?? '…'}</p>
        {note && <p className="text-[12.5px] text-taupe-2">{note}</p>}
      </div>
    </Card>
  )
}

/* ------------------------------------------------------------------ identity */

function Identity() {
  const { user, refreshUser } = useAuth()
  const toast = useToast()
  const [name, setName] = useState(user?.full_name ?? '')
  const save = useAction((n: string) => auth.updateMe(n))
  useEffect(() => { setName(user?.full_name ?? '') }, [user?.full_name])
  if (!user) return null
  const initials = user.full_name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]?.toUpperCase()).join('')
  const changed = name.trim() !== user.full_name && name.trim().length >= 2

  return (
    <Card tone="glass" radius="xl" className="grid gap-6 lg:grid-cols-[auto_1fr_1fr] lg:items-center">
      <div className="flex items-center gap-4">
        <span className="inline-flex size-16 shrink-0 items-center justify-center rounded-full bg-espresso font-display text-[24px] text-ink-on-dark" aria-hidden>{initials || <UserRound size={24} />}</span>
        <div className="min-w-0 lg:hidden">
          <p className="truncate font-display text-[22px] leading-tight text-espresso">{user.full_name}</p>
          <p className="truncate text-[13.5px] text-taupe-2">{user.email}</p>
        </div>
      </div>
      <dl className="grid grid-cols-[max-content_1fr] gap-x-5 gap-y-2 text-[14px]">
        <dt className="text-taupe-2">Email</dt><dd className="min-w-0 truncate text-espresso">{user.email}</dd>
        <dt className="text-taupe-2">Role</dt><dd><Badge tone="ink">{humanise(user.role)}</Badge></dd>
        {user.department && <><dt className="text-taupe-2">Team</dt><dd className="text-espresso">{user.department.name}</dd></>}
        <dt className="text-taupe-2">Member since</dt><dd className="text-espresso">{fmtDate(user.created_at, false)}</dd>
      </dl>
      <form
        className="flex flex-col gap-3"
        onSubmit={async (e) => {
          e.preventDefault()
          const r = await save.run(name.trim())
          if (r) { await refreshUser(); toast('ok', 'Your name has been updated.') } else if (save.error) toast('err', save.error)
        }}
      >
        <Field label="Your name" hint="Shown to staff on the complaints you raise.">{(id) => <Input id={id} value={name} onChange={(e) => setName(e.target.value)} maxLength={120} autoComplete="name" />}</Field>
        <div><Button type="submit" size="sm" loading={save.pending} disabled={!changed}>Save name</Button></div>
      </form>
    </Card>
  )
}

/* ------------------------------------------------------------------ two-step */

function TwoStep({ overview, onChange }: { overview?: S['SecurityOverview']; onChange: () => void }) {
  const toast = useToast()
  const [setup, setSetup] = useState<S['MfaSetupOut'] | null>(null)
  const [qr, setQr] = useState<string | null>(null)
  const [code, setCode] = useState('')
  const [codes, setCodes] = useState<string[] | null>(null)
  const [disabling, setDisabling] = useState(false)
  const [password, setPassword] = useState('')
  const begin = useAction(() => auth.mfaSetup())
  const enable = useAction((c: string) => auth.mfaEnable(c))
  const disable = useAction((p: string, c: string) => auth.mfaDisable(p, c))
  const regenerate = useAction((c: string) => auth.mfaRecoveryCodes(c))

  useEffect(() => {
    if (!setup) { setQr(null); return }
    QRCode.toDataURL(setup.otpauth_uri, { margin: 1, width: 220, color: { dark: '#2a1f17', light: '#fbf8f2' } })
      .then(setQr).catch(() => setQr(null))
  }, [setup])

  const on = overview?.mfa_enabled

  return (
    <Card radius="xl" className="flex flex-col gap-5">
      <PanelHeader title="Two-step sign-in" eyebrow={on ? <Badge tone="verified" dot>On</Badge> : <Badge tone="warning" dot>Off</Badge>} />
      <p className="text-[14px] leading-relaxed text-espresso-2">
        With two-step sign-in, a stolen password is not enough: signing in also needs the 6-digit code
        from an authenticator app on your phone (Google Authenticator, Microsoft Authenticator, Authy…).
      </p>

      {codes && (
        <RecoveryCodes codes={codes} onDone={() => setCodes(null)} />
      )}

      {!codes && !on && !setup && (
        <div><Button icon={<Smartphone size={16} aria-hidden />} loading={begin.pending} onClick={async () => { const r = await begin.run(); if (r) setSetup(r); else if (begin.error) toast('err', begin.error) }}>Set up two-step sign-in</Button></div>
      )}

      {!codes && !on && setup && (
        <div className="grid gap-5 md:grid-cols-[auto_1fr]">
          <div className="mx-auto flex flex-col items-center gap-2">
            {qr ? <img src={qr} alt="QR code to scan with your authenticator app" width={180} height={180} className="rounded-xl border border-line" /> : <div className="size-[180px] animate-pulse rounded-xl bg-sand" />}
            <p className="text-[12px] text-taupe-2">Scan with your app</p>
          </div>
          <form
            className="flex min-w-0 flex-col gap-3"
            onSubmit={async (e) => {
              e.preventDefault()
              const r = await enable.run(code.trim())
              if (r) { setCodes(r.codes); setSetup(null); setCode(''); onChange(); toast('ok', 'Two-step sign-in is on.') } else if (enable.error) toast('err', enable.error)
            }}
          >
            <p className="text-[13.5px] text-espresso-2">Can’t scan? Type this key into the app instead:</p>
            <Mono className="rounded-lg border border-line bg-ivory px-3 py-2 text-[13px] tracking-[0.12em] text-espresso">{setup.secret.match(/.{1,4}/g)?.join(' ')}</Mono>
            <Field label="Code from the app" hint="Enter the 6 digits it shows now.">{(id) => (
              <Input id={id} inputMode="numeric" autoComplete="one-time-code" value={code} onChange={(e) => setCode(e.target.value)} maxLength={6} className="font-mono text-[18px] tracking-[0.3em]" placeholder="000000" />
            )}</Field>
            <div className="flex flex-wrap gap-2">
              <Button type="submit" loading={enable.pending} disabled={code.trim().length !== 6}>Turn on</Button>
              <Button type="button" variant="ghost" onClick={() => { setSetup(null); setCode('') }}>Cancel</Button>
            </div>
          </form>
        </div>
      )}

      {!codes && on && (
        <div className="flex flex-col gap-4">
          <p className="flex items-center gap-2 text-[13.5px] text-taupe-2"><CheckCircle2 size={15} className="text-verified" aria-hidden /> On since {fmtDate(overview?.mfa_enabled_at, false)} · {overview?.recovery_codes_left ?? 0} recovery codes unused</p>
          {!disabling ? (
            <form
              className="flex flex-wrap items-end gap-2"
              onSubmit={async (e) => {
                e.preventDefault()
                const r = await regenerate.run(code.trim())
                if (r) { setCodes(r.codes); setCode(''); onChange() } else if (regenerate.error) toast('err', regenerate.error)
              }}
            >
              <Field label="Current code" className="w-[160px]">{(id) => <Input id={id} inputMode="numeric" value={code} onChange={(e) => setCode(e.target.value)} maxLength={16} className="font-mono" placeholder="000000" />}</Field>
              <Button type="submit" variant="secondary" loading={regenerate.pending} disabled={code.trim().length < 6} icon={<KeyRound size={15} aria-hidden />}>New recovery codes</Button>
              <Button type="button" variant="ghost" onClick={() => setDisabling(true)} icon={<ShieldOff size={15} aria-hidden />}>Turn off…</Button>
            </form>
          ) : (
            <form
              className="flex flex-col gap-3 rounded-2xl border border-warning/30 bg-warning-dim/50 p-4"
              onSubmit={async (e) => {
                e.preventDefault()
                const r = await disable.run(password, code.trim())
                if (r) { toast('ok', r.message); setDisabling(false); setPassword(''); setCode(''); onChange() } else if (disable.error) toast('err', disable.error)
              }}
            >
              <p className="text-[13.5px] text-espresso-2">Turning this off makes your account easier to break into. Confirm with your password and a current code.</p>
              <div className="grid gap-3 sm:grid-cols-2">
                <Field label="Password">{(id) => <PasswordInput id={id} autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />}</Field>
                <Field label="Code">{(id) => <Input id={id} inputMode="numeric" value={code} onChange={(e) => setCode(e.target.value)} maxLength={16} className="font-mono" placeholder="000000" />}</Field>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button type="submit" variant="danger" loading={disable.pending} disabled={!password || code.trim().length < 6}>Turn off two-step sign-in</Button>
                <Button type="button" variant="ghost" onClick={() => { setDisabling(false); setPassword(''); setCode('') }}>Keep it on</Button>
              </div>
            </form>
          )}
        </div>
      )}
    </Card>
  )
}

function RecoveryCodes({ codes, onDone }: { codes: string[]; onDone: () => void }) {
  const toast = useToast()
  const text = codes.join('\n')
  return (
    <div className="flex flex-col gap-3 rounded-2xl border border-rule-line bg-rule-soft/60 p-4">
      <p className="text-[14px] font-medium text-rule">Save these recovery codes now</p>
      <p className="text-[13px] text-espresso-2">If you lose your phone, each code signs you in once. They will not be shown again.</p>
      <ul className="grid grid-cols-2 gap-2 font-mono text-[14px] text-espresso">{codes.map((c) => <li key={c} className="rounded-lg bg-white/80 px-3 py-1.5 text-center">{c}</li>)}</ul>
      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="secondary" size="sm" icon={<Copy size={14} aria-hidden />} onClick={async () => { try { await navigator.clipboard.writeText(text); toast('ok', 'Copied.') } catch { toast('err', 'Copy failed; select the codes instead.') } }}>Copy</Button>
        <Button type="button" variant="secondary" size="sm" icon={<Download size={14} aria-hidden />} onClick={() => { const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([`SupportNova recovery codes\n\n${text}\n`], { type: 'text/plain' })); a.download = 'supportnova-recovery-codes.txt'; a.click(); URL.revokeObjectURL(a.href) }}>Download</Button>
        <Button type="button" size="sm" onClick={onDone}>I have saved them</Button>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ password */

function strength(pw: string): { score: number; label: string } {
  let score = 0
  if (pw.length >= 12) score++
  if (pw.length >= 16) score++
  if (/[a-z]/.test(pw) && /[A-Z]/.test(pw)) score++
  if (/\d/.test(pw)) score++
  if (/[^A-Za-z0-9]/.test(pw)) score++
  const label = pw.length < 12 ? 'Too short' : ['Weak', 'Weak', 'Fair', 'Good', 'Strong', 'Very strong'][score]
  return { score, label }
}

function Password({ onChange }: { onChange: () => void }) {
  const toast = useToast()
  const [cur, setCur] = useState(''); const [nw, setNw] = useState(''); const [again, setAgain] = useState('')
  const change = useAction((a: string, b: string) => auth.changePassword(a, b))
  const st = useMemo(() => strength(nw), [nw])
  return (
    <Card radius="xl">
      <PanelHeader title="Password" />
      <form
        className="flex flex-col gap-4"
        onSubmit={async (e) => {
          e.preventDefault()
          if (nw !== again) { toast('err', 'The new passwords do not match.'); return }
          const r = await change.run(cur, nw)
          if (r) { toast('ok', r.message); setCur(''); setNw(''); setAgain(''); onChange() } else if (change.error) toast('err', change.error)
        }}
      >
        <Field label="Current password">{(id) => <PasswordInput id={id} autoComplete="current-password" value={cur} onChange={(e) => setCur(e.target.value)} required />}</Field>
        <Field label="New password" hint="At least 12 characters. A short sentence is easy to remember and hard to guess.">{(id) => <PasswordInput id={id} autoComplete="new-password" value={nw} onChange={(e) => setNw(e.target.value)} required minLength={12} />}</Field>
        {nw && (
          <div className="-mt-2 flex items-center gap-3" aria-live="polite">
            <div className="flex h-1.5 flex-1 gap-1">{[0, 1, 2, 3, 4].map((i) => <span key={i} className={cn('h-full flex-1 rounded-full', i < st.score ? (st.score >= 4 ? 'bg-verified' : st.score >= 3 ? 'bg-rule-2' : 'bg-warning-glow') : 'bg-sand')} />)}</div>
            <span className="text-[12.5px] text-taupe-2">{st.label}</span>
          </div>
        )}
        <Field label="Repeat new password" error={again && again !== nw ? 'Does not match.' : null}>{(id) => <PasswordInput id={id} autoComplete="new-password" value={again} onChange={(e) => setAgain(e.target.value)} required />}</Field>
        <p className="text-[12.5px] text-taupe-2">Changing it signs you out on every other device.</p>
        <div><Button type="submit" loading={change.pending} disabled={!cur || nw.length < 12 || nw !== again}>Change password</Button></div>
      </form>
    </Card>
  )
}

/* ------------------------------------------------------------------ sessions */

function Sessions({ onChange }: { onChange: () => void }) {
  const toast = useToast()
  const { logout } = useAuth()
  const router = useRouter()
  const q = useApi(() => auth.sessions())
  const one = useAction((id: string) => auth.revokeSession(id))
  const others = useAction(() => auth.revokeOtherSessions())
  const rows = q.data ?? []
  const otherCount = rows.filter((r) => !r.current).length

  return (
    <Card radius="xl">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <PanelHeader title="Where you are signed in" className="mb-0" />
        <Button variant="secondary" size="sm" icon={<LogOut size={15} aria-hidden />} disabled={!otherCount} loading={others.pending}
          onClick={async () => { const r = await others.run(); if (r) { toast('ok', r.message); q.refresh(); onChange() } else if (others.error) toast('err', others.error) }}>
          Sign out everywhere else
        </Button>
      </div>
      {q.error ? <ErrorState message={q.error} onRetry={q.refresh} /> : !q.data ? <SkeletonRows rows={3} /> : (
        <ul className="divide-y divide-line-soft">
          {rows.map((s) => {
            const mobile = /iPhone|Android|iPad/.test(s.device)
            const Icon = mobile ? Smartphone : /Windows|macOS|Linux/.test(s.device) ? Laptop : Monitor
            return (
              <li key={s.id} className="flex flex-wrap items-center gap-x-4 gap-y-2 py-3.5">
                <span className="inline-flex size-10 shrink-0 items-center justify-center rounded-full bg-sand/70 text-espresso-2"><Icon size={18} aria-hidden /></span>
                <div className="min-w-0 flex-1">
                  <p className="flex flex-wrap items-center gap-2 text-[14.5px] font-medium text-espresso">{s.device}{s.current && <Badge tone="verified" dot>This device</Badge>}</p>
                  <p className="text-[12.5px] text-taupe-2">{s.ip_address ? `${s.ip_address} · ` : ''}signed in {fmtRelative(s.started_at)} · active {fmtRelative(s.last_active_at)}</p>
                </div>
                <Button variant="ghost" size="sm" loading={one.pending}
                  onClick={async () => {
                    const r = await one.run(String(s.id))
                    if (!r) { if (one.error) toast('err', one.error); return }
                    if (s.current) { await logout(); router.replace('/login'); return }
                    toast('ok', r.message); q.refresh(); onChange()
                  }}>
                  Sign out
                </Button>
              </li>
            )
          })}
        </ul>
      )}
    </Card>
  )
}

/* ------------------------------------------------------------------ activity */

function Activity() {
  const q = useApi(() => auth.activity(25))
  return (
    <Card radius="xl">
      <PanelHeader title="Recent activity" eyebrow="Sign-ins and security changes" />
      {q.error ? <ErrorState message={q.error} onRetry={q.refresh} /> : !q.data ? <SkeletonRows rows={5} /> : !q.data.length ? <p className="text-[13.5px] text-taupe-2">Nothing yet.</p> : (
        <ol className="flex flex-col">
          {q.data.map((a, i) => (
            <li key={i} className="grid grid-cols-[auto_1fr_auto] items-center gap-3 border-b border-line-soft py-2.5 last:border-b-0">
              {a.ok ? <CheckCircle2 size={16} className="text-verified" aria-label="OK" /> : <XCircle size={16} className="text-critical" aria-label="Failed" />}
              <div className="min-w-0">
                <p className="text-[14px] text-espresso">{a.label}</p>
                {(a.ip_address || a.detail) && <p className="truncate text-[12.5px] text-taupe-2">{[a.ip_address, a.detail].filter(Boolean).join(' · ')}</p>}
              </div>
              <time className="whitespace-nowrap text-[12.5px] text-taupe-2" dateTime={a.at} title={fmtDate(a.at)}>{fmtRelative(a.at)}</time>
            </li>
          ))}
        </ol>
      )}
      <p className="mt-4 text-[12.5px] text-taupe-2">Something you do not recognise? Change your password and sign out everywhere else.</p>
    </Card>
  )
}


