import pytest
from pydantic import ValidationError

from src.input_parser import ArbitrationInput, parse_input


def test_parse_input_accepts_valid_input() -> None:
    result = parse_input(
        original_prompt="What is the capital of France?",
        candidate_answer="The capital of France is Paris.",
    )

    assert isinstance(result, ArbitrationInput)
    assert result.original_prompt == "What is the capital of France?"
    assert result.candidate_answer == "The capital of France is Paris."


def test_parse_input_rejects_empty_prompt() -> None:
    with pytest.raises(ValidationError):
        parse_input(
            original_prompt="",
            candidate_answer="Paris is the capital of France.",
        )


def test_parse_input_rejects_empty_candidate_answer() -> None:
    with pytest.raises(ValidationError):
        parse_input(
            original_prompt="What is the capital of France?",
            candidate_answer="",
        )


def test_parse_input_rejects_unexpected_fields() -> None:
    with pytest.raises(ValidationError):
        ArbitrationInput(
            original_prompt="Test prompt",
            candidate_answer="Test answer",
            unexpected_field="not allowed",
        )