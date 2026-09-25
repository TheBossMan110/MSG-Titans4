import { Button, Wordmark } from '@/components/ui/primitives'

export default function NotFound() {
  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-6 px-6 text-center">
      <Wordmark />
      <h1 className="display text-h1">This page is not in the register.</h1>
      <p className="max-w-[44ch] text-[15px] text-taupe-2">The address may have been mistyped, or the page has moved. Complaints are tracked from the dashboard; policies from the knowledge base.</p>
      <div className="flex gap-2">
        <Button href="/">Home</Button>
        <Button href="/dashboard" variant="secondary">Dashboard</Button>
      </div>
    </main>
  )
}
