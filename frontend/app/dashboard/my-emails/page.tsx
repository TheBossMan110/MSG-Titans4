'use client'

import { AppShell } from '@/components/layout/app-shell'
import { Mailbox } from '@/components/app/email-views'
import { useAuth } from '@/lib/auth-context'

export default function MyEmailsPage() {
  return (
    <AppShell eyebrow="My emails" roles={['customer']}>
      <MyEmails />
    </AppShell>
  )
}

function MyEmails() {
  const { user } = useAuth()
  return (
    <div className="flex flex-col gap-6">
      <div>
        <p className="eyebrow mb-1">Complain by email</p>
        <h1 className="display text-h2">Your emails with support</h1>
        <p className="mt-2 max-w-[62ch] text-[14.5px] text-taupe-2">
          Email <a href="mailto:supportnova110@gmail.com" className="font-medium text-espresso underline underline-offset-4">supportnova110@gmail.com</a> from {user?.email ?? 'your address'} to raise a complaint.
          We reply straight away with your reference, and every email you send and every reply we send appears here.
        </p>
      </div>
      <Mailbox staff={false} />
    </div>
  )
}
