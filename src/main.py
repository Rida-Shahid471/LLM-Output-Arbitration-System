import logging

from src.config import settings
from src.llm_client import MockLLMClient
from src.logging_config import setup_logging
from src.utils.request_id import create_request_id


def main() -> None:
    setup_logging(settings.log_level)

    logger = logging.getLogger("arbitration")

    request_id = create_request_id()

    logger.info(
        "Starting arbitration foundation | request_id=%s",
        request_id,
    )

    logger.info(
        "Environment=%s | model=%s | timeout=%s",
        settings.app_env,
        settings.openai_model,
        settings.llm_timeout_seconds,
    )

    client = MockLLMClient()

    response = client.generate(
        prompt="Test prompt for Day 2.",
    )

    logger.info(
        "LLM client response received | request_id=%s",
        request_id,
    )

    print(response)


if __name__ == "__main__":
    main()
    