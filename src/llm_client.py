from abc import ABC, abstractmethod

from src.errors import LLMProviderError


class LLMClient(ABC):
    """Common interface for all LLM providers."""

    @abstractmethod
    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
    ) -> str:
        """Generate a text response from an LLM."""
        raise NotImplementedError


class MockLLMClient(LLMClient):
    """
    Simple local client used for development and testing.

    It does not call any external API.
    """

    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
    ) -> str:
        return (
            "Mock LLM response. "
            "The real provider integration will be added later."
        )


class OpenAIClient(LLMClient):
    """OpenAI provider implementation."""

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout: int = 60,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
    ) -> str:
        if not self.api_key:
            raise LLMProviderError(
                "OpenAI API key is not configured."
            )

        raise NotImplementedError(
            "OpenAI API call will be implemented in the next stage."
        )


class AnthropicClient(LLMClient):
    """Anthropic provider implementation."""

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout: int = 60,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
    ) -> str:
        if not self.api_key:
            raise LLMProviderError(
                "Anthropic API key is not configured."
            )

        raise NotImplementedError(
            "Anthropic API call will be implemented in the next stage."
        )
    