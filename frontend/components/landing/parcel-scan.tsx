'use client'

import { useEffect, useRef } from 'react'
import s from './parcel-scan.module.css'

/**
 * One parcel, opened, scanned and verified, on a ten-second loop: the
 * landing page's picture of what the product does. Pure CSS 3D -- no WebGL,
 * so it runs on any laptop and costs nothing to load.
 *
 * The drawing is authored at 560x500 and scaled to its column's width.
 */
export function ParcelScan({ className }: { className?: string }) {
  const wrap = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = wrap.current
    if (!el) return
    const fit = () => el.style.setProperty('--s', String(el.clientWidth / 560))
    fit()
    const observer = new ResizeObserver(fit)
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  return (
    <div ref={wrap} className={`${s.wrap} ${className ?? ''}`} role="img" aria-label="A parcel is opened and scanned. The AI proposes: lost shipment, P2, refund. The rules confirm: P1, compliance review, verify first.">
      <div className={s.canvas} aria-hidden>
        <div className={s.glow} />
        <div className={s.scene}>
          <div className={s.rig}>
            <div className={s.box}>
              <div className={s.shadow} />
              <div className={`${s.face} ${s.bottom}`} />
              <div className={`${s.face} ${s.back}`} />
              <div className={`${s.face} ${s.left}`} />
              <div className={`${s.face} ${s.right}`} />
              <div className={`${s.face} ${s.front}`}>
                <div className={s.tape} />
                <div className={s.label}>
                  <div className={s.barcode} />
                  <div className={`${s.ln} ${s.w1}`} />
                  <div className={`${s.ln} ${s.w2}`} />
                  <div className={`${s.ln} ${s.w3}`} />
                </div>
              </div>
              <div className={s.cavity}>
                <div className={s.grid} />
                <div className={s.beam} />
                <div className={s.contents}>
                  <div className={`${s.doc} ${s.d2}`}><div className={`${s.dl} ${s.dl1}`} /></div>
                  <div className={`${s.doc} ${s.d1}`}><div className={`${s.dl} ${s.dl1}`} /><div className={`${s.dl} ${s.dl2}`} /></div>
                </div>
              </div>
              <div className={`${s.face} ${s.top}`}><div className={s.tape} /></div>
            </div>
          </div>
        </div>

        <div className={s.overlay}>
          <div className={`${s.tag} ${s.category}`}><span className={s.dot} />Category · Lost shipment</div>
          <div className={`${s.tag} ${s.urgency}`}><span className={s.dot} />Urgency · High</div>
          <div className={`${s.tag} ${s.policy}`}><span className={s.dot} />Policy · DEL-POL-04 §5.2</div>

          <div className={`${s.badge} ${s.ai}`}>
            <div className={s.icon}>
              <svg viewBox="0 0 24 24" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 2l1.8 5.6L19.5 9l-5.7 1.4L12 16l-1.8-5.6L4.5 9l5.7-1.4L12 2z" /><path d="M19 15l.9 2.7L22.5 18l-2.6.8L19 21.5l-.9-2.7-2.6-.8 2.6-.8L19 15z" /></svg>
            </div>
            <div><div className={s.eyebrow}>AI proposes</div><div className={s.line}>Lost shipment · P2 · refund</div></div>
          </div>

          <div className={`${s.badge} ${s.rules}`}>
            <div className={s.icon}>
              <svg viewBox="0 0 24 24" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 2l8 4v6c0 5-3.5 8.5-8 10-4.5-1.5-8-5-8-10V6l8-4z" /><path d="M9 12l2 2 4-4" /></svg>
            </div>
            <div><div className={s.eyebrow}>Rules confirm</div><div className={s.line}>P1 · compliance review · verify first</div></div>
          </div>
        </div>
      </div>
    </div>
  )
}
