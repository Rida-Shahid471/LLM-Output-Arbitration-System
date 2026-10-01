from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class CriticType(str, Enum):
    """Supported specialist critic types."""

    FACTUAL_ACCURACY = "factual_accuracy"
    LOGICAL_CONSISTENCY = "logical_consistency"
    COMPLETENESS = "completeness"


class Severity(str, Enum):
    """Severity assigned to a detected issue."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Verdict(str, Enum):
    """Possible arbitration outcomes."""

    ACCEPT = "accept"
    REVISE = "revise"
    REJECT = "reject"


class Issue(BaseModel):
    """A single issue identified by a specialist critic."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    category: str = Field(
        min_length=1,
        description="Category of the identified issue.",
    )

    description: str = Field(
        min_length=1,
        description="Clear explanation of the issue.",
    )

    evidence: Optional[str] = Field(
        default=None,
        description="Relevant evidence from the candidate output.",
    )

    severity: Severity = Field(
        description="Severity of the identified issue.",
    )

    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Critic confidence in this issue.",
    )


class CriticReport(BaseModel):
    """Structured output produced by a specialist critic."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    critic_type: CriticType

    summary: str = Field(
        min_length=1,
        description="Overall assessment produced by the critic.",
    )

    issues: list[Issue] = Field(
        default_factory=list,
        description="Issues identified by the critic.",
    )

    overall_confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Overall confidence of the critic.",
    )


class Disagreement(BaseModel):
    """Represents a disagreement between specialist critics."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    topic: str = Field(
        min_length=1,
        description="Topic on which critics disagree.",
    )

    critic_a: CriticType

    critic_b: CriticType

    description: str = Field(
        min_length=1,
        description="Description of the disagreement.",
    )

    severity: Severity

    confidence: float = Field(
        ge=0.0,
        le=1.0,
    )


class FinalVerdict(BaseModel):
    """Final structured decision produced by the adjudication layer."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    verdict: Verdict

    rationale: str = Field(
        min_length=1,
        description="Explanation supporting the final verdict.",
    )

    confidence: float = Field(
        ge=0.0,
        le=1.0,
    )

    unresolved_disagreements: list[Disagreement] = Field(
        default_factory=list,
    )

    recommended_revision: Optional[str] = Field(
        default=None,
        description="Suggested revision when the answer requires changes.",
    )