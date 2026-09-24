"""
All ORM models, re-exported.

Importing this package registers every table on ``Base.metadata`` — which is
what Alembic autogenerate and the test fixtures rely on.  Import order matters
only for readability; SQLAlchemy resolves relationships lazily by name.
"""

from src.db.base import Base
from src.db.models.complaints import (
    Complaint,
    ComplaintAttachment,
    ComplaintEntity,
    ComplaintLink,
    ComplaintStatusHistory,
    Customer,
)
from src.db.models.identity import AuditLog, RefreshToken, User
from src.db.models.intelligence import (
    AgentGuidance,
    ClarificationQuestion,
    ComplaintPolicyRef,
    EligibilityDecision,
    ResolutionStep,
)
from src.db.models.knowledge import Chunk, Document, DocumentSection, DocumentVersion
from src.db.models.ops import (
    BenchmarkResult,
    BenchmarkRun,
    ImpactAnalysis,
    ImpactItem,
    InjectionEvent,
    Job,
    ReportExport,
    TrendSnapshot,
)
from src.db.models.pipelines import GenAIRun, LLMCache, PromptVersion, RuleHit, ValidationRun
from src.db.models.rules import Rule
from src.db.models.signals import InjectionPattern, LexiconTerm, PromisePattern
from src.db.models.taxonomy import (
    AppConfig,
    Category,
    Department,
    EscalationLevel,
    PriorityLevel,
    SLAPolicy,
    Subcategory,
)
from src.db.models.validation_issues import (
    ComplaintValidationIssue,
    DocumentValidationIssue,
)
from src.db.models.verification import Comparison, VerificationDecision
from src.db.models.workflow import (
    Escalation,
    FollowUp,
    Response,
    ResponseFlag,
    ReviewAction,
    ReviewQueueItem,
    SLAEvent,
)

__all__ = [
    "Base",
    # identity
    "User",
    "RefreshToken",
    "AuditLog",
    # taxonomy / config
    "Department",
    "Category",
    "Subcategory",
    "PriorityLevel",
    "EscalationLevel",
    "SLAPolicy",
    "AppConfig",
    # deterministic signal config
    "LexiconTerm",
    "InjectionPattern",
    "PromisePattern",
    # knowledge base
    "Document",
    "DocumentVersion",
    "DocumentSection",
    "Chunk",
    # rule matrix
    "Rule",
    # complaints
    "Customer",
    "Complaint",
    "ComplaintEntity",
    "ComplaintLink",
    "ComplaintStatusHistory",
    "ComplaintAttachment",
    # complaint intelligence detail
    "ComplaintPolicyRef",
    "ResolutionStep",
    "EligibilityDecision",
    "ClarificationQuestion",
    "AgentGuidance",
    # intake validation findings
    "ComplaintValidationIssue",
    "DocumentValidationIssue",
    # pipelines
    "PromptVersion",
    "LLMCache",
    "GenAIRun",
    "ValidationRun",
    "RuleHit",
    # verification
    "Comparison",
    "VerificationDecision",
    # workflow
    "Response",
    "ResponseFlag",
    "Escalation",
    "FollowUp",
    "ReviewQueueItem",
    "ReviewAction",
    "SLAEvent",
    # ops
    "InjectionEvent",
    "Job",
    "BenchmarkRun",
    "BenchmarkResult",
    "ImpactAnalysis",
    "ImpactItem",
    "ReportExport",
    "TrendSnapshot",
]
