'use client'

import dynamic from 'next/dynamic'
import { useEffect, useState } from 'react'
import { EnginePoster } from './poster'
import type { Progress } from './engine'
import { useIsCompact, useReducedMotion } from '@/components/motion/hooks'
import { cn } from '@/lib/utils'

const Engine = dynamic(() => import('./engine'), { ssr: false, loading: () => null })

/**
 * Mounts the WebGL engine only where it earns its cost: large viewports,
 * motion allowed, WebGL available, and after first paint. Everywhere else
 * the poster stands in, and nobody waits on three.js to see the page.
 */
export function EngineLoader({ progress, className }: { progress: Progress; className?: string }) {
  const compact = useIsCompact()
  const reduced = useReducedMotion()
  const [ready, setReady] = useState(false)

  useEffect(() => {
    if (compact || reduced) return
    let ok = false
    try {
      const c = document.createElement('canvas')
      ok = Boolean(c.getContext('webgl2') || c.getContext('webgl'))
    } catch { ok = false }
    if (!ok) return
    const id = window.requestIdleCallback ? window.requestIdleCallback(() => setReady(true), { timeout: 800 }) : window.setTimeout(() => setReady(true), 200)
    return () => { if (window.cancelIdleCallback && typeof id === 'number') window.cancelIdleCallback(id); else clearTimeout(id) }
  }, [compact, reduced])

  return (
    <div className={cn('relative', className)}>
      <EnginePoster className={cn('absolute inset-0 h-full w-full transition-opacity duration-700', ready ? 'opacity-0' : 'opacity-100')} />
      {ready && <Engine progress={progress} className="!absolute inset-0" />}
    </div>
  )
}
