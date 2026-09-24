// SupportNova API Client
// All 61 backend endpoints with auth, silent refresh, typed models.
// Backend: FastAPI at http://localhost:8000
// NEVER: no service role keys, no localStorage tokens, no direct Supabase calls.

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

// ── Token management (memory-only; refresh via httpOnly cookie) ──────────────
let _accessToken: string | null = null

export function setAccessToken(token: string | null) {
  _accessToken = token
}
export function getAccessToken(): string | null {
  return _accessToken
}

// ── Core fetch with silent 401 refresh ───────────────────────────────────────
type FetchOpts = RequestInit & { _retry?: boolean }

export async function apiFetch<T = unknown>(path: string, opts: FetchOpts = {}): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(opts.headers as Record<string, string>),
  }
  if (_accessToken) headers['Authorization'] = `Bearer ${_accessToken}`

  const res = await fetch(`${API_BASE}${path}`, {
    ...opts,
    headers,
    credentials: 'include',
  })

  if (res.status === 401 && !opts._retry) {
    const ok = await tryRefresh()
    if (ok) return apiFetch<T>(path, { ...opts, _retry: true })
    _accessToken = null
    if (typeof window !== 'undefined') window.dispatchEvent(new CustomEvent('auth:expired'))
    throw new ApiError(401, 'Session expired. Please sign in again.')
  }

  if (!res.ok) {
    let msg = `HTTP ${res.status}`
    try {
      const b = await res.json()
      msg = b?.detail ?? b?.message ?? b?.error ?? msg
    } catch {}
    throw new ApiError(res.status, msg)
  }

  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

async function tryRefresh(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/api/auth/refresh`, { method: 'POST', credentials: 'include' })
    if (!res.ok) return false
    const d = await res.json()
    if (d.access_token) { _accessToken = d.access_token; return true }
    return false
  } catch { return false }
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
    this.name = 'ApiError'
  }
}

// ── Types ─────────────────────────────────────────────────────────────────────
export type Role = 'customer' | 'agent' | 'reviewer' | 'manager' | 'admin' | 'evaluator'

export interface User {
  id: string; email: string; role: Role; display_name?: string; department?: string
}
export interface AuthResponse {
  access_token: string; token_type: string; user: User
}

export type ComplaintStatus =
  | 'SUBMITTED' | 'ANALYZING' | 'ANALYZED' | 'FAILED' | 'ASSIGNED'
  | 'IN_PROGRESS' | 'AWAITING_CUSTOMER' | 'RESOLVED' | 'CLOSED'
  | 'ESCALATED' | 'REOPENED' | 'IN_REVIEW'

export type PriorityLevel = 'P0' | 'P1' | 'P2' | 'P3'
export type UrgencyLevel = 'Critical' | 'High' | 'Medium' | 'Low'
export type VerificationOutcome = 'VERIFIED' | 'MISMATCH' | 'CRITICAL'

export interface ComplaintSummary {
  id: string; ref: string; public_ref: string; title: string
  status: ComplaintStatus; priority: PriorityLevel; urgency: UrgencyLevel
  category?: string; department?: string; created_at: string; updated_at: string
  awaiting_customer?: boolean; dataset_tag?: string
  verification_outcome?: VerificationOutcome | null
}

export interface PipelineResult {
  category?: string; subcategory?: string; urgency?: UrgencyLevel
  priority?: PriorityLevel; department?: string; escalation_required?: boolean
  escalation_level?: string; sentiment?: string; confidence?: number | null
  processing_time_ms?: number
}

export interface Disagreement {
  field: string; ai_value: string; python_value: string; winner: 'GENAI' | 'PYTHON'
}

export interface ReconciledResult {
  category: string; subcategory?: string; urgency: UrgencyLevel; priority: PriorityLevel
  department: string; escalation_required: boolean; escalation_level?: string
  agreement_score: number | null; source: 'GENAI' | 'PYTHON' | 'AGREEMENT'
  disagreements?: Disagreement[]
}

export interface ComplaintDetail extends ComplaintSummary {
  description: string; order_ref?: string; product?: string; amount?: number
  customer_id: string; customer_name?: string; customer_email?: string
  customer_type?: string; channel?: string; entities?: Record<string, string[]>
  summary?: string; escalation_required?: boolean; escalation_level?: string
  available_actions?: ComplaintStatus[]
  pipeline_ai?: PipelineResult; pipeline_python?: PipelineResult; reconciled?: ReconciledResult
}

export interface ExplainResult {
  rules_fired: { rule_id: string; description: string; outcome: string }[]
  genai_reasoning?: string; python_reasoning?: string; reconciliation_notes?: string
}

export interface ChecklistStep {
  step_id: string; title: string; description?: string
  type: 'RULE_REQUIRED' | 'SUGGESTED'; confirmed: boolean
  confirmed_at?: string; confirmed_by?: string
}

export interface FollowUp {
  id: string; complaint_ref: string; type: string; due_at: string
  completed: boolean; completed_at?: string; description?: string; minutes_late?: number
}

export interface EscalationNote {
  level: string; handler?: string; note?: string; note_available: boolean; escalated_at?: string
}

export interface LifecycleEvent {
  id: string; event_type: string; from_status?: ComplaintStatus; to_status?: ComplaintStatus
  actor?: string; note?: string; created_at: string
}

export interface SlaInfo {
  first_response_target_minutes?: number; first_response_met?: boolean | null
  resolution_target_minutes?: number; resolution_met?: boolean | null
  breached: boolean; minutes_remaining?: number; risk_level?: 'OK' | 'APPROACHING' | 'BREACHED'
}

export interface ReviewHistoryItem {
  id: string; action: string; reviewer_email: string; note?: string; created_at: string
}

export interface ReviewQueueItem {
  ref: string; title: string
  reason: 'GENAI_UNAVAILABLE' | 'GENAI_PYTHON_DISAGREEMENT' | 'MANUAL_FLAG' | string
  priority: PriorityLevel; queued_at: string; claimed_by?: string; complaint: ComplaintSummary
}

export interface ReviewStats {
  queue_depth: number; override_rate: number | null; avg_review_time_minutes?: number | null
}

export interface AnalyticsDashboard {
  total_complaints: number; resolved_count: number; escalated_count: number
  avg_resolution_hours?: number | null; pipeline_agreement_rate: number | null
  by_status: Record<string, number>; by_priority: Record<string, number>
}

export interface VolumeData { period: string; count: number }
export interface CategoryData { category: string; count: number; percentage: number | null }
export interface DepartmentData { department: string; count: number; resolved: number; pending: number }

export interface PipelineData {
  total: number; agreement_count: number; mismatch_count: number; agreement_rate: number | null
  by_field: { field: string; agreement_rate: number | null }[]
}

export interface TrendItem {
  id: string; metric: string; category?: string; change_pct: number | null
  direction: 'UP' | 'DOWN' | 'STABLE'; description?: string
}
export interface TrendHistory { metric: string; periods: { date: string; value: number }[] }

export interface Report { type: string; label: string; description?: string; row_count: number }
export interface ExportRecord {
  id: string; type: string; format: string; requested_by: string
  requested_at: string; file_size_bytes?: number
}

export interface KnowledgeDocument {
  id: string; document_id?: string; title: string; category?: string; file_type?: string
  version_count: number; active_version_id?: string; active_version?: string
  status: 'ACTIVE' | 'INACTIVE' | 'DRAFT'; created_at: string; updated_at?: string
}

export interface DocumentVersion {
  id: string; document_id: string; version_label: string
  status: 'ACTIVE' | 'INACTIVE' | 'DRAFT'; chunk_count: number
  section_count: number; created_at: string; activated_at?: string; deactivated_at?: string
}

export interface DocumentChunk {
  chunk_key: string; section_id: string; heading?: string; content: string
  page_number?: number; source_reference?: string
}

export interface DocumentCoverage {
  total_documents: number; active_documents: number; total_chunks: number
  categories_covered: string[]
}

export interface ValidationIssue {
  document_id: string; version_id?: string; issue_type: string
  severity: 'ERROR' | 'WARNING' | 'INFO'; description: string; created_at: string
}

export interface SearchResult {
  chunk_key: string; document_title: string; document_id: string
  version_label: string; version_status: 'ACTIVE' | 'INACTIVE'
  section_heading?: string; content_snippet: string; score?: number
}

export interface TraceResult {
  chunk_key: string; document_id: string; document_title: string
  version_id: string; version_label: string; version_status: 'ACTIVE' | 'INACTIVE'
  section?: string; content: string
}

export interface BenchmarkDataset {
  tag: string; total_count: number; labelled_count: number; scoreable: boolean; created_at?: string
}

export interface BenchmarkRun {
  id: string; dataset_tag: string; started_at: string; completed_at?: string
  status: 'RUNNING' | 'COMPLETED' | 'FAILED'
  overall_accuracy?: number | null; guard_compliance?: number | null
}

export interface BenchmarkRunDetail extends BenchmarkRun {
  per_field: { field: string; accuracy: number | null }[]
  failures: { ref: string; field: string; expected: string; got: string; description?: string }[]
}

export interface SystemHealth {
  status: 'OK' | 'DEGRADED' | 'DOWN'
  database: 'OK' | 'ERROR'; genai_provider: 'OK' | 'UNAVAILABLE' | 'ERROR'
  rule_engine: 'OK' | 'ERROR'; degraded_reason?: string
}
export interface SystemVersion {
  app_version: string; ruleset_version: string
  knowledge_base_version?: string; api_version?: string
}

export interface Paginated<T> {
  items: T[]; total: number; page: number; per_page: number; pages: number
}

// ── Auth ─────────────────────────────────────────────────────────────────────
export const auth = {
  login: (email: string, password: string) =>
    apiFetch<AuthResponse>('/api/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) }),
  refresh: () => apiFetch<AuthResponse>('/api/auth/refresh', { method: 'POST' }),
  me: () => apiFetch<User>('/api/auth/me'),
  changePassword: (current_password: string, new_password: string) =>
    apiFetch<void>('/api/auth/change-password', { method: 'POST', body: JSON.stringify({ current_password, new_password }) }),
  logout: () => apiFetch<void>('/api/auth/logout', { method: 'POST' }),
}

// ── Complaints ────────────────────────────────────────────────────────────────
export const complaints = {
  mine: () => apiFetch<ComplaintSummary[]>('/api/complaints/mine'),

  list: (params?: { status?: string; category?: string; department?: string; urgency?: string; priority?: string; verification_outcome?: string; dataset_tag?: string; q?: string; page?: number; per_page?: number }) => {
    const qs = new URLSearchParams()
    if (params) Object.entries(params).forEach(([k, v]) => { if (v != null && v !== '') qs.set(k, String(v)) })
    return apiFetch<Paginated<ComplaintSummary>>(`/api/complaints${qs.toString() ? '?' + qs : ''}`)
  },

  create: (data: { title: string; description: string; order_ref?: string; product?: string; amount?: number }) =>
    apiFetch<{ ref: string; public_ref: string; validation_findings?: string[] }>('/api/complaints', { method: 'POST', body: JSON.stringify(data) }),

  get: (ref: string) => apiFetch<ComplaintDetail>(`/api/complaints/${ref}`),
  status: (ref: string) => apiFetch<{ public_ref: string; status: ComplaintStatus; category?: string; summary?: string; specialist_involved?: boolean; outstanding_questions?: string[] }>(`/api/complaints/${ref}/status`),
  explain: (ref: string) => apiFetch<ExplainResult>(`/api/complaints/${ref}/explain`),
  checklist: (ref: string) => apiFetch<ChecklistStep[]>(`/api/complaints/${ref}/checklist`),
  confirmStep: (ref: string, step_id: string) => apiFetch<ChecklistStep>(`/api/complaints/${ref}/checklist/${step_id}/confirm`, { method: 'POST' }),
  followUps: (ref: string) => apiFetch<FollowUp[]>(`/api/complaints/${ref}/follow-ups`),
  completeFollowUp: (ref: string, id: string) => apiFetch<FollowUp>(`/api/complaints/${ref}/follow-ups/${id}/complete`, { method: 'POST' }),
  escalation: (ref: string) => apiFetch<EscalationNote>(`/api/complaints/${ref}/escalation`),
  lifecycle: (ref: string) => apiFetch<{ events: LifecycleEvent[]; available_actions: ComplaintStatus[] }>(`/api/complaints/${ref}/lifecycle`),
  updateStatus: (ref: string, status: ComplaintStatus, note?: string) => apiFetch<ComplaintDetail>(`/api/complaints/${ref}/status`, { method: 'POST', body: JSON.stringify({ status, note }) }),
  reanalyse: (ref: string) => apiFetch<ComplaintDetail>(`/api/complaints/${ref}/reanalyse`, { method: 'POST' }),
}

// ── Review ────────────────────────────────────────────────────────────────────
export const review = {
  queue: () => apiFetch<ReviewQueueItem[]>('/api/review/queue'),
  stats: () => apiFetch<ReviewStats>('/api/review/stats'),
  claim: (ref: string) => apiFetch<ReviewQueueItem>(`/api/review/queue/${ref}/claim`, { method: 'POST' }),
  action: (ref: string, action: 'APPROVE' | 'DISMISS' | 'OVERRIDE', data?: { note?: string; override_fields?: Record<string, unknown>; escalation_level?: string }) =>
    apiFetch<{ success: boolean }>(`/api/review/${ref}/actions`, { method: 'POST', body: JSON.stringify({ action, ...data }) }),
  history: (ref: string) => apiFetch<ReviewHistoryItem[]>(`/api/review/${ref}/history`),
  sla: (ref: string) => apiFetch<SlaInfo>(`/api/review/${ref}/sla`),
  followUpsDue: () => apiFetch<FollowUp[]>('/api/review/follow-ups/due'),
  slaSweep: () => apiFetch<{ updated_count: number }>('/api/review/sla/sweep', { method: 'POST' }),
}

// ── Analytics ─────────────────────────────────────────────────────────────────
export const analytics = {
  dashboard: () => apiFetch<AnalyticsDashboard>('/api/analytics/dashboard'),
  volume: (params?: { period?: string; from?: string; to?: string }) => {
    const qs = new URLSearchParams(params as Record<string, string>)
    return apiFetch<VolumeData[]>(`/api/analytics/volume?${qs}`)
  },
  categories: () => apiFetch<CategoryData[]>('/api/analytics/categories'),
  departments: () => apiFetch<DepartmentData[]>('/api/analytics/departments'),
  pipelines: () => apiFetch<PipelineData>('/api/analytics/pipelines'),
  myQueue: () => apiFetch<{ assigned: number; in_progress: number; breaching: number; complaints: ComplaintSummary[] }>('/api/analytics/my-queue'),
  trends: () => apiFetch<TrendItem[]>('/api/analytics/trends'),
  trendsHistory: (metric: string) => apiFetch<TrendHistory>(`/api/analytics/trends/history?metric=${metric}`),
  trendsSnapshot: () => apiFetch<{ period_id: string; created: boolean }>('/api/analytics/trends/snapshot', { method: 'POST' }),
  reports: () => apiFetch<Report[]>('/api/analytics/reports'),
  report: (type: string) => apiFetch<{ type: string; data: unknown[] }>(`/api/analytics/reports/${type}`),
  reportExportUrl: (type: string) => `${API_BASE}/api/analytics/reports/${type}/export?token=${_accessToken}`,
  exports: () => apiFetch<ExportRecord[]>('/api/analytics/exports'),
}

// ── Knowledge base ────────────────────────────────────────────────────────────
export const knowledge = {
  list: () => apiFetch<KnowledgeDocument[]>('/api/documents'),
  coverage: () => apiFetch<DocumentCoverage>('/api/documents/coverage'),
  validationIssues: () => apiFetch<ValidationIssue[]>('/api/documents/validation-issues'),
  upload: (files: File[]) => {
    const form = new FormData()
    files.forEach((f) => form.append('files', f))
    const headers: Record<string, string> = {}
    if (_accessToken) headers['Authorization'] = `Bearer ${_accessToken}`
    return fetch(`${API_BASE}/api/documents`, { method: 'POST', headers, credentials: 'include', body: form }).then((r) => r.json()) as Promise<{ results: { filename: string; success: boolean; document_id?: string; error?: string }[] }>
  },
  get: (document_id: string) => apiFetch<KnowledgeDocument & { versions: DocumentVersion[] }>(`/api/documents/${document_id}`),
  version: (version_id: string) => apiFetch<DocumentVersion & { sections: { id: string; heading: string; content_preview: string }[]; findings: ValidationIssue[] }>(`/api/documents/versions/${version_id}`),
  chunks: (version_id: string) => apiFetch<DocumentChunk[]>(`/api/documents/versions/${version_id}/chunks`),
  activate: (version_id: string) => apiFetch<DocumentVersion>(`/api/documents/versions/${version_id}/activate`, { method: 'POST' }),
  deactivate: (version_id: string) => apiFetch<DocumentVersion>(`/api/documents/versions/${version_id}/deactivate`, { method: 'POST' }),
  search: (query: string, limit?: number) => apiFetch<SearchResult[]>('/api/documents/search', { method: 'POST', body: JSON.stringify({ query, limit: limit ?? 10 }) }),
  trace: (chunk_key: string) => apiFetch<TraceResult>(`/api/documents/trace/${encodeURIComponent(chunk_key)}`),
  chunkByReference: (reference: string) => apiFetch<TraceResult>(`/api/documents/chunks/by-reference?reference=${encodeURIComponent(reference)}`),
}

// ── Benchmark ─────────────────────────────────────────────────────────────────
export const benchmark = {
  datasets: () => apiFetch<BenchmarkDataset[]>('/api/benchmark/datasets'),
  runs: () => apiFetch<BenchmarkRun[]>('/api/benchmark/runs'),
  run: (dataset_tag: string) => apiFetch<BenchmarkRun>('/api/benchmark/run', { method: 'POST', body: JSON.stringify({ dataset_tag }) }),
  dataset: (tag: string) => apiFetch<BenchmarkDataset & { sample_refs?: string[] }>(`/api/benchmark/datasets/${tag}`),
  importDataset: (tag: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    const headers: Record<string, string> = {}
    if (_accessToken) headers['Authorization'] = `Bearer ${_accessToken}`
    return fetch(`${API_BASE}/api/benchmark/datasets/${tag}/import`, { method: 'POST', headers, credentials: 'include', body: form }).then((r) => r.json()) as Promise<{ imported: number; labelled: number; rejected: number; rejection_reasons?: string[] }>
  },
  deleteDataset: (tag: string) => apiFetch<void>(`/api/benchmark/datasets/${tag}`, { method: 'DELETE' }),
  runDetail: (run_id: string) => apiFetch<BenchmarkRunDetail>(`/api/benchmark/runs/${run_id}`),
}

// ── System ────────────────────────────────────────────────────────────────────
export const system = {
  health: () => apiFetch<SystemHealth>('/api/system/health'),
  version: () => apiFetch<SystemVersion>('/api/system/version'),
}
