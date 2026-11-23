import pytest
from dataclasses import replace
from pydantic import ValidationError

from src.config import settings
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


def test_parse_input_accepts_exact_character_limits_and_rejects_overages(monkeypatch) -> None:
    monkeypatch.setattr("src.input_parser.settings", replace(settings, max_prompt_chars=5, max_answer_chars=5))

    accepted = parse_input("12345", "abcde")

    assert accepted.original_prompt == "12345"
    assert accepted.candidate_answer == "abcde"
    with pytest.raises(ValueError, match="Original prompt exceeds 5 characters"):
        parse_input("123456", "abcde")
    with pytest.raises(ValueError, match="Candidate answer exceeds 5 characters"):
        parse_input("12345", "abcdef")
