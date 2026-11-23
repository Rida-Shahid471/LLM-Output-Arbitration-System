"""Run the controlled factual-critic prompt comparison against local Ollama only.

This experiment changes exactly one variable: the factual-accuracy critic prompt.
The model, dataset, sampling settings, output budget, other critic prompts, and
adjudicator prompt remain fixed. Raw results are written to a new output folder.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import time
from textwrap import dedent
from urllib.parse import urlparse

import requests

import src.critic_runner as critic_runner_module
import src.evaluation as evaluation_module
import src.workflow as workflow_module
from src.config import settings
from src.evaluation import evaluate_dataset, load_evaluation_dataset
from src.prompts.critic_prompts import get_critic_prompt as baseline_get_critic_prompt
from src.schemas import ArbitrationResult, CriticType
from src.workflow import ArbitrationEngine

ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = ROOT / "tmp" / "ollama-qwen2.5-1.5b-dataset-v1.2.0-20261103.json"
DATASET_PATH = ROOT / "tests" / "evaluation_dataset.json"
EXPECTED_MODEL = "qwen2.5:1.5b"
EXPECTED_DIGEST = "65ec06548149b04c096a120e4a6da9d4017ea809c91734ea5631e89f96ddc57b"
PROMPT_VERSION = "day16-factual-calibration-v1"

FACTUAL_ACCURACY_PROMPT = dedent(
    """
    Evaluate the candidate answer for factual accuracy.

    Focus on concrete factual claims and distinguish false, unsupported, and
    incomplete claims. A fact is not unsupported merely because the prompt does
    not repeat it or the answer does not cite a source. Use stable, well-known
    facts when they are within reliable knowledge; do not invent sources or
    corrections. If a claim cannot be reliably verified, state the uncertainty
    and lower confidence instead of declaring it false. Use factual_error only
    for a claim that is contradicted by the prompt or reliably known facts. Use
    unsupported_claim only when the answer asserts a material claim that cannot
    be supported from the available context or reliable knowledge.

    Do not evaluate writing style unless it changes factual meaning.

    Original prompt:
    {original_prompt}

    Candidate answer:
    {candidate_answer}
    """
).strip()

METRIC_KEYS = (
    "issue_detection_precision",
    "issue_detection_recall",
    "issue_detection_f1",
    "clean_answer_false_positive_rate",
    "adjudication_agreement",
    "average_confidence",
    "evaluation_coverage",
    "error_rate",
)


def validate_case_accounting(report: dict, *, expected_cases: int = 20) -> None:
    if report.get("dataset_cases") != expected_cases + 1 or report.get("ambiguous_cases_skipped") != 1:
        raise RuntimeError("Evaluation did not preserve the expected scorable and ambiguous case counts.")
    if report.get("evaluated_cases", 0) + report.get("cases_excluded_due_to_critic_failures", 0) != expected_cases:
        raise RuntimeError("Evaluation did not account for every attempted scorable case.")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_local_configuration(model_digest: str) -> str:
    if settings.llm_provider != "ollama" or settings.llm_model != EXPECTED_MODEL:
        raise ValueError("Experiment requires LLM_PROVIDER=ollama and LLM_MODEL=qwen2.5:1.5b.")
    if settings.llm_temperature != 0.0:
        raise ValueError("Experiment requires temperature 0.0 to match the baseline.")
    if settings.provider_output_limit("ollama") != 1024:
        raise ValueError("Experiment requires the baseline 1,024-token Ollama output budget.")
    if any((settings.factual_provider, settings.logical_provider, settings.completeness_provider,
            settings.factual_model, settings.logical_model, settings.completeness_model)):
        raise ValueError("Per-critic provider/model overrides must be unset for this comparison.")
    parsed = urlparse(settings.ollama_base_url)
    if parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("Only a loopback Ollama endpoint is permitted for this experiment.")
    response = requests.get("http://127.0.0.1:11434/api/tags", timeout=5)
    response.raise_for_status()
    installed = response.json().get("models", [])
    if not any(model.get("name") == EXPECTED_MODEL and model.get("digest") == model_digest
               for model in installed):
        raise ValueError("The expected local model tag and digest are not present in Ollama.")
    if model_digest != EXPECTED_DIGEST:
        raise ValueError("The local model digest differs from the Task 4 baseline.")
    version_response = requests.get("http://127.0.0.1:11434/api/version", timeout=5)
    version_response.raise_for_status()
    return str(version_response.json().get("version", "unknown"))


def score_ids(report: dict) -> dict[str, list[str]]:
    false_positives: list[str] = []
    false_negatives: list[str] = []
    for row in report.get("case_results", []):
        if row.get("evaluation_status") not in {"scored", "critic_scored_adjudication_fallback"}:
            continue
        expected = row.get("expected_issue")
        predicted = row.get("predicted_issue")
        if predicted is True and expected is False:
            false_positives.append(row["id"])
        elif predicted is False and expected is True:
            false_negatives.append(row["id"])
    return {"false_positive_case_ids": false_positives, "false_negative_case_ids": false_negatives}


def build_comparison(baseline: dict, experiment: dict) -> dict:
    metrics: dict[str, dict] = {}
    for key in METRIC_KEYS:
        before, after = baseline.get(key), experiment.get(key)
        delta = round(after - before, 4) if isinstance(before, (int, float)) and isinstance(after, (int, float)) else None
        metrics[key] = {"baseline": before, "comparison": after, "delta": delta}
    return {
        "metrics": metrics,
        "baseline_confusion": baseline.get("confusion"),
        "comparison_confusion": experiment.get("confusion"),
        "baseline_false_positive_and_negative_ids": score_ids(baseline),
        "comparison_false_positive_and_negative_ids": score_ids(experiment),
        "baseline_adjudication_fallbacks": baseline.get("cases_with_adjudication_fallback"),
        "comparison_adjudication_fallbacks": experiment.get("cases_with_adjudication_fallback"),
        "baseline_critic_failures": baseline.get("cases_with_critic_failures"),
        "comparison_critic_failures": experiment.get("cases_with_critic_failures"),
        "baseline_disagreement_count": sum(len(row.get("disagreements", [])) for row in baseline.get("case_results", [])),
        "comparison_disagreement_count": sum(len(row.get("disagreements", [])) for row in experiment.get("case_results", [])),
    }


def _write_json_atomic(path: Path, payload: dict) -> None:
    """Persist progress without leaving a half-written metadata file."""
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def install_case_checkpoint(engine, dataset: list[dict], output_dir: Path,
                            metadata: dict, metadata_path: Path):
    """Checkpoint every completed real arbitration before evaluation continues."""
    scorable_cases = [case for case in dataset
                      if not case["reference"].get("ambiguous", False)
                      and not case.get("review_required", False)]
    expected = iter(scorable_cases)
    checkpoint_path = output_dir / "completed_cases.jsonl"
    checkpoint_path.touch(exist_ok=False)
    started = time.perf_counter()
    original_arbitrate = engine.arbitrate
    completed_ids: list[str] = []

    def checkpointed_arbitrate(original_prompt: str, candidate_answer: str, *, persist: bool = True):
        try:
            case = next(expected)
        except StopIteration as exc:
            raise RuntimeError("Evaluation attempted more cases than the validated scorable dataset.") from exc
        if (case["prompt"], case["candidate_answer"]) != (original_prompt, candidate_answer):
            raise RuntimeError(f"Evaluation case order/input changed unexpectedly at {case['id']}.")
        case_started = time.perf_counter()
        result = original_arbitrate(original_prompt, candidate_answer, persist=persist)
        result_payload = result.model_dump(mode="json")
        elapsed = round(time.perf_counter() - case_started, 3)
        event = {"case_id": case["id"], "elapsed_seconds": elapsed, "arbitration_result": result_payload}
        with checkpoint_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, ensure_ascii=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        completed_ids.append(case["id"])
        metadata["completed_cases"] = len(completed_ids)
        metadata["completed_case_ids"] = list(completed_ids)
        metadata["last_completed_case_at_utc"] = utc_now()
        metadata["elapsed_seconds"] = round(time.perf_counter() - started, 3)
        _write_json_atomic(metadata_path, metadata)
        print(f"Completed {len(completed_ids)}/{len(scorable_cases)}: {case['id']} "
              f"({elapsed:.1f}s; elapsed {metadata['elapsed_seconds']:.1f}s)", flush=True)
        return result

    engine.arbitrate = checkpointed_arbitrate
    print(f"Starting local Ollama comparison: {len(scorable_cases)} scorable cases; "
          f"ambiguous cases excluded={len(dataset) - len(scorable_cases)}", flush=True)
    return checkpoint_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path,
                        help="New, non-existing local results folder. Existing folders are never overwritten.")
    parser.add_argument("--finalize-checkpoint", type=Path,
                        help="Reaggregate a fully checkpointed run offline into a separate new output folder; makes no provider calls.")
    args = parser.parse_args()
    output_dir = args.output_dir.resolve()
    if output_dir.exists():
        raise FileExistsError(f"Refusing to reuse or overwrite existing experiment folder: {output_dir}")
    if args.finalize_checkpoint:
        finalize_checkpoint(args.finalize_checkpoint.resolve(), output_dir)
        return
    if not BASELINE_PATH.is_file() or not DATASET_PATH.is_file():
        raise FileNotFoundError("The original Task 4 baseline and approved evaluation dataset are required.")

    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    raw_dataset = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    dataset_version = raw_dataset.get("version", "unspecified")
    if dataset_version != "1.2.0":
        raise ValueError(f"Expected approved dataset version 1.2.0, found {dataset_version}.")
    if baseline.get("provider") != "ollama" or baseline.get("adjudicator_model") != EXPECTED_MODEL:
        raise ValueError("The supplied baseline does not match the expected local Ollama model.")
    if baseline.get("model_digest") != EXPECTED_DIGEST:
        raise ValueError("The baseline model digest is missing or does not match the expected model.")
    if baseline.get("critic_prompt_version") != "critic-prompts-v3" or baseline.get("adjudicator_prompt_version") != "adjudicator-prompt-v3":
        raise ValueError("The original Task 4 prompt versions do not match the documented baseline.")
    if baseline.get("dataset_cases") != 21 or baseline.get("evaluated_cases") != 20 or baseline.get("ambiguous_cases_skipped") != 1:
        raise ValueError("The Task 4 baseline does not contain the expected 20-scored/1-ambiguous coverage.")
    if baseline.get("provider_budgets", {}).get("ollama", {}).get("max_output_tokens") != 1024:
        raise ValueError("The baseline Ollama output budget is not the expected 1,024 tokens.")

    dataset = load_evaluation_dataset(DATASET_PATH)
    if len(dataset) != 21 or sum(bool(case["reference"].get("ambiguous")) for case in dataset) != 1:
        raise ValueError("The approved dataset shape or ambiguity count is not as expected.")
    ollama_version = validate_local_configuration(EXPECTED_DIGEST)

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=False, exist_ok=False)
    started_at = utc_now()
    metadata = {
        "experiment_id": "day16-qwen2.5-1.5b-factual-calibration-v1",
        "status": "running",
        "started_at_utc": started_at,
        "completed_at_utc": None,
        "provider": "ollama",
        "model": EXPECTED_MODEL,
        "model_digest": EXPECTED_DIGEST,
        "ollama_runtime_version": ollama_version,
        "ollama_endpoint": "http://127.0.0.1:11434/v1",
        "dataset_version": dataset_version,
        "dataset_cases": len(dataset),
        "scorable_cases": 20,
        "ambiguous_case_ids_excluded": ["ambiguous_001"],
        "baseline_report": str(BASELINE_PATH.relative_to(ROOT)),
        "baseline_sha256": sha256(BASELINE_PATH),
        "dataset_sha256": sha256(DATASET_PATH),
        "baseline_critic_prompt_version": "critic-prompts-v3",
        "comparison_critic_prompt_version": PROMPT_VERSION,
        "adjudicator_prompt_version": "adjudicator-prompt-v3 (unchanged)",
        "single_changed_variable": "factual_accuracy critic prompt text only",
        "fixed_conditions": {
            "logic_prompt": "critic-prompts-v3 (unchanged)",
            "completeness_prompt": "critic-prompts-v3 (unchanged)",
            "adjudicator_prompt": "adjudicator-prompt-v3 (unchanged)",
            "temperature": settings.llm_temperature,
            "max_output_tokens": settings.provider_output_limit("ollama"),
            "max_retries": settings.llm_max_retries,
            "timeout_seconds": settings.llm_timeout_seconds,
            "persist": False,
        },
        "comparison_factual_prompt": FACTUAL_ACCURACY_PROMPT,
        "completed_cases": 0,
        "completed_case_ids": [],
        "checkpoint_file": "completed_cases.jsonl",
        "limitations": [
            "The fixed dataset contains only 20 approved/scorable synthetic cases.",
            "Only one critic prompt is changed; this is not a comparison of model families.",
            "The current Ollama runtime may differ from the baseline runtime, although the model digest is checked.",
            "One run per case does not characterize sampling variance or broad model quality.",
        ],
    }
    metadata_path = output_dir / "metadata.json"
    _write_json_atomic(metadata_path, metadata)

    def experiment_get_critic_prompt(critic_type, original_prompt: str, candidate_answer: str) -> str:
        if critic_type != CriticType.FACTUAL_ACCURACY:
            return baseline_get_critic_prompt(critic_type, original_prompt, candidate_answer)
        return FACTUAL_ACCURACY_PROMPT.format(
            original_prompt=original_prompt,
            candidate_answer=candidate_answer,
        )

    critic_runner_module.get_critic_prompt = experiment_get_critic_prompt
    workflow_module.CRITIC_PROMPT_VERSION = PROMPT_VERSION
    evaluation_module.CRITIC_PROMPT_VERSION = PROMPT_VERSION

    try:
        engine = ArbitrationEngine(persist=False)
        install_case_checkpoint(engine, dataset, output_dir, metadata, metadata_path)
        report = evaluate_dataset(engine, dataset, dataset_version=dataset_version)
        validate_case_accounting(report)
        ambiguous = next((row for row in report.get("case_results", []) if row.get("id") == "ambiguous_001"), None)
        if not ambiguous or ambiguous.get("evaluation_status") != "skipped_ambiguous":
            raise RuntimeError("ambiguous_001 was not explicitly skipped by the evaluator.")
        metadata["status"] = ("completed" if report.get("evaluated_cases") == 20
                               else "completed_with_case_failures")
        metadata["completed_at_utc"] = utc_now()
        metadata["elapsed_seconds"] = report.get("total_execution_seconds")
        metadata["result_file"] = "results.json"
        report["experiment_metadata"] = metadata
        report["comparison_to_task4_baseline"] = build_comparison(baseline, report)
        report_path = output_dir / "results.json"
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        _write_json_atomic(metadata_path, metadata)
    except Exception as exc:
        metadata["status"] = "failed"
        metadata["completed_at_utc"] = utc_now()
        metadata["failure_type"] = type(exc).__name__
        metadata["elapsed_seconds"] = metadata.get("elapsed_seconds")
        _write_json_atomic(metadata_path, metadata)
        raise

    print(json.dumps({
        "status": metadata["status"],
        "output_dir": str(output_dir),
        "generated_at": report.get("generated_at"),
        "dataset_cases": report.get("dataset_cases"),
        "evaluated_cases": report.get("evaluated_cases"),
        "ambiguous_cases_skipped": report.get("ambiguous_cases_skipped"),
        "metrics": {key: report.get(key) for key in METRIC_KEYS},
        "comparison": report.get("comparison_to_task4_baseline"),
    }, indent=2))


def finalize_checkpoint(source_dir: Path, output_dir: Path) -> dict:
    """Recompute metrics from persisted real outputs without contacting a provider."""
    metadata_path = source_dir / "metadata.json"
    checkpoint_path = source_dir / "completed_cases.jsonl"
    if not metadata_path.is_file() or not checkpoint_path.is_file():
        raise FileNotFoundError("Checkpoint source must contain metadata.json and completed_cases.jsonl.")
    source_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    raw_dataset = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    dataset = load_evaluation_dataset(DATASET_PATH)
    expected = [case for case in dataset
                if not case["reference"].get("ambiguous", False) and not case.get("review_required", False)]
    if source_metadata.get("provider") != "ollama" or source_metadata.get("model") != EXPECTED_MODEL:
        raise ValueError("Checkpoint metadata does not identify the expected local Ollama model.")
    if source_metadata.get("model_digest") != EXPECTED_DIGEST:
        raise ValueError("Checkpoint model digest does not match the approved local model.")
    if source_metadata.get("baseline_sha256") != sha256(BASELINE_PATH):
        raise ValueError("Task 4 baseline changed since the checkpoint was created.")
    if source_metadata.get("dataset_sha256") != sha256(DATASET_PATH):
        raise ValueError("Approved dataset changed since the checkpoint was created.")
    rows = [json.loads(line) for line in checkpoint_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    expected_ids = [case["id"] for case in expected]
    row_ids = [row.get("case_id") for row in rows]
    if row_ids != expected_ids or len(set(row_ids)) != len(row_ids):
        raise ValueError("Checkpoint must contain exactly one result per approved case, in dataset order.")
    by_id = {case["id"]: case for case in expected}
    results = {}
    for row in rows:
        case = by_id[row["case_id"]]
        result = ArbitrationResult.model_validate(row["arbitration_result"])
        if result.original_prompt != case["prompt"] or result.candidate_output != case["candidate_answer"]:
            raise ValueError(f"Checkpoint input does not match approved dataset case {case['id']}.")
        if result.provider != "ollama":
            raise ValueError(f"Case {case['id']} does not identify Ollama as its provider.")
        results[case["id"]] = result

    # The configured engine is used only for provider/model metadata and token
    # accounting. Replacing arbitrate with a strict replay function prevents
    # any live model request during reaggregation.
    engine = ArbitrationEngine(persist=False)
    if engine.provider != "ollama" or getattr(engine.llm_client, "model", None) != EXPECTED_MODEL:
        raise ValueError("Offline reaggregation requires explicit Ollama/model configuration in the process environment.")
    remaining = iter(expected)

    def replay_arbitrate(prompt: str, candidate_answer: str, *, persist: bool = True):
        try:
            case = next(remaining)
        except StopIteration as exc:
            raise RuntimeError("Evaluator requested more cases than the checkpoint contains.") from exc
        if prompt != case["prompt"] or candidate_answer != case["candidate_answer"]:
            raise RuntimeError(f"Evaluator input order differs from checkpoint at {case['id']}.")
        return results[case["id"]]

    engine.arbitrate = replay_arbitrate
    report = evaluate_dataset(engine, dataset, dataset_version=raw_dataset.get("version", "unspecified"))
    validate_case_accounting(report)

    source_rows = {row["case_id"]: row for row in rows}
    for case_result in report["case_results"]:
        case_id = case_result.get("id")
        if case_id in source_rows:
            case_result["elapsed_seconds"] = source_rows[case_id]["elapsed_seconds"]
            # Reaggregation observes no usage counters, so don't mistake its
            # zero-call telemetry for the original inference's token usage.
            case_result["token_usage"] = None
    actual_durations = [float(row["elapsed_seconds"]) for row in rows]
    report["total_execution_seconds"] = round(sum(actual_durations), 3)
    report["average_case_execution_seconds"] = round(sum(actual_durations) / len(actual_durations), 3)
    report["provider_request_totals"] = None
    report["provider_request_totals_status"] = "not captured by the original checkpoint"

    finalized_metadata = dict(source_metadata)
    finalized_metadata.update({
        "status": "completed_with_case_failures" if report["cases_excluded_due_to_critic_failures"] else "completed",
        "completed_at_utc": utc_now(),
        "reaggregated_from": str(checkpoint_path.relative_to(ROOT)),
        "checkpoint_sha256": sha256(checkpoint_path),
        "result_file": "results.json",
        "metric_scored_cases": report["evaluated_cases"],
        "cases_excluded_due_to_critic_failures": report["cases_excluded_due_to_critic_failures"],
        "ambiguous_cases_skipped": report["ambiguous_cases_skipped"],
        "actual_inference_seconds": report["total_execution_seconds"],
        "average_case_execution_seconds": report["average_case_execution_seconds"],
        "token_usage": "not captured",
        "note": "Metrics were recomputed offline from the persisted real Ollama arbitration outputs; no provider calls were made during reaggregation.",
    })
    report["experiment_metadata"] = finalized_metadata
    report["experiment_completion_note"] = (
        "All 20 approved cases have persisted real outputs. Cases with incomplete critic sets are listed and excluded from issue metrics; the experiment is not represented as a full-coverage scored run."
    )
    report["comparison_to_task4_baseline"] = build_comparison(baseline, report)
    output_dir.mkdir(parents=True, exist_ok=False)
    report_path = output_dir / "results.json"
    _write_json_atomic(report_path, report)
    _write_json_atomic(output_dir / "metadata.json", finalized_metadata)
    print(json.dumps({
        "status": finalized_metadata["status"],
        "output_dir": str(output_dir),
        "source_checkpoint": str(checkpoint_path),
        "dataset_cases": report["dataset_cases"],
        "evaluated_cases": report["evaluated_cases"],
        "cases_excluded_due_to_critic_failures": report["cases_excluded_due_to_critic_failures"],
        "ambiguous_cases_skipped": report["ambiguous_cases_skipped"],
        "metrics": {key: report.get(key) for key in METRIC_KEYS},
        "provider_calls_during_reaggregation": 0,
    }, indent=2))
    return report


if __name__ == "__main__":
    main()
