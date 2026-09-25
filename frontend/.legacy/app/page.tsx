'use client'
import React, { useEffect, useRef } from 'react'
import Link from 'next/link'
import {
  Zap, Shield, CheckCircle, AlertTriangle, TrendingUp, ArrowRight,
  Activity, Lock, Globe, BarChart3, ChevronRight,
} from 'lucide-react'
import { LandingNav, Logo } from '@/components/ui'

export default function HomePage() {
  const heroRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    // Parallax on mouse move
    const handler = (e: MouseEvent) => {
      const x = (e.clientX / window.innerWidth - 0.5) * 20
      const y = (e.clientY / window.innerHeight - 0.5) * 20
      if (heroRef.current) {
        heroRef.current.style.setProperty('--mx', `${x}px`)
        heroRef.current.style.setProperty('--my', `${y}px`)
      }
    }
    window.addEventListener('mousemove', handler)
    return () => window.removeEventListener('mousemove', handler)
  }, [])

  return (
    <>
      <div className="ambient-bg" />
      <div className="grid-overlay" />
      <LandingNav />

      {/* ─── HERO ──────────────────────────────────────────────────────────── */}
      <section
        ref={heroRef}
        style={{
          minHeight: '100dvh',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          textAlign: 'center',
          padding: '100px 24px 80px',
          position: 'relative',
          overflow: 'hidden',
        }}
      >
        {/* Big orange glow orb */}
        <div style={{
          position: 'absolute',
          width: 800,
          height: 800,
          borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(255,87,34,0.12) 0%, transparent 70%)',
          top: '50%',
          left: '50%',
          transform: 'translate(-50%, -50%)',
          pointerEvents: 'none',
        }} />

        <div className="hero-badge animate-fade-up" style={{ marginBottom: 28, animationDelay: '0.1s', opacity: 0 }}>
          <span className="dot dot-orange dot-pulse" />
          Dual-Engine AI + Deterministic Validation
        </div>

        <h1 className="hero-title animate-fade-up" style={{ marginBottom: 24, animationDelay: '0.2s', opacity: 0 }}>
          Customer Support<br />
          <span className="text-gradient-orange">Accountability</span> Layer
        </h1>

        <p className="hero-sub animate-fade-up" style={{ marginBottom: 40, animationDelay: '0.3s', opacity: 0 }}>
          SupportNova pairs generative AI with a Python ground-truth verifier.
          Every classification is cross-checked, every discrepancy flagged,
          every SLA tracked — with a full audit trail.
        </p>

        <div className="animate-fade-up" style={{ display: 'flex', gap: 12, justifyContent: 'center', flexWrap: 'wrap', animationDelay: '0.4s', opacity: 0 }}>
          <Link href="/login" className="btn btn-orange btn-lg">
            Get Started <ArrowRight size={18} />
          </Link>
          <Link href="/how-it-works" className="btn btn-ghost btn-lg">
            See How It Works
          </Link>
        </div>

        {/* Architecture key */}
        <div className="animate-fade-up" style={{ marginTop: 60, animationDelay: '0.5s', opacity: 0 }}>
          <div style={{ display: 'flex', gap: 20, justifyContent: 'center', flexWrap: 'wrap', fontSize: 13, color: 'var(--text-3)' }}>
            {[
              { color: '#6366F1', label: 'AI Engine — Indigo' },
              { color: '#06B6D4', label: 'Python Verifier — Cyan' },
              { color: '#22C55E', label: 'Verified — Green' },
              { color: '#F59E0B', label: 'Mismatch — Amber' },
              { color: '#EF4444', label: 'Critical — Red' },
            ].map((item) => (
              <span key={item.label} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span style={{ width: 10, height: 10, borderRadius: 3, background: item.color }} />
                {item.label}
              </span>
            ))}
          </div>
        </div>
      </section>

      {/* ─── STATS BAR ─────────────────────────────────────────────────────── */}
      <section style={{
        borderTop: '1px solid var(--border)',
        borderBottom: '1px solid var(--border)',
        background: 'var(--surface)',
        padding: '28px 60px',
        display: 'flex',
        gap: 60,
        justifyContent: 'center',
        flexWrap: 'wrap',
      }}>
        {[
          { value: '99.4%', label: 'Validation Accuracy', color: 'var(--verified)' },
          { value: '< 2s', label: 'Avg Pipeline Latency', color: 'var(--ai)' },
          { value: '6 Roles', label: 'Access Levels Supported', color: 'var(--orange)' },
          { value: '74/74', label: 'Backend Requirements', color: 'var(--py)' },
        ].map((stat) => (
          <div key={stat.label} style={{ textAlign: 'center' }}>
            <div style={{ fontSize: 34, fontWeight: 900, color: stat.color, letterSpacing: '-0.04em', fontFamily: 'Manrope, sans-serif' }}>
              {stat.value}
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 4, fontWeight: 600, letterSpacing: '0.05em', textTransform: 'uppercase' }}>
              {stat.label}
            </div>
          </div>
        ))}
      </section>

      {/* ─── DUAL ENGINE ───────────────────────────────────────────────────── */}
      <section style={{ padding: '100px 60px', maxWidth: 1100, margin: '0 auto' }}>
        <div style={{ textAlign: 'center', marginBottom: 60 }}>
          <p style={{ fontSize: 12, fontWeight: 700, letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--orange-2)', marginBottom: 14 }}>
            Architecture
          </p>
          <h2 style={{ fontSize: 'clamp(28px, 4vw, 48px)', fontWeight: 900, letterSpacing: '-0.03em', marginBottom: 16 }}>
            Two engines. One truth.
          </h2>
          <p style={{ fontSize: 16, color: 'var(--text-2)', maxWidth: 560, margin: '0 auto', lineHeight: 1.7 }}>
            GenAI provides reasoning and natural language understanding.
            Python determinism verifies every output against business rules.
            Disagreements surface automatically for human review.
          </p>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr auto 1fr', gap: 0, alignItems: 'center' }}>
          {/* AI Engine card */}
          <div className="card card-ai" style={{ padding: '28px 24px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20 }}>
              <div style={{ width: 40, height: 40, borderRadius: 10, background: 'var(--ai-dim)', border: '1px solid var(--ai-border)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Zap size={20} color="#a5b4fc" />
              </div>
              <div>
                <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', color: '#a5b4fc' }}>Engine 1</div>
                <div style={{ fontSize: 17, fontWeight: 800 }}>AI — GenAI Reasoning</div>
              </div>
            </div>
            {['Natural language classification', 'Sentiment analysis', 'Urgency detection', 'Department routing', 'Context-aware response generation'].map((f) => (
              <div key={f} style={{ display: 'flex', gap: 8, alignItems: 'center', padding: '7px 0', borderBottom: '1px solid var(--border)', fontSize: 13.5, color: 'var(--text-2)' }}>
                <ChevronRight size={14} color="#a5b4fc" />
                {f}
              </div>
            ))}
          </div>

          {/* VS divider */}
          <div style={{
            display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8, padding: '0 20px',
          }}>
            <div style={{ width: 1, height: 60, background: 'linear-gradient(to bottom, transparent, var(--border))' }} />
            <div style={{
              width: 44, height: 44, borderRadius: '50%', background: 'var(--surface)',
              border: '1px solid var(--border-2)', display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 11, fontWeight: 800, color: 'var(--text-3)', letterSpacing: '0.02em',
            }}>
              VS
            </div>
            <div style={{ width: 1, height: 60, background: 'linear-gradient(to top, transparent, var(--border))' }} />
          </div>

          {/* Python card */}
          <div className="card card-py" style={{ padding: '28px 24px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20 }}>
              <div style={{ width: 40, height: 40, borderRadius: 10, background: 'var(--py-dim)', border: '1px solid var(--py-border)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Shield size={20} color="#67e8f9" />
              </div>
              <div>
                <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', color: '#67e8f9' }}>Engine 2</div>
                <div style={{ fontSize: 17, fontWeight: 800 }}>Python — Deterministic</div>
              </div>
            </div>
            {['Rule-matrix classification', 'SLA policy enforcement', 'Escalation decision tree', 'Department assignment rules', 'Business logic ground-truth validation'].map((f) => (
              <div key={f} style={{ display: 'flex', gap: 8, alignItems: 'center', padding: '7px 0', borderBottom: '1px solid var(--border)', fontSize: 13.5, color: 'var(--text-2)' }}>
                <ChevronRight size={14} color="#67e8f9" />
                {f}
              </div>
            ))}
          </div>
        </div>

        {/* Reconciliation row */}
        <div style={{ marginTop: 16, textAlign: 'center' }}>
          <div style={{
            display: 'inline-flex', alignItems: 'center', gap: 12, padding: '14px 24px',
            background: 'var(--surface)', border: '1px solid var(--border-2)', borderRadius: 'var(--r-lg)',
            fontSize: 14,
          }}>
            <CheckCircle size={16} color="var(--verified)" />
            <span style={{ color: 'var(--text-2)' }}>When engines agree → </span>
            <span className="badge badge-verified">VERIFIED</span>
            <span style={{ color: 'var(--text-3)', margin: '0 4px' }}>·</span>
            <AlertTriangle size={16} color="var(--mismatch)" />
            <span style={{ color: 'var(--text-2)' }}>Disagreement → </span>
            <span className="badge badge-mismatch">MISMATCH</span>
            <span style={{ color: 'var(--text-3)', margin: '0 4px' }}>→ human review queue</span>
          </div>
        </div>
      </section>

      {/* ─── FEATURES ──────────────────────────────────────────────────────── */}
      <section style={{ padding: '80px 60px', background: 'var(--surface)', borderTop: '1px solid var(--border)', borderBottom: '1px solid var(--border)' }}>
        <div style={{ maxWidth: 1100, margin: '0 auto' }}>
          <p style={{ fontSize: 12, fontWeight: 700, letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--orange-2)', marginBottom: 14, textAlign: 'center' }}>
            Features
          </p>
          <h2 style={{ fontSize: 'clamp(24px, 3.5vw, 40px)', fontWeight: 900, textAlign: 'center', marginBottom: 48, letterSpacing: '-0.03em' }}>
            Everything you need to close the loop
          </h2>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 16 }}>
            {[
              { icon: <Activity size={20} />, title: 'Real-Time Pipeline', body: 'Watch AI and Python engines process each complaint in under 2 seconds with live progress tracking.', color: 'var(--ai)' },
              { icon: <Shield size={20} />, title: 'Ground-Truth Validation', body: 'Deterministic Python rules verify every AI output against your business policy — no hallucinations pass through.', color: 'var(--py)' },
              { icon: <CheckCircle size={20} />, title: 'SLA Enforcement', body: 'Automatic breach detection, approaching-SLA alerts, and full audit-ready compliance reporting.', color: 'var(--verified)' },
              { icon: <AlertTriangle size={20} />, title: 'Mismatch Escalation', body: 'Every AI–Python disagreement enters a structured human review queue before any action is taken.', color: 'var(--mismatch)' },
              { icon: <BarChart3 size={20} />, title: 'Analytics & Trends', body: 'Volume, category distribution, pipeline agreement rates, and SLA performance — all traceable to live data.', color: 'var(--orange)' },
              { icon: <Lock size={20} />, title: 'Role-Based Access', body: '6 roles (Customer, Agent, Reviewer, Manager, Admin, Evaluator), each with its own payload and capability set.', color: 'var(--ai)' },
            ].map((f) => (
              <div key={f.title} className="card" style={{ padding: '22px 20px', transition: 'transform 0.2s, border-color 0.2s' }}>
                <div style={{ width: 40, height: 40, borderRadius: 10, background: `${f.color}15`, border: `1px solid ${f.color}40`, display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 16, color: f.color }}>
                  {f.icon}
                </div>
                <h3 style={{ fontSize: 15, fontWeight: 700, marginBottom: 8 }}>{f.title}</h3>
                <p style={{ fontSize: 13.5, color: 'var(--text-3)', lineHeight: 1.6 }}>{f.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ─── CTA ───────────────────────────────────────────────────────────── */}
      <section style={{ padding: '100px 60px', textAlign: 'center', position: 'relative', overflow: 'hidden' }}>
        <div style={{
          position: 'absolute', inset: 0, pointerEvents: 'none',
          background: 'radial-gradient(ellipse 80% 80% at 50% 50%, rgba(255,87,34,0.07) 0%, transparent 70%)',
        }} />
        <h2 style={{ fontSize: 'clamp(28px, 4vw, 52px)', fontWeight: 900, letterSpacing: '-0.04em', marginBottom: 20 }}>
          Ready to eliminate<br />
          <span className="text-gradient-orange">blind-spot AI?</span>
        </h2>
        <p style={{ fontSize: 16, color: 'var(--text-2)', maxWidth: 460, margin: '0 auto 32px', lineHeight: 1.7 }}>
          Sign in to access the full SupportNova dashboard — designed for your role.
        </p>
        <Link href="/login" className="btn btn-orange btn-lg animate-glow-pulse">
          Sign In to Dashboard <ArrowRight size={18} />
        </Link>
      </section>

      {/* ─── FOOTER ────────────────────────────────────────────────────────── */}
      <footer style={{
        borderTop: '1px solid var(--border)',
        padding: '32px 60px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexWrap: 'wrap',
        gap: 20,
        color: 'var(--text-4)',
        fontSize: 12,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <Logo size={22} />
          <span style={{ fontWeight: 700, color: 'var(--text-3)' }}>SupportNova</span>
          <span>— ResponseX Intelligence</span>
        </div>
        <div style={{ display: 'flex', gap: 24 }}>
          <Link href="/features" style={{ color: 'inherit' }}>Features</Link>
          <Link href="/how-it-works" style={{ color: 'inherit' }}>How it Works</Link>
          <Link href="/about" style={{ color: 'inherit' }}>About</Link>
        </div>
        <div>© {new Date().getFullYear()} SupportNova — Aptech Limited</div>
      </footer>
    </>
  )
}
