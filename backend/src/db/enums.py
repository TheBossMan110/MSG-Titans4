"""
System-state enumerations.

Design rule (see documentation/DATABASE.md):
  * **System states** (statuses, outcomes, roles) live here as code enums and
    are enforced with CHECK constraints — they are coupled to code paths.
  * **Business taxonomy** (categories, departments, priorities, escalation
    levels, SLAs, rules) lives in *database tables* so evaluators can add a
    category or department at runtime (SRS 1.8 #5 and #14).
"""

from __future__ import annotations

from enum import StrEnum


def values(e: type[StrEnum]) -> list[str]:
    return [m.value for m in e]


class UserRole(StrEnum):
    CUSTOMER = "customer"
    AGENT = "agent"
    REVIEWER = "reviewer"
    MANAGER = "manager"
    ADMIN = "admin"
    EVALUATOR = "evaluator"


class ComplaintStatus(StrEnum):
    NEW = "NEW"
    ANALYZING = "ANALYZING"
    ANALYZED = "ANALYZED"
    VALIDATED = "VALIDATED"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    AWAITING_CUSTOMER = "AWAITING_CUSTOMER"
    ESCALATED = "ESCALATED"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"
    REOPENED = "REOPENED"
    FAILED = "FAILED"


class Channel(StrEnum):
    WEB = "WEB"
    EMAIL = "EMAIL"
    CHAT = "CHAT"
    PHONE = "PHONE"
    UPLOAD = "UPLOAD"
    IMPORT = "IMPORT"


class Sentiment(StrEnum):
    POSITIVE = "POSITIVE"
    NEUTRAL = "NEUTRAL"
    NEGATIVE = "NEGATIVE"
    STRONGLY_NEGATIVE = "STRONGLY_NEGATIVE"


class Urgency(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class CustomerTier(StrEnum):
    STANDARD = "STANDARD"
    PREMIUM = "PREMIUM"
    VIP = "VIP"
    BUSINESS = "BUSINESS"


class DocType(StrEnum):
    POLICY = "POLICY"
    SOP = "SOP"
    FAQ = "FAQ"
    ROUTING_RULES = "ROUTING_RULES"
    ESCALATION = "ESCALATION"
    SLA = "SLA"
    COMPLIANCE = "COMPLIANCE"
    HANDBOOK = "HANDBOOK"
    PROCESS = "PROCESS"
    OTHER = "OTHER"


class DocStatus(StrEnum):
    """SRS Step 7 — policy version control."""

    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    EXPIRED = "EXPIRED"
    METADATA_REVIEW = "METADATA_REVIEW"   # hidden doc without our metadata convention


class FileFormat(StrEnum):
    PDF = "PDF"
    DOCX = "DOCX"
    TXT = "TXT"
    MD = "MD"
    CSV = "CSV"


class ParseStatus(StrEnum):
    PENDING = "PENDING"
    PARSING = "PARSING"
    PARSED = "PARSED"
    FAILED = "FAILED"
    NO_TEXT_LAYER = "NO_TEXT_LAYER"


class PolicyApplicability(StrEnum):
    """SRS Step 26."""

    APPLICABLE = "APPLICABLE"
    CONDITIONALLY_APPLICABLE = "CONDITIONALLY_APPLICABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    OUTDATED = "OUTDATED"


class RuleType(StrEnum):
    ROUTING = "ROUTING"
    CLASSIFICATION = "CLASSIFICATION"
    URGENCY = "URGENCY"
    ESCALATION = "ESCALATION"
    RESOLUTION = "RESOLUTION"
    ELIGIBILITY = "ELIGIBILITY"
    SLA = "SLA"


class GenAIPipeline(StrEnum):
    INTELLIGENCE = "INTELLIGENCE"
    RESPONSE = "RESPONSE"
    CLARIFICATION = "CLARIFICATION"
    ESCALATION_NOTE = "ESCALATION_NOTE"


class GenAIRunStatus(StrEnum):
    """SRS Step 47 — invalid GenAI response handling."""

    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    SCHEMA_INVALID = "SCHEMA_INVALID"
    REPAIRED = "REPAIRED"
    API_ERROR = "API_ERROR"
    TIMEOUT = "TIMEOUT"
    RATE_LIMITED = "RATE_LIMITED"
    CACHED = "CACHED"
    FAILED = "FAILED"


class ComparisonStatus(StrEnum):
    MATCH = "MATCH"
    MISMATCH = "MISMATCH"
    GENAI_MISSING = "GENAI_MISSING"
    PYTHON_MISSING = "PYTHON_MISSING"
    UNSUPPORTED = "UNSUPPORTED"
    CORRECTED = "CORRECTED"


class Severity(StrEnum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    INFORMATIONAL = "INFORMATIONAL"


class Winner(StrEnum):
    GENAI = "GENAI"
    PYTHON = "PYTHON"
    AGREED = "AGREED"
    NONE = "NONE"


class VerificationOutcome(StrEnum):
    """SRS Step 57 + FR xliii."""

    VERIFIED = "VERIFIED"
    VERIFIED_WITH_WARNING = "VERIFIED_WITH_WARNING"
    CORRECTED_BY_RULES = "CORRECTED_BY_RULES"
    MANUAL_REVIEW_REQUIRED = "MANUAL_REVIEW_REQUIRED"
    BLOCKED = "BLOCKED"
    INCOMPLETE = "INCOMPLETE"


class ResponseTone(StrEnum):
    """SRS Step 33."""

    PROFESSIONAL = "PROFESSIONAL"
    EMPATHETIC = "EMPATHETIC"
    CONCISE = "CONCISE"
    FORMAL = "FORMAL"


class GuardStatus(StrEnum):
    PENDING = "PENDING"
    CLEAN = "CLEAN"
    FLAGGED = "FLAGGED"
    BLOCKED = "BLOCKED"
    REGENERATED = "REGENERATED"


class ResponseFlagType(StrEnum):
    """SRS Steps 34, 35."""

    UNSUPPORTED_PROMISE = "UNSUPPORTED_PROMISE"
    HALLUCINATION = "HALLUCINATION"
    INVALID_CITATION = "INVALID_CITATION"
    OUTDATED_POLICY = "OUTDATED_POLICY"
    PROHIBITED_ACTION = "PROHIBITED_ACTION"
    MISSING_ACTION = "MISSING_ACTION"


class ReviewStatus(StrEnum):
    OPEN = "OPEN"
    IN_REVIEW = "IN_REVIEW"
    RESOLVED = "RESOLVED"
    DISMISSED = "DISMISSED"


class ReviewActionType(StrEnum):
    """SRS Step 58."""

    APPROVE = "APPROVE"
    REJECT = "REJECT"
    MODIFY = "MODIFY"
    RECLASSIFY = "RECLASSIFY"
    REASSIGN = "REASSIGN"
    ESCALATE = "ESCALATE"
    REGENERATE = "REGENERATE"
    COMMENT = "COMMENT"
    OVERRIDE = "OVERRIDE"


class LinkType(StrEnum):
    EXACT_DUPLICATE = "EXACT_DUPLICATE"
    NEAR_DUPLICATE = "NEAR_DUPLICATE"
    REPEAT = "REPEAT"
    RELATED = "RELATED"
    FOLLOW_UP = "FOLLOW_UP"


class EntityExtractor(StrEnum):
    PYTHON = "PYTHON"
    GENAI = "GENAI"


class InjectionAction(StrEnum):
    FLAGGED = "FLAGGED"
    NEUTRALIZED = "NEUTRALIZED"
    BLOCKED = "BLOCKED"
    REVIEW_ROUTED = "REVIEW_ROUTED"


class EscalationTrigger(StrEnum):
    PYTHON_RULE = "PYTHON_RULE"
    GENAI = "GENAI"
    REVIEWER = "REVIEWER"
    SLA = "SLA"


class JobStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ExportFormat(StrEnum):
    CSV = "CSV"
    PDF = "PDF"
    XLSX = "XLSX"


# ══════════════════════════════════════════════════════════════════
# Complaint-intelligence detail enums
# Added after a clause-by-clause SRS coverage audit (see
# documentation/REQUIREMENTS_COVERAGE.md) closed nine schema gaps.
# ══════════════════════════════════════════════════════════════════


class PolicyRefSource(StrEnum):
    """Who proposed this policy reference."""

    GENAI = "GENAI"          # cited by the model
    PYTHON = "PYTHON"        # required by a matched rule
    RETRIEVAL = "RETRIEVAL"  # surfaced by hybrid retrieval


class ResolutionStepSource(StrEnum):
    GENAI = "GENAI"                  # generated by Pipeline 1
    RULE_REQUIRED = "RULE_REQUIRED"  # mandated by a matched rule (Pipeline 2)


class ResolutionStepStatus(StrEnum):
    """SRS Step 28 — Python must verify mandatory steps and detect prohibited ones."""

    SUPPORTED = "SUPPORTED"      # generated and permitted by the rules
    REQUIRED_MET = "REQUIRED_MET"  # a mandatory step that the model did include
    MISSING = "MISSING"          # mandatory step the model omitted
    UNSUPPORTED = "UNSUPPORTED"  # generated but not traceable to policy or rule
    PROHIBITED = "PROHIBITED"    # generated but explicitly forbidden
    DUPLICATE = "DUPLICATE"


class EligibilityType(StrEnum):
    """SRS Steps 29-31."""

    REFUND = "REFUND"
    REPLACEMENT = "REPLACEMENT"
    COMPENSATION = "COMPENSATION"
    REPAIR = "REPAIR"
    POLICY_EXCEPTION = "POLICY_EXCEPTION"


class EligibilityOutcome(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    CONDITIONAL = "CONDITIONAL"
    REQUIRES_VERIFICATION = "REQUIRES_VERIFICATION"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class GuidanceSource(StrEnum):
    GENAI = "GENAI"
    RULE = "RULE"


class GuidanceKind(StrEnum):
    """SRS Step 45 — internal agent guidance."""

    ACTION = "ACTION"            # "Verify account", "Check transaction"
    CAUTION = "CAUTION"          # "Do not promise refund before verification"
    VERIFICATION = "VERIFICATION"
    ESCALATION = "ESCALATION"
    INFORMATION = "INFORMATION"


class ValidationIssueCode(StrEnum):
    """
    SRS Step 4 (document validation) and Step 10 (complaint validation).

    Every rejected or flagged intake records a row so the behaviour is
    demonstrable rather than merely asserted.
    """

    # complaints - SRS Step 10
    EMPTY_COMPLAINT = "EMPTY_COMPLAINT"
    TOO_SHORT = "TOO_SHORT"
    TOO_LONG = "TOO_LONG"
    DUPLICATE_COMPLAINT = "DUPLICATE_COMPLAINT"
    INVALID_REFERENCE_ID = "INVALID_REFERENCE_ID"
    MISSING_MANDATORY_FIELD = "MISSING_MANDATORY_FIELD"
    UNSUPPORTED_ATTACHMENT = "UNSUPPORTED_ATTACHMENT"
    SUSPECTED_INJECTION = "SUSPECTED_INJECTION"
    # documents - SRS Step 4
    UNSUPPORTED_FILE_TYPE = "UNSUPPORTED_FILE_TYPE"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    EMPTY_FILE = "EMPTY_FILE"
    DUPLICATE_DOCUMENT = "DUPLICATE_DOCUMENT"
    MISSING_DOCUMENT_ID = "MISSING_DOCUMENT_ID"
    MISSING_VERSION = "MISSING_VERSION"
    MISSING_EFFECTIVE_DATE = "MISSING_EFFECTIVE_DATE"
    EXPIRED_DOCUMENT = "EXPIRED_DOCUMENT"
    MISSING_CATEGORY = "MISSING_CATEGORY"
    NO_TEXT_LAYER = "NO_TEXT_LAYER"
    PARSE_FAILED = "PARSE_FAILED"
    METADATA_INCOMPLETE = "METADATA_INCOMPLETE"


class IssueOutcome(StrEnum):
    REJECTED = "REJECTED"      # intake refused
    ACCEPTED_WITH_WARNING = "ACCEPTED_WITH_WARNING"
    ROUTED_TO_REVIEW = "ROUTED_TO_REVIEW"


class TrendDirection(StrEnum):
    UP = "UP"
    DOWN = "DOWN"
    FLAT = "FLAT"
