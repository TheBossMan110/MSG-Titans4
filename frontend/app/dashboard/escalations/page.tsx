'use client'

import { useState } from 'react'
import Link from 'next/link'
import { DashboardShell, StatusBadge } from '@/components/supportnova'
import { mockComplaints, fictionalOrganization } from '@/lib/mock-data'
import { EscalationLevel } from '@/lib/types'
import {
  Zap,
  ShieldAlert,
  Search,
  ArrowRight,
  Filter,
  CheckCircle2,
  AlertTriangle,
  UserCheck,
  Building2,
  FileText,
  Clock,
  Send,
} from 'lucide-react'

export default function EscalationsPage() {
  const escalatedComplaints = mockComplaints.filter((c) => c.intelligence.escalationRequirement)
  const [levelFilter, setLevelFilter] = useState<string>('All')
  const [selectedId, setSelectedId] = useState<string>(escalatedComplaints[0]?.input.id || '')
  const [searchQuery, setSearchQuery] = useState('')
  const [pagedStatus, setPagedStatus] = useState<Record<string, boolean>>({})

  const filtered = escalatedComplaints.filter((item) => {
    const matchesLevel =
      levelFilter === 'All' ||
      item.intelligence.escalationLevel === levelFilter
    const matchesSearch =
      item.input.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      item.input.id.toLowerCase().includes(searchQuery.toLowerCase()) ||
      item.intelligence.category.toLowerCase().includes(searchQuery.toLowerCase())
    return matchesLevel && matchesSearch
  })

  const selectedItem =
    escalatedComplaints.find((c) => c.input.id === selectedId) || escalatedComplaints[0]

  const handlePageLead = (id: string) => {
    setPagedStatus({ ...pagedStatus, [id]: true })
  }

  const getLevelTone = (level?: EscalationLevel) => {
    switch (level) {
      case 'Critical Management Escalation':
        return 'rose'
      case 'Compliance Review':
        return 'rose'
      case 'Specialist Team':
        return 'amber'
      case 'Department Manager':
        return 'indigo'
      case 'Supervisor Review':
        return 'cyan'
      default:
        return 'slate'
    }
  }

  return (
    <DashboardShell title="Escalation Management Console">
      {/* Banner */}
      <div
        style={{
          background: 'linear-gradient(135deg, rgba(239, 68, 68, 0.12), rgba(245, 158, 11, 0.06))',
          border: '1px solid rgba(239, 68, 68, 0.3)',
          borderRadius: 12,
          padding: '16px 20px',
          marginBottom: 24,
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: 16,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div
            style={{
              width: 40,
              height: 40,
              borderRadius: 8,
              background: '#ef4444',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#fff',
            }}
          >
            <Zap size={22} />
          </div>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span className="eyebrow" style={{ color: '#fca5a5', fontWeight: 600 }}>
                STEPS 36, 37, 38 & 39: ESCALATION MATRIX & PYTHON SAFETY CATCH
              </span>
              <span className="badge rose">High SLA Queue</span>
            </div>
            <h3 style={{ fontSize: 17, fontWeight: 700, margin: '2px 0 2px 0', color: '#f8fafc' }}>
              Management & Specialist Escalation Matrix
            </h3>
            <p className="muted" style={{ fontSize: 12, margin: 0 }}>
              Triggered automatically by safety hazards, security/privacy incidents, legal threats, or SLA breach thresholds.
            </p>
          </div>
        </div>

        <div style={{ display: 'flex', gap: 12 }}>
          <div
            style={{
              background: 'rgba(15, 23, 42, 0.7)',
              padding: '6px 12px',
              borderRadius: 6,
              border: '1px solid rgba(255, 255, 255, 0.08)',
              fontSize: 12,
            }}
          >
            <span className="muted">ESCALATED TICKETS:</span>{' '}
            <strong style={{ color: '#ef4444' }}>{escalatedComplaints.length} Critical</strong>
          </div>
        </div>
      </div>

      {/* 2-Column: Left = Escalations List, Right = Structured Notes Deep Dive */}
      <div style={{ display: 'grid', gridTemplateColumns: '1.1fr 1.3fr', gap: 24, alignItems: 'start' }}>
        {/* Left Column: Filterable Escalations List */}
        <div className="table-card" style={{ padding: 20 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <h3 style={{ margin: 0, fontSize: 15 }}>Escalated Queue ({filtered.length})</h3>
            <span className="muted" style={{ fontSize: 12 }}>
              Priority Triage
            </span>
          </div>

          {/* Search & Level Filter */}
          <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr', gap: 8, marginBottom: 12 }}>
            <div className="search">
              <Search size={14} />
              <input
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search escalations..."
                style={{ fontSize: 12 }}
              />
            </div>
            <select
              value={levelFilter}
              onChange={(e) => setLevelFilter(e.target.value)}
              className="select-button"
              style={{ padding: '6px 8px', fontSize: 11 }}
            >
              <option value="All">All Escalation Levels</option>
              <option value="Supervisor Review">Supervisor Review</option>
              <option value="Department Manager">Department Manager</option>
              <option value="Specialist Team">Specialist Team</option>
              <option value="Compliance Review">Compliance Review</option>
              <option value="Critical Management Escalation">Critical Management Escalation</option>
            </select>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {filtered.map(({ input, intelligence, validation }) => {
              const isSelected = input.id === selectedItem?.input.id
              return (
                <div
                  key={input.id}
                  onClick={() => setSelectedId(input.id)}
                  style={{
                    padding: '12px 14px',
                    borderRadius: 8,
                    cursor: 'pointer',
                    background: isSelected ? 'rgba(239, 68, 68, 0.12)' : 'rgba(255, 255, 255, 0.02)',
                    border: `1px solid ${isSelected ? '#ef4444' : 'rgba(255, 255, 255, 0.06)'}`,
                    transition: 'all 0.15s ease',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                    <span style={{ fontWeight: 700, fontSize: 12, color: isSelected ? '#fca5a5' : '#f8fafc' }}>
                      {input.id} · {input.customerType}
                    </span>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      {intelligence.escalationOverrideNote && (
                        <span className="badge rose" style={{ fontSize: 9 }}>
                          Step 39 Override
                        </span>
                      )}
                      <StatusBadge tone={getLevelTone(intelligence.escalationLevel)}>
                        {intelligence.escalationLevel || 'Specialist Team'}
                      </StatusBadge>
                    </div>
                  </div>

                  <div style={{ fontSize: 13, fontWeight: 600, color: '#e2e8f0', marginBottom: 4 }}>
                    {input.title}
                  </div>

                  <div style={{ fontSize: 11, color: '#fde68a', marginBottom: 4 }}>
                    <strong>Trigger:</strong> {intelligence.escalationReason}
                  </div>

                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: '#94a3b8' }}>
                    <span>Route: {intelligence.requiredDepartment}</span>
                    <span style={{ color: '#34d399' }}>{validation.agreementScore}% Agreement</span>
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        {/* Right Column: Step 38 Structured Internal Escalation Notes */}
        <div className="table-card" style={{ padding: 22 }}>
          {selectedItem ? (
            <div>
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'flex-start',
                  borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
                  paddingBottom: 14,
                  marginBottom: 16,
                }}
              >
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                    <span className="eyebrow">{selectedItem.input.id}</span>
                    <StatusBadge tone={getLevelTone(selectedItem.intelligence.escalationLevel)}>
                      {selectedItem.intelligence.escalationLevel || 'Specialist Team'} (Step 37)
                    </StatusBadge>
                    {selectedItem.intelligence.escalationOverrideNote && (
                      <span className="badge rose">Step 39 Python Override</span>
                    )}
                  </div>
                  <h3 style={{ fontSize: 17, fontWeight: 700, margin: '2px 0 2px 0', color: '#f8fafc' }}>
                    {selectedItem.input.title}
                  </h3>
                  <p className="muted" style={{ fontSize: 12, margin: 0 }}>
                    Customer: {selectedItem.input.customerType} · Order: {selectedItem.input.orderOrTransactionRef}
                  </p>
                </div>

                <Link
                  href={`/dashboard/complaints/${selectedItem.input.id}`}
                  className="button button-secondary small"
                  style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11 }}
                >
                  Open Command Center <ArrowRight size={12} />
                </Link>
              </div>

              {/* Step 39 Python Override Alert Box */}
              {selectedItem.intelligence.escalationOverrideNote && (
                <div
                  style={{
                    background: 'rgba(239, 68, 68, 0.12)',
                    border: '1px solid #ef4444',
                    borderRadius: 8,
                    padding: '12px 14px',
                    marginBottom: 16,
                    fontSize: 12,
                    color: '#fca5a5',
                    lineHeight: 1.5,
                  }}
                >
                  <strong style={{ color: '#fff' }}>🛡️ Step 39 Python Ground-Truth Override Active:</strong>
                  <div style={{ marginTop: 4 }}>{selectedItem.intelligence.escalationOverrideNote}</div>
                </div>
              )}

              {/* Step 38 Structured Notes */}
              <div style={{ marginBottom: 18 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 12 }}>
                  <FileText size={16} className="text-amber-400" />
                  <strong style={{ fontSize: 13, color: '#f8fafc' }}>
                    Internal Escalation Briefing (Step 38 Schema)
                  </strong>
                </div>

                <div
                  style={{
                    background: 'rgba(15, 23, 42, 0.7)',
                    border: '1px solid rgba(255, 255, 255, 0.06)',
                    borderRadius: 8,
                    padding: 14,
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 12,
                    fontSize: 12,
                  }}
                >
                  <div>
                    <span className="muted" style={{ display: 'block', fontSize: 10, marginBottom: 2 }}>
                      1. COMPLAINT SUMMARY
                    </span>
                    <div style={{ color: '#f1f5f9' }}>
                      {selectedItem.intelligence.structuredEscalationNotes?.complaintSummary ||
                        selectedItem.intelligence.mainIssue}
                    </div>
                  </div>

                  <div>
                    <span className="muted" style={{ display: 'block', fontSize: 10, marginBottom: 2 }}>
                      2. REASON FOR ESCALATION (STEP 36 TRIGGER)
                    </span>
                    <div style={{ color: '#fde68a', fontWeight: 600 }}>
                      {selectedItem.intelligence.structuredEscalationNotes?.reasonForEscalation ||
                        selectedItem.intelligence.escalationReason}
                    </div>
                  </div>

                  <div>
                    <span className="muted" style={{ display: 'block', fontSize: 10, marginBottom: 2 }}>
                      3. KEY FACTS
                    </span>
                    <ul style={{ margin: '2px 0 0 16px', padding: 0, color: '#cbd5e1', lineHeight: 1.6 }}>
                      {selectedItem.intelligence.structuredEscalationNotes?.keyFacts ? (
                        selectedItem.intelligence.structuredEscalationNotes.keyFacts.map((fact, idx) => (
                          <li key={idx}>{fact}</li>
                        ))
                      ) : (
                        <li>Verified against customer records and intake metadata</li>
                      )}
                    </ul>
                  </div>

                  <div>
                    <span className="muted" style={{ display: 'block', fontSize: 10, marginBottom: 2 }}>
                      4. ACTIONS ALREADY TAKEN
                    </span>
                    <div style={{ color: '#a5b4fc' }}>
                      {selectedItem.intelligence.structuredEscalationNotes?.actionsAlreadyTaken.join(' · ') ||
                        'Initial intake completed and logged.'}
                    </div>
                  </div>

                  <div>
                    <span className="muted" style={{ display: 'block', fontSize: 10, marginBottom: 2 }}>
                      5. RELEVANT GROUND-TRUTH POLICY
                    </span>
                    <code style={{ background: 'rgba(0,0,0,0.3)', padding: '2px 6px', borderRadius: 4, color: '#38bdf8' }}>
                      {selectedItem.intelligence.structuredEscalationNotes?.relevantPolicy ||
                        selectedItem.intelligence.supportingPolicyReferences[0]?.documentId ||
                        'DOC-POL-001'}
                    </code>
                  </div>

                  <div>
                    <span className="muted" style={{ display: 'block', fontSize: 10, marginBottom: 2 }}>
                      6. REQUIRED NEXT ACTION
                    </span>
                    <div style={{ color: '#34d399', fontWeight: 600 }}>
                      {selectedItem.intelligence.structuredEscalationNotes?.requiredNextAction ||
                        'Assign lead and initiate direct communication.'}
                    </div>
                  </div>
                </div>
              </div>

              {/* Action Toolbar */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span className="muted" style={{ fontSize: 11 }}>
                  Ground-Truth Verified Escalation Level
                </span>

                <button
                  onClick={() => handlePageLead(selectedItem.input.id)}
                  className="button button-primary small"
                  style={{ display: 'flex', alignItems: 'center', gap: 6 }}
                >
                  <Send size={13} />
                  {pagedStatus[selectedItem.input.id]
                    ? 'Specialist Lead Paged (Confirmed)'
                    : 'Page Specialist Lead via PagerDuty'}
                </button>
              </div>
            </div>
          ) : (
            <div style={{ textAlign: 'center', padding: 40, color: '#64748b' }}>Select an escalation ticket</div>
          )}
        </div>
      </div>
    </DashboardShell>
  )
}
