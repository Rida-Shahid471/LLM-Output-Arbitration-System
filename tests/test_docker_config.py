from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def _compose() -> dict:
    return yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))


def test_compose_services_match_application_entrypoints_and_health_route() -> None:
    compose = _compose()
    services = compose["services"]
    assert {"api", "ui"} <= set(services)
    assert services["api"]["build"] == "."
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert 'CMD ["uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000"]' in dockerfile
    health_test = services["api"]["healthcheck"]["test"][-1]
    assert "http://127.0.0.1:8000/v1/health/live" in health_test
    assert '@app.get("/v1/health/live")' in (ROOT / "src/api.py").read_text(encoding="utf-8")
    assert "streamlit" in " ".join(services["ui"]["command"])
    assert "ui/app.py" in " ".join(services["ui"]["command"])


def test_compose_uses_loopback_ports_and_persistent_sqlite_volume() -> None:
    compose = _compose()
    services = compose["services"]
    assert services["api"]["ports"] == ["127.0.0.1:8000:8000"]
    assert services["ui"]["ports"] == ["127.0.0.1:8501:8501"]
    assert services["api"]["environment"]["DATABASE_PATH"] == "/app/data/arbitrations.sqlite3"
    assert services["api"]["volumes"] == ["arbitration-data:/app/data"]
    assert "arbitration-data" in compose["volumes"]


def test_ui_uses_compose_service_name_and_waits_for_healthy_api() -> None:
    ui = _compose()["services"]["ui"]
    assert ui["environment"]["ARBITRATION_API_URL"] == "http://api:8000"
    assert ui["environment"]["ARBITRATION_PROVIDER"] == "${LLM_PROVIDER:-mock}"
    assert ui["environment"]["ARBITRATION_FACTUAL_PROVIDER"] == "${FACTUAL_PROVIDER:-}"
    assert ui["environment"]["ARBITRATION_LOGICAL_PROVIDER"] == "${LOGICAL_PROVIDER:-}"
    assert ui["environment"]["ARBITRATION_COMPLETENESS_PROVIDER"] == "${COMPLETENESS_PROVIDER:-}"
    assert ui["depends_on"]["api"]["condition"] == "service_healthy"


def test_compose_ollama_defaults_to_host_gateway_and_mock_mode() -> None:
    api_environment = _compose()["services"]["api"]["environment"]
    assert api_environment["LLM_PROVIDER"] == "${LLM_PROVIDER:-mock}"
    assert api_environment["OLLAMA_BASE_URL"] == (
        "${OLLAMA_DOCKER_BASE_URL:-http://host.docker.internal:11434/v1}"
    )
    assert api_environment["OPENAI_API_KEY"] == "${OPENAI_API_KEY:-}"
    assert api_environment["ANTHROPIC_API_KEY"] == "${ANTHROPIC_API_KEY:-}"


def test_image_runs_as_non_root_disables_dotenv_and_build_context_excludes_local_data() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    ignore_lines = {
        line.strip() for line in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    assert "FROM python:3.11-slim" in dockerfile
    assert "COPY requirements.lock.txt ./" in dockerfile
    assert "COPY src ./src" in dockerfile
    assert "COPY scripts ./scripts" in dockerfile
    assert "COPY ui ./ui" in dockerfile
    assert "COPY tests/evaluation_dataset.json ./tests/evaluation_dataset.json" in dockerfile
    assert "PYTHON_DOTENV_DISABLED=1" in dockerfile
    assert "USER appuser" in dockerfile
    assert "EXPOSE 8000 8501" in dockerfile
    assert ".env" in ignore_lines
    assert ".env.*" in ignore_lines
    assert ".qa-venv" in ignore_lines
    assert ".venv" in ignore_lines
    assert ".git" in ignore_lines
    assert "data/" in ignore_lines
    assert "tmp/" in ignore_lines
    assert "tests/**" in ignore_lines
    assert "!tests/evaluation_dataset.json" in ignore_lines
    assert not any(line.upper().startswith("COPY .ENV") for line in dockerfile.splitlines())
