from abc import ABC, abstractmethod
from dataclasses import dataclass
import json
from typing import Callable
from urllib.parse import urlsplit

import httpx

from src.errors import (
    LLMInputLimitError, LLMNonRetryableProviderError, LLMProviderError,
    LLMResponseError, LLMTimeoutError,
)


@dataclass(frozen=True)
class LLMResponse:
    content: str
    model: str
    provider: str = "unknown"
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class LLMClient(ABC):
    @abstractmethod
    def generate(self, *, prompt: str, system_prompt: str | None = None) -> LLMResponse:
        raise NotImplementedError


class MockLLMClient(LLMClient):
    """Deterministic offline client. A callable may generate responses per prompt."""

    def __init__(self, response: str | Callable[[str, str | None], str] = "Mock LLM response.", model: str = "mock-model") -> None:
        self._response = response
        self.model = model

    def generate(self, *, prompt: str, system_prompt: str | None = None) -> LLMResponse:
        content = self._response(prompt, system_prompt) if callable(self._response) else self._response
        return LLMResponse(content=content, model=self.model, provider="mock")


class OpenAIClient(LLMClient):
    def __init__(self, api_key: str, model: str, timeout: int = 60, base_url: str | None = None, temperature: float = 0.0, max_input_chars: int = 100000, max_output_tokens: int = 2048, http_client=None, provider_name: str = "openai") -> None:
        if not api_key:
            raise LLMProviderError("OpenAI API key is not configured.")
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise LLMProviderError("Install the 'openai' package to use the OpenAI provider.") from exc
        self.model = model
        self.temperature = temperature
        self.max_input_chars = max_input_chars
        self.max_output_tokens = max_output_tokens
        self.provider_name = provider_name
        # Retry budget is enforced in CriticRunner/Adjudicator so malformed
        # structured output and provider errors share one predictable limit.
        self._client = OpenAI(api_key=api_key, timeout=timeout, max_retries=0, base_url=base_url, http_client=http_client)

    def generate(self, *, prompt: str, system_prompt: str | None = None) -> LLMResponse:
        _check_input_budget(prompt, system_prompt, self.max_input_chars)
        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": system_prompt or ""}, {"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=self.temperature,
                max_tokens=self.max_output_tokens,
            )
            content = response.choices[0].message.content
            if not content:
                raise LLMResponseError("OpenAI returned an empty response.")
            usage = getattr(response, "usage", None)
            return LLMResponse(
                content=content, model=getattr(response, "model", None) or self.model,
                provider=self.provider_name,
                prompt_tokens=getattr(usage, "prompt_tokens", None),
                completion_tokens=getattr(usage, "completion_tokens", None),
            )
        except LLMResponseError:
            raise
        except Exception as exc:
            _raise_provider_error("OpenAI", exc)


class AnthropicClient(LLMClient):
    def __init__(self, api_key: str, model: str, timeout: int = 60, temperature: float = 0.0, max_input_chars: int = 100000, max_output_tokens: int = 2048, http_client=None) -> None:
        if not api_key:
            raise LLMProviderError("Anthropic API key is not configured.")
        try:
            from anthropic import Anthropic
        except ImportError as exc:
            raise LLMProviderError("Install the 'anthropic' package to use the Anthropic provider.") from exc
        self.model = model
        self.temperature = temperature
        self.max_input_chars = max_input_chars
        self.max_output_tokens = max_output_tokens
        self._client = Anthropic(api_key=api_key, timeout=timeout, max_retries=0, http_client=http_client)

    def generate(self, *, prompt: str, system_prompt: str | None = None) -> LLMResponse:
        _check_input_budget(prompt, system_prompt, self.max_input_chars)
        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=self.max_output_tokens,
                system=system_prompt or "Return valid JSON only.",
                messages=[{"role": "user", "content": prompt}],
            )
            content = "".join(block.text for block in response.content if getattr(block, "type", None) == "text")
            if not content:
                raise LLMResponseError("Anthropic returned an empty response.")
            usage = getattr(response, "usage", None)
            return LLMResponse(
                content=content, model=getattr(response, "model", None) or self.model,
                provider="anthropic",
                prompt_tokens=getattr(usage, "input_tokens", None),
                completion_tokens=getattr(usage, "output_tokens", None),
            )
        except LLMResponseError:
            raise
        except Exception as exc:
            _raise_provider_error("Anthropic", exc)


def _raise_provider_error(provider: str, exc: Exception) -> None:
    name = type(exc).__name__.lower()
    if any(kind in name for kind in ("authenticationerror", "permissiondeniederror", "badrequesterror", "notfounderror")):
        raise LLMNonRetryableProviderError(f"{provider} request was rejected ({type(exc).__name__}).") from exc
    if "timeout" in name:
        raise LLMTimeoutError(f"{provider} request timed out.") from exc
    raise LLMProviderError(f"{provider} request failed: {type(exc).__name__}.") from exc


def _check_input_budget(prompt: str, system_prompt: str | None, limit: int) -> None:
    actual = len(prompt) + len(system_prompt or "")
    if actual > limit:
        raise LLMInputLimitError(f"Provider input exceeds configured character budget ({actual} > {limit}); request was not sent.")


class OllamaClient(LLMClient):
    """Local Ollama chat client with native JSON-schema constrained output."""

    provider_name = "ollama"
    supports_json_schema = True
    _LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "host.docker.internal"}

    def __init__(self, model: str, base_url: str = "http://localhost:11434/v1", timeout: int = 60,
                 temperature: float = 0.0, max_input_chars: int = 100000,
                 max_output_tokens: int = 2048, http_client=None) -> None:
        parsed = urlsplit(base_url)
        if parsed.scheme not in {"http", "https"} or parsed.hostname not in self._LOCAL_HOSTS:
            raise LLMProviderError("Ollama endpoint must use an approved local host; cloud endpoints are not allowed.")
        path = parsed.path.rstrip("/")
        if path.endswith("/v1"):
            path = path[:-3]
        self.endpoint = f"{parsed.scheme}://{parsed.netloc}{path}/api/chat"
        self.model = model
        self.temperature = temperature
        self.max_input_chars = max_input_chars
        self.max_output_tokens = max_output_tokens
        self.timeout = timeout
        self._http_client = http_client or httpx.Client(timeout=timeout)

    def generate(self, *, prompt: str, system_prompt: str | None = None,
                 json_schema: dict | None = None) -> LLMResponse:
        _check_input_budget(prompt, system_prompt, self.max_input_chars)
        body = {
            "model": self.model,
            "stream": False,
            "format": json_schema or "json",
            "messages": [
                {"role": "system", "content": system_prompt or "Return valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            "options": {"temperature": self.temperature, "num_predict": self.max_output_tokens},
        }
        try:
            response = self._http_client.post(self.endpoint, json=body, timeout=self.timeout)
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError("Ollama local request timed out.") from exc
        except httpx.RequestError as exc:
            raise LLMProviderError(f"Ollama local request failed: {type(exc).__name__}.") from exc
        if response.status_code in {400, 401, 403, 404}:
            detail = "requested model or local request was rejected"
            if response.status_code == 404:
                detail = "requested local model was not found"
            raise LLMNonRetryableProviderError(f"Ollama {detail} (HTTP {response.status_code}).")
        if response.status_code >= 400:
            raise LLMProviderError(f"Ollama local service returned HTTP {response.status_code}.")
        try:
            payload = response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise LLMResponseError("Ollama returned a malformed response.") from exc
        message = payload.get("message") if isinstance(payload, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise LLMResponseError("Ollama returned an empty or unexpected response.")
        prompt_tokens = payload.get("prompt_eval_count")
        completion_tokens = payload.get("eval_count")
        return LLMResponse(
            content=content, model=payload.get("model") or self.model, provider=self.provider_name,
            prompt_tokens=prompt_tokens if isinstance(prompt_tokens, int) else None,
            completion_tokens=completion_tokens if isinstance(completion_tokens, int) else None,
        )


def create_llm_client(provider: str, *, api_key: str | None, model: str, timeout: int = 60, base_url: str | None = None, temperature: float = 0.0, max_input_chars: int = 100000, max_output_tokens: int = 2048, http_client=None) -> LLMClient:
    provider = provider.lower().strip()
    if provider == "mock":
        return MockLLMClient()
    if provider == "openai":
        return OpenAIClient(api_key or "", model, timeout, base_url, temperature, max_input_chars, max_output_tokens, http_client)
    if provider == "anthropic":
        return AnthropicClient(api_key or "", model, timeout, temperature, max_input_chars, max_output_tokens, http_client)
    if provider == "ollama":
        return OllamaClient(model, base_url or "http://localhost:11434/v1", timeout, temperature, max_input_chars, max_output_tokens, http_client)
    raise LLMProviderError(f"Unsupported LLM provider: {provider}")
