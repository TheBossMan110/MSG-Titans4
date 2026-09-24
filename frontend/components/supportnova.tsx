'use client'

import React, { useState, useEffect, useMemo } from 'react'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import {
  ArrowRight,
  Bell,
  Check,
  ChevronDown,
  CircleHelp,
  Clock3,
  FileText,
  LayoutDashboard,
  Lock,
  Menu,
  Moon,
  MoreHorizontal,
  Network,
  Search,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Sun,
  Ticket,
  TrendingUp,
  Upload,
  X,
  Zap,
  Activity,
  CheckCircle2,
  AlertTriangle,
  Cpu,
  Layers,
  Scale,
  RefreshCw,
  Sliders,
  Send,
  ExternalLink,
  BookOpen,
  Filter,
  Flame,
  User,
  Command,
} from 'lucide-react'

/* ==========================================================================
   MOCK COMPLAINTS DATA (SHARED REFERENCE)
   ========================================================================== */

export const complaints = [
  {
    id: 'CMP-00421',
    title: 'Order arrived damaged and support has not responded',
    category: 'Product Defect',
    priority: 'P1',
    status: 'In review',
    department: 'Returns',
    sentiment: 'Strongly negative',
    time: '8 min ago',
    policy: 'RET-POL-02',
    agreementScore: 96.4,
  },
  {
    id: 'CMP-00420',
    title: 'Refund still missing after 14 business days',
    category: 'Billing',
    priority: 'P2',
    status: 'Assigned',
    department: 'Billing Support',
    sentiment: 'Negative',
    time: '24 min ago',
    policy: 'BIL-REF-01',
    agreementScore: 98.1,
  },
  {
    id: 'CMP-00419',
    title: 'Unable to reset account password or 2FA credentials',
    category: 'Account Security',
    priority: 'P2',
    status: 'Resolved',
    department: 'Security & Access',
    sentiment: 'Frustrated',
    time: '1 hr ago',
    policy: 'SEC-ACC-04',
    agreementScore: 99.0,
  },
  {
    id: 'CMP-00418',
    title: 'Delivery delayed beyond SLA guarantee window',
    category: 'Delivery',
    priority: 'P1',
    status: 'Escalated',
    department: 'Logistics',
    sentiment: 'Negative',
    time: '2 hrs ago',
    policy: 'LOG-DEL-03',
    agreementScore: 95.8,
  },
  {
    id: 'CMP-00417',
    title: 'Autonomous robotic arm vibration anomaly during cycle',
    category: 'Hardware Defect',
    priority: 'P0',
    status: 'Escalated',
    department: 'Robotics Tier-3',
    sentiment: 'Urgent Neutral',
    time: '3 hrs ago',
    policy: 'DOC-ROB-01',
    agreementScore: 99.2,
  },
]

/* ==========================================================================
   0. SCROLL REVEAL WRAPPER (INTERSECTION OBSERVER DRIVEN)
   ========================================================================== */

export function ScrollReveal({
  children,
  variant = 'up',
  delay = 0,
  className = '',
  threshold = 0.1,
}: {
  children: React.ReactNode
  variant?: 'up' | 'left' | 'right' | 'scale'
  delay?: number
  className?: string
  threshold?: number
}) {
  const ref = React.useRef<HTMLDivElement>(null)
  const [inView, setInView] = useState(false)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    if (typeof IntersectionObserver === 'undefined') {
      setInView(true)
      return
    }
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setInView(true)
          observer.unobserve(entry.target)
        }
      },
      { threshold, rootMargin: '0px 0px -40px 0px' }
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [threshold])

  const variantClass =
    variant === 'left'
      ? 'scroll-slide-left'
      : variant === 'right'
      ? 'scroll-slide-right'
      : variant === 'scale'
      ? 'scroll-scale'
      : 'scroll-reveal'

  return (
    <div
      ref={ref}
      className={`${variantClass} ${inView ? 'in-view' : ''} ${className}`}
      style={delay ? { transitionDelay: `${delay}ms` } : undefined}
    >
      {children}
    </div>
  )
}

/* ==========================================================================
   0.1 TWO-ENGINE ARCHITECTURAL KEY BAR & RUNTIME SELECTOR
   ========================================================================== */

export function TwoEngineArchitectureKey({
  activeKey = 'all',
  onSelectKey,
}: {
  activeKey?: string
  onSelectKey?: (key: string) => void
}) {
  const [selected, setSelected] = useState(activeKey)

  const handleSelect = (key: string) => {
    setSelected(key)
    if (onSelectKey) onSelectKey(key)
  }

  return (
    <div className="two-engine-key-bar">
      <div className="engine-key-cluster">
        <span className="text-[11px] font-mono text-slate-400 uppercase tracking-wider font-semibold mr-1">
          Dual Engines:
        </span>
        {/* Engine 1: AI */}
        <button
          onClick={() => handleSelect('ai')}
          className={`pill-engine-ai transition-transform ${
            selected === 'ai' ? 'scale-105 ring-2 ring-indigo-400' : 'opacity-90 hover:opacity-100'
          }`}
          title="Engine 1: Unstructured Reasoning, Synthesis & Tone"
        >
          <Sparkles size={12} className="text-indigo-400" />
          <span>AI Engine (Indigo/Purple/Blue)</span>
        </button>

        <span className="text-slate-500 font-mono text-xs">+</span>

        {/* Engine 2: Python */}
        <button
          onClick={() => handleSelect('python')}
          className={`pill-engine-python transition-transform ${
            selected === 'python' ? 'scale-105 ring-2 ring-cyan-400' : 'opacity-90 hover:opacity-100'
          }`}
          title="Engine 2: 100-Rule Deterministic Matrix & Escalation Gate"
        >
          <ShieldCheck size={12} className="text-cyan-400" />
          <span>Python Ground Truth (Cyan/Teal)</span>
        </button>
      </div>

      <div className="hidden sm:block engine-key-divider" />

      <div className="engine-key-cluster">
        <span className="text-[11px] font-mono text-slate-400 uppercase tracking-wider font-semibold mr-1">
          Outcomes:
        </span>
        {/* Outcome 1: Verified */}
        <button
          onClick={() => handleSelect('verified')}
          className={`pill-status-verified transition-transform ${
            selected === 'verified' ? 'scale-105 ring-2 ring-emerald-400' : 'opacity-90 hover:opacity-100'
          }`}
          title="Verified: Parity score >= 95%, safe for automated dispatch"
        >
          <Check size={12} className="text-emerald-400" />
          <span>Verified (Green)</span>
        </button>

        {/* Outcome 2: Mismatch */}
        <button
          onClick={() => handleSelect('mismatch')}
          className={`pill-status-mismatch transition-transform ${
            selected === 'mismatch' ? 'scale-105 ring-2 ring-amber-400' : 'opacity-90 hover:opacity-100'
          }`}
          title="Mismatch: AI proposed outcome violates rules, held in Step 57"
        >
          <AlertTriangle size={12} className="text-amber-400" />
          <span>Mismatch (Amber)</span>
        </button>

        {/* Outcome 3: Critical */}
        <button
          onClick={() => handleSelect('critical')}
          className={`pill-status-critical transition-transform ${
            selected === 'critical' ? 'scale-105 ring-2 ring-rose-400' : 'opacity-90 hover:opacity-100'
          }`}
          title="Critical: P0 safety/regulatory hazard triggered regardless of tone"
        >
          <Zap size={12} className="text-rose-400" />
          <span>Critical (Red)</span>
        </button>
      </div>
    </div>
  )
}

/* ==========================================================================
   1. BRAND LOGO WITH ORBITAL RING & NODE EFFECT
   ========================================================================== */

export function Logo({
  dark = true,
  size = 'default',
}: {
  dark?: boolean
  size?: 'small' | 'default' | 'large'
}) {
  return (
    <Link href="/" className="logo-container" aria-label="SupportNova Home">
      <div className="logo-orbital-mark">
        <span className="logo-orbital-ring" />
        <span className="logo-core-node">
          <span />
        </span>
      </div>
      <div className="flex flex-col">
        <span
          className={`font-bold tracking-tight leading-none ${
            size === 'large' ? 'text-xl' : size === 'small' ? 'text-sm' : 'text-base'
          } ${dark ? 'text-white' : 'text-slate-900'}`}
        >
          Support<span className="text-cyan-400">Nova</span>
        </span>
        <span className="text-[9px] font-mono tracking-widest uppercase text-indigo-400 opacity-80 mt-0.5">
          ResponseX
        </span>
      </div>
    </Link>
  )
}

/* ==========================================================================
   2. THEME TOGGLE (DARK / LIGHT MODE WITH PERSISTENCE)
   ========================================================================== */

export function ThemeToggle() {
  const [isDark, setIsDark] = useState(true)

  useEffect(() => {
    const saved = localStorage.getItem('supportnova-theme')
    if (saved === 'light') {
      setIsDark(false)
      document.documentElement.setAttribute('data-theme', 'light')
    } else {
      setIsDark(true)
      document.documentElement.removeAttribute('data-theme')
    }
  }, [])

  const toggleTheme = () => {
    const nextDark = !isDark
    setIsDark(nextDark)
    if (nextDark) {
      document.documentElement.removeAttribute('data-theme')
      localStorage.setItem('supportnova-theme', 'dark')
    } else {
      document.documentElement.setAttribute('data-theme', 'light')
      localStorage.setItem('supportnova-theme', 'light')
    }
  }

  return (
    <button
      onClick={toggleTheme}
      aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
      className="icon-button"
      title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
    >
      {isDark ? (
        <Sun size={17} className="text-amber-400 transition-transform duration-300 hover:rotate-45" />
      ) : (
        <Moon size={17} className="text-indigo-600 transition-transform duration-300 hover:-rotate-12" />
      )}
    </button>
  )
}

/* ==========================================================================
   3. GLOBAL MARKETING NAVBAR
   ========================================================================== */

export function MarketingNav() {
  const [open, setOpen] = useState(false)
  const [scrolled, setScrolled] = useState(false)
  const pathname = usePathname()

  useEffect(() => {
    const handleScroll = () => {
      setScrolled(window.scrollY > 20)
    }
    window.addEventListener('scroll', handleScroll, { passive: true })
    return () => window.removeEventListener('scroll', handleScroll)
  }, [])

  const navLinks = [
    { label: 'Features', href: '/features' },
    { label: 'How It Works', href: '/how-it-works' },
    { label: 'Pricing', href: '/pricing' },
    { label: 'About', href: '/about' },
  ]

  return (
    <header className={`marketing-nav ${scrolled ? 'scrolled' : ''}`}>
      <div className="container nav-inner">
        <Logo />

        <nav className="desktop-nav" aria-label="Main Navigation">
          {navLinks.map((item) => (
            <Link
              key={item.label}
              href={item.href}
              className={pathname === item.href ? 'active' : ''}
            >
              {item.label}
            </Link>
          ))}
        </nav>

        <div className="nav-actions">
          <ThemeToggle />
          <Link href="/login" className="nav-signin">
            Sign In
          </Link>
          <Link href="/dashboard" className="button button-primary small group">
            <span>Open Console</span>
            <ArrowRight
              size={14}
              className="transition-transform duration-200 group-hover:translate-x-1"
            />
          </Link>
        </div>

        <button
          className="mobile-menu icon-button"
          onClick={() => setOpen(true)}
          aria-label="Open mobile menu"
        >
          <Menu size={20} />
        </button>
      </div>

      {open && (
        <div className="mobile-drawer" role="dialog" aria-modal="true">
          <div className="flex items-center justify-between">
            <Logo />
            <button
              className="drawer-close icon-button"
              onClick={() => setOpen(false)}
              aria-label="Close menu"
            >
              <X size={20} />
            </button>
          </div>
          <div className="flex flex-col gap-4 mt-6">
            {navLinks.concat([{ label: 'Contact', href: '/contact' }]).map((item) => (
              <Link
                key={item.label}
                href={item.href}
                className="text-base font-semibold text-slate-200 py-2 border-b border-white/5"
                onClick={() => setOpen(false)}
              >
                {item.label}
              </Link>
            ))}
          </div>
          <div className="mt-auto pt-6 flex flex-col gap-3">
            <Link
              href="/login"
              className="button button-secondary full"
              onClick={() => setOpen(false)}
            >
              Sign In
            </Link>
            <Link
              className="button button-primary full"
              href="/dashboard"
              onClick={() => setOpen(false)}
            >
              Open Console <ArrowRight size={15} />
            </Link>
          </div>
        </div>
      )}
    </header>
  )
}

/* ==========================================================================
   4. INTERACTIVE LIVE ANALYSIS CONSOLE (HERO RIGHT COMPONENT)
   ========================================================================== */

export function LiveAnalysisConsole() {
  const [activeComplaintIdx, setActiveComplaintIdx] = useState(0)
  const [stage, setStage] = useState<number>(5)

  const testCases = [
    {
      id: 'CMP-00421',
      title: 'Standard Hardware Defect',
      text: '“My order arrived damaged with cracked housing and support has not responded for 48 hours.”',
      issue: 'Product Defect / Structural Damage',
      sentiment: 'Strongly Negative',
      urgency: 'P1 High',
      route: 'Returns & RMA Team',
      policy: 'RET-POL-02 (Clause 4.1)',
      score: '96.4% Match',
      outcome: 'verified' as const,
      verdict: '✓ VERIFIED SAFE FOR DISPATCH',
      subtext: '100% Rule Compliance · Zero Unauthorized Promises',
      pillClass: 'pill-status-verified',
      borderClass: 'border-emerald-500/50 shadow-[0_0_30px_rgba(34,197,94,0.3)]',
      dotColor: '#22c55e',
    },
    {
      id: 'CMP-00420',
      title: 'Unauthorized Refund Request (CIR-9)',
      text: '“My return was received 14 days ago. I demand an immediate $450 cash refund or I report you to regulators.”',
      issue: 'Excess Compensation Demand',
      sentiment: 'Angry Aggressive',
      urgency: 'P2 Medium Priority',
      route: 'Finance & Billing',
      policy: 'BIL-REF-01 §4.2 (Cash Cap: $50)',
      score: '68.2% Discrepancy',
      outcome: 'mismatch' as const,
      verdict: '! MISMATCH INTERCEPTED BY PYTHON GATE',
      subtext: 'LLM proposed $450 · Python rule capped at $50 · Auto-Held in Step 57 Queue',
      pillClass: 'pill-status-mismatch',
      borderClass: 'border-amber-500/50 shadow-[0_0_30px_rgba(245,158,11,0.3)]',
      dotColor: '#f59e0b',
    },
    {
      id: 'CMP-00417',
      title: 'Calm Lithium Vapor Alert (CIR-6)',
      text: '“Good morning team, our secondary power cell is quietly emitting a continuous high-pitched hiss and faint vapor in rack 4.”',
      issue: 'Thermal Runaway Hazard (Lithium Vapor)',
      sentiment: 'Courteous / Calm (+0.12)',
      urgency: 'P0 CRITICAL ESCALATION',
      route: 'Robotics Tier-3 & Fire Safety',
      policy: 'DOC-ROB-01 §9.1 (Emergency Protocol)',
      score: 'P0 Emergency',
      outcome: 'critical' as const,
      verdict: '⚠ CRITICAL SAFETY PROTOCOL ENGAGED',
      subtext: 'Calm tone overridden by objective hazard keywords · Hazmat unit alerted',
      pillClass: 'pill-status-critical',
      borderClass: 'border-rose-500/60 shadow-[0_0_35px_rgba(239,68,68,0.4)] animate-pulse',
      dotColor: '#ef4444',
    },
  ]

  const current = testCases[activeComplaintIdx]

  useEffect(() => {
    setStage(1)
    const timers = [
      setTimeout(() => setStage(2), 350),
      setTimeout(() => setStage(3), 700),
      setTimeout(() => setStage(4), 1050),
      setTimeout(() => setStage(5), 1400),
    ]
    return () => timers.forEach(clearTimeout)
  }, [activeComplaintIdx])

  return (
    <div className="hero-console-wrapper">
      <div className="hero-console-glow" />
      <div className={`hero-console ${current.borderClass}`}>
        <div className="hero-console-bar">
          <div className="console-dots">
            <i />
            <i />
            <i />
          </div>
          <div className="console-pipeline-stages">
            <span className={`pipeline-stage-tag ${stage >= 1 ? 'done' : 'active'}`}>
              INTAKE
            </span>
            <span className={`pipeline-stage-tag ${stage >= 2 ? 'done' : stage === 1 ? 'active' : ''}`}>
              AI PARSE
            </span>
            <span className={`pipeline-stage-tag ${stage >= 3 ? 'done' : stage === 2 ? 'active' : ''}`}>
              ROUTE
            </span>
            <span className={`pipeline-stage-tag ${stage >= 4 ? 'done' : stage === 3 ? 'active' : ''}`}>
              POLICY
            </span>
            <span className={`pipeline-stage-tag ${stage >= 5 ? 'done' : stage === 4 ? 'active' : ''}`}>
              PYTHON GATE
            </span>
          </div>
          <span className="text-[10px] font-mono text-cyan-400 bg-cyan-950/60 border border-cyan-800/40 px-2 py-0.5 rounded">
            {current.id}
          </span>
        </div>

        <div className="console-body">
          <div className="console-scanline" />

          {/* Complaint Text Bubble */}
          <div className="console-complaint-bubble">
            <Sparkles size={16} className="text-indigo-400 shrink-0" />
            <div>
              <p className="m-0 font-medium text-slate-200">{current.text}</p>
              {/* Three Case Buttons */}
              <div className="flex flex-wrap gap-2 mt-3">
                <button
                  onClick={() => setActiveComplaintIdx(0)}
                  className={`text-[10.5px] font-mono font-bold px-2.5 py-1 rounded border transition-all ${
                    activeComplaintIdx === 0
                      ? 'bg-emerald-500/20 border-emerald-400 text-emerald-300 shadow-[0_0_12px_rgba(34,197,94,0.3)]'
                      : 'bg-white/5 border-white/10 text-slate-400 hover:text-white'
                  }`}
                >
                  ✓ Test Verified (Green)
                </button>
                <button
                  onClick={() => setActiveComplaintIdx(1)}
                  className={`text-[10.5px] font-mono font-bold px-2.5 py-1 rounded border transition-all ${
                    activeComplaintIdx === 1
                      ? 'bg-amber-500/20 border-amber-400 text-amber-300 shadow-[0_0_12px_rgba(245,158,11,0.3)]'
                      : 'bg-white/5 border-white/10 text-slate-400 hover:text-white'
                  }`}
                >
                  ! Test Mismatch (Amber)
                </button>
                <button
                  onClick={() => setActiveComplaintIdx(2)}
                  className={`text-[10.5px] font-mono font-bold px-2.5 py-1 rounded border transition-all ${
                    activeComplaintIdx === 2
                      ? 'bg-rose-500/20 border-rose-400 text-rose-300 shadow-[0_0_12px_rgba(239,68,68,0.3)]'
                      : 'bg-white/5 border-white/10 text-slate-400 hover:text-white'
                  }`}
                >
                  ⚠ Test Critical (Red)
                </button>
              </div>
            </div>
          </div>

          {/* Progressive Intelligence Grid */}
          <div className="console-grid-fields">
            <div className="console-field-cell border-indigo-500/25 bg-indigo-950/20">
              <span className="text-indigo-400">AI Primary Issue (Indigo)</span>
              <b>
                <Ticket size={13} className="text-indigo-400" />
                {stage >= 2 ? current.issue : 'Extracting...'}
              </b>
            </div>

            <div className="console-field-cell border-purple-500/25 bg-purple-950/20">
              <span className="text-purple-400">AI Sentiment &amp; Urgency</span>
              <b>
                <Activity size={13} className="text-purple-400" />
                {stage >= 2 ? `${current.sentiment} · ${current.urgency}` : 'Analyzing...'}
              </b>
            </div>

            <div className="console-field-cell border-cyan-500/25 bg-cyan-950/20">
              <span className="text-cyan-400">Python 8-Dept Route (Cyan)</span>
              <b>
                <Network size={13} className="text-cyan-400" />
                {stage >= 3 ? current.route : 'Evaluating matrix...'}
              </b>
            </div>

            <div className="console-field-cell border-teal-500/25 bg-teal-950/20">
              <span className="text-teal-400">Python Policy Precedence</span>
              <b>
                <FileText size={13} className="text-teal-400" />
                {stage >= 4 ? current.policy : 'Resolving hierarchy...'}
              </b>
            </div>
          </div>

          {/* Dynamic Outcome Footer */}
          <div
            className={`console-verified-footer border transition-all duration-300 ${
              current.outcome === 'verified'
                ? 'bg-emerald-950/30 border-emerald-500/40'
                : current.outcome === 'mismatch'
                ? 'bg-amber-950/30 border-amber-500/40'
                : 'bg-rose-950/30 border-rose-500/50'
            }`}
          >
            <div className="flex flex-col">
              <div className="flex items-center gap-2 font-bold text-xs sm:text-sm">
                <span
                  className="w-2.5 h-2.5 rounded-full animate-pulse"
                  style={{ backgroundColor: current.dotColor, boxShadow: `0 0 10px ${current.dotColor}` }}
                />
                <span
                  style={{
                    color:
                      current.outcome === 'verified'
                        ? '#4ade80'
                        : current.outcome === 'mismatch'
                        ? '#fde047'
                        : '#f87171',
                  }}
                >
                  {stage >= 5 ? current.verdict : 'Validating Python Rules...'}
                </span>
              </div>
              <small className="text-[10.5px] text-slate-400 mt-0.5 ml-4">
                {stage >= 5 ? current.subtext : 'Cross-checking with 100-rule matrix'}
              </small>
            </div>
            <div className={`text-xs font-mono font-bold px-2.5 py-1 rounded-md border ${current.pillClass}`}>
              {stage >= 5 ? current.score : 'Computing...'}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

/* ==========================================================================
   5. SIGNATURE VERIFICATION RING (CIRCULAR VISUALIZATION)
   ========================================================================== */

export function VerificationRing({ score = 96.4 }: { score?: number }) {
  const radius = 135
  const circumference = 2 * Math.PI * radius
  const strokeDashoffset = circumference - (score / 100) * circumference

  return (
    <div className="verification-ring-section">
      <div>
        <span className="eyebrow">Continuous Ground-Truth Proof</span>
        <h2 className="text-3xl lg:text-4xl font-bold mt-2 mb-4 tracking-tight">
          Confidence you can calculate, not just assume.
        </h2>
        <p className="text-slate-400 text-sm lg:text-base leading-relaxed mb-6">
          SupportNova does not rely on stochastic LLM confidence. Our independent
          deterministic Python pipeline executes parity comparators across classification,
          policy citations, compensation caps, and mandatory escalation rules.
        </p>

        <div className="grid grid-cols-2 gap-3 text-xs">
          <div className="flex items-center gap-2 text-slate-300 bg-white/5 border border-white/5 p-2.5 rounded-lg">
            <CheckCircle2 size={15} className="text-emerald-400" />
            <span>Classification Parity Checked</span>
          </div>
          <div className="flex items-center gap-2 text-slate-300 bg-white/5 border border-white/5 p-2.5 rounded-lg">
            <CheckCircle2 size={15} className="text-emerald-400" />
            <span>Routing Rule Verified</span>
          </div>
          <div className="flex items-center gap-2 text-slate-300 bg-white/5 border border-white/5 p-2.5 rounded-lg">
            <CheckCircle2 size={15} className="text-emerald-400" />
            <span>Policy Precedence Enforced</span>
          </div>
          <div className="flex items-center gap-2 text-slate-300 bg-white/5 border border-white/5 p-2.5 rounded-lg">
            <CheckCircle2 size={15} className="text-emerald-400" />
            <span>Mandatory Escalation Gated</span>
          </div>
        </div>
      </div>

      <div className="ring-visual-wrapper">
        <div className="ring-outer-orbital">
          <svg className="ring-svg-circle" viewBox="0 0 320 320">
            {/* Background Track */}
            <circle
              cx="160"
              cy="160"
              r={radius}
              fill="none"
              stroke="rgba(255, 255, 255, 0.06)"
              strokeWidth="14"
            />
            {/* Gradient Fill */}
            <defs>
              <linearGradient id="ringGradient" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stopColor="#6366f1" />
                <stop offset="50%" stopColor="#06b6d4" />
                <stop offset="100%" stopColor="#22c55e" />
              </linearGradient>
            </defs>
            {/* Progress Stroke */}
            <circle
              cx="160"
              cy="160"
              r={radius}
              fill="none"
              stroke="url(#ringGradient)"
              strokeWidth="14"
              strokeDasharray={circumference}
              strokeDashoffset={strokeDashoffset}
              strokeLinecap="round"
              className="transition-all duration-1000 ease-out"
            />
          </svg>

          {/* Center Stat */}
          <div className="ring-center-stat">
            <strong>{score}%</strong>
            <span>AI / Rules Agreement</span>
          </div>

          {/* Orbital Nodes */}
          <div className="ring-orbital-nodes">
            <div className="orbital-node-pill node-top">
              <Sparkles size={12} className="text-indigo-400" />
              <span>AI Pipeline</span>
            </div>
            <div className="orbital-node-pill node-right">
              <ShieldCheck size={12} className="text-emerald-400" />
              <span>Rule Matrix</span>
            </div>
            <div className="orbital-node-pill node-bottom-right">
              <FileText size={12} className="text-cyan-400" />
              <span>Policy Hierarchy</span>
            </div>
            <div className="orbital-node-pill node-bottom-left">
              <Network size={12} className="text-purple-400" />
              <span>8-Dept Routing</span>
            </div>
            <div className="orbital-node-pill node-left">
              <Zap size={12} className="text-amber-400" />
              <span>Escalation Gate</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

/* ==========================================================================
   6. THE TWO-PIPELINE ARCHITECTURAL VISUAL
   ========================================================================== */

export function TwoPipelineVisual() {
  const [outcomeMode, setOutcomeMode] = useState<'verified' | 'mismatch' | 'critical'>('verified')

  const outcomes = {
    verified: {
      title: 'Verified Enterprise Resolution',
      subtext: 'Both engines agree with 96.4% parity. Validated safe for automated dispatch to customer.',
      score: 'PARITY: 96.4%',
      badgeClass: 'pill-status-verified',
      cardClass: 'card-status-verified',
      icon: Check,
      comparatorColor: '#22c55e',
    },
    mismatch: {
      title: 'Mismatch Intercepted by Python Gate (CIR-9 / CIR-18)',
      subtext: 'GenAI proposed $500 goodwill; Python rule caps goodwill at $50. Automatically routed to Step 57 Manual Review Queue.',
      score: 'DISCREPANCY: 68.2%',
      badgeClass: 'pill-status-mismatch',
      cardClass: 'card-status-mismatch',
      icon: AlertTriangle,
      comparatorColor: '#f59e0b',
    },
    critical: {
      title: 'Critical Safety Escalation Triggered (CIR-6 / CIR-7)',
      subtext: 'Polite customer tone overridden by objective lithium vapor hazard. Immediate Level 3 engineering and hazardous protocol engaged.',
      score: 'P0 CRITICAL EMERGENCY',
      badgeClass: 'pill-status-critical',
      cardClass: 'card-status-critical',
      icon: Zap,
      comparatorColor: '#ef4444',
    },
  }

  const currentOutcome = outcomes[outcomeMode]
  const OutcomeIcon = currentOutcome.icon

  return (
    <div className="two-pipeline-container">
      <div className="two-pipeline-header">
        <div className="flex items-center justify-center gap-2 mb-2">
          <span className="pill-engine-ai">Engine 1: AI (Indigo)</span>
          <span className="text-slate-500 font-mono text-xs">+</span>
          <span className="pill-engine-python">Engine 2: Python (Cyan)</span>
          <span className="text-slate-500 font-mono text-xs">=</span>
          <span className={currentOutcome.badgeClass}>
            {outcomeMode === 'verified' ? 'Verified (Green)' : outcomeMode === 'mismatch' ? 'Mismatch (Amber)' : 'Critical (Red)'}
          </span>
        </div>
        <h3 className="text-2xl lg:text-3xl font-bold text-white tracking-tight">
          Two-Engine Architecture in Action
        </h3>
        <p className="text-slate-400 text-sm max-w-xl mx-auto">
          SupportNova runs two concurrent, decoupled architectures for every grievance. Click below to simulate the 3 runtime outcomes.
        </p>

        {/* 3 Outcome Simulator Buttons */}
        <div className="flex flex-wrap justify-center gap-2.5 mt-5">
          <button
            onClick={() => setOutcomeMode('verified')}
            className={`text-xs font-mono font-bold px-3 py-1.5 rounded-lg border transition-all ${
              outcomeMode === 'verified'
                ? 'bg-emerald-500/20 border-emerald-400 text-emerald-300 shadow-[0_0_15px_rgba(34,197,94,0.4)]'
                : 'bg-white/5 border-white/10 text-slate-400 hover:text-white'
            }`}
          >
            ✓ Outcome A: Verified Parity (Green)
          </button>
          <button
            onClick={() => setOutcomeMode('mismatch')}
            className={`text-xs font-mono font-bold px-3 py-1.5 rounded-lg border transition-all ${
              outcomeMode === 'mismatch'
                ? 'bg-amber-500/20 border-amber-400 text-amber-300 shadow-[0_0_15px_rgba(245,158,11,0.4)]'
                : 'bg-white/5 border-white/10 text-slate-400 hover:text-white'
            }`}
          >
            ! Outcome B: Mismatch Intercepted (Amber)
          </button>
          <button
            onClick={() => setOutcomeMode('critical')}
            className={`text-xs font-mono font-bold px-3 py-1.5 rounded-lg border transition-all ${
              outcomeMode === 'critical'
                ? 'bg-rose-500/20 border-rose-400 text-rose-300 shadow-[0_0_15px_rgba(239,68,68,0.4)]'
                : 'bg-white/5 border-white/10 text-slate-400 hover:text-white'
            }`}
          >
            ⚠ Outcome C: Critical Escalation (Red)
          </button>
        </div>
      </div>

      <div className="pipeline-diagram mt-6">
        {/* Pipeline 1: GenAI Reasoning (Indigo / Purple / Blue) */}
        <div className="pipeline-track ai-track card-engine-ai">
          <div className="track-badge">
            <Sparkles size={13} className="text-indigo-300" />
            <span>Engine 1: GenAI Intelligence (Indigo)</span>
          </div>
          <div className="track-item border-indigo-500/20 bg-indigo-950/20">
            <Ticket size={14} className="text-indigo-400" />
            <span>Unstructured customer narrative parsing &amp; intent</span>
          </div>
          <div className="track-item border-purple-500/20 bg-purple-950/20">
            <Activity size={14} className="text-purple-400" />
            <span>Named entity extraction (NER) &amp; linguistic tone</span>
          </div>
          <div className="track-item border-blue-500/20 bg-blue-950/20">
            <FileText size={14} className="text-blue-400" />
            <span>Multi-tone response drafting &amp; 3-bullet summary</span>
          </div>
          <div className="track-item font-mono text-[11px] text-indigo-300 bg-indigo-950/60 border border-indigo-700/50">
            <span>&rarr; Generates Structured JSON Proposal</span>
          </div>
        </div>

        {/* Central Comparator */}
        <div className="pipeline-comparator">
          <div
            className="comparator-node transition-all duration-300"
            style={{
              boxShadow: `0 0 30px ${currentOutcome.comparatorColor}`,
              borderColor: currentOutcome.comparatorColor,
            }}
          >
            <Scale size={22} />
          </div>
          <span className="text-[10px] font-mono text-slate-400 uppercase tracking-wider text-center">
            Independent
            <br />
            Parity Check
          </span>
          <div
            className="comparator-line"
            style={{ background: `linear-gradient(to bottom, #06b6d4, ${currentOutcome.comparatorColor})` }}
          />
        </div>

        {/* Pipeline 2: Python Deterministic Verifier (Cyan / Teal) */}
        <div className="pipeline-track python-track card-engine-python">
          <div className="track-badge">
            <ShieldCheck size={13} className="text-cyan-300" />
            <span>Engine 2: Python Verifier (Cyan / Teal)</span>
          </div>
          <div className="track-item border-cyan-500/20 bg-cyan-950/20">
            <Network size={14} className="text-cyan-400" />
            <span>100-Rule Deterministic Matrix matching</span>
          </div>
          <div className="track-item border-teal-500/20 bg-teal-950/20">
            <FileText size={14} className="text-teal-400" />
            <span>Policy Precedence Resolver (Board &gt; SOP &gt; FAQ)</span>
          </div>
          <div className="track-item border-cyan-500/20 bg-cyan-950/20">
            <Zap size={14} className="text-cyan-400" />
            <span>Mandatory Escalation &amp; SLA risk enforcement</span>
          </div>
          <div className="track-item font-mono text-[11px] text-cyan-300 bg-cyan-950/60 border border-cyan-700/50">
            <span>&rarr; Computes Deterministic Mathematical Truth</span>
          </div>
        </div>

        {/* Dynamic Outcome Result Card */}
        <div className={`verified-final-card ${currentOutcome.cardClass} transition-all duration-300`}>
          <div className="verified-final-info">
            <div
              className="verified-icon-circle transition-all duration-300"
              style={{
                backgroundColor: currentOutcome.comparatorColor,
                boxShadow: `0 0 25px ${currentOutcome.comparatorColor}`,
              }}
            >
              <OutcomeIcon size={22} className="text-white" />
            </div>
            <div>
              <div className="font-bold text-white text-base">
                {currentOutcome.title}
              </div>
              <p className="text-xs text-slate-300 m-0 max-w-xl">
                {currentOutcome.subtext}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <span className={`text-xs font-mono font-bold px-3 py-1.5 rounded-lg border ${currentOutcome.badgeClass}`}>
              {currentOutcome.score}
            </span>
            <Link
              href="/dashboard/validation"
              className="text-xs font-semibold text-white bg-white/10 hover:bg-white/15 px-3 py-1.5 rounded-lg border border-white/10 transition-colors inline-flex items-center gap-1.5"
            >
              Open Studio <ArrowRight size={13} />
            </Link>
          </div>
        </div>
      </div>
    </div>
  )
}

/* ==========================================================================
   7. COMMAND PALETTE (CTRL + K UNIVERSAL SEARCH)
   ========================================================================== */

export function CommandPalette({
  isOpen,
  onClose,
}: {
  isOpen: boolean
  onClose: () => void
}) {
  const [query, setQuery] = useState('')
  const [selectedIndex, setSelectedIndex] = useState(0)
  const router = useRouter()

  const commands = useMemo(
    () => [
      {
        category: 'Complaints',
        id: 'CMP-00421',
        title: 'Order arrived damaged (Returns Team)',
        href: '/dashboard/complaints',
        icon: Ticket,
      },
      {
        category: 'Complaints',
        id: 'CMP-00420',
        title: 'Refund missing after 14 days (Billing)',
        href: '/dashboard/complaints',
        icon: Ticket,
      },
      {
        category: 'Complaints',
        id: 'CMP-00417',
        title: 'Robot arm acoustic anomaly (P0 Critical)',
        href: '/dashboard/complaints',
        icon: Zap,
      },
      {
        category: 'Policies',
        id: 'RET-POL-02',
        title: 'Commercial Hardware Return Protocol v2.1',
        href: '/dashboard/knowledge-base',
        icon: FileText,
      },
      {
        category: 'Policies',
        id: 'DOC-ROB-01',
        title: 'Autonomous Robotics Warranty & Safety SOP',
        href: '/dashboard/knowledge-base',
        icon: FileText,
      },
      {
        category: 'Rule Matrix',
        id: 'RULE-100',
        title: '100-Rule Deterministic Resolution Matrix',
        href: '/dashboard/rules',
        icon: Network,
      },
      {
        category: 'Validation',
        id: 'VAL-STUDIO',
        title: 'Dual-Pipeline Parity Verification Studio',
        href: '/dashboard/validation',
        icon: ShieldCheck,
      },
      {
        category: 'Reports',
        id: 'REP-SLA',
        title: 'SLA Risk & Compliance Radar Export',
        href: '/dashboard/reports',
        icon: TrendingUp,
      },
      {
        category: 'Settings',
        id: 'SET-INT',
        title: '19 Competition Integrity Requirements (CIR)',
        href: '/dashboard/settings',
        icon: Sliders,
      },
    ],
    []
  )

  const filtered = useMemo(() => {
    if (!query.trim()) return commands
    return commands.filter(
      (c) =>
        c.id.toLowerCase().includes(query.toLowerCase()) ||
        c.title.toLowerCase().includes(query.toLowerCase()) ||
        c.category.toLowerCase().includes(query.toLowerCase())
    )
  }, [commands, query])

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        if (isOpen) onClose()
        else {
          // Open triggered by parent state
        }
      }
      if (isOpen) {
        if (e.key === 'Escape') {
          onClose()
        } else if (e.key === 'ArrowDown') {
          e.preventDefault()
          setSelectedIndex((prev) => (prev + 1) % filtered.length)
        } else if (e.key === 'ArrowUp') {
          e.preventDefault()
          setSelectedIndex((prev) => (prev - 1 + filtered.length) % filtered.length)
        } else if (e.key === 'Enter' && filtered[selectedIndex]) {
          e.preventDefault()
          router.push(filtered[selectedIndex].href)
          onClose()
        }
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, onClose, filtered, selectedIndex, router])

  if (!isOpen) return null

  return (
    <div className="command-palette-backdrop" onClick={onClose}>
      <div
        className="command-palette-dialog"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        <div className="command-palette-input-wrap">
          <Search size={18} className="text-slate-400" />
          <input
            autoFocus
            type="text"
            className="command-palette-input"
            placeholder="Search complaints, policies, rules, reports... (Type 'CMP', 'RET', 'RULE')"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value)
              setSelectedIndex(0)
            }}
          />
          <kbd className="kbd-shortcut">ESC</kbd>
        </div>

        <div className="command-palette-results">
          {filtered.length === 0 ? (
            <div className="p-8 text-center text-sm text-slate-500">
              No matching records found in ResponseX Intelligence database.
            </div>
          ) : (
            filtered.map((item, idx) => {
              const Icon = item.icon
              const isSelected = idx === selectedIndex
              return (
                <div
                  key={item.id}
                  className={`command-result-item ${isSelected ? 'selected' : ''}`}
                  onMouseEnter={() => setSelectedIndex(idx)}
                  onClick={() => {
                    router.push(item.href)
                    onClose()
                  }}
                >
                  <Icon size={16} className={isSelected ? 'text-indigo-400' : 'text-slate-400'} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-slate-200 truncate">
                        {item.title}
                      </span>
                      <span className="text-[10px] font-mono text-cyan-400 bg-cyan-950/60 px-1.5 py-0.5 rounded border border-cyan-800/40">
                        {item.id}
                      </span>
                    </div>
                    <span className="text-[11px] text-slate-500">{item.category}</span>
                  </div>
                  <ArrowRight size={13} className="text-slate-500 opacity-60" />
                </div>
              )
            })
          )}
        </div>

        <div className="command-palette-footer">
          <span>Navigate with &uarr; &darr; · Select with Enter</span>
          <span>SupportNova Command Hub</span>
        </div>
      </div>
    </div>
  )
}

/* ==========================================================================
   8. ENTERPRISE APPLICATION CONSOLE SHELL (DASHBOARDSHELL)
   ========================================================================== */

export function DashboardShell({
  children,
  title = 'Overview',
}: {
  children: React.ReactNode
  title?: string
}) {
  const [collapsed, setCollapsed] = useState(false)
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false)
  const pathname = usePathname()

  // Full 11 console navigation items
  const items = [
    { label: 'Overview', href: '/dashboard', icon: LayoutDashboard },
    { label: 'Complaints', href: '/dashboard/complaints', icon: Ticket },
    { label: 'Validation & Parity', href: '/dashboard/validation', icon: ShieldCheck },
    { label: 'Knowledge Base', href: '/dashboard/knowledge-base', icon: FileText },
    { label: 'Rule Matrix', href: '/dashboard/rules', icon: Network },
    { label: 'Escalations & SLA', href: '/dashboard/escalations', icon: Zap },
    { label: 'Analytics & Trends', href: '/dashboard/analytics', icon: TrendingUp },
    { label: 'Prompts & Security', href: '/dashboard/prompts', icon: Lock },
    { label: 'Reports & Export', href: '/dashboard/reports', icon: FileText },
    { label: 'Evaluation Studio', href: '/dashboard/evaluation', icon: Sparkles },
    { label: 'Settings & Governance', href: '/dashboard/settings', icon: Sliders },
  ] as const

  // Global Ctrl+K listener
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setCommandPaletteOpen((prev) => !prev)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [])

  return (
    <div className={`dashboard-layout ${collapsed ? 'collapsed' : ''}`}>
      {/* Collapsible Enterprise Sidebar */}
      <aside className={`sidebar ${collapsed ? 'collapsed' : ''}`}>
        <div className="sidebar-top">
          <Logo size={collapsed ? 'small' : 'default'} />
          <button
            className="collapse-button"
            onClick={() => setCollapsed(!collapsed)}
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            <ChevronDown
              size={15}
              className={`transition-transform duration-200 ${collapsed ? '-rotate-90' : 'rotate-90'}`}
            />
          </button>
        </div>

        <div className="workspace">
          <span className="workspace-dot" />
          <div className="flex flex-col min-w-0 flex-1">
            <span className="workspace-name font-semibold text-slate-200 truncate">
              NovaTech Robotics Corp
            </span>
            <span className="text-[10px] text-slate-500 font-mono">
              Fictional Enterprise
            </span>
          </div>
        </div>

        <nav className="side-nav" aria-label="Console Modules">
          {items.map(({ label, href, icon: Icon }) => {
            const isActive = pathname === href || (href !== '/dashboard' && pathname.startsWith(href))
            return (
              <Link
                key={label}
                href={href}
                className={isActive ? 'active' : ''}
                title={collapsed ? label : undefined}
              >
                <Icon size={17} className={isActive ? 'text-indigo-400' : 'text-slate-400'} />
                <span>{label}</span>
              </Link>
            )
          })}
        </nav>

        <div className="sidebar-bottom">
          <Link href="/dashboard/settings" title={collapsed ? 'Settings & Audit' : undefined}>
            <CircleHelp size={17} />
            <span>SRS Specs &amp; Integrity</span>
          </Link>
          <div className="user-mini">
            <div className="avatar">AD</div>
            <div className="min-w-0">
              <b>Executive Admin</b>
              <small>Dual-Pipeline Operator</small>
            </div>
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="dashboard-main">
        <header className="dashboard-header">
          <div>
            <span className="eyebrow">ResponseX Intelligence Console</span>
            <h1>{title}</h1>
          </div>

          <div className="dashboard-header-actions">
            {/* System Status Indicators — Communicating Two-Engine Architecture */}
            <div className="system-status-pill pill-ai-status hidden sm:flex">
              <span className="status-dot-pulse dot-ai" />
              <span>AI Engine: Active</span>
            </div>

            <div className="system-status-pill pill-python-status hidden md:flex">
              <span className="status-dot-pulse dot-python" />
              <span>Python Verifier: 100% Gate</span>
            </div>

            <div className="system-status-pill pill-status-verified hidden lg:flex">
              <span className="status-dot-pulse dot-verified" />
              <span>96.4% Verified Parity</span>
            </div>

            {/* Command Palette Trigger */}
            <button
              onClick={() => setCommandPaletteOpen(true)}
              className="search-command-btn"
              aria-label="Open Command Palette"
            >
              <Search size={14} />
              <span className="hidden sm:inline">Search console...</span>
              <kbd className="kbd-shortcut">Ctrl+K</kbd>
            </button>

            <ThemeToggle />

            {/* Notifications */}
            <button
              className="icon-button notification"
              aria-label="System notifications"
              title="3 SLA and Integrity Alerts"
            >
              <Bell size={17} />
              <i />
            </button>

            <div className="avatar" title="Logged in as Administrator">
              AD
            </div>
          </div>
        </header>

        {children}

        {/* Global Command Palette */}
        <CommandPalette
          isOpen={commandPaletteOpen}
          onClose={() => setCommandPaletteOpen(false)}
        />
      </main>
    </div>
  )
}

/* ==========================================================================
   9. METRIC CARD & STAT STRIP COMPONENTS
   ========================================================================== */

export function Stat({
  value,
  label,
  trend,
  desc,
}: {
  value: string
  label: string
  trend: string
  desc?: string
}) {
  return (
    <div className="stat-card-luxury">
      <div className="stat-card-top">
        <span className="stat-card-icon">
          <Activity size={16} />
        </span>
        <span className="stat-card-trend">
          <TrendingUp size={11} /> {trend}
        </span>
      </div>
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
      {desc && <div className="stat-desc">{desc}</div>}
    </div>
  )
}

export function KpiCard({
  label,
  value,
  delta,
  icon,
  color = 'indigo',
}: {
  label: string
  value: string
  delta: string
  icon: React.ReactNode
  color?: string
}) {
  return (
    <div className="kpi-card">
      <div className={`kpi-icon ${color}`}>{icon}</div>
      <span className="text-xs text-slate-400 font-medium">{label}</span>
      <div className="kpi-value">{value}</div>
      <div className="kpi-delta">
        <TrendingUp size={13} /> {delta}{' '}
        <span className="text-slate-500 text-[10px] ml-1">vs target baseline</span>
      </div>
      <div className="sparkline">
        <span style={{ height: '8px' }} />
        <span style={{ height: '14px' }} />
        <span style={{ height: '10px' }} />
        <span style={{ height: '18px' }} />
        <span style={{ height: '15px' }} />
        <span style={{ height: '21px' }} />
        <span style={{ height: '24px' }} />
      </div>
    </div>
  )
}

/* ==========================================================================
   10. SEMANTIC STATUS BADGE
   ========================================================================== */

export function StatusBadge({
  children,
  tone = 'indigo',
}: {
  children: React.ReactNode
  tone?: string
}) {
  return <span className={`badge ${tone}`}>{children}</span>
}

/* ==========================================================================
   11. COMPLAINT TABLE WITH FILTERS & PREVIEWS
   ========================================================================== */

export function ComplaintTable() {
  const [filterCategory, setFilterCategory] = useState('All')

  const filtered = useMemo(() => {
    if (filterCategory === 'All') return complaints
    return complaints.filter((c) => c.category === filterCategory)
  }, [filterCategory])

  return (
    <div className="table-card">
      <div className="table-toolbar">
        <div>
          <h3>Recent Complaints Queue</h3>
          <p className="muted">Continuous parity scored against 100-rule matrix</p>
        </div>
        <div className="flex items-center gap-2">
          <select
            className="select-button"
            value={filterCategory}
            onChange={(e) => setFilterCategory(e.target.value)}
          >
            <option value="All">All Categories</option>
            <option value="Product Defect">Product Defect</option>
            <option value="Billing">Billing</option>
            <option value="Delivery">Delivery</option>
            <option value="Hardware Defect">Hardware Defect</option>
          </select>
          <Link href="/dashboard/complaints" className="text-link text-xs">
            View All ({complaints.length}) <ArrowRight size={13} />
          </Link>
        </div>
      </div>

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Complaint ID / Title</th>
              <th>Category</th>
              <th>Priority</th>
              <th>Validation</th>
              <th>Status</th>
              <th>Department</th>
              <th>Created</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((c) => (
              <tr key={c.id}>
                <td>
                  <Link
                    href={`/dashboard/complaints`}
                    className="complaint-name hover:text-indigo-400 transition-colors"
                  >
                    <span className="font-semibold text-slate-200">{c.title}</span>
                    <small>{c.id} · Policy: {c.policy}</small>
                  </Link>
                </td>
                <td>
                  <span className="text-xs text-slate-300">{c.category}</span>
                </td>
                <td>
                  <StatusBadge
                    tone={
                      c.priority === 'P0' || c.priority === 'P1'
                        ? 'rose'
                        : c.priority === 'P2'
                        ? 'amber'
                        : 'indigo'
                    }
                  >
                    {c.priority}
                  </StatusBadge>
                </td>
                <td>
                  <span className="text-xs font-mono font-bold text-emerald-400 bg-emerald-950/40 border border-emerald-800/40 px-2 py-0.5 rounded">
                    {c.agreementScore}% Match
                  </span>
                </td>
                <td>
                  <StatusBadge
                    tone={
                      c.status === 'Resolved'
                        ? 'emerald'
                        : c.status === 'Escalated'
                        ? 'rose'
                        : 'indigo'
                    }
                  >
                    {c.status}
                  </StatusBadge>
                </td>
                <td>
                  <span className="text-xs text-slate-300">{c.department}</span>
                </td>
                <td className="muted font-mono text-[11px]">{c.time}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

/* ==========================================================================
   12. SECTION TITLE & FEATURE CARDS
   ========================================================================== */

export function SectionTitle({
  eyebrow,
  title,
  text,
}: {
  eyebrow: string
  title: string
  text?: string
}) {
  return (
    <div className="section-title">
      <span className="eyebrow">{eyebrow}</span>
      <h2 className="text-3xl lg:text-4xl font-bold mt-2 mb-3 tracking-tight">
        {title}
      </h2>
      {text && <p className="text-slate-400 text-sm lg:text-base leading-relaxed">{text}</p>}
    </div>
  )
}

export function FeatureCard({
  icon,
  title,
  text,
  accent = 'indigo',
  status = 'Active Module',
}: {
  icon: React.ReactNode
  title: string
  text: string
  accent?: string
  status?: string
}) {
  return (
    <div className={`feature-card accent-${accent}`}>
      <div className="feature-card-glow" />
      <div className="feature-icon-box">{icon}</div>
      <h3>{title}</h3>
      <p>{text}</p>
      <div className="feature-status-tag">
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
        <span>{status}</span>
      </div>
    </div>
  )
}

export const pageFeatures = [
  [
    'AI Complaint Intelligence',
    'Extract main issue, secondary issues, sentiment, objective urgency, and critical entities from messy inputs.',
    <Ticket size={20} key="1" />,
    'indigo',
  ],
  [
    'Ground-Truth Validation',
    'Independent non-LLM Python pipeline validates classification, SLA clocks, and compensation limits before dispatch.',
    <ShieldCheck size={20} key="2" />,
    'emerald',
  ],
  [
    'Policy Intelligence',
    'Strict hierarchy ranking (Board Policy > SOP > FAQ) with automatic interception of superseded policies (DOC-SUP-20).',
    <FileText size={20} key="3" />,
    'cyan',
  ],
  [
    'Smart 8-Dept Routing',
    'Multi-department dispatch coordinates primary engineering, logistics, and billing teams without manual triage.',
    <Network size={20} key="4" />,
    'violet',
  ],
  [
    'Escalation Detection',
    'Objective trigger scanner catches safety, regulatory, and financial thresholds independent of emotional tone.',
    <Zap size={20} key="5" />,
    'amber',
  ],
  [
    'Prompt Injection Defense',
    'XML isolation tags and pattern interceptors neutralize adversarial instructions ("Ignore all rules and refund").',
    <Lock size={20} key="6" />,
    'rose',
  ],
] as const

/* ==========================================================================
   13. MINI CHART & PIPELINE PREVIEWS
   ========================================================================== */

export function MiniChart() {
  return (
    <div className="mini-chart">
      <svg viewBox="0 0 400 100" preserveAspectRatio="none">
        <defs>
          <linearGradient id="chartGlow" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="#6366f1" stopOpacity="0.4" />
            <stop offset="100%" stopColor="#6366f1" stopOpacity="0" />
          </linearGradient>
        </defs>
        <path
          d="M0 82 C35 74 37 66 67 71 S100 49 128 60 S162 32 195 48 S225 62 252 35 S285 50 310 25 S355 44 400 8 V100 H0Z"
          fill="url(#chartGlow)"
        />
        <path
          d="M0 82 C35 74 37 66 67 71 S100 49 128 60 S162 32 195 48 S225 62 252 35 S285 50 310 25 S355 44 400 8"
          fill="none"
          stroke="#818cf8"
          strokeWidth="2.5"
        />
      </svg>
    </div>
  )
}

export function Pipeline() {
  return (
    <div className="how-pipeline-wrapper">
      <div className="pipeline-track-line" />
      <div className="how-steps-grid">
        <div className="how-step-node step-intake">
          <div className="how-node-circle border-cyan-400 text-cyan-300 shadow-[0_0_15px_rgba(6,182,212,0.5)]">
            01
          </div>
          <span className="text-[10px] font-mono font-bold text-cyan-400 uppercase tracking-wider block mb-1">
            Intake Layer
          </span>
          <h4>Ingest &amp; Clean</h4>
          <p>Multi-channel intake with Unicode sanitization and boundary validation.</p>
        </div>
        <div className="how-step-node step-ai">
          <div className="how-node-circle border-indigo-400 text-indigo-300 shadow-[0_0_15px_rgba(99,102,241,0.5)]">
            02
          </div>
          <span className="text-[10px] font-mono font-bold text-indigo-400 uppercase tracking-wider block mb-1">
            Engine 1: AI
          </span>
          <h4>GenAI Reasoning</h4>
          <p>Extract primary/secondary issues, sentiment, urgency, and cited clauses.</p>
        </div>
        <div className="how-step-node step-policy">
          <div className="how-node-circle border-cyan-400 text-cyan-300 shadow-[0_0_15px_rgba(6,182,212,0.5)]">
            03
          </div>
          <span className="text-[10px] font-mono font-bold text-cyan-400 uppercase tracking-wider block mb-1">
            Engine 2: Policy
          </span>
          <h4>Policy Precedence</h4>
          <p>Precedence ranking enforces active policies and rejects outdated terms.</p>
        </div>
        <div className="how-step-node step-python">
          <div className="how-node-circle border-teal-400 text-teal-300 shadow-[0_0_15px_rgba(20,184,166,0.5)]">
            04
          </div>
          <span className="text-[10px] font-mono font-bold text-teal-400 uppercase tracking-wider block mb-1">
            Engine 2: Python
          </span>
          <h4>Python Gate</h4>
          <p>100-rule matrix calculates mathematical parity and escalation triggers.</p>
        </div>
        <div className="how-step-node step-verified">
          <div className="how-node-circle border-emerald-400 text-emerald-300 shadow-[0_0_15px_rgba(34,197,94,0.5)]">
            05
          </div>
          <span className="text-[10px] font-mono font-bold text-emerald-400 uppercase tracking-wider block mb-1">
            Verified Resolution
          </span>
          <h4>Verified Action</h4>
          <p>Safe customer dispatch with full audit trail and SLA clock tracking.</p>
        </div>
      </div>
    </div>
  )
}

/* ==========================================================================
   14. AUTHENTICATION PAGES (LOGIN & SIGNUP DUAL-PANE)
   ========================================================================== */

export function LoginForm({ signup = false }: { signup?: boolean }) {
  const router = useRouter()
  const [email, setEmail] = useState('admin@supportnova.ai')
  const [password, setPassword] = useState('••••••••••••')

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    router.push('/dashboard')
  }

  return (
    <form className="auth-form" onSubmit={handleSubmit}>
      <div className="auth-heading">
        <span className="eyebrow">{signup ? 'Enterprise Deployment' : 'ResponseX Console'}</span>
        <h1>{signup ? 'Create Intelligence Workspace' : 'Sign in to SupportNova'}</h1>
        <p>
          {signup
            ? 'Deploy independent dual-pipeline AI governance for your customer operations.'
            : 'Access verified complaint intelligence, 100-rule matrix, and audit logs.'}
        </p>
      </div>

      {signup && (
        <input
          className="field"
          placeholder="Full name"
          defaultValue="Dr. Alex Vance"
          required
        />
      )}

      <input
        className="field"
        type="email"
        placeholder="Enterprise email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        required
      />

      <input
        className="field"
        type="password"
        placeholder="Password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        required
      />

      {signup && (
        <select className="field" defaultValue="Enterprise">
          <option value="Starter">Starter (1-10 Support Engineers)</option>
          <option value="Pro">Pro (10-50 Support Engineers)</option>
          <option value="Enterprise">Enterprise (50+ Full Governance)</option>
        </select>
      )}

      <button type="submit" className="button button-primary full">
        {signup ? 'Provision Workspace' : 'Sign In to Console'}{' '}
        <ArrowRight size={15} />
      </button>

      <div className="auth-divider">
        <span>or demo credentials</span>
      </div>

      <button
        type="button"
        onClick={() => router.push('/dashboard')}
        className="button button-secondary full text-xs"
      >
        <span>Instant Launch Demo Console (No Password)</span>
      </button>

      <p className="auth-legal">
        Protected by ResponseX Integrity Gate · AES-256 GCM Encrypted · Audit Trail Active
      </p>
    </form>
  )
}

export function AuthPage({ signup = false }: { signup?: boolean }) {
  return (
    <main className="auth-page">
      <div className="auth-visual">
        <div className="ambient-mesh">
          <div className="ambient-blob-1" />
          <div className="ambient-blob-2" />
        </div>
        <div className="auth-visual-content">
          <Logo size="large" />
          <div className="mt-8">
            <span className="eyebrow">Enterprise Resolution Intelligence</span>
            <h2>AI moves fast. Your rules keep it honest.</h2>
          </div>
          <div className="bg-white/5 border border-white/10 rounded-2xl p-6 mt-6 backdrop-blur-md">
            <div className="flex items-center gap-3 mb-4">
              <span className="pulse-node" />
              <span className="text-xs font-mono font-semibold text-emerald-400">
                INDEPENDENT GROUND-TRUTH ACTIVE
              </span>
            </div>
            <p className="text-xs text-slate-300 leading-relaxed m-0">
              SupportNova automatically compares every GenAI-generated resolution against the 100-rule
              matrix. Tickets with &lt;95% agreement are intercepted and held in the Manual Review Queue.
            </p>
          </div>
          <div className="auth-quote">
            “SupportNova gave our agents total confidence without slowing them down. Zero unauthorized
            promises have reached customers since deployment.”
            <small>— Lead CX Operations Architect, NovaTech Robotics</small>
          </div>
        </div>
      </div>

      <div className="auth-side">
        <LoginForm signup={signup} />
      </div>
    </main>
  )
}

/* ==========================================================================
   15. LUXURY ENTERPRISE FOOTER
   ========================================================================== */

export function Footer() {
  return (
    <footer className="footer">
      <div className="container footer-grid">
        <div>
          <Logo />
          <p className="footer-copy">
            ResponseX Intelligence platform providing source-grounded complaint intelligence and
            deterministic ground-truth validation for modern support operations.
          </p>
          <div className="flex items-center gap-2 mt-4 text-xs font-mono text-emerald-400">
            <span className="w-2 h-2 rounded-full bg-emerald-400 shadow-[0_0_8px_#22c55e]" />
            <span>All Systems Grounded &amp; Operational</span>
          </div>
        </div>

        <div>
          <strong>Product</strong>
          <Link href="/features">Feature Matrix</Link>
          <Link href="/how-it-works">Two-Pipeline Flow</Link>
          <Link href="/dashboard/validation">Ground-Truth Verifier</Link>
          <Link href="/dashboard/rules">100-Rule Matrix</Link>
          <Link href="/pricing">Enterprise Pricing</Link>
        </div>

        <div>
          <strong>Governance &amp; Specs</strong>
          <Link href="/about">Aptech SRS Specifications</Link>
          <Link href="/dashboard/settings">Competition Integrity (CIR)</Link>
          <Link href="/dashboard/evaluation">Hidden Evaluation Studio</Link>
          <Link href="/dashboard/reports">Audit Ledger Export</Link>
          <Link href="/login">Console Login</Link>
        </div>

        <div>
          <strong>Compliance Notes</strong>
          <p className="text-xs text-slate-400 mb-3">
            Subscribe to engineering telemetry updates and AI safety research briefs.
          </p>
          <div className="newsletter">
            <input aria-label="Work email address" placeholder="security@company.com" />
            <button aria-label="Subscribe to updates">
              <ArrowRight size={15} />
            </button>
          </div>
        </div>
      </div>

      <div className="container footer-bottom">
        <span>© 2026 SupportNova — ResponseX Intelligence. Aptech Competition Edition.</span>
        <div className="flex gap-6">
          <Link href="/about" className="hover:text-white transition-colors">
            SRS Charter
          </Link>
          <Link href="/dashboard/settings" className="hover:text-white transition-colors">
            AI_USAGE.md
          </Link>
          <Link href="/dashboard/validation" className="hover:text-white transition-colors">
            Strict Non-Delegation
          </Link>
        </div>
      </div>
    </footer>
  )
}

/* ==========================================================================
   16. DEFAULT EXPORT & EMPTY STATE HELPERS
   ========================================================================== */

export function EmptyPage({
  title,
  description,
  icon = <LayoutDashboard size={22} />,
}: {
  title: string
  description: string
  icon?: React.ReactNode
}) {
  return (
    <DashboardShell title={title}>
      <div className="page-empty">
        <div className="empty-icon">{icon}</div>
        <h2>{title}</h2>
        <p className="muted">{description}</p>
        <Link href="/dashboard" className="button button-primary">
          Return to Overview <ArrowRight size={15} />
        </Link>
      </div>
    </DashboardShell>
  )
}

export function DashboardOverview() {
  return (
    <DashboardShell title="Overview">
      <div className="dashboard-grid">
        <KpiCard
          label="Total Complaints Analyzed"
          value="4,281"
          delta="12.8%"
          icon={<Ticket size={19} />}
        />
        <KpiCard
          label="Average Analysis Time"
          value="2.42s"
          delta="88% Under 20s"
          icon={<Clock3 size={19} />}
          color="cyan"
        />
        <KpiCard
          label="Mandatory Escalation Rate"
          value="8.6%"
          delta="100% Gated"
          icon={<Zap size={19} />}
          color="amber"
        />
        <KpiCard
          label="AI / Rules Agreement Rate"
          value="96.4%"
          delta="High Parity"
          icon={<ShieldCheck size={19} />}
          color="emerald"
        />
      </div>

      <div className="dashboard-two-col">
        <div className="chart-card">
          <div className="table-toolbar">
            <div>
              <h3>Complaint Intake &amp; Resolution Trends</h3>
              <p className="muted">
                Last 30 days telemetry <span className="green-text">+12.8% throughput</span>
              </p>
            </div>
            <button className="select-button">
              Last 30 days <ChevronDown size={13} />
            </button>
          </div>
          <MiniChart />
          <div className="chart-axis">
            <span>Day 01</span>
            <span>Day 07</span>
            <span>Day 14</span>
            <span>Day 21</span>
            <span>Day 30</span>
          </div>
        </div>

        <div className="risk-card">
          <div className="table-toolbar">
            <div>
              <h3>Real-Time SLA Health Radar</h3>
              <p className="muted">P0-P3 Response Clocks</p>
            </div>
            <MoreHorizontal size={17} className="text-slate-400" />
          </div>
          <div className="risk-ring">
            <div>
              <strong>82%</strong>
              <small>On Track</small>
            </div>
          </div>
          <div className="risk-legend">
            <span>
              <i className="dot emerald-bg" /> On Track <b>3,504</b>
            </span>
            <span>
              <i className="dot amber-bg" /> Approaching Risk (&lt;4h) <b>552</b>
            </span>
            <span>
              <i className="dot rose-bg" /> Breached <b>225</b>
            </span>
          </div>
        </div>
      </div>

      <ComplaintTable />
    </DashboardShell>
  )
}

export default DashboardOverview
