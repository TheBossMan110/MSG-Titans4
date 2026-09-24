export type CustomerType = 'Standard' | 'Premium' | 'VIP' | 'Enterprise' | 'New Customer'

export type ComplaintChannel = 'Email' | 'Web Form' | 'Live Chat' | 'Messaging App' | 'Customer Portal'

export type ComplaintCategory =
  | 'Product Defect'
  | 'Billing & Payment'
  | 'Delivery & Logistics'
  | 'Service Failure'
  | 'Refund Request'
  | 'Account & Security'
  | 'Technical Problem'
  | 'Inappropriate Service Experience'
  | 'Safety-Related Concern'

export type UrgencyLevel = 'Low' | 'Medium' | 'High' | 'Critical'

export type PriorityLevel = 'P0' | 'P1' | 'P2' | 'P3' | 'P4'

export type ComplaintStatus =
  | 'New'
  | 'Analyzed'
  | 'Assigned'
  | 'In Progress'
  | 'Awaiting Customer'
  | 'Escalated'
  | 'Resolved'
  | 'Closed'
  | 'Reopened'
  | 'In Review'
  | 'Submitted'

export type SentimentType = 'Strongly Negative' | 'Negative' | 'Neutral' | 'Mixed' | 'Positive'

export interface ComplaintAttachment {
  id: string
  name: string
  size: string
  type: string
  url?: string
}

export interface ComplaintHistoryItem {
  ticketId: string
  date: string
  issue: string
  status: string
}

// 1.2: Intake Schema
export interface ComplaintInput {
  id: string
  title: string
  description: string
  customerType: CustomerType
  customerId?: string // Step 53
  customerName?: string // Step 53
  customerEmail?: string // Step 53
  productOrService: string
  orderOrTransactionRef: string
  channel: ComplaintChannel
  date: string
  supportingDocuments: ComplaintAttachment[]
  previousHistory: ComplaintHistoryItem[] // Step 53
  requestedResolution: string
  status: ComplaintStatus // Step 60
  duplicateInfo?: DuplicateDetectionResult // Step 52
  repeatAlert?: RepeatComplaintAlert // Step 54
  slaTracking?: SlaStatusTracking // Step 55 & 56
  profiles?: ComplaintProfileType[] // Mandatory 14 Mixture Profiles
}

// Step 1: Fictional Organization Profile
export interface OrganizationProfile {
  name: string
  legalName: string
  domain: 'Consumer electronics' | 'E-commerce' | 'Subscription services'
  tagline: string
  products: string[]
  departments: string[]
  supportedChannels: ComplaintChannel[]
}

// Step 2: Knowledge Base Document Categories (13 Required Categories)
export type DocumentCategory =
  | 'Complaint policy'
  | 'Refund policy'
  | 'Replacement policy'
  | 'Cancellation policy'
  | 'Billing policy'
  | 'Delivery policy'
  | 'Warranty policy'
  | 'Privacy policy'
  | 'Escalation procedure'
  | 'Complaint SOP'
  | 'Department-routing rules'
  | 'Service-level rules'
  | 'FAQs'
  | 'Customer-service policy'
  | 'Product-support guideline'
  | 'Compliance guideline'
  | 'Response template'

// Step 3: Mandatory (PDF, DOCX) and Optional (TXT, MD, CSV) Formats
export type SupportedDocumentFormat = 'pdf' | 'docx' | 'txt' | 'md' | 'csv'

// Step 7: Policy Version Control
export type PolicyLifecycleStatus = 'Active policy' | 'Previous policy' | 'Superseded policy' | 'Draft policy'

// Step 4: Document Validation
export interface DocumentValidationSummary {
  fileTypeValid: boolean
  fileSizeValid: boolean
  notEmpty: boolean
  notDuplicate: boolean
  documentIdValid: boolean
  versionValid: boolean
  effectiveDateValid: boolean
  expiryDateValid: boolean
  categoryApproved: boolean
  allPassed: boolean
  errors: string[]
}

// Step 5 & 6: Document Parsing and Chunking
export interface DocumentChunk {
  chunkId: string
  documentId?: string
  sectionId: string
  heading: string
  content: string
  sourceReference: string
  pageNumber?: number
  pageReference?: string
  version?: string
}

export interface KnowledgeDocument {
  documentId: string
  title: string
  category: DocumentCategory
  fileType: SupportedDocumentFormat
  fileSize: string
  version: string
  effectiveDate: string
  expiryDate?: string
  uploadedAt: string
  lifecycleStatus?: PolicyLifecycleStatus
  status?: 'Active' | 'Under Review' | 'Archived'
  supersededBy?: string
  chunks: DocumentChunk[]
}

// Step 8: Complaint Resolution Rule Matrix
export interface ResolutionRule {
  ruleId: string
  category: ComplaintCategory
  subcategory: string
  responsibleDepartment: string
  urgencyRule: string
  urgencyLevel: UrgencyLevel
  escalationRule: string
  mandatoryActions: string[]
  prohibitedActions: string[]
  policyReferences: {
    documentId: string
    documentTitle: string
    sectionId: string
    clauseRef: string
  }[]
  followUpRequirements: string
  isPredefinedDeterministicMatrix?: boolean
}

// Step 9: Complaint Submission Input
export interface ComplaintSubmissionInput {
  title: string
  description: string
  productOrService: string
  orderReference: string
  customerType: CustomerType
  previousComplaintReference?: string
  preferredContactChannel: ComplaintChannel
  supportingInformation?: string
  attachments?: ComplaintAttachment[]
}

// Step 10: Complaint Validation Checks
export interface ComplaintValidationFeedback {
  isEmpty: boolean
  isTooShort: boolean // < 15 chars
  isDuplicate: boolean
  invalidRefId: boolean
  missingFields: string[]
  unsupportedAttachments: string[]
  isValid: boolean
}

// Step 11: Complaint Pre-processing Details
export interface PreProcessingMetadata {
  originalLength: number
  cleanedLength: number
  whitespaceNormalized: boolean
  charactersNormalized: boolean
  sanitized: boolean
  extractedEntitiesCount: number
  duplicateSimilarityScore: number // 0 - 100%
  cleanedText: string
}

// Step 14 & 15: Configurable Categories & Subcategories
export interface ConfigurableCategoryTaxonomy {
  id: string
  name: string
  description: string
  subcategories: string[]
  defaultDepartment: string
  defaultUrgency: UrgencyLevel
}

// Step 18: Emotion & Tone Indicators
export type EmotionIndicator =
  | 'Frustration'
  | 'Anger'
  | 'Disappointment'
  | 'Confusion'
  | 'Urgency'
  | 'Calm'
  | 'Neutral'

// Step 26: Policy Applicability
export type PolicyApplicabilityStatus = 'Applicable' | 'Conditionally Applicable' | 'Not Applicable' | 'Outdated'

// Step 16: Entity Extraction
export interface ExtractedEntity {
  label: string
  value: string
  type:
    | 'product'
    | 'service'
    | 'order_id'
    | 'transaction_id'
    | 'date'
    | 'amount'
    | 'monetary'
    | 'location'
    | 'department'
    | 'complaint_reference'
    | 'contact'
    | 'person'
}

// Step 25 & 26: Grounded Policy Reference with Applicability
export interface PolicyReferenceCitation {
  documentId: string
  documentTitle: string
  sectionId: string
  clause: string
  snippet: string
  relevanceScore: number
  applicabilityStatus?: PolicyApplicabilityStatus // Step 26
  applicabilityNote?: string
}

// Step 33: Configurable Response Tones
export type ResponseTone = 'Professional' | 'Empathetic' | 'Concise' | 'Formal'

// Step 37: Escalation Levels
export type EscalationLevel =
  | 'No Escalation'
  | 'Supervisor Review'
  | 'Department Manager'
  | 'Specialist Team'
  | 'Compliance Review'
  | 'Critical Management Escalation'

// Step 38: Structured Internal Escalation Notes
export interface StructuredEscalationNotes {
  complaintSummary: string
  keyFacts: string[]
  reasonForEscalation: string
  actionsAlreadyTaken: string[]
  relevantPolicy: string
  requiredNextAction: string
}

// Step 12 & 13 & 21 & 24 & 27-38: Full Complaint Intelligence Result
export interface ComplaintIntelligenceResult {
  complaintId: string
  mainIssue: string
  primaryIssue: string // Step 13
  secondaryIssue?: string // Step 13
  category: ComplaintCategory // Step 14
  subcategory: string // Step 15
  sentiment: SentimentType // Step 17
  detectedEmotions?: EmotionIndicator[] // Step 18
  urgency: UrgencyLevel // Step 19
  priority: PriorityLevel // Step 20
  trickyCaseClassification?: string // Step 21
  productOrService: string
  relevantEntities: ExtractedEntity[] // Step 16
  requiredDepartment: string // Step 22
  primaryDepartment?: string // Step 24
  supportingDepartment?: string // Step 24
  resolutionRecommendation: string
  resolutionSteps: string[] // Step 27
  missingMandatorySteps?: string[] // Step 28
  prohibitedActionsDetected?: string[] // Step 28
  refundEligibility?: 'Eligible' | 'Ineligible' | 'Requires Validation' // Step 29
  replacementEligibility?: 'Eligible' | 'Ineligible' | 'Requires Verification' // Step 30
  compensationPermitted?: boolean // Step 31
  compensationDetails?: string // Step 31
  escalationRequirement: boolean // Step 36
  escalationLevel?: EscalationLevel // Step 37
  escalationReason: string | null
  structuredEscalationNotes?: StructuredEscalationNotes // Step 38
  professionalCustomerResponse: string // Step 32
  responseTone?: ResponseTone // Step 33
  toneVariations?: Record<ResponseTone, string> // Step 33
  unsupportedPromisesDetected?: string[] // Step 34
  hallucinationsDetected?: string[] // Step 35
  followUpCommunication: string
  followUpOptions?: Record<FollowUpCommunicationType, string> // Step 40
  scheduledFollowUps?: ScheduledFollowUp[] // Step 41
  missingInformationAudit?: MissingInformationAudit // Step 42
  clarificationQuestions?: string[] // Step 43
  structuredSummary?: StructuredComplaintSummary // Step 44
  agentGuidance: string[]
  agentGuidanceItems?: AgentGuidanceChecklistItem[] // Step 45
  supportingPolicyReferences: PolicyReferenceCitation[] // Step 25 & 26
  preprocessing?: PreProcessingMetadata
  promptExecutionAudit?: PromptExecutionAuditLog // Step 49
  adversarialAudit?: AdversarialAttackAudit // Step 50 & 51
  escalationOverrideNote?: string // Step 39
  jsonSchemaReport?: JsonSchemaValidationReport // Step 46
  manualReviewInfo?: ManualReviewQueueEntry // Step 57
  reviewerOverrides?: ReviewerAuditTrailItem[] // Step 58 & 59
  profiles?: ComplaintProfileType[] // Mandatory 14 Mixture Profiles
}

// Pipeline 1: GenAI Provider Configuration
export type GenAIProvider = 'Google Gemini' | 'OpenAI' | 'Anthropic' | 'Approved Custom API'

export interface GenAIModelConfig {
  provider: GenAIProvider
  modelName: string
  temperature: number
  enforceJsonSchema: boolean
  ragChunkCount: number
}

// Sample GenAI Structured Output as defined in Pipeline 1 spec
export interface GenAIStructuredOutput {
  complaint_id: string
  primary_issue: string
  secondary_issue?: string
  issue_category: string
  subcategory: string
  sentiment: 'Strongly Negative' | 'Negative' | 'Neutral' | 'Mixed' | 'Positive'
  urgency: 'Critical' | 'High' | 'Medium' | 'Low'
  priority: 'P1' | 'P2' | 'P3' | 'P4'
  department: string
  policy_id: string
  policy_section: string
  resolution_steps: string[]
  escalation_required: boolean
  escalation_notes?: string
  response_type: string
  professional_response?: string
  follow_up_required: boolean
  follow_up_communication?: string
  agent_guidance?: string[]
  clarification_questions?: string[]
  extracted_entities?: ExtractedEntity[]
  raw_json?: string
}

// Pipeline 2: Python Ground-Truth Complaint Validation Pipeline
export type VerificationStatus = 'Passed' | 'Discrepancy' | 'Flagged' | 'Violation'

export interface GroundTruthVerificationItem {
  criterion:
    | 'Complaint category'
    | 'Complaint subcategory'
    | 'Department assignment'
    | 'Urgency'
    | 'Priority'
    | 'Mandatory escalation'
    | 'Policy applicability'
    | 'Policy version'
    | 'Resolution eligibility'
    | 'Required actions'
    | 'Prohibited actions'
    | 'Compensation eligibility'
    | 'Follow-up requirements'
    | 'Source-document references'
    | 'Unsupported generated claims'
    | 'Contradictory instructions'
    | 'Missing mandatory actions'
  expectedRuleValue: string
  genAiValue: string
  status: VerificationStatus
  ruleReference: string
  auditNote: string
}

export interface RuleValidationCheck {
  id: string
  name: string
  description: string
  expected: string
  aiValue: string
  status: 'Passed' | 'Flagged' | 'Review Required'
  ruleRef: string
  details?: string
}

export interface ValidationPipelineResult {
  complaintId: string
  agreementScore: number // e.g. 98.2%
  overallVerdict?: 'Approved for Dispatch' | 'Blocked / Policy Violation' | 'Requires Human Override'
  engineType?: 'Independent Deterministic Python Engine (Non-LLM)'
  classificationStatus: 'Passed' | 'Discrepancy'
  departmentStatus: 'Passed' | 'Discrepancy'
  urgencyStatus: 'Passed' | 'Discrepancy'
  policyGroundingStatus: 'Passed' | 'Partial' | 'Unverified'
  hallucinationRisk: 'Low' | 'Medium' | 'High'
  escalationValidationStatus?: 'Passed' | 'Discrepancy (Overridden by Python)' // Step 39
  prohibitedActionsDetected?: string[]
  missingMandatoryActions?: string[]
  unsupportedClaims?: string[]
  contradictoryInstructions?: string[]
  verificationItems?: GroundTruthVerificationItem[]
  checks: RuleValidationCheck[]
  pythonLogSummary: string
  timestamp: string
  jsonSchemaReport?: JsonSchemaValidationReport // Step 46
  retryHistory?: GenAiFailureHandlingResult // Step 47
  adversarialAudit?: AdversarialAttackAudit // Step 50 & 51
}

// ==========================================
// STEPS 39 - 51 TYPE DEFINITIONS
// ==========================================

// Step 40: Follow-Up Communication Types
export type FollowUpCommunicationType =
  | 'Request for additional information'
  | 'Resolution confirmation'
  | 'Refund-status update'
  | 'Replacement-status update'
  | 'Escalation acknowledgement'
  | 'Closure confirmation'

// Step 41: Follow-Up Scheduling
export interface ScheduledFollowUp {
  id: string
  complaintId: string
  followUpType: FollowUpCommunicationType
  scheduledDate: string
  triggerCondition: string
  assignedTo: string
  status: 'Scheduled' | 'Due Today' | 'Completed' | 'Cancelled'
  notes?: string
  createdAt: string
}

// Step 42: Missing Information Detection
export interface MissingInformationAudit {
  orderNumberPresent: boolean
  transactionDatePresent: boolean
  productPresent: boolean
  problemDescriptionClear: boolean
  evidenceProvided: boolean
  missingItems: string[]
  isComplete: boolean
  recommendation: string
}

// Step 44: Structured Complaint Summary
export interface StructuredComplaintSummary {
  customerSnapshot: string
  coreIncident: string
  businessImpact: string
  operationalStatus: string
  nextImmediateAction: string
}

// Step 45: Agent Guidance Checklist
export interface AgentGuidanceChecklistItem {
  id: string
  instruction: string
  isMandatory: boolean
  category:
    | 'Verification'
    | 'Compliance'
    | 'Escalation'
    | 'Financial Check'
    | 'Account Verification'
    | 'Logistics'
    | 'Evidence Collection'
    | 'Supervisory Review'
  completed: boolean
  warning?: string
}

// Step 46: GenAI JSON Schema Validation
export interface SchemaFieldValidation {
  field: string
  expectedType: string
  actualType: string
  rule: string
  passed: boolean
  error?: string
}

export interface JsonSchemaValidationReport {
  isValid: boolean
  passedChecksCount: number
  totalChecksCount: number
  validationErrors: string[]
  checks: SchemaFieldValidation[]
  validatedAt: string
}

// Step 47: Invalid GenAI Response Handling & Retry Strategy
export interface RetryAttemptLog {
  attemptNumber: number
  strategy: string
  errorMessage: string
  timestamp: string
  status: 'Failed' | 'Recovered' | 'Routed to Manual Review'
}

export interface GenAiFailureHandlingResult {
  totalRetries: number
  maxRetriesAllowed: number
  finalDisposition: 'Auto-Recovered' | 'Routed to Human Manual Review Queue'
  attempts: RetryAttemptLog[]
  failureLogged: boolean
  manualReviewReason?: string
}

// Step 48: Prompt Template Management
export interface PromptTemplate {
  templateId: string
  name: string
  version: string
  category: 'Analysis' | 'Response Generation' | 'Clarification' | 'Follow-Up' | 'Summary'
  systemInstruction: string
  userPromptTemplate: string
  inputVariables: string[]
  approvedPolicyVersion: string
  lastModified: string
  author: string
  status: 'Active' | 'Draft' | 'Deprecated'
}

// Step 49: Prompt Version Logging & Metadata
export interface PromptExecutionAuditLog {
  promptVersion: string
  provider: GenAIProvider
  model: string
  analysisTimestamp: string
  policyVersion: string
  latencyMs: number
  tokenUsage: {
    prompt: number
    completion: number
    total: number
  }
}

// Step 50 & 51: Prompt Injection Protection & Adversarial Complaint Detection
export interface AdversarialAttackAudit {
  overallRisk: 'Clean' | 'Low Risk' | 'Suspicious' | 'High Risk' | 'Critical Attack Blocked'
  threatScore: number // 0 - 100%
  flags: {
    promptInjection: { detected: boolean; snippets: string[] }
    fakeAdministrativeInstructions: { detected: boolean; snippets: string[] }
    manipulativeLanguage: { detected: boolean; snippets: string[] }
    embeddedPolicyClaims: { detected: boolean; snippets: string[] }
    unauthorizedCompensationAttempts: { detected: boolean; snippets: string[] }
  }
  defensiveAction: string
  sanitizedInputSnippet: string
  quarantineRequired: boolean
}

// ==========================================
// STEPS 52 - 63 TYPE DEFINITIONS
// ==========================================

// Step 52: Duplicate Complaint Detection
export type DuplicateDetectionType = 'Exact duplicate' | 'Near-duplicate' | 'Repeated submission'

export interface DuplicateDetectionResult {
  isDuplicate: boolean
  matchType?: DuplicateDetectionType
  similarityScore: number // 0 - 100%
  originalTicketId?: string
  originalTicketTitle?: string
  matchReason: string
  autoMerged?: boolean
  detectedAt?: string
}

// Step 53: Customer Complaint History
export interface CustomerComplaintProfile {
  customerId: string
  customerName: string
  customerEmail: string
  customerType: CustomerType
  totalTicketsCount: number
  unresolvedCount: number
  historyItems: ComplaintHistoryItem[]
}

// Step 54: Repeat Complaint Detection
export interface RepeatComplaintAlert {
  isRepeatComplaint: boolean
  repeatCount: number
  priorUnresolvedTicketIds: string[]
  escalationPriorityElevated: boolean
  originalPriority?: PriorityLevel
  elevatedPriority?: PriorityLevel
  elevationReason?: string
}

// Step 55: Service Level Agreement (SLA) Configuration
export interface SlaConfiguration {
  priority: PriorityLevel
  firstResponseHours: number
  resolutionHours: number
  warningThresholdPercent: number // e.g. 75%
}

// Step 56: SLA Risk Detection & Tracking
export interface SlaStatusTracking {
  firstResponseDeadline: string
  resolutionDeadline: string
  firstResponseElapsedPercent: number
  resolutionElapsedPercent: number
  riskLevel: 'On Track' | 'Approaching Deadline' | 'Breached'
  minutesRemaining: number
  slaSummary: string
  isBreached: boolean
}

// Step 57: Manual Review Queue
export type ManualReviewReason =
  | 'GenAI and Python disagree significantly'
  | 'Policy support is missing'
  | 'Complaint is ambiguous'
  | 'Escalation is unclear'
  | 'Policy contradiction exists'
  | 'Sensitive complaint requires review'

export interface ManualReviewQueueEntry {
  isQueuedForManualReview: boolean
  reasons: ManualReviewReason[]
  queuedTimestamp: string
  assignedReviewer?: string
  status: 'Pending Review' | 'In Review' | 'Review Completed' | 'Override Dispatched'
  reviewerNotes: string[]
}

// Step 58 & 59: Reviewer Actions & Reviewer Override Audit Trail
export type ReviewerActionType =
  | 'Approve'
  | 'Reject'
  | 'Modify'
  | 'Reclassify'
  | 'Reassign'
  | 'Escalate'
  | 'Regenerate response'
  | 'Add comments'

export interface ReviewerAuditTrailItem {
  id: string
  action: ReviewerActionType
  reviewerName: string
  reviewerRole: string
  timestamp: string
  originalField: string
  originalValue: string
  decisionValue: string
  justification: string
  retainedRecommendationAudit: string // Immutable Step 59 record
}

// Step 61, 62, 63 & FR-ii: Role-Based Access Control (5 Roles)
export type DashboardPersonaView = 'admin' | 'manager' | 'reviewer' | 'agent' | 'customer'

// ==========================================
// 14 MANDATORY COMPLAINT PROFILES
// ==========================================
export type ComplaintProfileType =
  | 'Simple'
  | 'Multi-issue'
  | 'Incomplete'
  | 'Emotional'
  | 'Calm but critical'
  | 'High-priority'
  | 'Low-priority'
  | 'Repeated'
  | 'Contradictory'
  | 'Policy-exception'
  | 'Unsupported refund'
  | 'Security'
  | 'Privacy'
  | 'Safety'

// ==========================================
// HIDDEN EVALUATION DATASET & DYNAMIC INGESTION
// ==========================================
export interface HiddenEvaluationPack {
  id: string
  name: string
  version: string
  badge: string
  description: string
  unseenElements: string[]
  sampleComplaint: {
    title: string
    description: string
    customerType: CustomerType
    productOrService: string
    orderOrTransactionRef: string
    channel: ComplaintChannel
    unseenCategory?: string
    unseenSubcategory?: string
    requestedResolution: string
  }
  sampleDocument?: {
    documentId: string
    title: string
    category: string
    fileType: SupportedDocumentFormat
    fileSize: string
    version: string
    effectiveDate: string
    lifecycleStatus: 'Active policy' | 'Revised policy' | 'Outdated policy'
    contentSnippet: string
    chunks: Array<{
      chunkId: string
      sectionId: string
      heading: string
      content: string
      pageNumber: number
    }>
  }
  unseenRoutingRule?: {
    ruleId: string
    category: string
    responsibleDepartment: string
    escalationTrigger: string
  }
}

export interface DynamicEvaluationRunResult {
  runId: string
  timestamp: string
  packName: string
  complaintId: string
  unseenCategoryDetected?: string
  unseenSubcategoryDetected?: string
  newPolicyIngested?: string
  policyStatusEnforced: 'Active' | 'Revised' | 'Outdated (Blocked by Python)'
  routingDepartment: string
  multiDepartmentRouting?: string[]
  priority: PriorityLevel
  urgency: UrgencyLevel
  adversarialCheck: {
    passed: boolean
    attackType?: string
    threatScore: number
    actionTaken: string
  }
  pythonValidationStatus: 'Approved for Dispatch' | 'Requires Human Override' | 'Quarantined'
  agreementScore: number
  generatedResponseSnippet: string
  manualReviewTriggered: boolean
  manualReviewReasons: string[]
}

export interface DynamicDocumentIngestionInput {
  title: string
  category: string
  fileType: SupportedDocumentFormat
  version: string
  effectiveDate: string
  lifecycleStatus: 'Active policy' | 'Revised policy' | 'Outdated policy'
  fileContent: string
}


