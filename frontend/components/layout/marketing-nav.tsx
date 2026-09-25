'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'
import { cn } from '@/lib/utils'
import { Button, Wordmark } from '@/components/ui/primitives'
import { useAuth } from '@/lib/auth-context'

const links = [
  { href: '#product', label: 'Product' },
  { href: '#intelligence', label: 'Intelligence' },
  { href: '#security', label: 'Security' },
  { href: '#analytics', label: 'Analytics' },
  { href: '#about', label: 'About' },
]

/**
 * Sticky, quiet, and honest about the page beneath it: transparent over the
 * hero, a cream veil once the reader has moved. The hairline at its foot is
 * the reading position — a progress bar that costs one transform per frame
 * and tells you how much document is left.
 */
export function MarketingNav() {
  const [scrolled, setScrolled] = useState(false)
  const [progress, setProgress] = useState(0)
  const [active, setActive] = useState<string>('')
  const [open, setOpen] = useState(false)
  const { user } = useAuth()

  useEffect(() => {
    let frame = 0
    const onScroll = () => {
      if (frame) return
      frame = requestAnimationFrame(() => {
        frame = 0
        const max = document.documentElement.scrollHeight - window.innerHeight
        setProgress(max > 0 ? window.scrollY / max : 0)
        setScrolled(window.scrollY > 24)
      })
    }
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => { window.removeEventListener('scroll', onScroll); if (frame) cancelAnimationFrame(frame) }
  }, [])

  // Which section is under the reader, so the nav says where they are.
  useEffect(() => {
    const ids = links.map((l) => l.href.slice(1))
    const targets = ids.map((id) => document.getElementById(id)).filter(Boolean) as HTMLElement[]
    if (!targets.length) return
    const io = new IntersectionObserver(
      (entries) => {
        const visible = entries.filter((e) => e.isIntersecting).sort((a, b) => b.intersectionRatio - a.intersectionRatio)
        if (visible[0]) setActive('#' + visible[0].target.id)
      },
      { rootMargin: '-45% 0px -45% 0px', threshold: [0, 0.2, 0.5] },
    )
    targets.forEach((t) => io.observe(t))
    return () => io.disconnect()
  }, [])

  useEffect(() => {
    document.body.style.overflow = open ? 'hidden' : ''
    return () => { document.body.style.overflow = '' }
  }, [open])

  return (
    <header
      className={cn(
        'fixed inset-x-0 top-0 z-50 transition-[background-color,box-shadow,backdrop-filter] duration-500',
        scrolled || open ? 'bg-cream/80 backdrop-blur-xl' : 'bg-transparent',
      )}
      style={{ paddingTop: 'env(safe-area-inset-top, 0px)' }}
    >
      <nav className="container-x flex h-[var(--nav-h)] items-center justify-between" aria-label="Primary">
        <Link href="/" aria-label="SupportNova home" className="shrink-0">
          <Wordmark />
        </Link>

        <ul className="hidden items-center gap-1 lg:flex">
          {links.map((l) => (
            <li key={l.href}>
              <a
                href={l.href}
                aria-current={active === l.href ? 'true' : undefined}
                className={cn(
                  'relative rounded-full px-3.5 py-1.5 text-[13.5px] font-medium transition-colors duration-300',
                  active === l.href ? 'text-espresso' : 'text-espresso-2/75 hover:text-espresso',
                )}
              >
                {l.label}
                <span
                  aria-hidden
                  className={cn(
                    'absolute inset-x-3.5 -bottom-0.5 h-px origin-left bg-espresso transition-transform duration-500 ease-[var(--ease-out-expo)]',
                    active === l.href ? 'scale-x-100' : 'scale-x-0',
                  )}
                />
              </a>
            </li>
          ))}
        </ul>

        <div className="hidden items-center gap-2 lg:flex">
          {user ? (
            <Button href="/dashboard" size="sm" arrow>Open dashboard</Button>
          ) : (
            <>
              <Button href="/login" variant="ghost" size="sm">Sign in</Button>
              <Button href="/register" size="sm">Create account</Button>
            </>
          )}
        </div>

        <button
          className="inline-flex size-10 items-center justify-center rounded-full border border-line bg-ivory/70 lg:hidden"
          aria-expanded={open}
          aria-label={open ? 'Close menu' : 'Open menu'}
          onClick={() => setOpen((o) => !o)}
        >
          <span className="relative block h-[9px] w-[17px]">
            <span className={cn('absolute left-0 top-0 h-[1.5px] w-full bg-espresso transition-transform duration-300', open && 'translate-y-[4px] rotate-45')} />
            <span className={cn('absolute left-0 bottom-0 h-[1.5px] w-full bg-espresso transition-transform duration-300', open && '-translate-y-[4px] -rotate-45')} />
          </span>
        </button>
      </nav>

      {/* reading position */}
      <div aria-hidden className="h-px w-full bg-line/50">
        <div
          className="h-full origin-left bg-espresso"
          style={{ transform: `scaleX(${progress})`, opacity: scrolled ? 1 : 0, transition: 'opacity .4s' }}
        />
      </div>

      {open && (
        <div className="border-t border-line bg-cream px-[var(--gutter)] pb-8 pt-4 lg:hidden">
          <ul className="flex flex-col">
            {links.map((l, i) => (
              <li key={l.href}>
                <a
                  href={l.href}
                  onClick={() => setOpen(false)}
                  className="flex items-baseline gap-4 border-b border-line-soft py-3.5 font-display text-[26px] tracking-[-0.02em]"
                >
                  <span className="eyebrow text-[10px] text-taupe">{String(i + 1).padStart(2, '0')}</span>
                  {l.label}
                </a>
              </li>
            ))}
          </ul>
          <div className="mt-6 flex gap-2">
            <Button href="/login" variant="secondary" className="flex-1">Sign in</Button>
            <Button href="/register" className="flex-1">Create account</Button>
          </div>
        </div>
      )}
    </header>
  )
}
