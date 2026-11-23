# Docker Deployment Verification — Task 5

**Date:** 2026-11-12
**Overall status:** **FULLY COMPLETE for the Task 5 local/demo deployment acceptance checks.** Docker Compose configuration, image build, API, UI, isolated SQLite persistence, real host-Ollama inference through Docker, offline regression tests, and documentation were verified. No public deployment or cloud-provider call was made.

## Objective

Prepare and verify the FastAPI service, Streamlit dashboard, SQLite persistence, evaluation runner, and local Ollama provider as a Docker Compose deployment while preserving project data and the Task 4 evaluation.

## Environment

| Check | Result |
|---|---|
| Windows | Windows 11 Pro, build 26200 / DisplayVersion 25H2, x64 (read-only system inventory; registry ProductName was stale) |
| Memory / free disk | 16.86 GB RAM; 251.6 GB free on C: |
| Docker Desktop | Running; Docker reports `OperatingSystem=Docker Desktop` |
| Docker CLI | Docker Desktop CLI was available at its per-user installation location; it was invoked by full path because this verification shell did not have it on `PATH`. The personal installation path is intentionally omitted. |
| Docker client / server | 29.9.3 / 29.9.3; Engine reports Linux containers |
| Docker Compose | v5.7.0 |
| WSL | 3.0.5.0, as verified by the user for this resumption |
| Compose validation | `docker compose --env-file .env.example config --quiet` succeeded; services resolved to `api` and `ui` |
| Docker image build | Both API and UI images built successfully using Compose with parallelism limited to one; the isolated-project rebuild reused cached dependency layers |
| Ollama on host | CLI is not on this shell's PATH, but `http://127.0.0.1:11434/api/tags` responded with installed model `qwen2.5:1.5b`, digest `65ec06548149b04c096a120e4a6da9d4017ea809c91734ea5631e89f96ddc57b`, size 986,061,892 bytes |

The earlier pre-resumption report described Docker/WSL as blocked. This section supersedes that earlier environment snapshot. Docker was accessed directly through its verified per-user CLI. During testing, the API container was explicitly configured for local Ollama; OpenAI and Anthropic credentials were blank and their values were never printed. See [Docker Desktop for Windows system requirements](https://docs.docker.com/desktop/setup/install/windows-install/) and [Microsoft's WSL installation guidance](https://learn.microsoft.com/windows/wsl/install).

## Files inspected

- `Dockerfile`, `docker-compose.yml`, `.dockerignore`
- `README.md`, `requirements.lock.txt`, `requirements.txt`
- `src/api.py`, `src/config.py`, `src/storage.py`, `src/workflow.py`, `src/llm_client.py`
- `ui/app.py`, `scripts/evaluate.py`
- `tests/evaluation_dataset.json`, `docs/evaluation-dataset-review.md`
- `docs/ollama-local-model-evaluation.md`
- Existing Git status (read-only)

The private `.env` was not opened, read, printed, or changed. No Git staging, branch, commit, remote, or history operation was performed.

## Configuration review and changes

### Verified from source

- The Dockerfile uses `python:3.11-slim`, installs the pinned `requirements.lock.txt`, sets `/app` as the working directory, and runs the API with `uvicorn src.api:app` on port 8000.
- The image creates and runs as non-root user `appuser`.
- Compose defines `api` and `ui` services. The UI uses `http://api:8000` inside the Compose network and waits for the API health check.
- Host ports 8000 and 8501 bind to `127.0.0.1`.
- The API health check uses the existing `/v1/health/live` route. This is liveness only and does not prove provider connectivity or readiness of a real model.
- SQLite is configured at `/app/data/arbitrations.sqlite3` and mapped to the named `arbitration-data` volume.
- The Ollama Compose URL defaults to `http://host.docker.internal:11434/v1`; the project’s Ollama client accepts this Docker host alias. Container-to-host reachability and real inference were verified during this task.
- Compose defaults to the mock provider. API keys are environment interpolations rather than hard-coded values. The Dockerfile does not copy `.env`.
- The API uses the Dockerfile `CMD`; the UI overrides it with its Streamlit command. The image exposes both 8000 and 8501.
- No restart policy is configured; Compose’s default is to leave stopped local/demo containers stopped.

### Changes made

- `.dockerignore`: added `.qa-venv`, local `data/`, temporary `tmp/` reports, docs, caches, Git/agent metadata, database files, logs, and test files except `tests/evaluation_dataset.json` required by the image. `.env` and `.env.*` remain excluded.
- `Dockerfile`: set `PYTHON_DOTENV_DISABLED=1` in the image, copied `scripts/` so `python -m scripts.evaluate` is available, and declared both service ports.
- `docker-compose.yml`: the UI now receives non-secret provider labels, including per-critic overrides, so its notice reflects the API's provider configuration without passing API credentials into the UI container.
- `ui/app.py`: replaced the always-visible mock-mode text with provider-aware messaging and shows provider/model attribution on each result.
- `README.md`: documents verified Docker versions, build/start/stop commands, API/UI URLs, SQLite volume behavior, local Ollama host routing, and troubleshooting.
- `tests/test_docker_config.py`: added offline checks for Compose structure, application entrypoints/health route, loopback ports, volume configuration, UI provider labels/networking, Ollama defaults, dotenv protection, and build-context exclusions.
- `tests/test_ui.py`: tests provider-aware notices and provider/model attribution in addition to existing UI regressions.

Compose configuration validation and image builds were run after these checks; see the results below.

## Deployment results

| Component | Status | Evidence / limitation |
|---|---|---|
| Compose schema/config | **Verified** | `docker compose --env-file .env.example config --quiet` exited successfully; resolved services were `api` and `ui` |
| API/UI image builds | **Verified** | `docker compose --parallel 1 --env-file .env.example -p arbitration-task5-verify-20261112 build api ui` completed successfully; locked dependencies installed and images were tagged for the isolated project |
| Container startup | **Verified** | Only the required API and UI services were started; API became healthy, UI remained running; ports bind to `127.0.0.1` |
| FastAPI health/docs | **Verified** | `/v1/health/live` returned `{"status":"ok"}`; `/v1/health/ready` reported provider `ollama` and `provider_connectivity=not_checked`; `/docs` returned HTTP 200 |
| FastAPI workflow and errors | **Verified** | `POST /v1/arbitrate` returned a real Ollama result; history/retrieval and analytics returned the record; unknown ID returned 404; invalid single request and empty batch returned 422; 21-item batch returned documented 413 before arbitration |
| Streamlit dashboard | **Verified** | Host URL returned HTTP 200 and Streamlit content. Browser showed the Arbitration Verdict Explorer, provider-specific `ollama` notice, forms, History and Analytics. Refreshing Analytics loaded the empty-volume state. The UI container reached `http://api:8000/v1/health/live` and received HTTP 200. A real local-model result rendered in the UI. |
| SQLite initialization/schema | **Verified** | Container database `/app/data/arbitrations.sqlite3` initialized with the `arbitrations` table in the isolated named volume |
| SQLite persistence/cleanup | **Verified** | Test row survived `--force-recreate` of the API container and was retrieved afterward. Each temporary record was then deleted by exact ID after confirming it was the only row; final isolated-volume count is zero. |
| Host Ollama / Docker routing | **Verified** | Host Ollama API listed `qwen2.5:1.5b`; container was configured to `http://host.docker.internal:11434/v1`; local model process appeared while inference was running |
| Real Docker inference / end-to-end workflow | **Verified with a documented fallback** | Direct API run returned 3 Ollama critic reports, 4 disagreements, 3 confirmed issues, reject verdict, confidence 0.90, and no errors in 72.86 seconds. Dashboard run returned all 3 critic reports and rendered the final reject verdict; adjudication used the conservative fallback because the model's verdict conflicted with its issue resolutions. |
| Task 4 evaluation | **Preserved** | No dataset-wide evaluation was run; dataset and previous Task 4 result report were not modified |

The dataset loader/validator reported version 1.2.0, 21 cases, 20 scorable cases, and `ambiguous_001` as the only ambiguous case. It was not sent to the inference workflow or included in metrics. No dataset-wide evaluation was run in Task 5, and the human-reviewed labels, review ledger, backup, and prior Task 4 model-quality report were left untouched.

## Security and data safety

- The image does not copy `.env`; `.dockerignore` excludes `.env` and `.env.*`.
- `PYTHON_DOTENV_DISABLED=1` prevents dotenv file loading inside the image.
- Docker build context excludes local databases, evaluation output in `tmp/`, virtual environments, caches, and unrelated test/report files while retaining the dataset the evaluation runner needs.
- Host API/UI ports remain loopback-only.
- The API container runs as `appuser`.
- The API container's effective UID was 1000, and `/app/.env` was absent from the image/container.
- Sanitized container settings showed provider `ollama`, model `qwen2.5:1.5b`, the host gateway endpoint, blank OpenAI/Anthropic credentials, and `PYTHON_DOTENV_DISABLED=1`.
- SQLite records remain in the named volume. `docker compose down` preserves it; `docker compose down -v` would remove volumes and is not part of the documented routine.
- The private `.env` file was never read or modified. No API keys were printed or sent; no OpenAI/Anthropic endpoint or cloud model was called.
- The API has no authentication or rate limiting; the Compose setup is a local/demo configuration, not public deployment authorization.

## Tests and checks

All Python commands used `.qa-venv\Scripts\python.exe` with `PYTHON_DOTENV_DISABLED=1` set before launch.

| Command/check | Result |
|---|---|
| `docker compose --env-file .env.example config --quiet` | Passed; services `api`, `ui` |
| `docker compose --parallel 1 --env-file .env.example build` | API and UI images built; locked dependencies installed. Build emitted the standard pip-as-root warning and pip upgrade notice only. |
| Isolated `docker compose ... up -d --no-build api ui` | API healthy; UI running; loopback ports 8000 and 8501 |
| API HTTP checks | Liveness/readiness, `/docs`, arbitration, history/retrieval, analytics, 404, single-input 422, empty-batch 422, and over-limit batch 413 verified; analytics remained at 0 after validation-only requests |
| Dashboard checks | HTTP 200; visible form/tabs/provider label; History and Analytics views; UI-to-API HTTP 200; real result rendered |
| SQLite test | Database table initialized; exact test row persisted across API container recreation; exact row removed; final count 0 |
| Docker Ollama request 1 | 3 critic reports; 4 disagreements; adjudicator provider/model Ollama/qwen2.5:1.5b; reject, 0.90 confidence, 3 confirmed issues, 0 errors; 72.86 seconds |
| Docker Ollama request 2 (dashboard) | 3 critic reports and 4 disagreements; rendered reject, score 1/10, confidence 0.35. Adjudicator response failed consistency validation, so application fallback was displayed. |
| Focused UI + Docker tests | `pytest -q -p no:cacheprovider tests/test_ui.py tests/test_docker_config.py`: 15 passed, 0 failed; 4 Pandas warnings |
| Full offline test suite | `pytest -q -p no:cacheprovider`: 140 passed, 0 failed, 0 skipped; 4 existing Pandas/Streamlit deprecation warnings |
| Host `pip check` | No broken requirements found |
| Container `pip check` | No broken requirements found |
| Dataset validator | Version 1.2.0; 21 total; 20 scorable; ambiguous `ambiguous_001` excluded |
| Evaluation runner in image | `python -m scripts.evaluate --help` succeeded with dotenv disabled; no dataset-wide evaluation was run |

One initial `up --no-build` attempt used isolated project tags that had not yet been built and failed with “No such image.” The API/UI images were then built under the same isolated Compose project name using cached layers, after which startup succeeded. A PowerShell quoting error in a read-only SQLite metadata command was corrected; it did not modify data. No actual test failure was hidden or converted into a skip.

## Reproduction commands and verified configuration

The Task 5 verification used an isolated project name and explicit safe environment file to avoid implicit `.env` loading:

```powershell
$docker = (Get-Command docker -ErrorAction Stop).Source
$env:LLM_PROVIDER = 'ollama'
$env:LLM_MODEL = 'qwen2.5:1.5b'
$env:OLLAMA_DOCKER_BASE_URL = 'http://host.docker.internal:11434/v1'
$env:OPENAI_API_KEY = ''
$env:ANTHROPIC_API_KEY = ''
& $docker compose --env-file .env.example config --quiet
& $docker compose --parallel 1 --env-file .env.example -p arbitration-task5-verify-20261112 build api ui
& $docker compose --env-file .env.example -p arbitration-task5-verify-20261112 up -d api ui
& $docker compose --env-file .env.example -p arbitration-task5-verify-20261112 ps
Invoke-RestMethod http://127.0.0.1:8000/v1/health/live
Invoke-RestMethod http://127.0.0.1:8000/v1/health/ready
Invoke-WebRequest http://127.0.0.1:8000/docs
Invoke-WebRequest http://127.0.0.1:8501
```

The real synthetic test prompt was `What is the capital of Australia?` with candidate answer `The capital of Australia is Sydney.` It was submitted through both the API and UI, then test records were removed by exact IDs from the isolated volume. The Compose stack is currently left running under `arbitration-task5-verify-20261112`; no volumes were removed. `docker compose down` without `-v` stops it while retaining the isolated volume. Never use `down -v` against a volume containing data to preserve.

## Remaining requirements and final status

**Task 5 local/demo acceptance criteria are met.** Docker build, Compose startup, API, UI, isolated SQLite persistence, real host-Ollama inference, an end-to-end workflow, and offline tests all passed. One of the two real local requests used a fallback because the small model returned an adjudication that contradicted its issue resolutions; this is an observed model limitation, not a deployment failure. Exact provider request counts are not available in the current runtime telemetry, so this report does not assert a total request count beyond the three critic outputs and adjudicator outcome shown in the results.

No manual system action is required for Task 5 verification. The stack remains available at `http://127.0.0.1:8000` and `http://127.0.0.1:8501`. Keep the local/demo ports loopback-only; public deployment is outside this task and needs a separate security review.
