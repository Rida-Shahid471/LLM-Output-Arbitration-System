import pytest

from src.errors import BatchPersistenceError
from src.schemas import (
    ArbitrationResult, ConfirmedIssue, CriticReport, CriticType, Disagreement,
    FinalVerdict, Issue, Severity, Verdict,
)
from src.storage import ArbitrationStore


def _result(arbitration_id: str, *, disagreement: bool, error: bool = False) -> ArbitrationResult:
    reports = [
        CriticReport(critic_type=CriticType.FACTUAL_ACCURACY, score=2, summary="Issue found.",
                     issues=[Issue(category="fact", description="Bad fact", evidence="Sydney", severity=Severity.HIGH, confidence=0.9)], overall_confidence=0.9),
        CriticReport(critic_type=CriticType.LOGICAL_CONSISTENCY, score=4, summary="Reviewed.", issues=[], overall_confidence=0.8),
        CriticReport(critic_type=CriticType.COMPLETENESS, score=4, summary="Reviewed.", issues=[], overall_confidence=0.8),
    ]
    disagreements = [Disagreement(
        topic="fact", critic_a=CriticType.FACTUAL_ACCURACY,
        critic_b=CriticType.LOGICAL_CONSISTENCY, description="Presence differs.",
        severity=Severity.HIGH, confidence=0.8,
    )] if disagreement else []
    errors = ["completeness: CriticResponseError: malformed output"] if error else []
    return ArbitrationResult(
        arbitration_id=arbitration_id, original_prompt="Q", candidate_output="Sydney",
        critic_reports=reports, disagreements=disagreements,
        final_verdict=FinalVerdict(
            verdict=Verdict.REVISE, overall_score=5, confidence=0.5,
            confirmed_issues=[ConfirmedIssue(issue=reports[0].issues[0], critic_type=CriticType.FACTUAL_ACCURACY)],
            summary="Review required.", unresolved_disagreements=disagreements,
        ), errors=errors,
        timings_ms={"factual_accuracy_ms": 10, "logical_consistency_ms": 20,
                    "completeness_ms": 30, "disagreement_detection_ms": 2,
                    "adjudication_ms": 3, "total": 40},
        provider="mock", created_at=f"2026-11-02T00:00:0{arbitration_id}+00:00",
    )


def test_analytics_uses_pairwise_agreement_and_tracks_failures(tmp_path) -> None:
    store = ArbitrationStore(str(tmp_path / "analytics.sqlite3"))
    store.save(_result("1", disagreement=True, error=True))
    store.save(_result("2", disagreement=False))

    analytics = store.analytics()

    assert analytics["total_arbitrations"] == 2
    assert analytics["comparable_critic_pairs"] == 6
    assert analytics["disagreeing_critic_pairs"] == 1
    assert analytics["agreement_rate"] == round(5 / 6, 3)
    assert analytics["disagreement_rate"] == round(1 / 6, 3)
    assert analytics["failures_by_type"] == {"CriticResponseError": 1}
    assert analytics["failures_by_critic"] == {"completeness": 1}
    assert analytics["final_scores"] == {"5": 2}
    assert analytics["average_critic_latency_ms"] == {
        "factual_accuracy": 10.0,
        "logical_consistency": 20.0,
        "completeness": 30.0,
    }
def test_save_many_rolls_back_all_records_when_second_insert_fails(tmp_path) -> None:
    store = ArbitrationStore(str(tmp_path / "atomic-batch.sqlite3"))
    with store._connection() as connection:
        connection.execute("""
            CREATE TRIGGER fail_second_batch_insert BEFORE INSERT ON arbitrations
            WHEN (SELECT COUNT(*) FROM arbitrations) >= 1
            BEGIN SELECT RAISE(ABORT, 'deliberate second insert failure'); END;
        """)

    with pytest.raises(BatchPersistenceError, match="no batch records were committed"):
        store.save_many([_result("1", disagreement=False), _result("2", disagreement=False)])

    assert store.list() == []


def test_failed_batch_preserves_preexisting_records(tmp_path) -> None:
    store = ArbitrationStore(str(tmp_path / "preserve-existing.sqlite3"))
    existing = _result("seed", disagreement=False)
    store.save(existing)
    with store._connection() as connection:
        connection.execute("""
            CREATE TRIGGER fail_second_new_insert BEFORE INSERT ON arbitrations
            WHEN (SELECT COUNT(*) FROM arbitrations) >= 2
            BEGIN SELECT RAISE(ABORT, 'deliberate second insert failure'); END;
        """)

    with pytest.raises(BatchPersistenceError):
        store.save_many([_result("new-1", disagreement=False), _result("new-2", disagreement=False)])

    assert store.list() == [existing]


def test_records_survive_store_reopen_and_remain_retrievable(tmp_path) -> None:
    database_path = str(tmp_path / "restart.sqlite3")
    original_store = ArbitrationStore(database_path)
    original = _result("persisted", disagreement=False)
    original_store.save(original)

    reopened_store = ArbitrationStore(database_path)

    assert reopened_store.get("persisted") == original
    assert reopened_store.list(limit=10, offset=0) == [original]
    assert reopened_store.analytics()["total_arbitrations"] == 1
