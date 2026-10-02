import pytest

from src.critic_runner import CriticRunner
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


def test_critic_runner_run_is_not_ready_for_raw_output() -> None:
    client = MockLLMClient(
        response="placeholder",
    )

    runner = CriticRunner(client)

    arbitration_input = parse_input(
        original_prompt="Test prompt",
        candidate_answer="Test answer",
    )

    with pytest.raises(NotImplementedError):
        runner.run(
            critic_type=CriticType.COMPLETENESS,
            arbitration_input=arbitration_input,
        )