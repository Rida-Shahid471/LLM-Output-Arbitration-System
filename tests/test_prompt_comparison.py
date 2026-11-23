import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.run_prompt_comparison import install_case_checkpoint, validate_case_accounting


class _FakeResult:
    def __init__(self, value: str) -> None:
        self.value = value

    def model_dump(self, mode: str = "python") -> dict:
        return {"mode": mode, "value": self.value}


class _FakeEngine:
    def arbitrate(self, prompt: str, candidate_answer: str, *, persist: bool = True):
        return _FakeResult(f"{prompt}:{candidate_answer}:{persist}")


def test_checkpoint_writes_completed_cases_and_progress_atomically(tmp_path: Path, capsys) -> None:
    dataset = [
        {"id": "first", "prompt": "Q1", "candidate_answer": "A1",
         "reference": {"ambiguous": False}},
        {"id": "ambiguous_001", "prompt": "Q2", "candidate_answer": "A2",
         "reference": {"ambiguous": True}},
        {"id": "last", "prompt": "Q3", "candidate_answer": "A3",
         "reference": {"ambiguous": False}},
    ]
    metadata_path = tmp_path / "metadata.json"
    metadata = {"completed_cases": 0, "completed_case_ids": []}
    engine = _FakeEngine()

    checkpoint_path = install_case_checkpoint(engine, dataset, tmp_path, metadata, metadata_path)
    assert checkpoint_path.name == "completed_cases.jsonl"
    assert engine.arbitrate("Q1", "A1", persist=False).value == "Q1:A1:False"
    assert engine.arbitrate("Q3", "A3", persist=False).value == "Q3:A3:False"

    rows = [json.loads(line) for line in checkpoint_path.read_text(encoding="utf-8").splitlines()]
    saved_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert [row["case_id"] for row in rows] == ["first", "last"]
    assert "ambiguous_001" not in [row["case_id"] for row in rows]
    assert rows[0]["arbitration_result"]["mode"] == "json"
    assert saved_metadata["completed_cases"] == 2
    assert saved_metadata["completed_case_ids"] == ["first", "last"]
    assert "Completed 2/2: last" in capsys.readouterr().out
    assert not list(tmp_path.glob("metadata.json.tmp"))


def test_checkpoint_rejects_unexpected_case_order(tmp_path: Path) -> None:
    dataset = [{"id": "first", "prompt": "Q", "candidate_answer": "A",
                "reference": {"ambiguous": False}}]
    metadata_path = tmp_path / "metadata.json"
    metadata = {"completed_cases": 0, "completed_case_ids": []}
    engine = _FakeEngine()
    install_case_checkpoint(engine, dataset, tmp_path, metadata, metadata_path)

    with pytest.raises(RuntimeError, match="order/input changed"):
        engine.arbitrate("unexpected", "answer")

    assert (tmp_path / "completed_cases.jsonl").read_text(encoding="utf-8") == ""
    assert metadata["completed_cases"] == 0


def test_checkpoint_does_not_mark_a_failed_case_complete(tmp_path: Path) -> None:
    class FailingEngine(_FakeEngine):
        def arbitrate(self, prompt: str, candidate_answer: str, *, persist: bool = True):
            raise TimeoutError("simulated local-provider timeout")

    dataset = [{"id": "slow-case", "prompt": "Q", "candidate_answer": "A",
                "reference": {"ambiguous": False}}]
    metadata_path = tmp_path / "metadata.json"
    metadata = {"completed_cases": 0, "completed_case_ids": []}
    engine = FailingEngine()
    checkpoint_path = install_case_checkpoint(engine, dataset, tmp_path, metadata, metadata_path)

    with pytest.raises(TimeoutError, match="simulated local-provider timeout"):
        engine.arbitrate("Q", "A")

    assert checkpoint_path.read_text(encoding="utf-8") == ""
    assert metadata["completed_cases"] == 0
    assert metadata["completed_case_ids"] == []


def test_accounting_allows_explicitly_excluded_critic_failure() -> None:
    # A fully recorded local run may have fewer than 20 metric-scored cases;
    # the remaining attempt must be explicitly excluded for its critic failure.
    validate_case_accounting({
        "dataset_cases": 21,
        "evaluated_cases": 19,
        "cases_excluded_due_to_critic_failures": 1,
        "ambiguous_cases_skipped": 1,
    })


def test_accounting_rejects_missing_case_outcome() -> None:
    with pytest.raises(RuntimeError, match="account for every attempted"):
        validate_case_accounting({
            "dataset_cases": 21,
            "evaluated_cases": 18,
            "cases_excluded_due_to_critic_failures": 1,
            "ambiguous_cases_skipped": 1,
        })
