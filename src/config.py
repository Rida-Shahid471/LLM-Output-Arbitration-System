import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    app_env: str = os.getenv("APP_ENV", "development")

    openai_api_key: str | None = os.getenv("OPENAI_API_KEY") or None
    anthropic_api_key: str | None = os.getenv("ANTHROPIC_API_KEY") or None

    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    anthropic_model: str = os.getenv(
        "ANTHROPIC_MODEL",
        "claude-3-5-sonnet",
    )

    llm_timeout_seconds: int = int(
        os.getenv("LLM_TIMEOUT_SECONDS", "60")
    )

    llm_max_retries: int = int(
        os.getenv("LLM_MAX_RETRIES", "2")
    )

    factual_threshold: int = int(
        os.getenv("FACTUAL_THRESHOLD", "3")
    )

    logical_threshold: int = int(
        os.getenv("LOGICAL_THRESHOLD", "3")
    )

    completeness_threshold: int = int(
        os.getenv("COMPLETENESS_THRESHOLD", "3")
    )

    log_level: str = os.getenv("LOG_LEVEL", "INFO")


settings = Settings()
