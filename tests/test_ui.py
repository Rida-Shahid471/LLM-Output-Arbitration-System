from pathlib import Path
import json
import requests
import time
import pytest

from streamlit.testing.v1 import AppTest
from fastapi.testclient import TestClient

from src.api import app as api_app
from src.llm_client import MockLLMClient
from src.storage import ArbitrationStore
from src.workflow import ArbitrationEngine


def _response(prompt: str, system_prompt: str | None) -> str:
    if system_prompt and "adjudicator" in system_prompt.lower():
        return json.dumps({"verdict": "accept", "overall_score": 10, "confidence": 0.9,
                           "confirmed_issues": [], "dismissed_flags": [], "summary": "Reviewed.",
                           "unresolved_disagreements": []})
    lowered = prompt.lower()
    critic = next(x for x in ("factual_accuracy", "logical_consistency", "completeness") if f"evaluate the candidate answer for {x.replace('_', ' ')}" in lowered)
    return json.dumps({"critic_type": critic, "score": 5, "summary": "Reviewed.", "issues": [], "overall_confidence": 0.9})

def test_verdict_explorer_renders_all_primary_workflows() -> None:
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "ui" / "app.py")).run(timeout=15)

    assert not app.exception
    labels = {tab.label for tab in app.tabs}
    assert labels == {"Arbitrate", "Batch", "History", "Analytics"}
    assert any("Mock mode is deterministic" in caption.value for caption in app.caption)


def test_ui_does_not_describe_live_provider_as_mock(monkeypatch) -> None:
    monkeypatch.setenv("ARBITRATION_PROVIDER", "ollama")
    monkeypatch.setenv("ARBITRATION_FACTUAL_PROVIDER", "")
    monkeypatch.setenv("ARBITRATION_LOGICAL_PROVIDER", "")
    monkeypatch.setenv("ARBITRATION_COMPLETENESS_PROVIDER", "")
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "ui" / "app.py")).run(timeout=15)

    assert not app.exception
    captions = [caption.value for caption in app.caption]
    assert any("ollama" in caption for caption in captions)
    assert not any("Mock mode is deterministic" in caption for caption in captions)


def test_ui_single_submission_uses_api_and_renders_stored_result(tmp_path, monkeypatch) -> None:
    engine = ArbitrationEngine(
        llm_client=MockLLMClient(response=_response),
        store=ArbitrationStore(str(tmp_path / "ui-integration.sqlite3")),
    )
    monkeypatch.setattr("src.api._engine", lambda: engine)
    api_client = TestClient(api_app)
    monkeypatch.setattr(requests, "post", lambda url, json, timeout: api_client.post("/v1/arbitrate", json=json))
    monkeypatch.setenv("ARBITRATION_API_URL", "http://testserver")
    page = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "ui" / "app.py")).run(timeout=15)
    page.text_area[0].set_value("What is 2 + 2?")
    page.text_area[1].set_value("2 + 2 = 4.")
    page.button[0].click().run(timeout=15)

    assert not page.exception
    assert engine.store.list()[0].candidate_output == "2 + 2 = 4."
    assert any("Candidate answer" in item.value for item in page.markdown)
    assert any("mock/mock-model" in caption.value for caption in page.caption)


def test_ui_batch_submission_displays_partial_failure(tmp_path, monkeypatch) -> None:
    def response(prompt: str, system_prompt: str | None) -> str:
        time.sleep(0.005)
        if system_prompt and "adjudicator" in system_prompt.lower():
            return json.dumps({"verdict": "revise", "overall_score": 5, "confidence": 0.3,
                               "confirmed_issues": [], "dismissed_flags": [], "summary": "Partial review.",
                               "unresolved_disagreements": []})
        lowered = prompt.lower()
        critic = next(x for x in ("factual_accuracy", "logical_consistency", "completeness") if f"evaluate the candidate answer for {x.replace('_', ' ')}" in lowered)
        if "fail-this-case" in lowered and critic == "logical_consistency":
            return "malformed"
        return json.dumps({"critic_type": critic, "score": 4, "summary": "Reviewed.", "issues": [], "overall_confidence": 0.8})

    engine = ArbitrationEngine(llm_client=MockLLMClient(response=response), store=ArbitrationStore(str(tmp_path / "ui-batch.sqlite3")))
    monkeypatch.setattr("src.api._engine", lambda: engine)
    api_client = TestClient(api_app)
    monkeypatch.setattr(requests, "post", lambda url, json, timeout: api_client.post(url.split("testserver", 1)[-1], json=json))
    monkeypatch.setenv("ARBITRATION_API_URL", "http://testserver")
    page = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "ui" / "app.py")).run(timeout=15)
    page.text_area[2].set_value(json.dumps([
        {"original_prompt": "ordinary", "candidate_answer": "Answer one"},
        {"original_prompt": "fail-this-case", "candidate_answer": "Answer two"},
    ]))
    page.button[1].click().run(timeout=30)

    assert not page.exception
    assert len(engine.store.list()) == 2
    assert any("critic failure" in warning.value.lower() for warning in page.warning)


def test_ui_malformed_batch_response_is_user_visible(monkeypatch) -> None:
    class MalformedResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"not": "a result list"}

    monkeypatch.setattr(requests, "post", lambda *args, **kwargs: MalformedResponse())
    page = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "ui" / "app.py")).run(timeout=15)
    page.text_area[2].set_value("[]")
    page.button[1].click().run(timeout=15)
    assert any("malformed batch response" in error.value.lower() for error in page.error)


def test_ui_api_unavailable_message_is_visible(monkeypatch) -> None:
    def unavailable(*args, **kwargs):
        raise requests.ConnectionError("API offline")

    monkeypatch.setattr(requests, "post", unavailable)
    page = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "ui" / "app.py")).run(timeout=15)
    page.text_area[0].set_value("Question")
    page.text_area[1].set_value("Answer")
    page.button[0].click().run(timeout=15)
    assert any("API request failed" in error.value for error in page.error)


@pytest.mark.parametrize(
    "workflow,expected_message",
    [("single", "API request failed"), ("batch", "Batch request failed")],
)
def test_ui_timeout_message_is_visible(monkeypatch, workflow, expected_message) -> None:
    def timed_out(*args, **kwargs):
        raise requests.Timeout("simulated provider/API timeout")

    monkeypatch.setattr(requests, "post", timed_out)
    page = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "ui" / "app.py")).run(timeout=15)
    if workflow == "single":
        page.text_area[0].set_value("Question")
        page.text_area[1].set_value("Answer")
        page.button[0].click().run(timeout=15)
    else:
        page.text_area[2].set_value(json.dumps([{"original_prompt": "Question", "candidate_answer": "Answer"}]))
        page.button[1].click().run(timeout=15)

    assert not page.exception
    assert any(expected_message in error.value for error in page.error)
    assert any("simulated provider/API timeout" in error.value for error in page.error)


def test_ui_history_pagination_retrieval_and_analytics(tmp_path, monkeypatch) -> None:
    engine = ArbitrationEngine(
        llm_client=MockLLMClient(response=_response),
        store=ArbitrationStore(str(tmp_path / "ui-history.sqlite3")),
    )
    result = engine.arbitrate("Question", "Candidate answer")
    api_client = TestClient(api_app)
    observed_params = []

    def get(url, params=None, timeout=None):
        observed_params.append(params)
        return api_client.get(url.split("testserver", 1)[-1], params=params)

    monkeypatch.setattr("src.api._engine", lambda: engine)
    monkeypatch.setattr(requests, "get", get)
    monkeypatch.setenv("ARBITRATION_API_URL", "http://testserver")
    page = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "ui" / "app.py")).run(timeout=15)
    page.number_input[0].set_value(2)
    page.button[2].click().run(timeout=15)

    assert not page.exception
    assert observed_params[-1] == {"limit": 50, "offset": 50}
    page.text_input[0].set_value(result.arbitration_id)
    page.button[3].click().run(timeout=15)
    assert not page.exception
    assert any("Candidate answer" in markdown.value for markdown in page.markdown)
    page.button[4].click().run(timeout=15)
    assert not page.exception
    assert any(metric.label == "Critic-pair agreement" for metric in page.metric)


def test_ui_http_404_and_validation_errors_are_visible(tmp_path, monkeypatch) -> None:
    api_client = TestClient(api_app)
    def as_requests_response(test_response):
        response = requests.Response()
        response.status_code = test_response.status_code
        response._content = test_response.content
        response.headers.update(test_response.headers)
        response.url = str(test_response.url)
        return response

    monkeypatch.setattr(requests, "get", lambda url, params=None, timeout=None: as_requests_response(api_client.get(url.split("testserver", 1)[-1], params=params)))
    monkeypatch.setattr(requests, "post", lambda url, json, timeout: as_requests_response(api_client.post("/v1/arbitrate", json=json)))
    engine = ArbitrationEngine(llm_client=MockLLMClient(response=_response), store=ArbitrationStore(str(tmp_path / "ui-errors.sqlite3")))
    monkeypatch.setattr("src.api._engine", lambda: engine)
    monkeypatch.setenv("ARBITRATION_API_URL", "http://testserver")
    page = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "ui" / "app.py")).run(timeout=15)
    page.text_input[0].set_value("missing-id")
    page.button[3].click().run(timeout=15)
    assert any("Could not retrieve arbitration" in error.value for error in page.error)
    page.text_area[0].set_value(" ")
    page.text_area[1].set_value("Answer")
    page.button[0].click().run(timeout=15)
    assert any("API request failed" in error.value for error in page.error)
