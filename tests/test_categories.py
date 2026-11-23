from src.categories import CANONICAL_ISSUE_CATEGORIES, canonicalize_issue_category
from src.disagreement_detector import detect_disagreements
from src.schemas import CriticReport, CriticType, Issue, Severity


def _report(kind: CriticType, category: str) -> CriticReport:
    return CriticReport(
        critic_type=kind, score=4, summary="Reviewed.",
        issues=[Issue(category=category, description="Issue", evidence="quote", severity=Severity.MEDIUM, confidence=0.8)],
        overall_confidence=0.8,
    )


def test_category_aliases_normalize_synonyms_punctuation_and_known_spelling_variants() -> None:
    assert canonicalize_issue_category("Factual Error") == "factual_error"
    assert canonicalize_issue_category("incorrect-fact") == "factual_error"
    assert canonicalize_issue_category("Contradiciton") == "logical_contradiction"
    assert canonicalize_issue_category("incompletness") == "incomplete_answer"
    assert canonicalize_issue_category("missing requirement") == "incomplete_answer"


def test_known_synonyms_do_not_create_false_category_disagreement() -> None:
    reports = [
        _report(CriticType.FACTUAL_ACCURACY, "fact"),
        _report(CriticType.LOGICAL_CONSISTENCY, "incorrect fact"),
    ]
    assert reports[0].issues[0].category == "factual_error"
    assert reports[1].issues[0].category == "factual_error"
    assert detect_disagreements(reports) == []


def test_unknown_categories_are_explicit_and_not_collapsed_into_known_taxonomy() -> None:
    first = canonicalize_issue_category("Novel-Concern")
    second = canonicalize_issue_category("unsupported claim")
    assert first == "unknown:novel_concern"
    assert second == "unsupported_claim"
    assert first != second
    assert canonicalize_issue_category(first) == first
    assert CANONICAL_ISSUE_CATEGORIES == {
        "factual_error", "unsupported_claim", "logical_contradiction", "invalid_inference",
        "incomplete_answer", "format_violation", "calculation_error", "other",
    }
