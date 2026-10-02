from pydantic import BaseModel, ConfigDict, Field, ValidationError


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

    return ArbitrationInput(
        original_prompt=original_prompt,
        candidate_answer=candidate_answer,
    )