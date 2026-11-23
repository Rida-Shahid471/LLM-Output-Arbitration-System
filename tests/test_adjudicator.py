import json
import pytest

from src.adjudicator import adjudicate
from src.errors import LLMNonRetryableProviderError
from src.input_parser import parse_input
from src.llm_client import MockLLMClient
from src.schemas import CriticReport, CriticType, Disagreement, Issue, Severity


def test_adjudicator_retries_then_returns_conservative_fallback() -> None:
    calls = 0

    def malformed(prompt: str, system_prompt: str | None) -> str:
        nonlocal calls
        calls += 1
        return "malformed"

    issue = Issue(category="factual", description="Incorrect claim", evidence="Sydney", severity=Severity.HIGH, confidence=0.9)
    report = CriticReport(critic_type=CriticType.FACTUAL_ACCURACY, score=2, summary="Found a fact issue.", issues=[issue], overall_confidence=0.9)
    verdict = adjudicate(
        llm_client=MockLLMClient(response=malformed), arbitration_input=parse_input("Capital of Australia?", "Sydney"),
        reports=[report], disagreements=[], max_retries=1,
    )

    assert calls == 2
    assert verdict.confirmed_issues[0].issue.evidence == "Sydney"
    assert verdict.confidence <= 0.35
    assert "fallback" in verdict.summary.lower()


def test_adjudicator_does_not_retry_permanent_provider_rejections() -> None:
    calls = 0

    def rejected(prompt: str, system_prompt: str | None) -> str:
        nonlocal calls
        calls += 1
        raise LLMNonRetryableProviderError("OpenAI request was rejected (AuthenticationError).")

    verdict = adjudicate(
        llm_client=MockLLMClient(response=rejected), arbitration_input=parse_input("Q", "A"),
        reports=[], disagreements=[], max_retries=3,
    )

    assert calls == 1
    assert "fallback" in verdict.summary.lower()
    assert "offline-test-key" not in verdict.rationale


def test_adjudicator_rejects_unreported_evidence_and_falls_back() -> None:
    issue = Issue(category="factual", description="Incorrect claim", evidence="Sydney", severity=Severity.HIGH, confidence=0.9)
    report = CriticReport(critic_type=CriticType.FACTUAL_ACCURACY, score=2, summary="Found a fact issue.", issues=[issue], overall_confidence=0.9)
    bad_result = json.dumps({
        "verdict": "reject", "overall_score": 1, "confidence": 1.0,
        "confirmed_issues": [{"critic_type": "factual_accuracy", "issue": {
            "category": "factual", "description": "Invented", "evidence": "invented quote", "severity": "high", "confidence": 1.0,
        }}],
        "dismissed_flags": [], "summary": "Bad evidence.", "unresolved_disagreements": [],
    })

    verdict = adjudicate(
        llm_client=MockLLMClient(response=bad_result), arbitration_input=parse_input("Q", "Sydney"),
        reports=[report], disagreements=[], max_retries=0,
    )

    assert verdict.confirmed_issues[0].issue.evidence == "Sydney"
    assert "fallback" in verdict.summary.lower()


def _disagreement() -> Disagreement:
    return Disagreement(
        topic="factual_error", critic_a=CriticType.FACTUAL_ACCURACY,
        critic_b=CriticType.LOGICAL_CONSISTENCY, description="Only one critic reported the issue.",
        severity=Severity.MEDIUM, confidence=0.7,
    )


def _verdict_json(unresolved: list[dict]) -> str:
    return json.dumps({
        "verdict": "revise", "overall_score": 6, "confidence": 0.7,
        "confirmed_issues": [], "dismissed_flags": [], "summary": "Reviewed.",
        "unresolved_disagreements": unresolved,
    })


def test_adjudicator_may_leave_an_exact_input_disagreement_unresolved() -> None:
    disagreement = _disagreement()
    client = MockLLMClient(response=_verdict_json([disagreement.model_dump(mode="json")]), model="actual-mock-id")
    verdict = adjudicate(
        llm_client=client,
        arbitration_input=parse_input("Q", "A"), reports=[], disagreements=[disagreement], max_retries=0,
    )
    assert verdict.unresolved_disagreements == [disagreement]
    assert verdict.rationale is None
    assert verdict.adjudicator_provider == "mock"
    assert verdict.adjudicator_model == "actual-mock-id"


def test_adjudicator_may_omit_a_disagreement_it_resolved() -> None:
    verdict = adjudicate(
        llm_client=MockLLMClient(response=_verdict_json([])),
        arbitration_input=parse_input("Q", "A"), reports=[], disagreements=[_disagreement()], max_retries=0,
    )
    assert verdict.unresolved_disagreements == []
    assert verdict.rationale is None


@pytest.mark.parametrize("kind", ["invented", "duplicate", "mismatched"])
def test_adjudicator_rejects_invalid_unresolved_disagreements(kind: str) -> None:
    disagreement = _disagreement().model_dump(mode="json")
    if kind == "invented":
        disagreement["topic"] = "unsupported invented topic"
    elif kind == "mismatched":
        disagreement["severity"] = "critical"
    unresolved = [disagreement, disagreement] if kind == "duplicate" else [disagreement]
    verdict = adjudicate(
        llm_client=MockLLMClient(response=_verdict_json(unresolved)),
        arbitration_input=parse_input("Q", "A"), reports=[], disagreements=[_disagreement()], max_retries=0,
    )
    assert "fallback" in verdict.summary.lower()
    assert verdict.unresolved_disagreements == [_disagreement()]
