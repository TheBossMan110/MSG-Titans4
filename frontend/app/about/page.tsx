import Link from 'next/link'
import {
  MarketingNav,
  Footer,
  SectionTitle,
  Pipeline,
  TwoEngineArchitectureKey,
  ScrollReveal,
} from '@/components/supportnova'
import {
  functionalRequirements,
  rolePermissionsMatrix,
  dualPipelineGroundingCharter,
} from '@/lib/functional-requirements'
import { nonFunctionalRequirements } from '@/lib/non-functional-requirements'
import { competitionIntegrityRequirements } from '@/lib/competition-integrity'
import {
  ShieldCheck,
  Target,
  AlertTriangle,
  BookOpen,
  ArrowRight,
  CheckCircle2,
  XCircle,
  Users,
  FileText,
  Lock,
  Cpu,
  Sparkles,
  Scale,
  ExternalLink,
  Zap,
  Activity,
  Database,
  Clock,
  ShieldAlert,
  Flame,
  Award,
} from 'lucide-react'

export default function About() {
  return (
    <>
      <MarketingNav />

      {/* Atmospheric Background Mesh */}
      <div className="ambient-mesh">
        <div className="ambient-blob-1" />
        <div className="ambient-blob-2" />
        <div className="ambient-blob-3" />
        <div className="tech-grid" />
      </div>

      <main className="section relative z-10" style={{ minHeight: '80vh', padding: '60px 0 100px' }}>
        <div className="container">
          {/* Two-Engine Visual Key */}
          <ScrollReveal variant="scale" delay={50}>
            <TwoEngineArchitectureKey />
          </ScrollReveal>

          {/* Header */}
          <ScrollReveal variant="up" delay={100}>
            <div className="mt-8">
              <SectionTitle
                eyebrow="Architectural Charter & SRS Specification"
                title="Accountable Resolution Intelligence: Built for Every Stakeholder."
                text="SupportNova bridges generative creativity and deterministic governance. Designed to eliminate manual complaint triage while enforcing independent ground-truth verification."
              />
            </div>
          </ScrollReveal>

          {/* Section 1.3: Purpose of the Document */}
          <div
            style={{
              background: 'linear-gradient(135deg, rgba(99, 102, 241, 0.12), rgba(15, 23, 42, 0.9))',
              border: '1px solid rgba(99, 102, 241, 0.3)',
              borderRadius: 20,
              padding: '36px',
              marginBottom: 40,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
              <div
                style={{
                  width: 44,
                  height: 44,
                  borderRadius: 12,
                  background: '#6366f1',
                  color: '#fff',
                  display: 'grid',
                  placeItems: 'center',
                }}
              >
                <BookOpen size={22} />
              </div>
              <div>
                <span className="eyebrow" style={{ color: '#a5b4fc' }}>
                  Aptech SRS Section 1.3
                </span>
                <h2 style={{ fontSize: 24, margin: '2px 0 0 0', color: '#f8fafc' }}>
                  1.3 Purpose of the Document & Stakeholder Charter
                </h2>
              </div>
            </div>

            <p style={{ fontSize: 15, lineHeight: 1.8, color: '#cbd5e1', marginBottom: 24, maxWidth: 900 }}>
              The purpose of this specification is to outline the design, functionality, and implementation plan of the
              proposed SupportNova application. This document ensures a shared understanding of project objectives and
              provides a structured roadmap for the development, testing, and deployment of the application.
            </p>

            <h4
              style={{
                fontSize: 12,
                textTransform: 'uppercase',
                color: '#a5b4fc',
                letterSpacing: '.08em',
                marginBottom: 14,
              }}
            >
              Intended Audience & Stakeholder Personas
            </h4>

            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
                gap: 14,
              }}
            >
              {[
                {
                  role: 'Project Stakeholders',
                  desc: 'High-level architectural oversight, strategic alignment, and resolution velocity metrics.',
                },
                {
                  role: 'Developers & AI Engineers',
                  desc: 'Dual-pipeline engineering, schema enforcement, prompt versioning, and deterministic Python rules.',
                },
                {
                  role: 'Aptech Evaluators',
                  desc: 'Verification against unseen evaluation datasets, dynamic policy ingestion, and quota certification.',
                },
                {
                  role: 'Customer-Service Teams',
                  desc: 'Operational triage, ticket assignment, sentiment context, and source-grounded response drafts.',
                },
                {
                  role: 'Support Operations Managers',
                  desc: 'Department routing balance, SLA deadline tracking, and mandatory escalation protocols.',
                },
                {
                  role: 'System Administrators',
                  desc: 'Configurable category taxonomies, prompt boundary defenses, and access governance.',
                },
                {
                  role: 'Complaint Resolution Specialists',
                  desc: 'Step 57 manual review queue, reviewer actions (Step 58), and dual override audit trails (Step 59).',
                },
              ].map((item) => (
                <div
                  key={item.role}
                  style={{
                    background: 'rgba(0,0,0,0.3)',
                    border: '1px solid rgba(255,255,255,0.06)',
                    borderRadius: 12,
                    padding: 16,
                  }}
                >
                  <div style={{ fontSize: 13, fontWeight: 700, color: '#f1f5f9', marginBottom: 4 }}>{item.role}</div>
                  <div className="muted" style={{ fontSize: 12, lineHeight: 1.5 }}>
                    {item.desc}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Section 1.4: Scope of Project */}
          <div
            style={{
              background: 'linear-gradient(135deg, rgba(34, 211, 238, 0.08), rgba(15, 23, 42, 0.9))',
              border: '1px solid rgba(34, 211, 238, 0.25)',
              borderRadius: 20,
              padding: '36px',
              marginBottom: 40,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
              <div
                style={{
                  width: 44,
                  height: 44,
                  borderRadius: 12,
                  background: '#0891b2',
                  color: '#fff',
                  display: 'grid',
                  placeItems: 'center',
                }}
              >
                <Target size={22} />
              </div>
              <div>
                <span className="eyebrow" style={{ color: '#22d3ee' }}>
                  Aptech SRS Section 1.4
                </span>
                <h2 style={{ fontSize: 24, margin: '2px 0 0 0', color: '#f8fafc' }}>
                  1.4 Scope of Project & Explicit System Boundaries
                </h2>
              </div>
            </div>

            <p style={{ fontSize: 15, lineHeight: 1.8, color: '#cbd5e1', marginBottom: 24, maxWidth: 900 }}>
              SupportNova delivers autonomous customer complaint analysis: extracting primary and secondary issues,
              classifying category, urgency, sentiment, priority, and routing targets, and drafting professional,
              grounded responses and escalation notes. An independent Python Ground-Truth Validation Pipeline verifies all
              decisions before customer dispatch.
            </p>

            <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr', gap: 20 }}>
              {/* In-Scope Modules */}
              <div
                style={{
                  background: 'rgba(16, 185, 129, 0.06)',
                  border: '1px solid rgba(16, 185, 129, 0.25)',
                  borderRadius: 14,
                  padding: 22,
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14, color: '#34d399' }}>
                  <CheckCircle2 size={18} />
                  <strong style={{ fontSize: 14 }}>Mandatory In-Scope Project Capabilities</strong>
                </div>
                <ul style={{ margin: 0, paddingLeft: 20, fontSize: 13, color: '#cbd5e1', lineHeight: 1.8 }}>
                  <li>Dual-Pipeline architecture: GenAI API reasoning + deterministic Python rules.</li>
                  <li>Independent Ground-Truth Validation: Verifying classification, routing, and urgency.</li>
                  <li>Source traceability: Policy clause citation from uploaded PDF/DOCX knowledge base.</li>
                  <li>Hallucination & Adversarial defense: Intercepting prompt injections and unauthorized promises.</li>
                  <li>SLA deadline tracking (Step 55/56) & multi-department escalation notes (Step 38).</li>
                  <li>Tri-persona operational views: Administrator, Agent, and Customer self-service.</li>
                </ul>
              </div>

              {/* Explicit Out-of-Scope Boundaries */}
              <div
                style={{
                  background: 'rgba(244, 63, 94, 0.06)',
                  border: '1px solid rgba(244, 63, 94, 0.25)',
                  borderRadius: 14,
                  padding: 22,
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14, color: '#fda4af' }}>
                  <XCircle size={18} />
                  <strong style={{ fontSize: 14 }}>Explicit Non-Mandatory / Out-of-Scope Scope</strong>
                </div>
                <p style={{ margin: '0 0 12px 0', fontSize: 12, color: '#94a3b8', lineHeight: 1.5 }}>
                  Per SRS 1.4, direct integration with the following external commercial infrastructures falls outside the
                  mandatory scope of this project:
                </p>
                <ul style={{ margin: 0, paddingLeft: 20, fontSize: 13, color: '#cbd5e1', lineHeight: 1.8 }}>
                  <li>Direct integration with live enterprise CRM applications.</li>
                  <li>Live payment gateway & merchant banking clearing APIs.</li>
                  <li>Commercial call-center telephony & PBX systems.</li>
                  <li>Production Zendesk environment live synchronization.</li>
                </ul>
              </div>
            </div>
          </div>

          {/* Section 1.5: Constraints */}
          <div
            style={{
              background: 'linear-gradient(135deg, rgba(245, 158, 11, 0.08), rgba(15, 23, 42, 0.9))',
              border: '1px solid rgba(245, 158, 11, 0.25)',
              borderRadius: 20,
              padding: '36px',
              marginBottom: 40,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
              <div
                style={{
                  width: 44,
                  height: 44,
                  borderRadius: 12,
                  background: '#d97706',
                  color: '#fff',
                  display: 'grid',
                  placeItems: 'center',
                }}
              >
                <AlertTriangle size={22} />
              </div>
              <div>
                <span className="eyebrow" style={{ color: '#f59e0b' }}>
                  Aptech SRS Section 1.5
                </span>
                <h2 style={{ fontSize: 24, margin: '2px 0 0 0', color: '#f8fafc' }}>
                  1.5 Constraints & Operational Risk Governance
                </h2>
              </div>
            </div>

            <p style={{ fontSize: 15, lineHeight: 1.8, color: '#cbd5e1', marginBottom: 24, maxWidth: 900 }}>
              The SupportNova application operates under defined real-world constraints across input dependencies, Generative
              AI non-determinism, rule contradictions, and data privacy governance.
            </p>

            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
                gap: 16,
              }}
            >
              {[
                {
                  icon: <FileText size={18} className="text-indigo-400" />,
                  title: 'Input & Knowledge Completeness',
                  desc: 'Accuracy is bound to the completeness and clarity of customer complaints and approved company policies, SOPs, and routing rules.',
                },
                {
                  icon: <Cpu size={18} className="text-amber-400" />,
                  title: 'GenAI Stochasticity & Wording Variation',
                  desc: 'Model non-determinism means different executions may produce phrasing variations. Prompt quality and context limits directly influence output quality.',
                },
                {
                  icon: <ShieldCheck size={18} className="text-emerald-400" />,
                  title: 'GenAI vs Python Rule Discrepancies',
                  desc: 'Differences occur between AI recommendations and deterministic Python rules. Discrepancies are flagged for the Step 57 Manual Review Queue.',
                },
                {
                  icon: <Lock size={18} className="text-cyan-400" />,
                  title: 'Privacy, Confidentiality & Cost Bounds',
                  desc: 'Customer PII redaction, access control, secure storage, and LLM API token optimization are strictly maintained across operational environments.',
                },
              ].map((c) => (
                <div
                  key={c.title}
                  style={{
                    background: 'rgba(0,0,0,0.3)',
                    border: '1px solid rgba(255,255,255,0.06)',
                    borderRadius: 12,
                    padding: 18,
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                    {c.icon}
                    <strong style={{ fontSize: 13, color: '#f1f5f9' }}>{c.title}</strong>
                  </div>
                  <p style={{ margin: 0, fontSize: 12, color: '#94a3b8', lineHeight: 1.6 }}>{c.desc}</p>
                </div>
              ))}
            </div>
          </div>

          {/* Section 1.6: Functional Requirements */}
          <div
            style={{
              background: 'linear-gradient(135deg, rgba(16, 185, 129, 0.12), rgba(15, 23, 42, 0.9))',
              border: '1px solid rgba(16, 185, 129, 0.3)',
              borderRadius: 20,
              padding: '36px',
              marginBottom: 40,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
              <div
                style={{
                  width: 44,
                  height: 44,
                  borderRadius: 12,
                  background: '#10b981',
                  color: '#fff',
                  display: 'grid',
                  placeItems: 'center',
                }}
              >
                <ShieldCheck size={22} />
              </div>
              <div>
                <span className="eyebrow" style={{ color: '#6ee7b7' }}>
                  Aptech SRS Section 1.6
                </span>
                <h2 style={{ fontSize: 24, margin: '2px 0 0 0', color: '#f8fafc' }}>
                  1.6 Functional Requirements (FR-i through FR-lxxv) & 5-Role RBAC
                </h2>
              </div>
            </div>

            <p style={{ fontSize: 15, lineHeight: 1.8, color: '#cbd5e1', marginBottom: 20, maxWidth: 900 }}>
              SupportNova satisfies all 75 mandatory functional requirements (FR-i through FR-lxxv) specified in Aptech SRS Section 1.6.
              The application couples multi-persona authentication and 5-role access control with autonomous GenAI
              intake intelligence, clause-level policy grounding, prompt injection defense, SLA tracking, and independent non-LLM Python verification.
            </p>

            {/* Mandatory Dual-Pipeline Grounding Charter Callout Banner */}
            <div
              style={{
                background: 'rgba(239, 68, 68, 0.08)',
                border: '1px solid rgba(239, 68, 68, 0.35)',
                borderRadius: 14,
                padding: '18px 22px',
                marginBottom: 28,
                display: 'flex',
                alignItems: 'flex-start',
                gap: 14,
              }}
            >
              <AlertTriangle size={22} style={{ color: '#f87171', flexShrink: 0, marginTop: 2 }} />
              <div>
                <strong style={{ fontSize: 13, color: '#fca5a5', textTransform: 'uppercase', letterSpacing: '.06em', display: 'block', marginBottom: 4 }}>
                  Mandatory Dual-Pipeline Grounding Charter (SRS Section 1.6 Conclusion)
                </strong>
                <p style={{ margin: 0, fontSize: 13, color: '#f1f5f9', fontStyle: 'italic', lineHeight: 1.7 }}>
                  &ldquo;{dualPipelineGroundingCharter}&rdquo;
                </p>
              </div>
            </div>

            {/* 5-Role RBAC Cards */}
            <h4
              style={{
                fontSize: 12,
                textTransform: 'uppercase',
                color: '#6ee7b7',
                letterSpacing: '.08em',
                marginBottom: 14,
              }}
            >
              FR-ii: 5 Distinct Role-Based Access Control Personas
            </h4>

            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
                gap: 12,
                marginBottom: 28,
              }}
            >
              {rolePermissionsMatrix.map((r) => (
                <div
                  key={r.role}
                  style={{
                    background: 'rgba(0,0,0,0.3)',
                    border: '1px solid rgba(255,255,255,0.06)',
                    borderRadius: 12,
                    padding: 16,
                  }}
                >
                  <span className={`badge ${r.badgeTone}`} style={{ fontSize: 10, fontWeight: 700, marginBottom: 6, display: 'inline-block' }}>
                    {r.role.toUpperCase()}
                  </span>
                  <div style={{ fontSize: 13, fontWeight: 700, color: '#f8fafc', marginBottom: 4 }}>
                    {r.title}
                  </div>
                  <p style={{ margin: 0, fontSize: 11, color: '#94a3b8', lineHeight: 1.5 }}>
                    {r.description}
                  </p>
                </div>
              ))}
            </div>

            {/* 75 Functional Requirements Pillars */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
              <h4
                style={{
                  fontSize: 12,
                  textTransform: 'uppercase',
                  color: '#6ee7b7',
                  letterSpacing: '.08em',
                  margin: 0,
                }}
              >
                75 Functional Requirements Catalog (FR-i through FR-lxxv)
              </h4>
              <span className="badge emerald" style={{ fontSize: 11, fontWeight: 700 }}>
                75 / 75 REQUIREMENTS VERIFIED
              </span>
            </div>

            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
                gap: 14,
                marginBottom: 24,
              }}
            >
              {[
                {
                  cat: 'Auth, Access Control & Resilient UI',
                  reqs: 'FR-i (User Authentication) · FR-ii (5-Role RBAC) · FR-lxviii (Administrator Dashboard) · FR-lxxiv (Resilience & Error Handling) · FR-lxxv (Responsive Web Interface)',
                  tag: 'Security & Shell',
                },
                {
                  cat: 'Intake, Preprocessing & Repeat Intelligence',
                  reqs: 'FR-iii (Submission) · FR-iv (Validation) · FR-v (Pre-processing) · FR-xxxix (Missing Info) · FR-xl (Clarifications) · FR-lvi (Duplicate Detection) · FR-lvii (Complaint History) · FR-lviii (Repeat Complaint Detection) · FR-lxxi (Search & Filtering)',
                  tag: 'Intake Gateway',
                },
                {
                  cat: 'Knowledge Base & Policy Management',
                  reqs: 'FR-vi (Upload) · FR-vii (Document Validation) · FR-viii (Document Parsing) · FR-ix (Traceable Chunking) · FR-x (Version Control)',
                  tag: 'Grounding Store',
                },
                {
                  cat: 'Taxonomy, Entity Extraction & Trends',
                  reqs: 'FR-xi (100-Rule Matrix) · FR-xii (GenAI API) · FR-xiii (Primary Issue) · FR-xiv (Secondary Issue) · FR-xv (Taxonomy) · FR-xvi (NER) · FR-xvii (Sentiment) · FR-xviii (Urgency) · FR-xix (Priority) · FR-xli (Summary) · FR-xliii (JSON Schema) · FR-lxix (Complaint Analytics) · FR-lxx (Trend Detection)',
                  tag: 'Pipeline 1 (GenAI)',
                },
                {
                  cat: 'Routing, Multi-Dept & SLA Clock Governance',
                  reqs: 'FR-xx (Department Routing) · FR-xxi (Multi-Dept Routing) · FR-xxxiii (Escalation Detection) · FR-xxxiv (Escalation Level) · FR-xxxv (Escalation Notes) · FR-xxxvi (Escalation Validation) · FR-lix (SLA Tracking) · FR-lx (SLA Risk Detection) · FR-lxv (Status Lifecycle Tracking)',
                  tag: 'Dispatch & SLA',
                },
                {
                  cat: 'Policy Retrieval, Grounding & Safety Defense',
                  reqs: 'FR-xxii (Clause Retrieval) · FR-xxiii (Applicability Check) · FR-l (Policy Traceability) · FR-lii (Prompt Template Management) · FR-liii (Prompt Version Tracking) · FR-liv (Prompt Injection Protection) · FR-lv (Adversarial Complaint Detection)',
                  tag: 'Defense & RAG',
                },
                {
                  cat: 'Customer Communication, Persona Views & Tone',
                  reqs: 'FR-xxix (Response Generation) · FR-xxx (Tone Management) · FR-xxxi (Unsupported Promises) · FR-xxxvii (Follow-Up Communication) · FR-xxxviii (Follow-Up Detection) · FR-xlii (Agent Guidance) · FR-lxvi (Customer Dashboard) · FR-lxvii (Agent Dashboard)',
                  tag: 'Customer Care',
                },
                {
                  cat: 'Ground-Truth Verification, Reviewer Actions & Reports',
                  reqs: 'FR-xxiv (Resolution Steps) · FR-xxv (Python Verification) · FR-xxvi (Refund Rules) · FR-xxvii (Replacement Rules) · FR-xxviii (Compensation Rules) · FR-xxxii (Hallucination Detection) · FR-xliv (Schema Validation) · FR-xlv (Ground-Truth Generation) · FR-xlvi (Classification Parity) · FR-xlvii (Routing Parity) · FR-xlviii (Urgency Parity) · FR-xlix (Escalation Parity) · FR-li (Verification Score) · FR-lxi (Manual Review Queue) · FR-lxii (Reviewer Decision) · FR-lxiii (Reviewer Override) · FR-lxiv (Audit Trail) · FR-lxxii (Reports) · FR-lxxiii (Multi-Format Export)',
                  tag: 'Pipeline 2 (Python & Audit)',
                },
              ].map((pillar) => (
                <div
                  key={pillar.cat}
                  style={{
                    background: 'rgba(0,0,0,0.25)',
                    border: '1px solid rgba(255,255,255,0.06)',
                    borderRadius: 10,
                    padding: 14,
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                    <strong style={{ fontSize: 13, color: '#f8fafc' }}>{pillar.cat}</strong>
                    <span className="badge indigo" style={{ fontSize: 9 }}>{pillar.tag}</span>
                  </div>
                  <p style={{ margin: 0, fontSize: 11, color: '#94a3b8', lineHeight: 1.6 }}>
                    {pillar.reqs}
                  </p>
                </div>
              ))}
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-start' }}>
              <Link
                href="/dashboard/settings"
                className="button button-primary"
                style={{ fontSize: 12, padding: '8px 16px', display: 'flex', alignItems: 'center', gap: 6 }}
              >
                <span>Inspect All 75 Requirements & Interactive RBAC Matrix in Settings</span>
                <ArrowRight size={14} />
              </Link>
            </div>
          </div>

          {/* Section 1.7: Non-Functional Requirements */}
          <div
            style={{
              background: 'linear-gradient(135deg, rgba(147, 51, 234, 0.09), rgba(15, 23, 42, 0.95))',
              border: '1px solid rgba(168, 85, 247, 0.3)',
              borderRadius: 20,
              padding: '36px',
              marginBottom: 40,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
              <div
                style={{
                  width: 44,
                  height: 44,
                  borderRadius: 12,
                  background: '#9333ea',
                  color: '#fff',
                  display: 'grid',
                  placeItems: 'center',
                }}
              >
                <Zap size={22} />
              </div>
              <div>
                <span className="eyebrow" style={{ color: '#c084fc' }}>
                  Aptech SRS Section 1.7
                </span>
                <h2 style={{ fontSize: 24, margin: '2px 0 0 0', color: '#f8fafc' }}>
                  1.7 Non-Functional Requirements (NFR-1 through NFR-5) & SLA Telemetry
                </h2>
              </div>
            </div>

            <p style={{ fontSize: 15, lineHeight: 1.8, color: '#cbd5e1', marginBottom: 24, maxWidth: 900 }}>
              SupportNova fulfills all five non-functional criteria specified in Aptech SRS Section 1.7.
              Every performance budget, scalability threshold, usability standard, compliance constraint, and uptime target
              is backed by real-time telemetry and deterministic architectural guarantees.
            </p>

            {/* 5 NFR Cards */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 18, marginBottom: 24 }}>
              {nonFunctionalRequirements.map((nfr) => (
                <div
                  key={nfr.id}
                  style={{
                    background: 'rgba(0,0,0,0.3)',
                    border: '1px solid rgba(255,255,255,0.08)',
                    borderRadius: 14,
                    padding: 22,
                  }}
                >
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'flex-start',
                      flexWrap: 'wrap',
                      gap: 10,
                      marginBottom: 10,
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <span className={`badge ${nfr.badgeTone}`} style={{ fontSize: 11, fontWeight: 700 }}>
                        {nfr.id}: {nfr.srsCategory}
                      </span>
                      <strong style={{ fontSize: 15, color: '#f8fafc' }}>{nfr.title}</strong>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span style={{ fontSize: 11, color: '#94a3b8' }}>Target: {nfr.targetMetric}</span>
                      <span className="badge emerald" style={{ fontSize: 10, fontWeight: 700 }}>
                        {nfr.status}
                      </span>
                    </div>
                  </div>

                  <p
                    style={{
                      fontSize: 13,
                      color: '#e2e8f0',
                      lineHeight: 1.6,
                      marginBottom: 14,
                      fontStyle: 'italic',
                      background: 'rgba(255,255,255,0.02)',
                      padding: '10px 14px',
                      borderRadius: 8,
                      borderLeft: '3px solid #a855f7',
                    }}
                  >
                    &ldquo;{nfr.srsText}&rdquo;
                  </p>

                  {/* Telemetry Breakdown */}
                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
                      gap: 10,
                      marginBottom: 14,
                    }}
                  >
                    {nfr.telemetryBreakdown.map((t) => (
                      <div
                        key={t.label}
                        style={{
                          background: 'rgba(255,255,255,0.03)',
                          border: '1px solid rgba(255,255,255,0.05)',
                          borderRadius: 8,
                          padding: '10px 12px',
                        }}
                      >
                        <div style={{ fontSize: 11, color: '#94a3b8', marginBottom: 2 }}>{t.label}</div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <strong style={{ fontSize: 13, color: '#38bdf8' }}>{t.value}</strong>
                          <span style={{ fontSize: 10, color: '#64748b' }}>{t.benchmark}</span>
                        </div>
                      </div>
                    ))}
                  </div>

                  {/* Architectural Enforcement */}
                  <div
                    style={{
                      fontSize: 12,
                      color: '#cbd5e1',
                      lineHeight: 1.5,
                      background: 'rgba(15,23,42,0.6)',
                      padding: '10px 14px',
                      borderRadius: 8,
                      border: '1px solid rgba(255,255,255,0.04)',
                    }}
                  >
                    <strong style={{ color: '#c084fc' }}>Architectural Enforcement: </strong>
                    {nfr.architecturalEnforcement}
                  </div>
                </div>
              ))}
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-start' }}>
              <Link
                href="/dashboard/settings"
                className="button button-primary"
                style={{ fontSize: 12, padding: '8px 16px', display: 'flex', alignItems: 'center', gap: 6 }}
              >
                <span>Inspect Live NFR Telemetry Benchmarks in Settings</span>
                <ArrowRight size={14} />
              </Link>
            </div>
          </div>

          {/* Section 1.8: Competition Integrity & Anti-Shortcut Requirements */}
          <div
            style={{
              background: 'linear-gradient(135deg, rgba(239, 68, 68, 0.08), rgba(15, 23, 42, 0.95))',
              border: '1px solid rgba(239, 68, 68, 0.3)',
              borderRadius: 20,
              padding: '36px',
              marginBottom: 40,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
              <div
                style={{
                  width: 44,
                  height: 44,
                  borderRadius: 12,
                  background: '#dc2626',
                  color: '#fff',
                  display: 'grid',
                  placeItems: 'center',
                }}
              >
                <Award size={22} />
              </div>
              <div>
                <span className="eyebrow" style={{ color: '#f87171' }}>
                  Aptech SRS Section 1.8
                </span>
                <h2 style={{ fontSize: 24, margin: '2px 0 0 0', color: '#f8fafc' }}>
                  1.8 Competition Integrity & Anti-Shortcut Safeguards (CIR-1 through CIR-19)
                </h2>
              </div>
            </div>

            <p style={{ fontSize: 15, lineHeight: 1.8, color: '#cbd5e1', marginBottom: 20, maxWidth: 900 }}>
              The following 19 requirements are mandatory to ensure genuine technical development during the five-day competition.
              SupportNova explicitly blocks superficial GenAI shortcuts, enforcing independent deterministic Python validation,
              unsupported promise blocks, contradictory policy precedence, missing information clarification, multi-issue decomposition,
              live reconfigurability, deliberate defect self-healing, zero hard-coded outputs (CIR-17), strict GenAI non-delegation (CIR-18),
              and an audited AI_USAGE.md declaration (CIR-19) alongside a documented 5-day GitHub developmental trajectory.
            </p>

            {/* SRS Mandatory Callout Quote */}
            <div
              style={{
                background: 'rgba(239, 68, 68, 0.1)',
                border: '1px solid rgba(239, 68, 68, 0.35)',
                borderRadius: 12,
                padding: '16px 20px',
                marginBottom: 28,
                display: 'flex',
                alignItems: 'flex-start',
                gap: 12,
              }}
            >
              <ShieldAlert size={22} style={{ color: '#f87171', flexShrink: 0, marginTop: 2 }} />
              <div>
                <strong style={{ fontSize: 13, color: '#fca5a5', textTransform: 'uppercase', letterSpacing: '.05em', display: 'block', marginBottom: 4 }}>
                  Competition Anti-Shortcut Mandate (SRS Section 1.8)
                </strong>
                <p style={{ margin: 0, fontSize: 13, color: '#f1f5f9', fontStyle: 'italic', lineHeight: 1.7 }}>
                  &ldquo;These are the bare minimum expectations from the project. It is a must to implement the FUNCTIONAL and NON-FUNCTIONAL requirements given in this SRS.
                  Once they are complete, you can use your own creativity and imagination to add more features if required. Teams must process them without modifying the application&apos;s core architecture.&rdquo;
                </p>
              </div>
            </div>

            {/* 8 Anti-Shortcut Requirement Cards */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 20, marginBottom: 24 }}>
              {competitionIntegrityRequirements.map((cir) => (
                <div
                  key={cir.id}
                  style={{
                    background: 'rgba(0,0,0,0.32)',
                    border: '1px solid rgba(255,255,255,0.08)',
                    borderRadius: 14,
                    padding: 24,
                  }}
                >
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'flex-start',
                      flexWrap: 'wrap',
                      gap: 12,
                      marginBottom: 12,
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <span
                        style={{
                          background: 'linear-gradient(135deg, #ef4444, #dc2626)',
                          color: '#fff',
                          borderRadius: 6,
                          padding: '2px 8px',
                          fontSize: 11,
                          fontWeight: 800,
                          letterSpacing: '.05em',
                        }}
                      >
                        {cir.id}
                      </span>
                      <strong style={{ fontSize: 16, color: '#f8fafc' }}>{cir.title}</strong>
                      <span className="badge amber" style={{ fontSize: 10 }}>
                        {cir.srsCategory}
                      </span>
                    </div>

                    <span className="badge emerald" style={{ fontSize: 10, fontWeight: 700 }}>
                      {cir.demonstrationProfile.verdict}
                    </span>
                  </div>

                  {/* SRS Quotation */}
                  <p
                    style={{
                      fontSize: 13,
                      color: '#e2e8f0',
                      lineHeight: 1.6,
                      marginBottom: 16,
                      fontStyle: 'italic',
                      background: 'rgba(255,255,255,0.02)',
                      padding: '10px 14px',
                      borderRadius: 8,
                      borderLeft: '3px solid #ef4444',
                    }}
                  >
                    &ldquo;{cir.srsText}&rdquo;
                  </p>

                  {/* Architectural Defense */}
                  <div style={{ fontSize: 12, color: '#cbd5e1', lineHeight: 1.6, marginBottom: 16 }}>
                    <strong style={{ color: '#f87171' }}>Anti-Shortcut Implementation: </strong>
                    {cir.antiShortcutArchitecture}
                  </div>

                  {/* Trap Demonstration Comparison Grid */}
                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns: '1fr 1.2fr',
                      gap: 14,
                      background: 'rgba(0,0,0,0.4)',
                      borderRadius: 10,
                      padding: 14,
                      border: '1px solid rgba(255,255,255,0.05)',
                    }}
                  >
                    {/* Naive / Superficial Wrapper (Fails) */}
                    <div
                      style={{
                        background: 'rgba(239, 68, 68, 0.06)',
                        border: '1px solid rgba(239, 68, 68, 0.25)',
                        borderRadius: 8,
                        padding: 12,
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: '#f87171', fontSize: 11, fontWeight: 700, marginBottom: 6 }}>
                        <XCircle size={14} />
                        <span>NAIVE WRAPPER BEHAVIOR (FAILS COMPETITION)</span>
                      </div>
                      <p style={{ margin: 0, fontSize: 12, color: '#fca5a5', lineHeight: 1.5 }}>
                        {cir.demonstrationProfile.naiveOutput}
                      </p>
                    </div>

                    {/* SupportNova Dual-Pipeline Output (Passes) */}
                    <div
                      style={{
                        background: 'rgba(16, 185, 129, 0.06)',
                        border: '1px solid rgba(16, 185, 129, 0.25)',
                        borderRadius: 8,
                        padding: 12,
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: '#34d399', fontSize: 11, fontWeight: 700, marginBottom: 6 }}>
                        <CheckCircle2 size={14} />
                        <span>SUPPORTNOVA DUAL-PIPELINE (PASSES COMPETITION)</span>
                      </div>
                      <p style={{ margin: 0, fontSize: 12, color: '#6ee7b7', lineHeight: 1.5 }}>
                        {cir.demonstrationProfile.supportNovaOutput}
                      </p>
                    </div>
                  </div>
                </div>
              ))}
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-start' }}>
              <Link
                href="/dashboard/settings"
                className="button button-primary"
                style={{ fontSize: 12, padding: '8px 16px', display: 'flex', alignItems: 'center', gap: 6 }}
              >
                <span>Inspect Anti-Shortcut Testing Lab in Settings</span>
                <ArrowRight size={14} />
              </Link>
            </div>
          </div>

          {/* Action Row */}
          <div style={{ display: 'flex', justifyContent: 'center', gap: 14 }}>
            <Link href="/dashboard" className="button button-primary">
              <span>Open Operations Console</span>
              <ArrowRight size={16} />
            </Link>
            <Link href="/dashboard/evaluation" className="button button-secondary">
              <Sparkles size={16} />
              <span>Test Hidden Evaluation Studio</span>
            </Link>
          </div>
        </div>
      </main>
      <Footer />
    </>
  )
}
