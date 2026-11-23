import json
from typing import Any

from pydantic import ValidationError

from src.errors import CriticResponseError
from src.schemas import CriticReport


def parse_critic_response(raw_response: str) -> CriticReport:
    """Parse and validate a raw LLM critic response."""

    if not raw_response or not raw_response.strip():
        raise CriticResponseError(
            "Critic response is empty."
        )

    content = raw_response.strip()
    if content.startswith("```"):
        content = content.removeprefix("```json").removeprefix("```")
        content = content.removesuffix("```").strip()
    try:
        payload: Any = json.loads(content)
    except json.JSONDecodeError as exc:
        raise CriticResponseError(
            "Critic response is not valid JSON."
        ) from exc

    if not isinstance(payload, dict):
        raise CriticResponseError(
            "Critic response must be a JSON object."
        )

    try:
        return CriticReport.model_validate(payload)
    except ValidationError as exc:
        raise CriticResponseError(
            "Critic response does not match the expected schema."
        ) from exc
