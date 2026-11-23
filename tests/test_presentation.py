from src.presentation import disagreement_topics_by_critic, render_answer_with_markers


def test_disagreement_topics_are_highlighted_for_both_critics() -> None:
    topics = disagreement_topics_by_critic([
        {"critic_a": "factual_accuracy", "critic_b": "logical_consistency", "topic": "fact_presence"},
        {"critic_a": "factual_accuracy", "critic_b": "completeness", "topic": "evidence"},
    ])

    assert topics == {
        "factual_accuracy": ["evidence", "fact_presence"],
        "logical_consistency": ["fact_presence"],
        "completeness": ["evidence"],
    }


def test_evidence_markers_highlight_confirmed_low_confidence_and_validated_text_safely() -> None:
    candidate = "Bad claim. Maybe claim. Verified claim. <script>alert(1)</script>"
    reports = [{
        "critic_type": "factual_accuracy",
        "issues": [
            {"category": "fact", "evidence": "Bad claim.", "confidence": 0.95},
            {"category": "logic", "evidence": "Maybe claim.", "confidence": 0.4},
            {"category": "completeness", "evidence": "Verified claim.", "confidence": 0.9},
        ],
    }]
    verdict = {"confirmed_issues": [{"critic_type": "factual_accuracy", "issue": {"category": "fact", "evidence": "Bad claim."}}]}

    rendered = render_answer_with_markers(candidate, reports, verdict)

    assert 'class="arb-confirmed"' in rendered
    assert 'class="arb-low-confidence"' in rendered
    assert 'class="arb-validated"' in rendered
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in rendered
    assert "<script>" not in rendered
