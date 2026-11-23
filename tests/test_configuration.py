from pathlib import Path

import yaml
import pytest
from src.config import Settings
from src.errors import ConfigurationError


ROOT = Path(__file__).resolve().parents[1]


def test_compose_uses_docker_specific_ollama_url() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    api_environment = compose["services"]["api"]["environment"]
    example = (ROOT / ".env.example").read_text(encoding="utf-8")

    assert api_environment["OLLAMA_BASE_URL"] == "${OLLAMA_DOCKER_BASE_URL:-http://host.docker.internal:11434/v1}"
    for setting in (
        "LLM_TIMEOUT_SECONDS", "LLM_MAX_RETRIES", "LLM_TEMPERATURE", "FACTUAL_THRESHOLD",
        "LLM_MAX_OUTPUT_TOKENS", "MAX_PROVIDER_INPUT_CHARS", "LOGICAL_THRESHOLD", "COMPLETENESS_THRESHOLD", "MAX_PROMPT_CHARS", "MAX_ANSWER_CHARS",
        "OPENAI_MAX_INPUT_CHARS", "ANTHROPIC_MAX_INPUT_CHARS", "OLLAMA_MAX_INPUT_CHARS",
        "OPENAI_MAX_OUTPUT_TOKENS", "ANTHROPIC_MAX_OUTPUT_TOKENS", "OLLAMA_MAX_OUTPUT_TOKENS",
        "MAX_BATCH_SIZE", "LOG_LEVEL",
    ):
        assert setting in api_environment
    assert "OLLAMA_DOCKER_BASE_URL=http://host.docker.internal:11434/v1" in example
    assert api_environment["MAX_BATCH_SIZE"] == "${MAX_BATCH_SIZE:-2}"
    assert api_environment["LLM_MAX_OUTPUT_TOKENS"] == "${LLM_MAX_OUTPUT_TOKENS:-2048}"
    assert api_environment["MAX_PROVIDER_INPUT_CHARS"] == "${MAX_PROVIDER_INPUT_CHARS:-100000}"
    assert compose["services"]["api"]["ports"] == ["127.0.0.1:8000:8000"]
    assert compose["services"]["ui"]["ports"] == ["127.0.0.1:8501:8501"]
    assert "health/live" in compose["services"]["api"]["healthcheck"]["test"][-1]


def test_default_batch_timeout_covers_configured_worst_case() -> None:
    config = Settings(
        llm_provider="mock", llm_model="mock", openai_api_key=None, anthropic_api_key=None,
        llm_timeout_seconds=60, llm_max_retries=2, max_batch_size=2,
        factual_provider=None, logical_provider=None, completeness_provider=None,
        factual_model=None, logical_model=None, completeness_model=None,
    )
    assert config.batch_request_timeout_seconds >= 2 * 2 * 60 * 3


def test_provider_specific_budgets_are_used_for_provider_clients() -> None:
    config = Settings(
        llm_provider="mock", llm_model="mock", openai_api_key=None, anthropic_api_key=None,
        max_provider_input_chars=9000,
        openai_max_input_chars=8000, anthropic_max_input_chars=7000, ollama_max_input_chars=6000,
        llm_max_output_tokens=1500,
        openai_max_output_tokens=1200, anthropic_max_output_tokens=1000, ollama_max_output_tokens=800,
        factual_provider=None, logical_provider=None, completeness_provider=None,
        factual_model=None, logical_model=None, completeness_model=None,
    )

    assert config.provider_input_limit("openai") == 8000
    assert config.provider_input_limit("anthropic") == 7000
    assert config.provider_input_limit("ollama") == 6000
    assert config.provider_output_limit("openai") == 1200
    assert config.provider_output_limit("anthropic") == 1000
    assert config.provider_output_limit("ollama") == 800


def test_provider_specific_budgets_are_documented_in_compose_and_example() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    api_environment = compose["services"]["api"]["environment"]
    example = (ROOT / ".env.example").read_text(encoding="utf-8")

    for setting in (
        "OPENAI_MAX_INPUT_CHARS", "ANTHROPIC_MAX_INPUT_CHARS", "OLLAMA_MAX_INPUT_CHARS",
        "OPENAI_MAX_OUTPUT_TOKENS", "ANTHROPIC_MAX_OUTPUT_TOKENS", "OLLAMA_MAX_OUTPUT_TOKENS",
    ):
        assert setting in api_environment
        assert f"{setting}=" in example


def test_anthropic_configuration_accepts_temperature_but_client_omits_it() -> None:
    config = Settings(
        llm_provider="anthropic", anthropic_api_key="test-key", llm_temperature=1.5,
        factual_provider=None, logical_provider=None, completeness_provider=None,
        factual_model=None, logical_model=None, completeness_model=None, openai_api_key=None,
    )

    assert config.llm_temperature == 1.5


def test_openai_configuration_requires_key_for_global_or_critic_provider() -> None:
    common = {
        "openai_api_key": None,
        "anthropic_api_key": None,
        "factual_model": None,
        "logical_model": None,
        "completeness_model": None,
        "factual_provider": None,
        "logical_provider": None,
        "completeness_provider": None,
    }

    with pytest.raises(ConfigurationError, match="OPENAI_API_KEY is required"):
        Settings(llm_provider="openai", **common)

    with pytest.raises(ConfigurationError, match="OPENAI_API_KEY is required for a critic"):
        Settings(llm_provider="mock", factual_provider="openai", **{key: value for key, value in common.items() if key != "factual_provider"})


def test_anthropic_configuration_requires_key_for_global_or_critic_provider() -> None:
    common = {
        "openai_api_key": None,
        "anthropic_api_key": None,
        "factual_model": None,
        "logical_model": None,
        "completeness_model": None,
        "factual_provider": None,
        "logical_provider": None,
        "completeness_provider": None,
    }

    with pytest.raises(ConfigurationError, match="ANTHROPIC_API_KEY is required"):
        Settings(llm_provider="anthropic", **common)

    with pytest.raises(ConfigurationError, match="ANTHROPIC_API_KEY is required for a critic"):
        Settings(llm_provider="mock", factual_provider="anthropic", **{key: value for key, value in common.items() if key != "factual_provider"})
