import pytest

from pydantic import ValidationError

from src.schemas import (
    CriticReport,
    CriticType,
    Issue,
    Severity,
)


def test_issue_accepts_valid_data() -> None:
    issue = Issue(
        category="factual_error",
        description="The answer contains an incorrect claim.",
        evidence="Claim X conflicts with the provided information.",
        severity=Severity.HIGH,
        confidence=0.95,
    )

    assert issue.severity == Severity.HIGH
    assert issue.confidence == 0.95


def test_issue_rejects_invalid_confidence() -> None:
    with pytest.raises(ValidationError):
        Issue(
            category="factual_error",
            description="Invalid confidence.",
            severity=Severity.HIGH,
            confidence=1.5,
        )


def test_critic_report_accepts_empty_issue_list() -> None:
    report = CriticReport(
        critic_type=CriticType.COMPLETENESS,
        summary="The answer addresses the requested information.",
        overall_confidence=0.90,
    )

    assert report.issues == []


def test_critic_report_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        CriticReport(
            critic_type=CriticType.FACTUAL_ACCURACY,
            summary="Test report.",
            overall_confidence=0.90,
            unexpected_field="invalid",
        )