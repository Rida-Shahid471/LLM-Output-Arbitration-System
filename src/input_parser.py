from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.config import settings


class ArbitrationInput(BaseModel):
    """Validated input entering the arbitration pipeline."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    original_prompt: str = Field(
        min_length=1,
        description="Original user prompt.",
    )

    candidate_answer: str = Field(
        min_length=1,
        description="Candidate answer produced by an LLM.",
    )


def parse_input(
    original_prompt: str,
    candidate_answer: str,
) -> ArbitrationInput:
    """Validate and construct an arbitration input object."""

    parsed = ArbitrationInput(
        original_prompt=original_prompt,
        candidate_answer=candidate_answer,
    )
    if len(parsed.original_prompt) > settings.max_prompt_chars:
        raise ValueError(f"Original prompt exceeds {settings.max_prompt_chars} characters.")
    if len(parsed.candidate_answer) > settings.max_answer_chars:
        raise ValueError(f"Candidate answer exceeds {settings.max_answer_chars} characters.")
    return parsed
