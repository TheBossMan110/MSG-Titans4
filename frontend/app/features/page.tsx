'use client'
import Link from 'next/link'
import {
  Zap, Shield, CheckCircle, AlertTriangle, BarChart3, Lock,
  GitMerge, Clock, Users, Activity, Book, FlaskConical, ArrowRight,
} from 'lucide-react'
import { LandingNav, Logo } from '@/components/ui'

const features = [
  {
    group: 'Dual-Engine Pipeline',
    icon: <GitMerge size={20} />,
    color: '#6366F1',
    items: [
      { title: 'AI Reasoning Engine', body: 'GenAI classifies complaints with natural language understanding — category, urgency, department, and escalation need.' },
      { title: 'Python Deterministic Verifier', body: 'A rule-matrix cross-checks every AI output. Business policy always wins over probabilistic output.' },
      { title: 'Reconciliation Protocol', body: 'When engines agree — VERIFIED. When they disagree — MISMATCH, routed to human review. No silent failures.' },
    ],
  },
  {
    group: 'Complaint Lifecycle',
    icon: <Activity size={20} />,
    color: '#06B6D4',
    items: [
      { title: 'Real-Time Processing', body: 'Complaints are analysed within seconds of submission. Status updates are reflected immediately.' },
      { title: 'Checklist Enforcement', body: 'RULE_REQUIRED checklist steps must be confirmed before a case can be closed. Skipping is not possible.' },
      { title: 'Follow-Up Tracking', body: 'Scheduled follow-ups with due-date alerts and late-minute reporting. Every commitment is tracked.' },
    ],
  },
  {
    group: 'SLA & Escalation',
    icon: <Clock size={20} />,
    color: '#EF4444',
    items: [
      { title: 'SLA Monitoring', body: 'First-response and resolution SLAs tracked per complaint. APPROACHING and BREACHED states trigger alerts.' },
      { title: 'Automatic Escalation', body: 'Python verifier enforces escalation rules — no AI confidence score can override a business-rule escalation.' },
      { title: 'Audit-Ready Logs', body: 'Full lifecycle timeline, rule-fired records, and review history. Every action attributed to a user and timestamp.' },
    ],
  },
  {
    group: 'Role-Based Access',
    icon: <Lock size={20} />,
    color: '#F59E0B',
    items: [
      { title: '6 Role System', body: 'Customer, Agent, Reviewer, Manager, Admin, Evaluator — each with a distinct payload and capability set.' },
      { title: 'Customer View Isolation', body: 'Customers receive a different API payload — not a hidden one. Internal fields never reach the customer endpoint.' },
      { title: 'Zero Trust Frontend', body: 'SUPABASE_SERVICE_ROLE_KEY never appears in frontend code. Tokens are memory-only; httpOnly cookies for refresh.' },
    ],
  },
  {
    group: 'Analytics & Benchmark',
    icon: <BarChart3 size={20} />,
    color: '#22C55E',
    items: [
      { title: 'Live Dashboards', body: 'Volume, category distribution, pipeline agreement rates — all figures traceable to actual database records.' },
      { title: 'Trend Analysis', body: 'Period-over-period change tracking. Percentages only appear when there is a denominator to compute them.' },
      { title: 'Accuracy Benchmarking', body: 'Run labelled datasets through the live pipeline. Per-field accuracy, failure tables, guard compliance scores.' },
    ],
  },
]

export default function FeaturesPage() {
  return (
    <>
      <div className="ambient-bg" />
      <div className="grid-overlay" />
      <LandingNav />

      <div style={{ padding: '120px 60px 80px', maxWidth: 1100, margin: '0 auto' }}>
        <div style={{ textAlign: 'center', marginBottom: 64 }}>
          <div className="hero-badge" style={{ display: 'inline-flex', marginBottom: 20 }}>
            <Activity size={13} /> Full Feature Set
          </div>
          <h1 className="hero-title" style={{ marginBottom: 20 }}>
            Built for<br /><span className="text-gradient-orange">accountability</span>
          </h1>
          <p className="hero-sub" style={{ margin: '0 auto' }}>
            Every feature exists to close the gap between AI classification and business-grade reliability.
          </p>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 48 }}>
          {features.map((group) => (
            <div key={group.group}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20, paddingBottom: 14, borderBottom: '1px solid var(--border)' }}>
                <div style={{ width: 36, height: 36, borderRadius: 9, background: `${group.color}15`, border: `1px solid ${group.color}40`, display: 'flex', alignItems: 'center', justifyContent: 'center', color: group.color }}>
                  {group.icon}
                </div>
                <h2 style={{ fontSize: 18, fontWeight: 800 }}>{group.group}</h2>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 14 }}>
                {group.items.map((item) => (
                  <div key={item.title} className="card" style={{ padding: '20px', borderLeft: `2px solid ${group.color}50` }}>
                    <h3 style={{ fontSize: 14, fontWeight: 700, marginBottom: 8 }}>{item.title}</h3>
                    <p style={{ fontSize: 13.5, color: 'var(--text-3)', lineHeight: 1.65 }}>{item.body}</p>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>

        <div style={{ marginTop: 64, textAlign: 'center' }}>
          <Link href="/login" className="btn btn-orange btn-lg">
            Access the Platform <ArrowRight size={18} />
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
