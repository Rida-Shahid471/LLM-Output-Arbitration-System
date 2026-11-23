import json
import os
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
import time
from typing import Any

from src.adjudicator import ADJUDICATOR_PROMPT_VERSION
from src.categories import CANONICAL_ISSUE_CATEGORIES
from src.config import settings
from src.llm_client import LLMClient, LLMResponse
from src.prompts.critic_prompts import CRITIC_PROMPT_VERSION
from src.workflow import ArbitrationEngine
from src.schemas import Verdict


class _UsageTrackingClient(LLMClient):
    """Transparent evaluation-only wrapper for request and returned token counts."""

    def __init__(self, client: LLMClient) -> None:
        self._client = client
        self.model = getattr(client, "model", None)
        self.provider_name = getattr(client, "provider_name", "unknown")
        self.supports_json_schema = getattr(client, "supports_json_schema", False)
        self._lock = Lock()
        self._stats = {"requests": 0, "successful_requests": 0, "failed_requests": 0,
                       "usage_requests": 0, "prompt_tokens": 0, "completion_tokens": 0}

    def generate(self, *, prompt: str, system_prompt: str | None = None,
                 json_schema: dict | None = None) -> LLMResponse:
        with self._lock:
            self._stats["requests"] += 1
        try:
            if json_schema is not None and self.supports_json_schema:
                response = self._client.generate(prompt=prompt, system_prompt=system_prompt, json_schema=json_schema)
            else:
                response = self._client.generate(prompt=prompt, system_prompt=system_prompt)
        except Exception:
            with self._lock:
                self._stats["failed_requests"] += 1
            raise
        with self._lock:
            self._stats["successful_requests"] += 1
            prompt_tokens = getattr(response, "prompt_tokens", None)
            completion_tokens = getattr(response, "completion_tokens", None)
            if isinstance(prompt_tokens, int) and isinstance(completion_tokens, int):
                self._stats["usage_requests"] += 1
                self._stats["prompt_tokens"] += prompt_tokens
                self._stats["completion_tokens"] += completion_tokens
        return response

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return dict(self._stats)


def _track_engine_clients(engine: ArbitrationEngine) -> list[_UsageTrackingClient]:
    wrappers: dict[int, _UsageTrackingClient] = {}

    def wrap(client):
        if client is None:
            return None
        key = id(client)
        if key not in wrappers:
            wrappers[key] = _UsageTrackingClient(client)
        return wrappers[key]

    if hasattr(engine, "llm_client"):
        engine.llm_client = wrap(engine.llm_client)
    if hasattr(engine, "critic_clients"):
        engine.critic_clients = {kind: wrap(client) for kind, client in engine.critic_clients.items()}
    # ArbitrationEngine builds LangGraph nodes in __init__, and those nodes
    # capture the then-current critic clients. Rebuild after wrapping so the
    # evaluation telemetry observes critic calls as well as adjudicator calls.
    if wrappers and hasattr(engine, "_build_graph"):
        engine.graph = engine._build_graph()
    return list(wrappers.values())


def _usage_totals(trackers: list[_UsageTrackingClient]) -> dict[str, int]:
    totals = {key: 0 for key in ("requests", "successful_requests", "failed_requests", "usage_requests", "prompt_tokens", "completion_tokens")}
    for tracker in trackers:
        for key, value in tracker.snapshot().items():
            totals[key] += value
    return totals


def _usage_delta(after: dict[str, int], before: dict[str, int]) -> dict[str, int]:
    return {key: after[key] - before[key] for key in after}


def _render_usage(stats: dict[str, int]) -> dict[str, Any]:
    usage_complete = stats["successful_requests"] > 0 and stats["usage_requests"] == stats["successful_requests"]
    usage_partial = stats["usage_requests"] > 0 and not usage_complete
    return {
        "requests": stats["requests"], "successful_requests": stats["successful_requests"],
        "failed_requests": stats["failed_requests"],
        "status": "complete" if usage_complete else "partial" if usage_partial else "unavailable",
        "prompt_tokens": stats["prompt_tokens"] if usage_complete else None,
        "completion_tokens": stats["completion_tokens"] if usage_complete else None,
        "total_tokens": stats["prompt_tokens"] + stats["completion_tokens"] if usage_complete else None,
    }


def _render_critic_report(report) -> dict[str, Any]:
    if hasattr(report, "model_dump"):
        return report.model_dump(mode="json")
    return {
        "critic_type": getattr(getattr(report, "critic_type", None), "value", None),
        "issues": [getattr(issue, "category", issue) for issue in getattr(report, "issues", [])],
    }


def _render_final_verdict(verdict) -> dict[str, Any]:
    if hasattr(verdict, "model_dump"):
        return verdict.model_dump(mode="json")
    return {
        "verdict": getattr(getattr(verdict, "verdict", None), "value", None),
        "confidence": getattr(verdict, "confidence", None),
    }


def load_evaluation_dataset(path: str | Path) -> list[dict[str, Any]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        if not isinstance(data.get("version"), str) or not data["version"].strip():
            raise ValueError("Evaluation dataset must include a non-empty version.")
        data = data.get("cases")
    if not isinstance(data, list) or not data:
        raise ValueError("Evaluation dataset must contain a non-empty list of labeled cases.")
    seen_ids: set[str] = set()
    allowed_verdicts = {verdict.value for verdict in Verdict}
    for row in data:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"].strip():
            raise ValueError("Every evaluation case must have a non-empty string id.")
        if row["id"] in seen_ids:
            raise ValueError(f"Duplicate evaluation case id: {row['id']}.")
        seen_ids.add(row["id"])
        if not isinstance(row.get("prompt"), str) or not isinstance(row.get("candidate_answer"), str):
            raise ValueError(f"Evaluation case {row['id']} must include prompt and candidate_answer strings.")
        reference = row.get("reference")
        if (not isinstance(reference, dict) or not isinstance(reference.get("has_issue"), bool)
                or not isinstance(reference.get("ambiguous"), bool)
                or reference.get("expected_verdict") not in allowed_verdicts
                or not isinstance(reference.get("labels"), list)
                or any(not isinstance(label, str) or not label.strip() for label in reference.get("labels", []))):
            raise ValueError(f"Evaluation case {row['id']} has an invalid reference label.")
        labels = reference["labels"]
        unknown_labels = set(labels) - CANONICAL_ISSUE_CATEGORIES
        if unknown_labels:
            raise ValueError(f"Evaluation case {row['id']} has unknown issue labels: {', '.join(sorted(unknown_labels))}.")
        if len(labels) != len(set(labels)):
            raise ValueError(f"Evaluation case {row['id']} has duplicate issue labels.")
        review_required = row.get("review_required", False)
        if not isinstance(review_required, bool):
            raise ValueError(f"Evaluation case {row['id']} review_required must be a boolean.")
        if review_required and (not isinstance(row.get("review_reason"), str) or not row["review_reason"].strip()):
            raise ValueError(f"Evaluation case {row['id']} requires a non-empty review_reason.")
        if reference["ambiguous"]:
            if reference["has_issue"] or labels or reference["expected_verdict"] != Verdict.ACCEPT.value:
                raise ValueError(f"Ambiguous evaluation case {row['id']} must not assert a scored issue or non-accept verdict.")
        else:
            if reference["has_issue"] != bool(labels):
                raise ValueError(f"Evaluation case {row['id']} has inconsistent has_issue and labels.")
            if (reference["expected_verdict"] == Verdict.ACCEPT.value) == reference["has_issue"]:
                raise ValueError(f"Evaluation case {row['id']} has inconsistent has_issue and expected_verdict.")
    return data


def evaluate_dataset(engine: ArbitrationEngine, dataset: list[dict[str, Any]], dataset_version: str = "unspecified") -> dict[str, Any]:
    evaluation_started = time.perf_counter()
    trackers = _track_engine_clients(engine)
    tp = fp = fn = tn = verdict_matches = 0
    confidence_sum = 0.0
    evaluated = 0
    cases_with_critic_failures = 0
    total_critic_failures = 0
    critic_failures_by_type: dict[str, int] = {}
    cases_excluded_due_to_critic_failures = 0
    cases_with_adjudication_fallback = 0
    failed_case_ids: set[str] = set()
    verdict_evaluated = 0
    ambiguous_skipped = 0
    human_review_skipped = 0
    observed_critic_models: dict[str, set[str]] = {}
    observed_critic_providers: dict[str, set[str]] = {}
    observed_adjudicator_models: set[str] = set()
    observed_adjudicator_providers: set[str] = set()
    issue_category_counts: dict[str, int] = {}
    results = []
    attempted_case_durations: list[float] = []
    for case in dataset:
        reference = case["reference"]
        if reference.get("ambiguous", False):
            ambiguous_skipped += 1
            results.append({"id": case["id"], "evaluation_status": "skipped_ambiguous"})
            continue
        if case.get("review_required", False):
            human_review_skipped += 1
            results.append({"id": case["id"], "evaluation_status": "skipped_human_review", "review_reason": case["review_reason"]})
            continue
        usage_before = _usage_totals(trackers)
        case_started = time.perf_counter()
        result = engine.arbitrate(case["prompt"], case["candidate_answer"])
        case_duration = time.perf_counter() - case_started
        attempted_case_durations.append(case_duration)
        case_usage = _usage_delta(_usage_totals(trackers), usage_before)
        for report in result.critic_reports:
            for issue in report.issues:
                category = getattr(issue, "category", issue if isinstance(issue, str) else None)
                if category:
                    issue_category_counts[category] = issue_category_counts.get(category, 0) + 1
            critic_name = getattr(getattr(report, "critic_type", None), "value", None)
            if critic_name and getattr(report, "model", None):
                observed_critic_models.setdefault(critic_name, set()).add(report.model)
            if critic_name and getattr(report, "provider", None):
                observed_critic_providers.setdefault(critic_name, set()).add(report.provider)
        adjudicator_model = getattr(result.final_verdict, "adjudicator_model", None)
        adjudicator_provider = getattr(result.final_verdict, "adjudicator_provider", None)
        if adjudicator_model:
            observed_adjudicator_models.add(adjudicator_model)
        if adjudicator_provider:
            observed_adjudicator_providers.add(adjudicator_provider)
        if result.errors:
            cases_with_critic_failures += 1
            total_critic_failures += len(result.errors)
        case_failure_types = []
        for error in result.errors:
            parts = error.split(": ", 2)
            failure_type = parts[1] if len(parts) > 1 else "UnknownError"
            case_failure_types.append(failure_type)
            critic_failures_by_type[failure_type] = critic_failures_by_type.get(failure_type, 0) + 1
        rationale = getattr(result.final_verdict, "rationale", None)
        fallback_used = bool(rationale and rationale.startswith("Fallback used:"))
        cases_with_adjudication_fallback += int(fallback_used)
        if result.errors or fallback_used:
            failed_case_ids.add(case["id"])
        complete_critic_set = len(result.critic_reports) == 3 and not result.errors
        if complete_critic_set:
            predicted_issue = any(report.issues for report in result.critic_reports)
            expected_issue = reference["has_issue"]
            tp += int(predicted_issue and expected_issue)
            fp += int(predicted_issue and not expected_issue)
            fn += int(not predicted_issue and expected_issue)
            tn += int(not predicted_issue and not expected_issue)
            evaluated += 1
            if not fallback_used:
                verdict_matches += int(result.final_verdict.verdict.value == reference["expected_verdict"])
                confidence_sum += result.final_verdict.confidence
                verdict_evaluated += 1
            evaluation_status = "scored" if not fallback_used else "critic_scored_adjudication_fallback"
        else:
            predicted_issue = None
            expected_issue = reference["has_issue"]
            cases_excluded_due_to_critic_failures += 1
            evaluation_status = "excluded_incomplete_critic_set"
        results.append({"id": case["id"], "evaluation_status": evaluation_status,
                        "predicted_issue": predicted_issue, "expected_issue": expected_issue,
                        "verdict": result.final_verdict.verdict.value, "expected_verdict": reference["expected_verdict"],
                        "confidence": result.final_verdict.confidence,
                        "critic_report_count": len(result.critic_reports), "critic_failure_count": len(result.errors),
                        "critic_failure_types": case_failure_types,
                        "adjudication_fallback": fallback_used,
                        "elapsed_seconds": round(case_duration, 3),
                        "critic_reports": [_render_critic_report(report) for report in result.critic_reports],
                        "disagreements": [item.model_dump(mode="json") for item in getattr(result, "disagreements", [])],
                        "adjudicator_output": _render_final_verdict(result.final_verdict),
                        "issue_categories": sorted({
                            category for report in result.critic_reports for issue in report.issues
                            if (category := getattr(issue, "category", issue if isinstance(issue, str) else None))
                        }),
                        "errors": list(result.errors),
                        "token_usage": _render_usage(case_usage)})
    total_execution_seconds = time.perf_counter() - evaluation_started
    total_usage = _usage_totals(trackers)
    eligible_cases = max(0, len(dataset) - ambiguous_skipped - human_review_skipped)
    precision = round(tp / (tp + fp), 4) if tp + fp else None
    recall = round(tp / (tp + fn), 4) if tp + fn else None
    f1 = round(2 * precision * recall / (precision + recall), 4) if precision is not None and recall is not None and precision + recall else None
    coverage = round(evaluated / eligible_cases, 4) if eligible_cases else None
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset_version": dataset_version,
        "critic_prompt_version": CRITIC_PROMPT_VERSION,
        "adjudicator_prompt_version": ADJUDICATOR_PROMPT_VERSION,
        "model_digest": os.getenv("OLLAMA_MODEL_DIGEST") if settings.llm_provider == "ollama" else None,
        "provider_budgets": {
            provider_name: {
                "max_input_chars": settings.provider_input_limit(provider_name),
                "max_output_tokens": settings.provider_output_limit(provider_name),
            }
            for provider_name in ("openai", "anthropic", "ollama")
        },
        "provider": getattr(engine, "provider", "unknown"),
        "adjudicator_model": getattr(getattr(engine, "llm_client", None), "model", None),
        "critic_models": {
            critic_type.value: getattr(client, "model", None)
            for critic_type, client in getattr(engine, "critic_clients", {}).items()
        },
        "observed_critic_models": {name: sorted(values) for name, values in observed_critic_models.items()},
        "observed_critic_providers": {name: sorted(values) for name, values in observed_critic_providers.items()},
        "observed_adjudicator_models": sorted(observed_adjudicator_models),
        "observed_adjudicator_providers": sorted(observed_adjudicator_providers),
        "dataset_cases": len(dataset), "evaluated_cases": evaluated, "ambiguous_cases_skipped": ambiguous_skipped,
        "human_review_cases_skipped": human_review_skipped,
        "cases_excluded_due_to_critic_failures": cases_excluded_due_to_critic_failures,
        "issue_detection_precision": precision,
        "issue_detection_precision_status": "defined" if tp + fp else "undefined_no_positive_predictions",
        "issue_detection_recall": round(tp / (tp + fn), 4) if tp + fn else None,
        "issue_detection_recall_status": "defined" if tp + fn else "undefined_no_actual_positive_cases",
        "issue_detection_f1": f1,
        "issue_detection_f1_status": "defined" if f1 is not None else "undefined_precision_or_recall",
        "clean_answer_false_positive_rate": round(fp / (fp + tn), 4) if fp + tn else None,
        "clean_answer_false_positive_rate_status": "defined" if fp + tn else "undefined_no_clean_cases",
        "adjudication_agreement": round(verdict_matches / verdict_evaluated, 4) if verdict_evaluated else None,
        "adjudication_agreement_status": "defined" if verdict_evaluated else "undefined_no_verdicts_scored",
        "verdict_evaluated_cases": verdict_evaluated,
        "verdict_matches": verdict_matches,
        "average_confidence": round(confidence_sum / verdict_evaluated, 4) if verdict_evaluated else None,
        "metric_denominators": {
            "issue_detection_precision": {"count": tp + fp, "predicted_positive_cases": tp + fp},
            "issue_detection_recall": {"count": tp + fn, "actual_positive_cases": tp + fn},
            "clean_answer_false_positive_rate": {"count": fp + tn, "clean_cases": fp + tn},
            "adjudication_agreement": {"count": verdict_evaluated, "verdict_matches": verdict_matches},
        },
        "cases_with_critic_failures": cases_with_critic_failures,
        "total_critic_failures": total_critic_failures,
        "critic_failures_by_type": critic_failures_by_type,
        "cases_with_adjudication_fallback": cases_with_adjudication_fallback,
        "eligible_cases": eligible_cases,
        "evaluation_coverage": coverage,
        "evaluation_coverage_status": "defined" if coverage is not None else "undefined_no_eligible_cases",
        "failed_case_count": len(failed_case_ids),
        "error_rate": round(len(failed_case_ids) / eligible_cases, 4) if eligible_cases else None,
        "error_rate_status": "defined" if eligible_cases else "undefined_no_eligible_cases",
        "total_execution_seconds": round(total_execution_seconds, 3),
        "average_case_execution_seconds": round(sum(attempted_case_durations) / len(attempted_case_durations), 3) if attempted_case_durations else None,
        "provider_request_totals": _render_usage(total_usage),
        "issue_category_counts": dict(sorted(issue_category_counts.items())),
        "confusion": {"true_positive": tp, "false_positive": fp, "false_negative": fn, "true_negative": tn},
        "case_results": results,
        "note": "Metrics describe this run and dataset only; they are not a guarantee of general accuracy.",
    }
