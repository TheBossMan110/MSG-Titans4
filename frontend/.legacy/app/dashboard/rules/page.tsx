'use client'

import { useState } from 'react'
import { DashboardShell, StatusBadge } from '@/components/supportnova'
import { mockResolutionRules, fictionalOrganization } from '@/lib/mock-data'
import { ResolutionRule, ComplaintCategory, UrgencyLevel } from '@/lib/types'
import {
  Network,
  ShieldCheck,
  Search,
  Filter,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  FileText,
  Clock,
  Zap,
  Building2,
  Lock,
  Eye,
  Info,
} from 'lucide-react'

export default function RuleMatrixPage() {
  const [rules, setRules] = useState<ResolutionRule[]>(mockResolutionRules)
  const [selectedRuleId, setSelectedRuleId] = useState<string>(mockResolutionRules[0].ruleId)
  const [searchQuery, setSearchQuery] = useState('')
  const [categoryFilter, setCategoryFilter] = useState<string>('All')
  const [departmentFilter, setDepartmentFilter] = useState<string>('All')

  const selectedRule = rules.find((r) => r.ruleId === selectedRuleId) || rules[0]

  const filteredRules = rules.filter((r) => {
    const matchesSearch =
      r.ruleId.toLowerCase().includes(searchQuery.toLowerCase()) ||
      r.category.toLowerCase().includes(searchQuery.toLowerCase()) ||
      r.subcategory.toLowerCase().includes(searchQuery.toLowerCase()) ||
      r.responsibleDepartment.toLowerCase().includes(searchQuery.toLowerCase())
    const matchesCategory = categoryFilter === 'All' || r.category === categoryFilter
    const matchesDept = departmentFilter === 'All' || r.responsibleDepartment === departmentFilter
    return matchesSearch && matchesCategory && matchesDept
  })

  const getUrgencyTone = (level: UrgencyLevel) => {
    switch (level) {
      case 'Critical':
        return 'rose'
      case 'High':
        return 'amber'
      case 'Medium':
        return 'indigo'
      default:
        return 'slate'
    }
  }

  return (
    <DashboardShell title="Complaint Resolution Rule Matrix">
      {/* Step 8 Core Notice: Static Deterministic Architecture */}
      <div
        style={{
          background: 'linear-gradient(135deg, rgba(16, 185, 129, 0.08), rgba(99, 102, 241, 0.08))',
          border: '1px solid rgba(16, 185, 129, 0.25)',
          borderRadius: 12,
          padding: '16px 20px',
          marginBottom: 24,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 16,
          flexWrap: 'wrap',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div
            style={{
              width: 38,
              height: 38,
              borderRadius: 8,
              background: '#10b981',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#fff',
            }}
          >
            <Lock size={20} />
          </div>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span className="eyebrow" style={{ color: '#34d399', fontWeight: 600 }}>
                STEP 8: DETERMINISTIC BUSINESS LOGIC (NON-GENAI GENERATED)
              </span>
              <span className="badge emerald">Audit Sealed</span>
            </div>
            <p style={{ margin: '2px 0 0 0', fontSize: 13, color: '#f1f5f9' }}>
              This Rule Matrix defines approved organizational complaint logic and cannot be overwritten at runtime by
              Generative AI. Pipeline 2 validates all AI outputs against these exact constraints.
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
            <span className="muted">ORGANIZATION:</span>{' '}
            <strong style={{ color: '#f8fafc' }}>{fictionalOrganization.name}</strong>
          </div>
          <div
            style={{
              background: 'rgba(15, 23, 42, 0.7)',
              padding: '6px 12px',
              borderRadius: 6,
              border: '1px solid rgba(255, 255, 255, 0.08)',
              fontSize: 12,
            }}
          >
            <span className="muted">ACTIVE RULES:</span>{' '}
            <strong style={{ color: '#34d399' }}>{rules.length} Rules Loaded</strong>
          </div>
        </div>
      </div>

      {/* Main Grid: Left = Matrix Table, Right = Selected Rule Deep Audit */}
      <div style={{ display: 'grid', gridTemplateColumns: '1.1fr 1fr', gap: 24, alignItems: 'start' }}>
        {/* Left: Filterable Rules Table */}
        <div className="table-card" style={{ padding: 20 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
            <div>
              <h3 style={{ margin: 0, fontSize: 16 }}>Approved Resolution Rules</h3>
              <p className="muted" style={{ fontSize: 12, marginTop: 3 }}>
                Categories, departments, urgency formulas, and mandatory actions
              </p>
            </div>
            <span className="badge indigo">{filteredRules.length} of {rules.length}</span>
          </div>

          {/* Search & Filters */}
          <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr 1fr', gap: 8, marginBottom: 14 }}>
            <div className="search">
              <Search size={14} />
              <input
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search rules, IDs, depts..."
                style={{ fontSize: 12 }}
              />
            </div>
            <select
              value={categoryFilter}
              onChange={(e) => setCategoryFilter(e.target.value)}
              className="select-button"
              style={{ padding: '6px 8px', fontSize: 12 }}
            >
              <option value="All">All Categories</option>
              <option value="Product Defect">Product Defect</option>
              <option value="Refund Request">Refund Request</option>
              <option value="Delivery & Logistics">Delivery & Logistics</option>
              <option value="Safety-Related Concern">Safety Concern</option>
              <option value="Account & Security">Account & Security</option>
            </select>
            <select
              value={departmentFilter}
              onChange={(e) => setDepartmentFilter(e.target.value)}
              className="select-button"
              style={{ padding: '6px 8px', fontSize: 12 }}
            >
              <option value="All">All Departments</option>
              {fictionalOrganization.departments.map((dept) => (
                <option key={dept} value={dept}>
                  {dept}
                </option>
              ))}
            </select>
          </div>

          {/* Rules List */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, maxHeight: 560, overflowY: 'auto' }}>
            {filteredRules.map((rule) => {
              const isSelected = rule.ruleId === selectedRuleId
              return (
                <div
                  key={rule.ruleId}
                  onClick={() => setSelectedRuleId(rule.ruleId)}
                  style={{
                    padding: '12px 14px',
                    borderRadius: 8,
                    cursor: 'pointer',
                    background: isSelected ? 'rgba(99, 102, 241, 0.16)' : 'rgba(255, 255, 255, 0.02)',
                    border: `1px solid ${isSelected ? '#6366f1' : 'rgba(255, 255, 255, 0.06)'}`,
                    transition: 'all 0.15s ease',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span style={{ fontWeight: 700, fontSize: 12, color: isSelected ? '#a5b4fc' : '#e2e8f0' }}>
                        {rule.ruleId}
                      </span>
                      <StatusBadge tone={getUrgencyTone(rule.urgencyLevel)}>{rule.urgencyLevel}</StatusBadge>
                    </div>
                    <span style={{ fontSize: 11, color: '#94a3b8' }}>{rule.responsibleDepartment}</span>
                  </div>

                  <div style={{ fontSize: 13, fontWeight: 600, color: '#f8fafc', marginBottom: 4 }}>
                    {rule.category} · <span style={{ color: '#c7d2fe' }}>{rule.subcategory}</span>
                  </div>

                  <p
                    style={{
                      fontSize: 11,
                      color: '#94a3b8',
                      margin: '0 0 6px 0',
                      lineHeight: 1.4,
                      whiteSpace: 'nowrap',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                    }}
                  >
                    <strong>Urgency:</strong> {rule.urgencyRule}
                  </p>

                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 11 }}>
                    <span style={{ color: '#34d399', display: 'flex', alignItems: 'center', gap: 4 }}>
                      <CheckCircle2 size={11} /> {rule.mandatoryActions.length} mandatory actions
                    </span>
                    <span style={{ color: '#f87171', display: 'flex', alignItems: 'center', gap: 4 }}>
                      <XCircle size={11} /> {rule.prohibitedActions.length} prohibited guardrails
                    </span>
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        {/* Right: Selected Rule Detail / Audit Inspector */}
        <div className="table-card" style={{ padding: 22 }}>
          {selectedRule ? (
            <div>
              {/* Header */}
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'flex-start',
                  borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
                  paddingBottom: 16,
                  marginBottom: 16,
                }}
              >
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                    <span className="eyebrow">{selectedRule.ruleId}</span>
                    <span className="badge indigo">{selectedRule.category}</span>
                    <StatusBadge tone={getUrgencyTone(selectedRule.urgencyLevel)}>
                      {selectedRule.urgencyLevel} Urgency
                    </StatusBadge>
                  </div>
                  <h3 style={{ fontSize: 18, fontWeight: 700, margin: '4px 0 2px 0', color: '#f8fafc' }}>
                    {selectedRule.subcategory}
                  </h3>
                  <p className="muted" style={{ fontSize: 12, margin: 0 }}>
                    Responsible Queue: <strong style={{ color: '#e2e8f0' }}>{selectedRule.responsibleDepartment}</strong>
                  </p>
                </div>

                <div
                  style={{
                    background: 'rgba(16, 185, 129, 0.12)',
                    border: '1px solid rgba(16, 185, 129, 0.3)',
                    padding: '4px 10px',
                    borderRadius: 6,
                    fontSize: 11,
                    color: '#34d399',
                    fontWeight: 600,
                  }}
                >
                  Ground Truth Active
                </div>
              </div>

              {/* Urgency & Escalation Rules */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 16 }}>
                <div
                  style={{
                    background: 'rgba(15, 23, 42, 0.65)',
                    border: '1px solid rgba(255, 255, 255, 0.06)',
                    borderRadius: 8,
                    padding: 12,
                  }}
                >
                  <small className="muted" style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11 }}>
                    <Clock size={12} /> URGENCY RULE
                  </small>
                  <p style={{ fontSize: 12, color: '#e2e8f0', margin: '4px 0 0 0', lineHeight: 1.5 }}>
                    {selectedRule.urgencyRule}
                  </p>
                </div>
                <div
                  style={{
                    background: 'rgba(15, 23, 42, 0.65)',
                    border: '1px solid rgba(255, 255, 255, 0.06)',
                    borderRadius: 8,
                    padding: 12,
                  }}
                >
                  <small className="muted" style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11 }}>
                    <Zap size={12} className="text-amber-400" /> ESCALATION THRESHOLD
                  </small>
                  <p style={{ fontSize: 12, color: '#fde68a', margin: '4px 0 0 0', lineHeight: 1.5 }}>
                    {selectedRule.escalationRule}
                  </p>
                </div>
              </div>

              {/* Mandatory Actions (Required for Pipeline 2 Approval) */}
              <div style={{ marginBottom: 16 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
                  <CheckCircle2 size={15} className="text-emerald-400" />
                  <strong style={{ fontSize: 13, color: '#f1f5f9' }}>
                    Mandatory Resolution Actions ({selectedRule.mandatoryActions.length})
                  </strong>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {selectedRule.mandatoryActions.map((action, idx) => (
                    <div
                      key={idx}
                      style={{
                        background: 'rgba(16, 185, 129, 0.07)',
                        borderLeft: '3px solid #10b981',
                        borderRadius: '0 6px 6px 0',
                        padding: '8px 12px',
                        fontSize: 12,
                        color: '#d1fae5',
                      }}
                    >
                      {action}
                    </div>
                  ))}
                </div>
              </div>

              {/* Prohibited Actions (Anti-Hallucination Guardrails) */}
              <div style={{ marginBottom: 16 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
                  <AlertTriangle size={15} className="text-rose-400" />
                  <strong style={{ fontSize: 13, color: '#f1f5f9' }}>
                    Prohibited Actions & Guardrails ({selectedRule.prohibitedActions.length})
                  </strong>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {selectedRule.prohibitedActions.map((action, idx) => (
                    <div
                      key={idx}
                      style={{
                        background: 'rgba(244, 63, 94, 0.08)',
                        borderLeft: '3px solid #f43f5e',
                        borderRadius: '0 6px 6px 0',
                        padding: '8px 12px',
                        fontSize: 12,
                        color: '#fecdd3',
                      }}
                    >
                      {action}
                    </div>
                  ))}
                </div>
              </div>

              {/* Policy Grounding References */}
              <div style={{ marginBottom: 16 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
                  <FileText size={15} className="text-indigo-400" />
                  <strong style={{ fontSize: 13, color: '#f1f5f9' }}>
                    Approved Policy Citations ({selectedRule.policyReferences.length})
                  </strong>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {selectedRule.policyReferences.map((ref, idx) => (
                    <div
                      key={idx}
                      style={{
                        background: 'rgba(99, 102, 241, 0.08)',
                        border: '1px solid rgba(99, 102, 241, 0.2)',
                        borderRadius: 6,
                        padding: '8px 12px',
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        fontSize: 12,
                      }}
                    >
                      <div>
                        <strong style={{ color: '#a5b4fc' }}>{ref.documentId}</strong> · {ref.sectionId}
                        <div className="muted" style={{ fontSize: 11, marginTop: 2 }}>
                          {ref.documentTitle}
                        </div>
                      </div>
                      <span className="badge indigo">{ref.clauseRef}</span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Follow-up Requirements */}
              <div
                style={{
                  background: 'rgba(15, 23, 42, 0.65)',
                  border: '1px solid rgba(255, 255, 255, 0.06)',
                  borderRadius: 8,
                  padding: 12,
                }}
              >
                <small className="muted" style={{ display: 'block', fontSize: 11, marginBottom: 4 }}>
                  FOLLOW-UP REQUIREMENT
                </small>
                <p style={{ fontSize: 12, color: '#cbd5e1', margin: 0, lineHeight: 1.5 }}>
                  {selectedRule.followUpRequirements}
                </p>
              </div>
            </div>
          ) : (
            <div style={{ textAlign: 'center', padding: 40, color: '#64748b' }}>Select a rule to view specifications</div>
          )}
        </div>
      </div>
    </DashboardShell>
  )
}
