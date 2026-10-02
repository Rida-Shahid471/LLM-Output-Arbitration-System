from abc import ABC, abstractmethod
from dataclasses import dataclass

from src.errors import LLMProviderError


@dataclass(frozen=True)
class LLMResponse:
    """Normalized response returned by an LLM provider."""

    content: str
    model: str


class LLMClient(ABC):
    """Common interface for all LLM providers."""

    @abstractmethod
    def generate(
        self,
        *,
        prompt: str,
        system_prompt: str | None = None,
    ) -> LLMResponse:
        """Generate a normalized response from an LLM."""
        raise NotImplementedError


class MockLLMClient(LLMClient):
    """
    Deterministic local client used for development and testing.

    It does not call any external API.
    """

    def __init__(
        self,
        response: str = "Mock LLM response.",
        model: str = "mock-model",
    ) -> None:
        self._response = response
        self._model = model

    def generate(
        self,
        *,
        prompt: str,
        system_prompt: str | None = None,
    ) -> LLMResponse:
        """Return a deterministic local response."""

        return LLMResponse(
            content=self._response,
            model=self._model,
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
        *,
        prompt: str,
        system_prompt: str | None = None,
    ) -> LLMResponse:
        """Generate a response using OpenAI.

        The actual provider API integration will be implemented
        in a later stage.
        """

        if not self.api_key:
            raise LLMProviderError(
                "OpenAI API key is not configured."
            )

        raise NotImplementedError(
            "OpenAI API integration will be implemented "
            "in the next stage."
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
        *,
        prompt: str,
        system_prompt: str | None = None,
    ) -> LLMResponse:
        """Generate a response using Anthropic.

        The actual provider API integration will be implemented
        in a later stage.
        """

        if not self.api_key:
            raise LLMProviderError(
                "Anthropic API key is not configured."
            )

        raise NotImplementedError(
            "Anthropic API integration will be implemented "
            "in the next stage."
        )
    