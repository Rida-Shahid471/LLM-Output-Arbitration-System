# Change log

## 2026-11-02 — Roadmap completion pass

- Aligned critic and final verdict Pydantic contracts with the roadmap, connected response parsing, and enforced verbatim candidate evidence.
- Implemented OpenAI, Anthropic, and Ollama-compatible clients, retry/timeout handling, optional per-critic model/provider assignments, and clearly labeled offline mock behavior.
- Added parallel LangGraph orchestration, deterministic disagreement detection, evidence-checked adjudication, partial-failure confidence reduction, and the unanimous-good shortcut.
- Added SQLite audit history, batch/single/history/analytics/health FastAPI routes, a Streamlit verdict explorer, a versioned evaluation dataset/runner, and Docker Compose files.
- Added and expanded tests for schemas, 12 synthetic structured-output examples, SDK request normalization, workflow, persistence, detector, and API. Final offline result: 27 passed.
- Live provider calls and Docker runtime were not exercised; those checks require credentials or a Docker installation.
