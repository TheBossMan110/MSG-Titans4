'use client'
import Link from 'next/link'
import { ArrowRight, Zap, Shield, CheckCircle, AlertTriangle, Users, Activity } from 'lucide-react'
import { LandingNav, Logo } from '@/components/ui'

const steps = [
  {
    n: '01',
    title: 'Customer Submits',
    color: 'var(--orange)',
    icon: <Activity size={20} />,
    body: 'A complaint arrives via the portal or API. Title, description, order reference, and amount are captured. The submission is validated and a public reference issued within milliseconds.',
  },
  {
    n: '02',
    title: 'AI Engine Analyses',
    color: 'var(--ai)',
    icon: <Zap size={20} />,
    body: 'Engine 1 (GenAI) processes the text — classifying category, subcategory, urgency, department, and sentiment. It also determines if escalation is warranted and extracts entities. Confidence score is recorded.',
  },
  {
    n: '03',
    title: 'Python Verifier Cross-Checks',
    color: 'var(--py)',
    icon: <Shield size={20} />,
    body: 'Engine 2 runs the same complaint through a deterministic rule matrix. Business policy, SLA configuration, escalation decision trees — all applied independently. The Python output is the ground truth.',
  },
  {
    n: '04',
    title: 'Reconciliation',
    color: 'var(--verified)',
    icon: <CheckCircle size={20} />,
    body: 'The two outputs are compared field by field. Where they agree: VERIFIED, Python result applied. Where they disagree: MISMATCH recorded, all disagreeing fields surfaced, complaint enters the review queue.',
  },
  {
    n: '05',
    title: 'Human Review (Mismatches Only)',
    color: 'var(--mismatch)',
    icon: <AlertTriangle size={20} />,
    body: 'A reviewer claims the complaint, sees both engine outputs side-by-side, and either approves (AI wins), dismisses (Python wins), or overrides with custom values. All actions are audited.',
  },
  {
    n: '06',
    title: 'Agent Resolution',
    color: 'var(--orange)',
    icon: <Users size={20} />,
    body: 'The assigned agent confirms checklist steps (RULE_REQUIRED steps cannot be skipped), completes follow-ups, and progresses the complaint to RESOLVED or CLOSED. SLA timers run throughout.',
  },
]

export default function HowItWorksPage() {
  return (
    <>
      <div className="ambient-bg" />
      <div className="grid-overlay" />
      <LandingNav />

      <div style={{ padding: '120px 60px 80px', maxWidth: 900, margin: '0 auto' }}>
        <div style={{ textAlign: 'center', marginBottom: 64 }}>
          <div className="hero-badge" style={{ display: 'inline-flex', marginBottom: 20 }}>
            <Zap size={13} /> The Pipeline
          </div>
          <h1 className="hero-title" style={{ marginBottom: 20 }}>
            How the<br /><span className="text-gradient-orange">Dual Engine</span> works
          </h1>
          <p className="hero-sub" style={{ margin: '0 auto' }}>
            From submission to resolution — every step is deterministic, traceable, and role-appropriate.
          </p>
        </div>

        <div style={{ position: 'relative' }}>
          {/* Vertical line */}
          <div style={{
            position: 'absolute', left: 28, top: 40, bottom: 40,
            width: 2, background: 'linear-gradient(to bottom, var(--orange), var(--ai), var(--py), var(--verified), var(--mismatch), var(--orange))',
            opacity: 0.3,
          }} />

          <div style={{ display: 'flex', flexDirection: 'column', gap: 40 }}>
            {steps.map((step, i) => (
              <div key={step.n} style={{ display: 'flex', gap: 24, alignItems: 'flex-start' }}>
                {/* Number orb */}
                <div style={{
                  width: 56, height: 56, borderRadius: '50%', flexShrink: 0,
                  background: `${step.color}15`, border: `2px solid ${step.color}40`,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  position: 'relative', zIndex: 1,
                }}>
                  <span style={{ color: step.color, fontFamily: 'DM Mono, monospace', fontWeight: 800, fontSize: 14 }}>
                    {step.n}
                  </span>
                </div>

                {/* Content */}
                <div className="card" style={{ flex: 1, padding: '20px 22px', borderLeft: `2px solid ${step.color}40` }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
                    <span style={{ color: step.color }}>{step.icon}</span>
                    <h2 style={{ fontSize: 17, fontWeight: 800 }}>{step.title}</h2>
                  </div>
                  <p style={{ fontSize: 14, color: 'var(--text-2)', lineHeight: 1.72 }}>{step.body}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div style={{ marginTop: 64, textAlign: 'center', padding: '40px 32px', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--r-xl)' }}>
          <h2 style={{ fontSize: 22, fontWeight: 800, marginBottom: 12 }}>Key Guarantees</h2>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 14, marginBottom: 28 }}>
            {[
              'Python rules always override AI on escalation',
              'Mismatches are surfaced, never silently resolved',
              'Confidence null = "Not measured", not 0%',
              'Customer payload is distinct, not filtered',
              'SUPABASE_SERVICE_ROLE_KEY never in frontend',
              'Every citation is a traceable source link',
            ].map((g) => (
              <div key={g} style={{ display: 'flex', gap: 8, fontSize: 13, color: 'var(--text-2)', textAlign: 'left', alignItems: 'flex-start' }}>
                <CheckCircle size={14} color="var(--verified)" style={{ flexShrink: 0, marginTop: 2 }} />
                {g}
              </div>
            ))}
          </div>
          <Link href="/login" className="btn btn-orange">
            Get Started <ArrowRight size={16} />
          </Link>
        </div>
      </div>

      <footer style={{ borderTop: '1px solid var(--border)', padding: '28px 60px', display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 16, color: 'var(--text-4)', fontSize: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <Logo size={20} /><span>SupportNova — ResponseX Intelligence</span>
        </div>
        <Link href="/" style={{ color: 'inherit' }}>← Home</Link>
      </footer>
    </>
  )
}
