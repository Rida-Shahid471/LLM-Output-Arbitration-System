import json

import pytest

from src.critic_runner import CriticRunner
from src.errors import CriticResponseError, LLMNonRetryableProviderError, LLMTimeoutError
from src.input_parser import parse_input
from src.llm_client import MockLLMClient
from src.schemas import CriticType


def test_critic_runner_builds_specialist_prompt() -> None:
    client = MockLLMClient(
        response="placeholder",
    )

    runner = CriticRunner(client)

    arbitration_input = parse_input(
        original_prompt="What is the capital of France?",
        candidate_answer="The capital of France is Paris.",
    )

    prompt = runner.build_prompt(
        critic_type=CriticType.FACTUAL_ACCURACY,
        arbitration_input=arbitration_input,
    )

    assert "factual accuracy" in prompt.lower()
    assert "What is the capital of France?" in prompt
    assert "The capital of France is Paris." in prompt


def test_critic_runner_parses_structured_report() -> None:
    client = MockLLMClient(response=json.dumps({
        "critic_type": "completeness", "score": 4,
        "summary": "The answer is mostly complete.", "issues": [],
        "overall_confidence": 0.9,
    }))

    runner = CriticRunner(client)

    arbitration_input = parse_input(
        original_prompt="Test prompt",
        candidate_answer="Test answer",
    )

    report = runner.run(
        critic_type=CriticType.COMPLETENESS,
        arbitration_input=arbitration_input,
    )
    assert report.critic_type == CriticType.COMPLETENESS
    assert report.score == 4


def test_critic_runner_exhausts_retry_budget_for_malformed_responses() -> None:
    calls = 0

    def malformed(prompt: str, system_prompt: str | None) -> str:
        nonlocal calls
        calls += 1
        return "not valid JSON"

    runner = CriticRunner(MockLLMClient(response=malformed), max_retries=2)

    with pytest.raises(CriticResponseError):
        runner.run(critic_type=CriticType.FACTUAL_ACCURACY, arbitration_input=parse_input("Q", "A"))

    assert calls == 3


def test_critic_runner_retries_provider_timeouts() -> None:
    calls = 0

    def timeout(prompt: str, system_prompt: str | None) -> str:
        nonlocal calls
        calls += 1
        raise LLMTimeoutError("provider timed out")

    runner = CriticRunner(MockLLMClient(response=timeout), max_retries=1)

    with pytest.raises(LLMTimeoutError):
        runner.run(critic_type=CriticType.LOGICAL_CONSISTENCY, arbitration_input=parse_input("Q", "A"))

    assert calls == 2


def test_critic_runner_does_not_retry_permanent_provider_rejections() -> None:
    calls = 0

    def rejected(prompt: str, system_prompt: str | None) -> str:
        nonlocal calls
        calls += 1
        raise LLMNonRetryableProviderError("OpenAI request was rejected (AuthenticationError).")

    runner = CriticRunner(MockLLMClient(response=rejected), max_retries=3)

    with pytest.raises(LLMNonRetryableProviderError, match="AuthenticationError"):
        runner.run(critic_type=CriticType.FACTUAL_ACCURACY, arbitration_input=parse_input("Q", "A"))

    assert calls == 1


def test_critic_runner_rejects_duplicate_issue_entries() -> None:
    issue = {
        "category": "factual error", "description": "Incorrect fact", "evidence": "Sydney",
        "severity": "high", "confidence": 0.9,
    }
    payload = {
        "critic_type": "factual_accuracy", "score": 2, "summary": "Found a fact issue.",
        "issues": [issue, {**issue, "category": "fact", "confidence": 0.7}],
        "overall_confidence": 0.9,
    }
    runner = CriticRunner(MockLLMClient(response=json.dumps(payload)), max_retries=0)

    with pytest.raises(CriticResponseError, match="duplicate issue entries"):
        runner.run(critic_type=CriticType.FACTUAL_ACCURACY, arbitration_input=parse_input("Q", "Sydney"))
