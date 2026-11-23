import json
import time
from dataclasses import replace

from fastapi.testclient import TestClient

from src.api import app
from src.config import settings
from src.llm_client import MockLLMClient
from src.storage import ArbitrationStore
from src.workflow import ArbitrationEngine


def test_api_arbitrate_batch_history_and_analytics(tmp_path, monkeypatch) -> None:
    def response(prompt: str, system_prompt: str | None) -> str:
        if system_prompt and "adjudicator" in system_prompt.lower():
            return json.dumps({"verdict": "accept", "overall_score": 10, "confidence": 0.9,
                               "confirmed_issues": [], "dismissed_flags": [], "summary": "Clean.", "unresolved_disagreements": []})
        lowered = prompt.lower()
        critic = next(x for x in ("factual_accuracy", "logical_consistency", "completeness") if f"evaluate the candidate answer for {x.replace('_', ' ')}" in lowered)
        return json.dumps({"critic_type": critic, "score": 5, "summary": "Clear.", "issues": [], "overall_confidence": 0.9})
    engine = ArbitrationEngine(llm_client=MockLLMClient(response=response), store=ArbitrationStore(str(tmp_path / "api.sqlite3")))
    monkeypatch.setattr("src.api._engine", lambda: engine)
    client = TestClient(app)
    assert client.get("/v1/health/live").json() == {"status": "ok"}
    ready = client.get("/v1/health/ready").json()
    assert ready == {"status": "configured", "provider": "mock", "provider_connectivity": "not_checked"}
    assert client.get("/v1/health").json() == ready
    assert "key" not in str(ready).lower()
    single = client.post("/v1/arbitrate", json={"original_prompt": "Question", "candidate_answer": "Answer"})
    assert single.status_code == 200
    arbitration_id = single.json()["arbitration_id"]
    assert client.get(f"/v1/arbitrations/{arbitration_id}").status_code == 200
    assert client.get("/v1/arbitrations/missing").status_code == 404
    batch = client.post("/v1/arbitrate/batch", json={"items": [
        {"original_prompt": "Q1", "candidate_answer": "A1"},
        {"original_prompt": "Q2", "candidate_answer": "A2"},
    ]})
    assert batch.status_code == 200 and len(batch.json()) == 2
    assert len(client.get("/v1/arbitrations").json()) == 3
    assert len(client.get("/v1/arbitrations?limit=1&offset=1").json()) == 1
    assert client.get("/v1/analytics").json()["total_arbitrations"] == 3


def test_api_rejects_empty_values() -> None:
    client = TestClient(app)
    response = client.post("/v1/arbitrate", json={"original_prompt": " ", "candidate_answer": "answer"})
    assert response.status_code == 422


def test_api_rejects_missing_fields_unknown_fields_and_invalid_history_queries() -> None:
    client = TestClient(app)

    missing = client.post("/v1/arbitrate", json={"original_prompt": "Question"})
    extra = client.post("/v1/arbitrate", json={
        "original_prompt": "Question", "candidate_answer": "Answer", "unexpected": True,
    })
    invalid_limit = client.get("/v1/arbitrations?limit=0")
    invalid_offset = client.get("/v1/arbitrations?offset=-1")

    assert missing.status_code == 422
    assert extra.status_code == 422
    assert invalid_limit.status_code == 422
    assert invalid_offset.status_code == 422


def test_api_rejects_prompt_over_configured_character_limit(monkeypatch) -> None:
    monkeypatch.setattr("src.input_parser.settings", replace(settings, max_prompt_chars=4))

    response = TestClient(app).post("/v1/arbitrate", json={
        "original_prompt": "prompt too long", "candidate_answer": "answer",
    })

    assert response.status_code == 422
    assert "exceeds 4 characters" in response.json()["detail"]


def test_batch_validates_all_items_before_persisting_any(tmp_path, monkeypatch) -> None:
    def response(prompt: str, system_prompt: str | None) -> str:
        if system_prompt and "adjudicator" in system_prompt.lower():
            return json.dumps({"verdict": "accept", "overall_score": 9, "confidence": 0.8,
                               "confirmed_issues": [], "dismissed_flags": [], "summary": "Clear.",
                               "unresolved_disagreements": []})
        lowered = prompt.lower()
        critic = next(x for x in ("factual_accuracy", "logical_consistency", "completeness") if f"evaluate the candidate answer for {x.replace('_', ' ')}" in lowered)
        return json.dumps({"critic_type": critic, "score": 4, "summary": "Reviewed.", "issues": [], "overall_confidence": 0.8})

    strict_limits = replace(settings, max_answer_chars=4)
    monkeypatch.setattr("src.input_parser.settings", strict_limits)
    store = ArbitrationStore(str(tmp_path / "batch-validation.sqlite3"))
    engine = ArbitrationEngine(llm_client=MockLLMClient(response=response), store=store)
    monkeypatch.setattr("src.api._engine", lambda: engine)
    client = TestClient(app)

    result = client.post("/v1/arbitrate/batch", json={"items": [
        {"original_prompt": "Q", "candidate_answer": "OK"},
        {"original_prompt": "Q", "candidate_answer": "too long"},
    ]})

    assert result.status_code == 422
    assert store.list() == []


def test_openapi_lists_public_routes() -> None:
    document = TestClient(app).get("/openapi.json").json()

    assert {"/v1/arbitrate", "/v1/arbitrate/batch", "/v1/arbitrations", "/v1/arbitrations/{arbitration_id}", "/v1/analytics", "/v1/health", "/v1/health/live", "/v1/health/ready"} <= set(document["paths"])


def test_batch_limit_returns_consistent_413_and_empty_batch_422(monkeypatch) -> None:
    monkeypatch.setattr("src.api.settings", replace(settings, max_batch_size=2))
    client = TestClient(app)
    item = {"original_prompt": "Q", "candidate_answer": "A"}
    too_many = client.post("/v1/arbitrate/batch", json={"items": [item, item, item]})
    absolute_max = client.post("/v1/arbitrate/batch", json={"items": [item] * 21})
    empty = client.post("/v1/arbitrate/batch", json={"items": []})
    assert too_many.status_code == 413
    assert absolute_max.status_code == 413
    assert empty.status_code == 422


def test_batch_handles_slow_provider_and_partial_critic_failure_atomically(tmp_path, monkeypatch) -> None:
    def response(prompt: str, system_prompt: str | None) -> str:
        time.sleep(0.01)
        if system_prompt and "adjudicator" in system_prompt.lower():
            return json.dumps({"verdict": "revise", "overall_score": 5, "confidence": 0.3,
                               "confirmed_issues": [], "dismissed_flags": [], "summary": "Partial.",
                               "unresolved_disagreements": []})
        lowered = prompt.lower()
        critic = next(x for x in ("factual_accuracy", "logical_consistency", "completeness") if f"evaluate the candidate answer for {x.replace('_', ' ')}" in lowered)
        if "fail-this-case" in lowered and critic == "logical_consistency":
            return "malformed"
        return json.dumps({"critic_type": critic, "score": 4, "summary": "Reviewed.", "issues": [], "overall_confidence": 0.8})

    store = ArbitrationStore(str(tmp_path / "slow-batch.sqlite3"))
    engine = ArbitrationEngine(llm_client=MockLLMClient(response=response), store=store)
    monkeypatch.setattr("src.api._engine", lambda: engine)
    monkeypatch.setattr("src.api.settings", replace(settings, max_batch_size=2))
    client = TestClient(app)
    started = time.perf_counter()
    result = client.post("/v1/arbitrate/batch", json={"items": [
        {"original_prompt": "ordinary", "candidate_answer": "short"},
        {"original_prompt": "fail-this-case", "candidate_answer": "short"},
    ]})
    elapsed = time.perf_counter() - started

    assert result.status_code == 200
    assert len(result.json()) == 2
    assert elapsed >= 0.05
    assert any("logical_consistency" in error for error in result.json()[1]["errors"])
    assert len(store.list()) == 2


def test_batch_database_failure_returns_503_and_rolls_back(tmp_path, monkeypatch) -> None:
    def response(prompt: str, system_prompt: str | None) -> str:
        if system_prompt and "adjudicator" in system_prompt.lower():
            return json.dumps({"verdict": "accept", "overall_score": 9, "confidence": 0.8,
                               "confirmed_issues": [], "dismissed_flags": [], "summary": "Clear.",
                               "unresolved_disagreements": []})
        lowered = prompt.lower()
        critic = next(x for x in ("factual_accuracy", "logical_consistency", "completeness") if f"evaluate the candidate answer for {x.replace('_', ' ')}" in lowered)
        return json.dumps({"critic_type": critic, "score": 4, "summary": "Reviewed.", "issues": [], "overall_confidence": 0.8})

    store = ArbitrationStore(str(tmp_path / "api-atomic.sqlite3"))
    with store._connection() as connection:
        connection.execute("""
            CREATE TRIGGER fail_second_api_insert BEFORE INSERT ON arbitrations
            WHEN (SELECT COUNT(*) FROM arbitrations) >= 1
            BEGIN SELECT RAISE(ABORT, 'deliberate second insert failure'); END;
        """)
    engine = ArbitrationEngine(llm_client=MockLLMClient(response=response), store=store)
    monkeypatch.setattr("src.api._engine", lambda: engine)
    monkeypatch.setattr("src.api.settings", replace(settings, max_batch_size=2))
    client = TestClient(app)
    item = {"original_prompt": "Q", "candidate_answer": "A"}

    result = client.post("/v1/arbitrate/batch", json={"items": [item, item]})

    assert result.status_code == 503
    assert store.list() == []
