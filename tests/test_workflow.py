import json
from dataclasses import replace
from pathlib import Path
from threading import Barrier, BrokenBarrierError

import httpx
import httpx2

from src.llm_client import AnthropicClient, MockLLMClient, OllamaClient, OpenAIClient
from src.config import settings
from src.storage import ArbitrationStore
from src.workflow import ArbitrationEngine


def clean_response(prompt: str, system_prompt: str | None) -> str:
    if system_prompt and "adjudicator" in system_prompt.lower():
        return json.dumps({"verdict": "accept", "overall_score": 10, "confidence": 0.9,
                           "confirmed_issues": [], "dismissed_flags": [], "summary": "All good.",
                           "unresolved_disagreements": []})
    lowered = prompt.lower()
    critic_type = next(x for x in ("factual_accuracy", "logical_consistency", "completeness") if f"evaluate the candidate answer for {x.replace('_', ' ')}" in lowered)
    return json.dumps({"critic_type": critic_type, "score": 5, "summary": "No issues found.", "issues": [], "overall_confidence": 0.9})


def test_parallel_pipeline_shortcut_and_persistence(tmp_path) -> None:
    store = ArbitrationStore(str(tmp_path / "audit.sqlite3"))
    engine = ArbitrationEngine(llm_client=MockLLMClient(response=clean_response), store=store)
    result = engine.arbitrate("What is 2 + 2?", "2 + 2 = 4.")
    assert len(result.critic_reports) == 3, result.errors
    assert result.final_verdict.overall_score == 10
    assert result.timings_ms["total"] >= 0
    assert result.timings_ms["disagreement_detection_ms"] >= 0
    assert result.timings_ms["adjudication_ms"] >= 0
    assert store.get(result.arbitration_id) == result
    assert store.analytics()["total_arbitrations"] == 1
    assert result.critic_prompt_version == "critic-prompts-v3"
    assert result.adjudicator_prompt_version == "adjudicator-prompt-v3"
    assert {report.provider for report in result.critic_reports} == {"mock"}
    assert result.final_verdict.adjudicator_provider == "system_shortcut"


def test_workflow_detects_disagreement_and_adjudicates_exact_evidence() -> None:
    def response(prompt: str, system_prompt: str | None) -> str:
        if system_prompt and "adjudicator" in system_prompt.lower():
            return json.dumps({
                "verdict": "revise", "overall_score": 4, "confidence": 0.8,
                "confirmed_issues": [{
                    "critic_type": "factual_accuracy",
                    "issue": {
                        "category": "factual_error", "description": "Sydney is not Australia's capital.",
                        "evidence": "Sydney", "severity": "high", "confidence": 0.9,
                    },
                }],
                "dismissed_flags": [], "summary": "The cited claim is incorrect.",
                "unresolved_disagreements": [],
            })
        lowered = prompt.lower()
        critic = next(x for x in ("factual_accuracy", "logical_consistency", "completeness") if f"evaluate the candidate answer for {x.replace('_', ' ')}" in lowered)
        if critic == "factual_accuracy":
            issues = [{
                "category": "fact", "description": "Sydney is not Australia's capital.",
                "evidence": "Sydney", "severity": "high", "confidence": 0.9,
            }]
            score = 2
        else:
            issues = []
            score = 4
        return json.dumps({
            "critic_type": critic, "score": score, "summary": "Reviewed.",
            "issues": issues, "overall_confidence": 0.8,
        })

    result = ArbitrationEngine(llm_client=MockLLMClient(response=response), persist=False).arbitrate(
        "What is Australia's capital?", "Sydney",
    )

    assert len(result.critic_reports) == 3
    assert len(result.disagreements) >= 1
    assert result.final_verdict.verdict.value == "revise"
    assert len(result.final_verdict.confirmed_issues) == 1
    assert result.final_verdict.confirmed_issues[0].issue.evidence == "Sydney"
    assert result.final_verdict.unresolved_disagreements == []
    assert result.errors == []


def test_unanimous_good_shortcut_skips_adjudicator() -> None:
    def response(prompt: str, system_prompt: str | None) -> str:
        if system_prompt and "adjudicator" in system_prompt.lower():
            raise AssertionError("Unanimous-good shortcut should not call adjudicator.")
        lowered = prompt.lower()
        critic_type = next(x for x in ("factual_accuracy", "logical_consistency", "completeness") if f"evaluate the candidate answer for {x.replace('_', ' ')}" in lowered)
        return json.dumps({"critic_type": critic_type, "score": 5, "summary": "Clean.", "issues": [], "overall_confidence": 0.9})

    result = ArbitrationEngine(llm_client=MockLLMClient(response=response), persist=False).arbitrate("Q", "A")

    assert result.final_verdict.verdict.value == "accept"
    assert result.errors == []


def test_four_portfolio_cases_complete_offline_pipeline() -> None:
    demo_cases = json.loads((Path(__file__).parent / "demo_cases.json").read_text(encoding="utf-8"))
    engine = ArbitrationEngine(llm_client=MockLLMClient(response=clean_response), persist=False)

    results = [engine.arbitrate(case["prompt"], case["candidate_output"]) for case in demo_cases]

    assert {case["type"] for case in demo_cases} == {"factual_error", "logical_flaw", "incomplete", "good"}
    assert len(results) == 4
    assert all(len(result.critic_reports) == 3 and not result.errors for result in results)


def test_failed_critic_does_not_stop_other_critics(tmp_path) -> None:
    def response(prompt: str, system_prompt: str | None) -> str:
        if system_prompt and "adjudicator" in system_prompt.lower():
            return json.dumps({"verdict": "revise", "overall_score": 6, "confidence": 0.95,
                               "confirmed_issues": [], "dismissed_flags": [], "summary": "Partial review.",
                               "unresolved_disagreements": []})
        lowered = prompt.lower()
        critic_type = next(x for x in ("factual_accuracy", "logical_consistency", "completeness") if f"evaluate the candidate answer for {x.replace('_', ' ')}" in lowered)
        if critic_type == "logical_consistency":
            return "malformed"
        return json.dumps({"critic_type": critic_type, "score": 4, "summary": "Reviewed.", "issues": [], "overall_confidence": 0.8})

    engine = ArbitrationEngine(llm_client=MockLLMClient(response=response), store=ArbitrationStore(str(tmp_path / "audit.sqlite3")))
    result = engine.arbitrate("Prompt", "Answer")
    assert len(result.critic_reports) == 2
    assert any("logical_consistency" in error for error in result.errors)
    assert result.final_verdict.confidence <= 0.5


def test_provider_created_per_critic_mock_uses_valid_mock_reports(monkeypatch) -> None:
    mock_settings = replace(
        settings,
        llm_provider="mock",
        llm_model="mock-model",
        factual_provider="mock",
        factual_model="mock-factual",
        logical_provider=None,
        logical_model=None,
        completeness_provider=None,
        completeness_model=None,
    )
    monkeypatch.setattr("src.workflow.settings", mock_settings)
    engine = ArbitrationEngine(persist=False)

    result = engine.arbitrate("Question", "Candidate answer")

    assert len(result.critic_reports) == 3
    assert result.errors == []
    assert engine.provider == "mock"


def test_per_critic_ollama_override_never_receives_openai_credential(monkeypatch) -> None:
    openai_settings = replace(
        settings, llm_provider="openai", llm_model="hosted-model",
        openai_api_key="OPENAI_SECRET_SENTINEL", anthropic_api_key=None,
        factual_provider="ollama", factual_model="local-model",
        logical_provider=None, logical_model=None,
        completeness_provider=None, completeness_model=None,
    )
    observed = []

    def factory(provider: str, **kwargs):
        observed.append((provider, kwargs.get("api_key")))
        return MockLLMClient()

    monkeypatch.setattr("src.workflow.settings", openai_settings)
    monkeypatch.setattr("src.workflow.create_llm_client", factory)

    ArbitrationEngine(persist=False)

    assert ("openai", "OPENAI_SECRET_SENTINEL") in observed
    assert ("ollama", None) in observed


def test_provider_input_budget_rejects_before_any_llm_call(monkeypatch) -> None:
    calls = 0

    def response(prompt: str, system_prompt: str | None) -> str:
        nonlocal calls
        calls += 1
        return "{}"

    monkeypatch.setattr("src.workflow.settings", replace(settings, max_provider_input_chars=20))
    engine = ArbitrationEngine(llm_client=MockLLMClient(response=response), persist=False)

    try:
        engine.arbitrate("A prompt too long for the configured test budget", "answer")
    except ValueError as exc:
        assert "no provider request was sent" in str(exc)
    else:
        raise AssertionError("Oversized input should fail before the graph invokes a client.")

    assert calls == 0


def test_langgraph_runs_critic_calls_concurrently() -> None:
    critics_started = Barrier(3, timeout=5)

    def response(prompt: str, system_prompt: str | None) -> str:
        if system_prompt and "adjudicator" in system_prompt.lower():
            return json.dumps({"verdict": "revise", "overall_score": 5, "confidence": 0.5,
                               "confirmed_issues": [], "dismissed_flags": [], "summary": "Reviewed.",
                               "unresolved_disagreements": []})
        lowered = prompt.lower()
        critic_type = next(x for x in ("factual_accuracy", "logical_consistency", "completeness") if f"evaluate the candidate answer for {x.replace('_', ' ')}" in lowered)
        try:
            critics_started.wait()
        except BrokenBarrierError:
            raise AssertionError("Critic calls were executed sequentially.")
        return json.dumps({"critic_type": critic_type, "score": 3, "summary": "Reviewed.", "issues": [], "overall_confidence": 0.5})

    result = ArbitrationEngine(llm_client=MockLLMClient(response=response), persist=False).arbitrate("Q", "A")

    assert len(result.critic_reports) == 3
    assert result.errors == []


def test_openai_sdk_transport_completes_arbitration_offline() -> None:
    captured = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        captured.append({"url": str(request.url), "authorization": request.headers.get("authorization"), "payload": payload})
        system_prompt = payload["messages"][0]["content"].lower()
        user_prompt = payload["messages"][1]["content"].lower()
        if "evidence-based adjudicator" in system_prompt:
            content = json.dumps({
                "verdict": "revise", "overall_score": 4, "confidence": 0.8,
                "confirmed_issues": [{"critic_type": "factual_accuracy", "issue": {
                    "category": "factual_error", "description": "The capital claim is incorrect.",
                    "evidence": "Sydney", "severity": "high", "confidence": 0.9,
                }}],
                "dismissed_flags": [], "summary": "The reported factual issue is supported.",
                "unresolved_disagreements": [], "rationale": "The answer conflicts with known geography.",
            })
        else:
            critic_type = next(
                kind for kind in ("factual_accuracy", "logical_consistency", "completeness")
                if f"evaluate the candidate answer for {kind.replace('_', ' ')}" in user_prompt
            )
            issues = ([{
                "category": "factual_error", "description": "The capital claim is incorrect.",
                "evidence": "Sydney", "severity": "high", "confidence": 0.9,
            }] if critic_type == "factual_accuracy" else [])
            content = json.dumps({
                "critic_type": critic_type, "score": 2 if issues else 4,
                "summary": "A test-only offline critic result.", "issues": issues,
                "overall_confidence": 0.9,
            })
        return httpx.Response(200, json={
            "id": "chatcmpl-offline-workflow", "object": "chat.completion", "created": 1,
            "model": "returned-offline-model",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 20, "total_tokens": 40},
        }, request=request)

    transport = httpx.Client(transport=httpx.MockTransport(handler))
    client = OpenAIClient(
        "offline-test-key", "configured-offline-model", base_url="https://openai-mock.invalid/v1",
        http_client=transport,
    )
    try:
        result = ArbitrationEngine(llm_client=client, persist=False).arbitrate(
            "What is Australia's capital?", "Sydney",
        )
    finally:
        transport.close()

    assert len(captured) == 4  # Three critics plus one adjudicator; every request hit MockTransport.
    assert all(call["url"].startswith("https://openai-mock.invalid/") for call in captured)
    assert all(call["authorization"] == "Bearer offline-test-key" for call in captured)
    assert len(result.critic_reports) == 3
    assert result.errors == []
    assert {report.provider for report in result.critic_reports} == {"openai"}
    assert {report.model for report in result.critic_reports} == {"returned-offline-model"}
    assert result.final_verdict.verdict.value == "revise"
    assert result.final_verdict.adjudicator_provider == "openai"
    assert result.final_verdict.adjudicator_model == "returned-offline-model"
    assert result.final_verdict.confirmed_issues[0].issue.evidence == "Sydney"


def test_anthropic_sdk_transport_completes_arbitration_offline() -> None:
    captured = []

    def message_response(request: httpx2.Request, content: str) -> httpx2.Response:
        return httpx2.Response(200, json={
            "id": "msg_offline_workflow", "type": "message", "role": "assistant",
            "content": [{"type": "text", "text": content}],
            "model": "returned-anthropic-offline-model", "stop_reason": "end_turn", "stop_sequence": None,
            "usage": {"input_tokens": 20, "output_tokens": 20},
        }, request=request)

    def handler(request: httpx2.Request) -> httpx2.Response:
        payload = json.loads(request.content)
        captured.append({"url": str(request.url), "api_key": request.headers.get("x-api-key"), "payload": payload})
        system_prompt = payload["system"].lower()
        user_prompt = payload["messages"][0]["content"].lower()
        if "evidence-based adjudicator" in system_prompt:
            content = json.dumps({
                "verdict": "revise", "overall_score": 4, "confidence": 0.8,
                "confirmed_issues": [{"critic_type": "factual_accuracy", "issue": {
                    "category": "factual_error", "description": "The capital claim is incorrect.",
                    "evidence": "Sydney", "severity": "high", "confidence": 0.9,
                }}],
                "dismissed_flags": [], "summary": "The reported factual issue is supported.",
                "unresolved_disagreements": [], "rationale": "The answer conflicts with known geography.",
            })
        else:
            critic_type = next(
                kind for kind in ("factual_accuracy", "logical_consistency", "completeness")
                if f"evaluate the candidate answer for {kind.replace('_', ' ')}" in user_prompt
            )
            issues = ([{
                "category": "factual_error", "description": "The capital claim is incorrect.",
                "evidence": "Sydney", "severity": "high", "confidence": 0.9,
            }] if critic_type == "factual_accuracy" else [])
            content = json.dumps({
                "critic_type": critic_type, "score": 2 if issues else 4,
                "summary": "A test-only offline critic result.", "issues": issues,
                "overall_confidence": 0.9,
            })
        return message_response(request, content)

    transport = httpx2.Client(transport=httpx2.MockTransport(handler))
    client = AnthropicClient(
        "offline-test-key", "configured-anthropic-model", http_client=transport,
    )
    try:
        result = ArbitrationEngine(llm_client=client, persist=False).arbitrate(
            "What is Australia's capital?", "Sydney",
        )
    finally:
        transport.close()

    assert len(captured) == 4  # Three critics and one adjudicator, intercepted by MockTransport.
    assert all(call["url"].endswith("/v1/messages") for call in captured)
    assert all(call["api_key"] == "offline-test-key" for call in captured)
    assert len(result.critic_reports) == 3
    assert result.errors == []
    assert {report.provider for report in result.critic_reports} == {"anthropic"}
    assert {report.model for report in result.critic_reports} == {"returned-anthropic-offline-model"}
    assert result.final_verdict.verdict.value == "revise"
    assert result.final_verdict.adjudicator_provider == "anthropic"
    assert result.final_verdict.adjudicator_model == "returned-anthropic-offline-model"
    assert result.final_verdict.confirmed_issues[0].issue.evidence == "Sydney"


def test_ollama_native_json_schema_transport_completes_arbitration_offline() -> None:
    captured = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        captured.append({"url": str(request.url), "authorization": request.headers.get("authorization"), "payload": payload})
        system_prompt = payload["messages"][0]["content"].lower()
        user_prompt = payload["messages"][1]["content"].lower()
        if "evidence-based adjudicator" in system_prompt:
            adjudication_input = json.loads(payload["messages"][1]["content"])
            content = json.dumps({
                "verdict": "revise", "overall_score": 4, "confidence": 0.8,
                "summary": "The reported factual issue is supported.", "rationale": "Offline fixture.",
                "recommended_revision": None,
                "resolutions": [{"issue_id": item["issue_id"], "decision": "confirm", "reason": "Supported."}
                                for item in adjudication_input["critic_findings"]],
                "unresolved_disagreement_ids": [],
            })
        else:
            critic_type = next(
                kind for kind in ("factual_accuracy", "logical_consistency", "completeness")
                if f"evaluate the candidate answer for {kind.replace('_', ' ')}" in user_prompt
            )
            issues = ([{
                "category": "factual_error", "description": "The capital claim is incorrect.",
                "evidence": "Sydney", "severity": "high", "confidence": 0.9,
            }] if critic_type == "factual_accuracy" else [])
            content = json.dumps({
                "critic_type": critic_type, "score": 2 if issues else 4,
                "summary": "Offline transport fixture only.", "issues": issues,
                "overall_confidence": 0.9,
            })
        return httpx.Response(200, json={
            "model": "returned-ollama-offline-model",
            "message": {"role": "assistant", "content": content},
            "prompt_eval_count": 20, "eval_count": 20,
        }, request=request)

    transport = httpx.Client(transport=httpx.MockTransport(handler))
    client = OllamaClient("configured-ollama-model", "http://127.0.0.1:11434/v1", http_client=transport)
    try:
        result = ArbitrationEngine(llm_client=client, persist=False).arbitrate(
            "What is Australia's capital?", "Sydney",
        )
    finally:
        transport.close()

    assert len(captured) == 4
    assert all(call["url"] == "http://127.0.0.1:11434/api/chat" for call in captured)
    assert all(call["authorization"] is None for call in captured)
    assert all(isinstance(call["payload"]["format"], dict) for call in captured)
    assert all("resolutions" in call["payload"]["format"]["properties"] for call in captured if "evidence-based adjudicator" in call["payload"]["messages"][0]["content"].lower())
    assert len(result.critic_reports) == 3
    assert result.errors == []
    assert {report.provider for report in result.critic_reports} == {"ollama"}
    assert {report.model for report in result.critic_reports} == {"returned-ollama-offline-model"}
    assert result.final_verdict.verdict.value == "revise"
    assert result.final_verdict.adjudicator_provider == "ollama"
    assert result.final_verdict.adjudicator_model == "returned-ollama-offline-model"
