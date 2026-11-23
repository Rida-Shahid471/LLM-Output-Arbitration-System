from src.disagreement_detector import detect_disagreements
from src.schemas import CriticReport, CriticType, Issue, Severity


def _report(kind: CriticType, score: int, category: str | None = None, severity: Severity = Severity.LOW) -> CriticReport:
    issues = []
    if category:
        issues = [Issue(category=category, description="A concrete issue.", evidence="quoted text", severity=severity, confidence=0.8)]
    return CriticReport(critic_type=kind, score=score, summary="Review complete.", issues=issues, overall_confidence=0.8)


def test_detects_score_and_issue_presence_disagreements() -> None:
    reports = [_report(CriticType.FACTUAL_ACCURACY, 1, "factual_error", Severity.HIGH),
               _report(CriticType.LOGICAL_CONSISTENCY, 5), _report(CriticType.COMPLETENESS, 4)]
    disagreements = detect_disagreements(reports)
    assert any(d.topic == "overall_score" for d in disagreements)
    assert any(d.topic == "factual_error" for d in disagreements)


def test_no_disagreement_when_reports_agree() -> None:
    reports = [_report(kind, 5) for kind in CriticType]
    assert detect_disagreements(reports) == []


def test_detects_different_evidence_for_same_category() -> None:
    factual = _report(CriticType.FACTUAL_ACCURACY, 3, "factual_error")
    logical = _report(CriticType.LOGICAL_CONSISTENCY, 3, "factual-error")
    factual.issues[0].evidence = "quoted claim A"
    logical.issues[0].evidence = "quoted claim B"
    disagreements = detect_disagreements([factual, logical])
    assert any(d.topic == "factual_error_evidence" for d in disagreements)


def test_detects_large_severity_gap_for_same_category() -> None:
    factual = _report(CriticType.FACTUAL_ACCURACY, 3, "factual_error", Severity.LOW)
    logical = _report(CriticType.LOGICAL_CONSISTENCY, 3, "factual-error", Severity.CRITICAL)

    disagreements = detect_disagreements([factual, logical])

    assert any(d.topic == "factual_error" and "different severity" in d.description for d in disagreements)
