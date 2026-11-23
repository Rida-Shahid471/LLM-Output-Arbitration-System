import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.evaluation import evaluate_dataset, load_evaluation_dataset
from src.llm_client import LLMResponse
from src.schemas import CriticReport, CriticType, Issue, Severity, Verdict


def test_versioned_dataset_has_unique_ids_and_all_required_cases() -> None:
    path = Path(__file__).parent / "evaluation_dataset.json"
    cases = load_evaluation_dataset(path)
    dataset = json.loads(path.read_text(encoding="utf-8"))
    labels = {label for case in cases for label in case["reference"]["labels"]}

    assert dataset["version"] == "1.2.0"
    assert len(cases) == 21
    assert len({case["id"] for case in cases}) == 21
    assert {"factual_error", "logical_contradiction", "incomplete_answer"} <= labels
    assert "calculation_error" in labels
    assert "format_violation" in labels
    assert any(case["reference"]["ambiguous"] for case in cases)
    assert not any(case.get("review_required") for case in cases)
    assert next(case for case in cases if case["id"] == "complete_001")["prompt"].endswith("RYB) model.")
    assert next(case for case in cases if case["id"] == "logic_003")["reference"]["labels"] == ["calculation_error"]
    assert next(case for case in cases if case["id"] == "format_002")["reference"]["labels"] == ["incomplete_answer", "format_violation"]


def test_dataset_loader_rejects_duplicate_ids_and_bad_labels(tmp_path) -> None:
    path = tmp_path / "bad.json"
    case = {"id": "duplicate", "prompt": "Q", "candidate_answer": "A",
            "reference": {"has_issue": False, "expected_verdict": "accept", "ambiguous": False, "labels": []}}
    path.write_text(json.dumps({"version": "x", "cases": [case, case]}), encoding="utf-8")

    with pytest.raises(ValueError, match="Duplicate"):
        load_evaluation_dataset(path)


@pytest.mark.parametrize("reference,extra,match", [
    ({"has_issue": True, "expected_verdict": "revise", "ambiguous": False, "labels": ["invented_label"]}, {}, "unknown issue labels"),
    ({"has_issue": True, "expected_verdict": "revise", "ambiguous": False, "labels": []}, {}, "inconsistent has_issue and labels"),
    ({"has_issue": False, "expected_verdict": "revise", "ambiguous": False, "labels": []}, {}, "inconsistent has_issue and expected_verdict"),
    ({"has_issue": True, "expected_verdict": "revise", "ambiguous": True, "labels": ["factual_error"]}, {}, "Ambiguous evaluation case"),
    ({"has_issue": False, "expected_verdict": "accept", "ambiguous": False, "labels": []}, {"review_required": True}, "review_reason"),
])
def test_dataset_loader_rejects_inconsistent_reference_schema(tmp_path, reference, extra, match) -> None:
    path = tmp_path / "invalid-reference.json"
    case = {"id": "case", "prompt": "Q", "candidate_answer": "A", "reference": reference, **extra}
    path.write_text(json.dumps({"version": "test", "cases": [case]}), encoding="utf-8")
    with pytest.raises(ValueError, match=match):
        load_evaluation_dataset(path)


def test_evaluator_skips_ambiguous_cases_and_reports_case_level_metrics() -> None:
    class FakeEngine:
        def arbitrate(self, prompt: str, candidate_answer: str):
            return SimpleNamespace(
                critic_reports=[SimpleNamespace(issues=[]) for _ in range(3)],
                errors=[],
                final_verdict=SimpleNamespace(verdict=Verdict.ACCEPT, confidence=0.75),
            )

    dataset = [
        {"id": "issue", "prompt": "Q", "candidate_answer": "A", "reference": {"has_issue": True, "expected_verdict": "revise", "ambiguous": False, "labels": ["x"]}},
        {"id": "clean", "prompt": "Q", "candidate_answer": "A", "reference": {"has_issue": False, "expected_verdict": "accept", "ambiguous": False, "labels": []}},
        {"id": "ambiguous", "prompt": "Q", "candidate_answer": "A", "reference": {"has_issue": False, "expected_verdict": "accept", "ambiguous": True, "labels": []}},
        {"id": "review", "prompt": "Q", "candidate_answer": "A", "reference": {"has_issue": False, "expected_verdict": "accept", "ambiguous": False, "labels": []}, "review_required": True, "review_reason": "Needs human label review."},
    ]

    report = evaluate_dataset(FakeEngine(), dataset, "test")

    assert report["dataset_version"] == "test"
    assert report["generated_at"].endswith("+00:00")
    assert report["critic_prompt_version"] == "critic-prompts-v3"
    assert report["adjudicator_prompt_version"] == "adjudicator-prompt-v3"
    assert report["provider"] == "unknown"
    assert report["critic_models"] == {}
    assert report["evaluated_cases"] == 2
    assert report["ambiguous_cases_skipped"] == 1
    assert report["human_review_cases_skipped"] == 1
    assert report["issue_detection_precision"] is None
    assert report["issue_detection_precision_status"] == "undefined_no_positive_predictions"
    assert report["metric_denominators"]["issue_detection_precision"] == {"count": 0, "predicted_positive_cases": 0}
    assert report["issue_detection_recall"] == 0.0
    assert report["clean_answer_false_positive_rate"] == 0.0
    assert report["adjudication_agreement"] == 0.5
    assert report["average_confidence"] == 0.75
    assert report["verdict_matches"] == 1
    assert report["cases_with_critic_failures"] == 0
    assert report["total_critic_failures"] == 0
    assert report["cases_excluded_due_to_critic_failures"] == 0
    assert report["verdict_evaluated_cases"] == 2


def test_ambiguous_placeholder_is_excluded_from_every_scored_metric() -> None:
    class MetricEngine:
        def __init__(self):
            self.prompts = []

        def arbitrate(self, prompt: str, candidate_answer: str):
            self.prompts.append(prompt)
            has_issue = prompt == "issue"
            return SimpleNamespace(
                critic_reports=[SimpleNamespace(issues=["factual_error"] if has_issue else []) for _ in range(3)],
                errors=[],
                final_verdict=SimpleNamespace(
                    verdict=Verdict.REVISE if has_issue else Verdict.ACCEPT,
                    confidence=0.8 if has_issue else 0.9,
                ),
            )

    engine = MetricEngine()
    dataset = [
        {"id": "issue", "prompt": "issue", "candidate_answer": "A",
         "reference": {"has_issue": True, "expected_verdict": "revise", "ambiguous": False, "labels": ["factual_error"]}},
        {"id": "clean", "prompt": "clean", "candidate_answer": "A",
         "reference": {"has_issue": False, "expected_verdict": "accept", "ambiguous": False, "labels": []}},
        # This accept value is only the schema-required neutral placeholder, not a scored label.
        {"id": "ambiguous", "prompt": "ambiguous", "candidate_answer": "A",
         "reference": {"has_issue": False, "expected_verdict": "accept", "ambiguous": True, "labels": []}},
    ]

    report = evaluate_dataset(engine, dataset, "test")

    assert engine.prompts == ["issue", "clean"]
    assert report["dataset_cases"] == 3
    assert report["evaluated_cases"] == 2
    assert report["ambiguous_cases_skipped"] == 1
    assert report["confusion"] == {"true_positive": 1, "false_positive": 0, "false_negative": 0, "true_negative": 1}
    assert report["issue_detection_precision"] == 1.0
    assert report["issue_detection_recall"] == 1.0
    assert report["clean_answer_false_positive_rate"] == 0.0
    assert report["adjudication_agreement"] == 1.0
    assert report["verdict_evaluated_cases"] == 2
    assert report["average_confidence"] == 0.85
    assert report["metric_denominators"] == {
        "issue_detection_precision": {"count": 1, "predicted_positive_cases": 1},
        "issue_detection_recall": {"count": 1, "actual_positive_cases": 1},
        "clean_answer_false_positive_rate": {"count": 1, "clean_cases": 1},
        "adjudication_agreement": {"count": 2, "verdict_matches": 2},
    }
    ambiguous_result = next(result for result in report["case_results"] if result["id"] == "ambiguous")
    assert ambiguous_result == {"id": "ambiguous", "evaluation_status": "skipped_ambiguous"}


def test_evaluator_excludes_failed_critic_runs_from_quality_denominators() -> None:
    class FailedEngine:
        def arbitrate(self, prompt: str, candidate_answer: str):
            return SimpleNamespace(
                critic_reports=[], errors=["factual_accuracy: LLMTimeoutError: timed out"],
                final_verdict=SimpleNamespace(
                    verdict=Verdict.REJECT, confidence=0.1, rationale="Fallback used: all critics failed.",
                ),
            )

    dataset = [{"id": "failed", "prompt": "Q", "candidate_answer": "A",
                "reference": {"has_issue": True, "expected_verdict": "reject", "ambiguous": False, "labels": ["fact"]}}]

    report = evaluate_dataset(FailedEngine(), dataset)

    assert report["evaluated_cases"] == 0
    assert report["cases_excluded_due_to_critic_failures"] == 1
    assert report["critic_failures_by_type"] == {"LLMTimeoutError": 1}
    assert report["ambiguous_cases_skipped"] == 0
    assert report["confusion"] == {"true_positive": 0, "false_positive": 0, "false_negative": 0, "true_negative": 0}
    assert report["adjudication_agreement"] is None
    assert report["adjudication_agreement_status"] == "undefined_no_verdicts_scored"
    assert report["case_results"][0]["predicted_issue"] is None
    assert report["case_results"][0]["critic_failure_types"] == ["LLMTimeoutError"]


def test_evaluation_report_includes_per_case_outputs_timing_metrics_and_provider_usage() -> None:
    issue = Issue(category="factual_error", description="A wrong claim.", evidence="wrong", severity=Severity.HIGH, confidence=0.9)

    class UsageClient:
        provider_name = "ollama"
        model = "qwen2.5:1.5b"
        supports_json_schema = False

        def generate(self, *, prompt: str, system_prompt: str | None = None):
            return LLMResponse(content="ok", model=self.model, provider=self.provider_name,
                               prompt_tokens=3, completion_tokens=2)

    class UsageEngine:
        def __init__(self):
            self.provider = "ollama"
            self.llm_client = UsageClient()

        def arbitrate(self, prompt: str, candidate_answer: str):
            self.llm_client.generate(prompt=prompt, system_prompt="offline")
            has_issue = prompt == "issue"
            report = CriticReport(
                critic_type=CriticType.FACTUAL_ACCURACY, score=2 if has_issue else 5,
                summary="Fixture report.", issues=[issue] if has_issue else [], overall_confidence=0.8,
                model="qwen2.5:1.5b", provider="ollama",
            )
            return SimpleNamespace(
                critic_reports=[report, report.model_copy(update={"critic_type": CriticType.LOGICAL_CONSISTENCY}),
                                report.model_copy(update={"critic_type": CriticType.COMPLETENESS})],
                disagreements=[], errors=[],
                final_verdict=SimpleNamespace(
                    verdict=Verdict.REVISE if has_issue else Verdict.ACCEPT,
                    confidence=0.8,
                ),
            )

    dataset = [
        {"id": "issue", "prompt": "issue", "candidate_answer": "wrong",
         "reference": {"has_issue": True, "expected_verdict": "revise", "ambiguous": False, "labels": ["factual_error"]}},
        {"id": "clean", "prompt": "clean", "candidate_answer": "fine",
         "reference": {"has_issue": False, "expected_verdict": "accept", "ambiguous": False, "labels": []}},
    ]

    report = evaluate_dataset(UsageEngine(), dataset, "telemetry-test")

    assert report["issue_detection_f1"] == 1.0
    assert report["evaluation_coverage"] == 1.0
    assert report["error_rate"] == 0.0
    assert report["total_execution_seconds"] >= 0
    assert report["average_case_execution_seconds"] >= 0
    assert report["issue_category_counts"] == {"factual_error": 3}
    assert report["provider_request_totals"] == {
        "requests": 2, "successful_requests": 2, "failed_requests": 0,
        "status": "complete", "prompt_tokens": 6, "completion_tokens": 4, "total_tokens": 10,
    }
    first = report["case_results"][0]
    assert len(first["critic_reports"]) == 3
    assert first["adjudicator_output"]["verdict"] == "revise"
    assert first["issue_categories"] == ["factual_error"]
    assert first["token_usage"]["total_tokens"] == 5


def test_evaluator_tracks_captured_critic_clients_and_adjudicator_calls() -> None:
    from src.workflow import ArbitrationEngine

    class CountedClient:
        provider_name = "ollama"
        model = "offline-eval-model"
        supports_json_schema = False

        def __init__(self):
            self.calls = 0

        def generate(self, *, prompt: str, system_prompt: str | None = None):
            self.calls += 1
            if system_prompt and "evidence-based adjudicator" in system_prompt:
                confirmed = [{
                    "critic_type": critic,
                    "issue": {
                        "category": "factual_error", "description": "The capital claim is wrong.",
                        "evidence": "Sydney.", "severity": "high", "confidence": 0.9,
                    },
                } for critic in ("factual_accuracy", "logical_consistency", "completeness")]
                content = json.dumps({
                    "verdict": "revise", "overall_score": 3, "confidence": 0.9,
                    "confirmed_issues": confirmed, "dismissed_flags": [], "summary": "Issues confirmed.",
                    "unresolved_disagreements": [], "rationale": "The answer gives the wrong capital.",
                    "recommended_revision": "Canberra.",
                })
            else:
                lower_prompt = prompt.casefold()
                critic = next(kind for kind in ("factual_accuracy", "logical_consistency", "completeness")
                              if f"evaluate the candidate answer for {kind.replace('_', ' ')}" in lower_prompt)
                issue = {
                    "category": "factual_error", "description": "The capital claim is wrong.",
                    "evidence": "Sydney.", "severity": "high", "confidence": 0.9,
                }
                content = json.dumps({
                    "critic_type": critic, "score": 1, "summary": "Found an incorrect capital.",
                    "issues": [issue], "overall_confidence": 0.9,
                })
            return LLMResponse(content=content, model=self.model, provider=self.provider_name,
                               prompt_tokens=3, completion_tokens=2)

    client = CountedClient()
    engine = ArbitrationEngine(llm_client=client, persist=False)
    dataset = [{
        "id": "local-instrumentation", "prompt": "What is the capital of Australia?",
        "candidate_answer": "Sydney.",
        "reference": {"has_issue": True, "expected_verdict": "revise", "ambiguous": False,
                      "labels": ["factual_error"]},
    }]

    report = evaluate_dataset(engine, dataset, "telemetry-test")

    assert client.calls == 4  # Three graph-captured critics plus the adjudicator.
    assert report["provider_request_totals"] == {
        "requests": 4, "successful_requests": 4, "failed_requests": 0,
        "status": "complete", "prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20,
    }
    assert report["case_results"][0]["token_usage"]["requests"] == 4
