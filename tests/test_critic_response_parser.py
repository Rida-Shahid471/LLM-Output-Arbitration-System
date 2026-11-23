import json

import pytest

from src.critic_response_parser import parse_critic_response
from src.errors import CriticResponseError
from src.schemas import CriticType


def test_parses_valid_report_and_json_fence() -> None:
    payload = {"critic_type": CriticType.FACTUAL_ACCURACY.value, "score": 4,
               "summary": "Mostly accurate.", "issues": [], "overall_confidence": 0.9}
    report = parse_critic_response("```json\n" + json.dumps(payload) + "\n```")
    assert report.score == 4


def test_parses_twelve_structured_output_examples() -> None:
    for index in range(12):
        critic_type = list(CriticType)[index % len(CriticType)]
        payload = {
            "critic_type": critic_type.value,
            "score": index % 5 + 1,
            "summary": f"Synthetic schema example {index}.",
            "issues": [],
            "overall_confidence": (index % 10) / 10,
        }
        assert parse_critic_response(json.dumps(payload)).critic_type == critic_type


@pytest.mark.parametrize("raw", ["", "not json", "[]", "{}"])
def test_rejects_invalid_report(raw: str) -> None:
    with pytest.raises(CriticResponseError):
        parse_critic_response(raw)
