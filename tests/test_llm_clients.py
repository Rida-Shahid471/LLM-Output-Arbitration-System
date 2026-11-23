import json
from types import SimpleNamespace

import pytest
import httpx
import httpx2

from src.critic_runner import CriticRunner
from src.errors import (
    CriticResponseError,
    LLMInputLimitError, LLMNonRetryableProviderError, LLMProviderError,
    LLMResponseError, LLMTimeoutError,
)
from src.input_parser import parse_input
from src.llm_client import AnthropicClient, MockLLMClient, OllamaClient, OpenAIClient, _raise_provider_error, create_llm_client
from src.input_parser import parse_input
from src.schemas import CriticType


def test_mock_client_returns_normalized_response() -> None:
    client = MockLLMClient(response="ok", model="mock-example")
    response = client.generate(prompt="test")
    assert response.content == "ok"
    assert response.model == "mock-example"
    assert client.model == "mock-example"


def test_provider_clients_initialize_without_network_calls() -> None:
    assert OpenAIClient("test-key", "test-model").model == "test-model"
    assert AnthropicClient("test-key", "test-model").model == "test-model"
    ollama = create_llm_client("ollama", api_key=None, model="local-model")
    assert isinstance(ollama, OllamaClient)
    assert ollama.provider_name == "ollama"


def test_openai_request_is_normalized_without_network() -> None:
    client = OpenAIClient("test-key", "test-model", temperature=0.25, max_output_tokens=777)
    calls = {}

    def create(**kwargs):
        calls.update(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"score":5}'))], model="actual-openai-model")

    client._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    response = client.generate(prompt="review", system_prompt="system")
    assert response.content == '{"score":5}'
    assert response.model == "actual-openai-model"
    assert response.provider == "openai"
    assert calls["response_format"] == {"type": "json_object"}
    assert calls["temperature"] == 0.25
    assert calls["max_tokens"] == 777
    assert calls["messages"][0] == {"role": "system", "content": "system"}


def test_anthropic_request_omits_unsupported_temperature_parameter() -> None:
    client = AnthropicClient("test-key", "test-model", temperature=0.25, max_output_tokens=888)
    calls = {}

    def create(**kwargs):
        calls.update(kwargs)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text='{"score":4}')], model="actual-anthropic-model")

    client._client = SimpleNamespace(messages=SimpleNamespace(create=create))
    response = client.generate(prompt="review", system_prompt="system")
    assert response.content == '{"score":4}'
    assert response.model == "actual-anthropic-model"
    assert response.provider == "anthropic"
    assert calls["model"] == "test-model"
    assert calls["max_tokens"] == 888
    assert "temperature" not in calls


def test_timeout_errors_are_classified_without_leaking_exception_text() -> None:
    with pytest.raises(LLMTimeoutError, match="OpenAI request timed out"):
        _raise_provider_error("OpenAI", TimeoutError("private provider detail"))


def test_ollama_native_request_is_local_and_never_receives_openai_key() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers.get("authorization")
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={
            "model": "actual-local-model", "message": {"role": "assistant", "content": '{"ok":true}'},
            "prompt_eval_count": 1, "eval_count": 2,
        }, request=request)

    transport = httpx.Client(transport=httpx.MockTransport(handler))
    client = create_llm_client(
        "ollama", api_key="sk-openai-secret-that-must-not-leak", model="configured-local",
        base_url="http://127.0.0.1:11434/v1", http_client=transport,
    )

    schema = {"type": "object", "required": ["ok"], "properties": {"ok": {"type": "boolean"}}}
    response = client.generate(prompt="review", system_prompt="system", json_schema=schema)

    assert captured["authorization"] is None
    assert captured["url"] == "http://127.0.0.1:11434/api/chat"
    assert captured["body"]["format"] == schema
    assert captured["body"]["messages"] == [
        {"role": "system", "content": "system"}, {"role": "user", "content": "review"},
    ]
    assert captured["body"]["options"]["num_predict"] == client.max_output_tokens
    assert response.provider == "ollama"
    assert response.model == "actual-local-model"
    assert response.prompt_tokens == 1
    assert response.completion_tokens == 2
    transport.close()


def test_ollama_rejects_nonlocal_endpoint() -> None:
    with pytest.raises(LLMProviderError, match="local host"):
        create_llm_client("ollama", api_key=None, model="local-model", base_url="https://ollama.com/v1")


@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_ollama_rejected_requests_are_nonretryable(status: int) -> None:
    transport = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(status, request=request)))
    client = create_llm_client("ollama", api_key=None, model="local-model", http_client=transport)
    with pytest.raises(LLMNonRetryableProviderError):
        client.generate(prompt="review")
    transport.close()


def test_ollama_malformed_and_empty_responses_are_rejected() -> None:
    malformed = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b"not-json", request=request)))
    client = create_llm_client("ollama", api_key=None, model="local-model", http_client=malformed)
    with pytest.raises(LLMResponseError, match="malformed"):
        client.generate(prompt="review")
    malformed.close()

    empty = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"message": {"content": ""}}, request=request)))
    client = create_llm_client("ollama", api_key=None, model="local-model", http_client=empty)
    with pytest.raises(LLMResponseError, match="empty or unexpected"):
        client.generate(prompt="review")
    empty.close()


def test_ollama_timeout_and_connection_failures_are_classified() -> None:
    timeout = httpx.Client(transport=httpx.MockTransport(lambda request: (_ for _ in ()).throw(httpx.ReadTimeout("private timeout", request=request))))
    client = create_llm_client("ollama", api_key=None, model="local-model", http_client=timeout)
    with pytest.raises(LLMTimeoutError, match="Ollama local request timed out"):
        client.generate(prompt="review")
    timeout.close()

    connection = httpx.Client(transport=httpx.MockTransport(lambda request: (_ for _ in ()).throw(httpx.ConnectError("private network detail", request=request))))
    client = create_llm_client("ollama", api_key=None, model="local-model", http_client=connection)
    with pytest.raises(LLMProviderError, match="Ollama local request failed: ConnectError") as error:
        client.generate(prompt="review")
    assert "private network detail" not in str(error.value)
    connection.close()


def test_provider_input_budget_fails_before_request() -> None:
    client = OpenAIClient("test-key", "test-model", max_input_chars=5)
    called = False

    def create(**kwargs):
        nonlocal called
        called = True

    client._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    with pytest.raises(LLMInputLimitError, match="request was not sent"):
        client.generate(prompt="too long")
    assert not called


def _chat_completion_response(request: httpx.Request, content: str | None, model: str = "returned-openai-model") -> httpx.Response:
    return httpx.Response(200, json={
        "id": "chatcmpl-offline", "object": "chat.completion", "created": 1,
        "model": model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }, request=request)


def _openai_mock_client(handler, *, timeout: float = 1.0) -> tuple[OpenAIClient, httpx.Client]:
    transport = httpx.Client(transport=httpx.MockTransport(handler))
    client = OpenAIClient(
        "offline-test-key", "configured-test-model", timeout=timeout,
        base_url="https://openai-mock.invalid/v1", http_client=transport,
    )
    return client, transport


def test_openai_http_transport_success_and_attribution_are_offline() -> None:
    observed = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed["url"] = str(request.url)
        observed["authorization"] = request.headers.get("authorization")
        observed["payload"] = json.loads(request.content)
        return _chat_completion_response(request, '{"score":5}')

    client, transport = _openai_mock_client(handler)
    try:
        result = client.generate(prompt="offline prompt", system_prompt="offline system")
    finally:
        transport.close()

    assert observed["url"] == "https://openai-mock.invalid/v1/chat/completions"
    assert observed["authorization"] == "Bearer offline-test-key"
    assert observed["payload"]["model"] == "configured-test-model"
    assert observed["payload"]["response_format"] == {"type": "json_object"}
    assert result.content == '{"score":5}'
    assert result.provider == "openai"
    assert result.model == "returned-openai-model"


def test_openai_requires_api_key_without_constructing_a_request() -> None:
    with pytest.raises(LLMProviderError, match="API key is not configured"):
        OpenAIClient("", "configured-test-model")


@pytest.mark.parametrize(
    "status_code,error_type,expected_type",
    [
        (401, "authentication_error", LLMNonRetryableProviderError),
        (403, "permission_error", LLMNonRetryableProviderError),
        (400, "invalid_request_error", LLMNonRetryableProviderError),
        (429, "rate_limit_error", LLMProviderError),
    ],
)
def test_openai_http_errors_are_classified_and_redacted(status_code, error_type, expected_type) -> None:
    secret_detail = "provider-response-private-detail"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={"error": {
            "message": secret_detail, "type": error_type, "code": error_type,
        }}, request=request)

    client, transport = _openai_mock_client(handler)
    try:
        with pytest.raises(expected_type) as caught:
            client.generate(prompt="offline prompt")
    finally:
        transport.close()

    assert secret_detail not in str(caught.value)
    assert "offline-test-key" not in str(caught.value)
    if status_code == 429:
        assert not isinstance(caught.value, LLMNonRetryableProviderError)


@pytest.mark.parametrize(
    "transport_error,expected_type",
    [
        (httpx.ReadTimeout("private-timeout-detail"), LLMTimeoutError),
        (httpx.ConnectError("private-network-detail"), LLMProviderError),
    ],
)
def test_openai_transport_failures_are_typed_without_exposing_details(transport_error, expected_type) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise transport_error

    client, transport = _openai_mock_client(handler)
    try:
        with pytest.raises(expected_type) as caught:
            client.generate(prompt="offline prompt")
    finally:
        transport.close()

    assert "private-" not in str(caught.value)
    assert "offline-test-key" not in str(caught.value)


def test_openai_empty_response_is_a_sanitized_response_error() -> None:
    client, transport = _openai_mock_client(lambda request: _chat_completion_response(request, ""))
    try:
        with pytest.raises(LLMResponseError, match="empty response"):
            client.generate(prompt="offline prompt")
    finally:
        transport.close()


def test_openai_model_attribution_falls_back_to_configured_model() -> None:
    client = OpenAIClient("offline-test-key", "configured-test-model")
    client._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content='{"score":5}'))], model=None,
    ))))

    result = client.generate(prompt="offline prompt")

    assert result.model == "configured-test-model"
    assert result.provider == "openai"


def test_openai_rate_limit_retries_through_critic_runner_offline() -> None:
    calls = 0
    critic_json = json.dumps({
        "critic_type": "factual_accuracy", "score": 4,
        "summary": "No factual issue found.", "issues": [], "overall_confidence": 0.8,
    })

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, json={"error": {"message": "temporary throttle", "type": "rate_limit_error"}}, request=request)
        return _chat_completion_response(request, critic_json)

    client, transport = _openai_mock_client(handler)
    try:
        report = CriticRunner(client, max_retries=1).run(
            critic_type=CriticType.FACTUAL_ACCURACY,
            arbitration_input=parse_input("Question", "Candidate"),
        )
    finally:
        transport.close()

    assert calls == 2
    assert report.provider == "openai"
    assert report.model == "returned-openai-model"


def test_openai_malformed_model_json_is_retried_then_safely_rejected() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return _chat_completion_response(request, "not valid JSON")

    client, transport = _openai_mock_client(handler)
    try:
        with pytest.raises(CriticResponseError, match="not valid JSON"):
            CriticRunner(client, max_retries=1).run(
                critic_type=CriticType.FACTUAL_ACCURACY,
                arbitration_input=parse_input("Question", "Candidate"),
            )
    finally:
        transport.close()

    assert calls == 2


def test_openai_unexpected_wire_response_is_not_returned_as_model_content() -> None:
    client, transport = _openai_mock_client(lambda request: httpx.Response(200, json={"unexpected": "private-detail"}, request=request))
    try:
        with pytest.raises(LLMProviderError) as caught:
            client.generate(prompt="offline prompt")
    finally:
        transport.close()

    assert "private-detail" not in str(caught.value)


def _anthropic_message_response(request: httpx2.Request, text_blocks: list[str], model: str = "returned-anthropic-model") -> httpx2.Response:
    return httpx2.Response(200, json={
        "id": "msg_offline", "type": "message", "role": "assistant",
        "content": [{"type": "text", "text": text} for text in text_blocks],
        "model": model, "stop_reason": "end_turn", "stop_sequence": None,
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }, request=request)


def _anthropic_mock_client(handler, *, timeout: float = 1.0) -> tuple[AnthropicClient, httpx2.Client]:
    transport = httpx2.Client(transport=httpx2.MockTransport(handler))
    client = create_llm_client(
        "anthropic", api_key="offline-test-key", model="configured-anthropic-model",
        timeout=timeout, temperature=0.35, max_input_chars=10000,
        max_output_tokens=777, http_client=transport,
    )
    assert isinstance(client, AnthropicClient)
    return client, transport


def test_anthropic_sdk_http_transport_uses_messages_format_and_combines_text_blocks() -> None:
    observed = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        observed["url"] = str(request.url)
        observed["api_key"] = request.headers.get("x-api-key")
        observed["authorization"] = request.headers.get("authorization")
        observed["payload"] = json.loads(request.content)
        return _anthropic_message_response(request, ['{"score":', '4}'])

    client, transport = _anthropic_mock_client(handler)
    try:
        result = client.generate(prompt="offline user prompt", system_prompt="offline system prompt")
    finally:
        transport.close()

    assert observed["url"].endswith("/v1/messages")
    assert observed["api_key"] == "offline-test-key"
    assert observed["authorization"] is None
    assert observed["payload"]["model"] == "configured-anthropic-model"
    assert observed["payload"]["system"] == "offline system prompt"
    assert observed["payload"]["messages"] == [{"role": "user", "content": "offline user prompt"}]
    assert observed["payload"]["max_tokens"] == 777
    assert "temperature" not in observed["payload"]
    assert result.content == '{"score":4}'
    assert result.provider == "anthropic"
    assert result.model == "returned-anthropic-model"


def test_anthropic_requires_api_key_without_constructing_a_request() -> None:
    with pytest.raises(LLMProviderError, match="Anthropic API key is not configured"):
        AnthropicClient("", "configured-anthropic-model")


def test_anthropic_sdk_timeout_and_retry_settings_are_explicit(monkeypatch) -> None:
    import anthropic

    captured = {}

    def fake_client(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace()

    monkeypatch.setattr(anthropic, "Anthropic", fake_client)

    AnthropicClient("offline-test-key", "configured-anthropic-model", timeout=23)

    assert captured["timeout"] == 23
    assert captured["max_retries"] == 0


@pytest.mark.parametrize(
    "status_code,error_type,expected_type",
    [
        (401, "authentication_error", LLMNonRetryableProviderError),
        (403, "permission_error", LLMNonRetryableProviderError),
        (400, "invalid_request_error", LLMNonRetryableProviderError),
        (404, "not_found_error", LLMNonRetryableProviderError),
        (429, "rate_limit_error", LLMProviderError),
    ],
)
def test_anthropic_http_errors_are_classified_and_redacted(status_code, error_type, expected_type) -> None:
    private_detail = "anthropic-provider-private-detail"

    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(status_code, json={
            "type": "error", "error": {"type": error_type, "message": private_detail},
        }, request=request)

    client, transport = _anthropic_mock_client(handler)
    try:
        with pytest.raises(expected_type) as caught:
            client.generate(prompt="offline prompt")
    finally:
        transport.close()

    assert private_detail not in str(caught.value)
    assert "offline-test-key" not in str(caught.value)
    if status_code == 429:
        assert not isinstance(caught.value, LLMNonRetryableProviderError)


@pytest.mark.parametrize(
    "transport_error,expected_type",
    [
        (httpx2.ReadTimeout("private-anthropic-timeout"), LLMTimeoutError),
        (httpx2.ConnectError("private-anthropic-network-error"), LLMProviderError),
    ],
)
def test_anthropic_transport_failures_are_typed_and_redacted(transport_error, expected_type) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise transport_error

    client, transport = _anthropic_mock_client(handler)
    try:
        with pytest.raises(expected_type) as caught:
            client.generate(prompt="offline prompt")
    finally:
        transport.close()

    assert "private-anthropic" not in str(caught.value)
    assert "offline-test-key" not in str(caught.value)


def test_anthropic_empty_content_is_a_response_error() -> None:
    client, transport = _anthropic_mock_client(lambda request: _anthropic_message_response(request, []))
    try:
        with pytest.raises(LLMResponseError, match="empty response"):
            client.generate(prompt="offline prompt")
    finally:
        transport.close()


def test_anthropic_model_attribution_falls_back_to_configured_model() -> None:
    client = AnthropicClient("offline-test-key", "configured-anthropic-model")
    client._client = SimpleNamespace(messages=SimpleNamespace(create=lambda **kwargs: SimpleNamespace(
        content=[SimpleNamespace(type="text", text='{"score":4}')], model=None,
    )))

    result = client.generate(prompt="offline prompt")

    assert result.model == "configured-anthropic-model"
    assert result.provider == "anthropic"


def test_anthropic_unexpected_wire_response_is_sanitized() -> None:
    client, transport = _anthropic_mock_client(lambda request: httpx2.Response(200, json={"private-detail": "untrusted"}, request=request))
    try:
        with pytest.raises(LLMProviderError) as caught:
            client.generate(prompt="offline prompt")
    finally:
        transport.close()

    assert "untrusted" not in str(caught.value)
    assert "offline-test-key" not in str(caught.value)


def test_anthropic_rate_limit_retries_through_critic_runner_offline() -> None:
    calls = 0
    report_json = json.dumps({
        "critic_type": "factual_accuracy", "score": 4,
        "summary": "No factual issue found.", "issues": [], "overall_confidence": 0.8,
    })

    def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx2.Response(429, json={
                "type": "error", "error": {"type": "rate_limit_error", "message": "throttled"},
            }, request=request)
        return _anthropic_message_response(request, [report_json])

    client, transport = _anthropic_mock_client(handler)
    try:
        report = CriticRunner(client, max_retries=1).run(
            critic_type=CriticType.FACTUAL_ACCURACY,
            arbitration_input=parse_input("Question", "Candidate"),
        )
    finally:
        transport.close()

    assert calls == 2
    assert report.provider == "anthropic"
    assert report.model == "returned-anthropic-model"


def test_anthropic_authentication_failure_is_not_retried_by_critic_runner() -> None:
    calls = 0

    def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        return httpx2.Response(401, json={
            "type": "error", "error": {"type": "authentication_error", "message": "private"},
        }, request=request)

    client, transport = _anthropic_mock_client(handler)
    try:
        with pytest.raises(LLMNonRetryableProviderError):
            CriticRunner(client, max_retries=3).run(
                critic_type=CriticType.FACTUAL_ACCURACY,
                arbitration_input=parse_input("Question", "Candidate"),
            )
    finally:
        transport.close()

    assert calls == 1


def test_anthropic_malformed_model_json_retries_then_is_rejected() -> None:
    calls = 0

    def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        return _anthropic_message_response(request, ["not valid JSON"])

    client, transport = _anthropic_mock_client(handler)
    try:
        with pytest.raises(CriticResponseError, match="not valid JSON"):
            CriticRunner(client, max_retries=1).run(
                critic_type=CriticType.FACTUAL_ACCURACY,
                arbitration_input=parse_input("Question", "Candidate"),
            )
    finally:
        transport.close()

    assert calls == 2
