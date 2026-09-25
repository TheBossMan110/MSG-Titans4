'use client'

import { AppShell } from '@/components/layout/app-shell'
import { ChatPanel } from '@/components/app/chat'

export default function AssistantPage() {
  return (
    <AppShell eyebrow="Chat with Nova">
      <div className="mx-auto flex w-full max-w-[760px] flex-col gap-4">
        <div>
          <p className="eyebrow mb-1">Complain by chat</p>
          <h1 className="display text-h2">Tell Nova what happened.</h1>
          <p className="mt-2 max-w-[60ch] text-[14.5px] text-taupe-2">
            Nova asks for anything missing and writes your complaint up for you to check. When you press
            “File this complaint” it goes through exactly the same checks as the form, and you get your reference here.
          </p>
        </div>
        <ChatPanel className="h-[min(680px,calc(100dvh-260px))] min-h-[460px] overflow-hidden rounded-3xl border border-line shadow-card" />
      </div>
    </AppShell>
  )
}
