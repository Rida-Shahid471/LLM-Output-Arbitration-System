from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.categories import canonicalize_issue_category


class CriticType(str, Enum):
    FACTUAL_ACCURACY = "factual_accuracy"
    LOGICAL_CONSISTENCY = "logical_consistency"
    COMPLETENESS = "completeness"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Verdict(str, Enum):
    ACCEPT = "accept"
    REVISE = "revise"
    REJECT = "reject"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Issue(StrictModel):
    category: str = Field(min_length=1)
    description: str = Field(min_length=1)
    evidence: str = Field(min_length=1, description="Exact quote from the candidate answer.")
    severity: Severity
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("category")
    @classmethod
    def canonical_category(cls, value: str) -> str:
        return canonicalize_issue_category(value)


class CriticReport(StrictModel):
    critic_type: CriticType
    score: int = Field(ge=1, le=5, description="Quality score, where 5 is best.")
    summary: str = Field(min_length=1)
    issues: list[Issue] = Field(default_factory=list)
    overall_confidence: float = Field(ge=0.0, le=1.0)
    model: Optional[str] = None
    provider: Optional[str] = None


class Disagreement(StrictModel):
    topic: str = Field(min_length=1)
    critic_a: CriticType
    critic_b: CriticType
    description: str = Field(min_length=1)
    severity: Severity
    confidence: float = Field(ge=0.0, le=1.0)


class DismissedFlag(StrictModel):
    issue: Issue
    critic_type: CriticType
    reason: str = Field(min_length=1)


class ConfirmedIssue(StrictModel):
    issue: Issue
    critic_type: CriticType


class FinalVerdict(StrictModel):
    verdict: Verdict
    overall_score: int = Field(ge=1, le=10)
    confidence: float = Field(ge=0.0, le=1.0)
    confirmed_issues: list[ConfirmedIssue] = Field(default_factory=list)
    dismissed_flags: list[DismissedFlag] = Field(default_factory=list)
    summary: str = Field(min_length=1)
    unresolved_disagreements: list[Disagreement] = Field(default_factory=list)
    rationale: Optional[str] = None
    recommended_revision: Optional[str] = None
    adjudicator_provider: Optional[str] = None
    adjudicator_model: Optional[str] = None


class ArbitrationRequest(StrictModel):
    original_prompt: str = Field(min_length=1, max_length=1_000_000)
    candidate_answer: str = Field(min_length=1, max_length=1_000_000)


class ArbitrationResult(StrictModel):
    arbitration_id: str
    original_prompt: str
    candidate_output: str
    critic_reports: list[CriticReport]
    disagreements: list[Disagreement]
    final_verdict: FinalVerdict
    errors: list[str] = Field(default_factory=list)
    timings_ms: dict[str, float] = Field(default_factory=dict)
    provider: str = "mock"
    created_at: str
    critic_prompt_version: str = "unknown"
    adjudicator_prompt_version: str = "unknown"
