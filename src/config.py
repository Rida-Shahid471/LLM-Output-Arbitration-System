import os
import math
from dataclasses import dataclass

from dotenv import load_dotenv

from src.errors import ConfigurationError

load_dotenv()


def _integer(name: str, default: int, minimum: int = 0, maximum: int | None = None) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer.") from exc
    if value < minimum:
        raise ConfigurationError(f"{name} must be at least {minimum}.")
    if maximum is not None and value > maximum:
        raise ConfigurationError(f"{name} must be at most {maximum}.")
    return value


def _float(name: str, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be a number.") from exc
    if not math.isfinite(value) or value < minimum or value > maximum:
        raise ConfigurationError(f"{name} must be between {minimum} and {maximum}.")
    return value


@dataclass(frozen=True)
class Settings:
    app_env: str = os.getenv("APP_ENV", "development")
    llm_provider: str = os.getenv("LLM_PROVIDER", "mock").strip().lower()
    llm_model: str = os.getenv("LLM_MODEL") or (
        "claude-sonnet-5" if os.getenv("LLM_PROVIDER", "mock").strip().lower() == "anthropic"
        else os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    )
    factual_provider: str | None = os.getenv("FACTUAL_PROVIDER", "").strip().lower() or None
    logical_provider: str | None = os.getenv("LOGICAL_PROVIDER", "").strip().lower() or None
    completeness_provider: str | None = os.getenv("COMPLETENESS_PROVIDER", "").strip().lower() or None
    factual_model: str | None = os.getenv("FACTUAL_MODEL") or None
    logical_model: str | None = os.getenv("LOGICAL_MODEL") or None
    completeness_model: str | None = os.getenv("COMPLETENESS_MODEL") or None
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY") or None
    anthropic_api_key: str | None = os.getenv("ANTHROPIC_API_KEY") or None
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    llm_timeout_seconds: int = _integer("LLM_TIMEOUT_SECONDS", 60, 1)
    llm_max_retries: int = _integer("LLM_MAX_RETRIES", 2)
    llm_temperature: float = _float("LLM_TEMPERATURE", 0.0, 0.0, 2.0)
    llm_max_output_tokens: int = _integer("LLM_MAX_OUTPUT_TOKENS", 2048, 1, 32768)
    max_provider_input_chars: int = _integer("MAX_PROVIDER_INPUT_CHARS", 100000, 1)
    openai_max_input_chars: int = _integer("OPENAI_MAX_INPUT_CHARS", 100000, 1)
    anthropic_max_input_chars: int = _integer("ANTHROPIC_MAX_INPUT_CHARS", 100000, 1)
    ollama_max_input_chars: int = _integer("OLLAMA_MAX_INPUT_CHARS", 100000, 1)
    openai_max_output_tokens: int = _integer("OPENAI_MAX_OUTPUT_TOKENS", _integer("LLM_MAX_OUTPUT_TOKENS", 2048, 1, 32768), 1, 32768)
    anthropic_max_output_tokens: int = _integer("ANTHROPIC_MAX_OUTPUT_TOKENS", _integer("LLM_MAX_OUTPUT_TOKENS", 2048, 1, 32768), 1, 32768)
    ollama_max_output_tokens: int = _integer("OLLAMA_MAX_OUTPUT_TOKENS", _integer("LLM_MAX_OUTPUT_TOKENS", 2048, 1, 32768), 1, 32768)
    max_prompt_chars: int = _integer("MAX_PROMPT_CHARS", 20000, 1)
    max_answer_chars: int = _integer("MAX_ANSWER_CHARS", 50000, 1)
    max_batch_size: int = _integer("MAX_BATCH_SIZE", 2, 1, 20)
    factual_threshold: int = _integer("FACTUAL_THRESHOLD", 3, 1, 5)
    logical_threshold: int = _integer("LOGICAL_THRESHOLD", 3, 1, 5)
    completeness_threshold: int = _integer("COMPLETENESS_THRESHOLD", 3, 1, 5)
    database_path: str = os.getenv("DATABASE_PATH", "data/arbitrations.sqlite3")
    log_level: str = os.getenv("LOG_LEVEL", "INFO").upper()

    def __post_init__(self) -> None:
        if self.llm_provider not in {"mock", "openai", "anthropic", "ollama"}:
            raise ConfigurationError("LLM_PROVIDER must be mock, openai, anthropic, or ollama.")
        if self.llm_provider == "openai" and not self.openai_api_key:
            raise ConfigurationError("OPENAI_API_KEY is required when LLM_PROVIDER=openai.")
        if self.llm_provider == "anthropic" and not self.anthropic_api_key:
            raise ConfigurationError("ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic.")
        for dimension in (self.factual_provider, self.logical_provider, self.completeness_provider):
            if dimension and dimension not in {"mock", "openai", "anthropic", "ollama"}:
                raise ConfigurationError("Critic providers must be mock, openai, anthropic, or ollama.")
            if dimension == "openai" and not self.openai_api_key:
                raise ConfigurationError("OPENAI_API_KEY is required for a critic configured with the OpenAI provider.")
            if dimension == "anthropic" and not self.anthropic_api_key:
                raise ConfigurationError("ANTHROPIC_API_KEY is required for a critic configured with the Anthropic provider.")

    @property
    def batch_request_timeout_seconds(self) -> int:
        # Per arbitration, three critic calls run concurrently, followed by one
        # adjudicator call. Each can consume the full timeout on every retry.
        worst_case_per_item = 2 * self.llm_timeout_seconds * (self.llm_max_retries + 1)
        return max(900, self.max_batch_size * worst_case_per_item + 60)

    @property
    def single_request_timeout_seconds(self) -> int:
        return max(300, 2 * self.llm_timeout_seconds * (self.llm_max_retries + 1) + 30)

    def provider_input_limit(self, provider: str) -> int:
        return getattr(self, f"{provider}_max_input_chars", self.max_provider_input_chars)

    def provider_output_limit(self, provider: str) -> int:
        return getattr(self, f"{provider}_max_output_tokens", self.llm_max_output_tokens)
settings = Settings()
