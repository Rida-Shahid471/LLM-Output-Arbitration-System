# OpenAI provider verification and future evaluation guide

## Verification scope and result

The OpenAI adapter is implemented using the OpenAI Python SDK's Chat Completions JSON mode. Offline verification exercised the SDK through `httpx.MockTransport`; requests were intercepted in memory and were never sent to an OpenAI host. The mock transport verifies request construction, error handling, response parsing, model/provider attribution, and end-to-end use by the critics and adjudicator. These checks establish integration behavior, not real account access or model quality.

No real OpenAI API call was made for this verification. No money or API credits were spent. No real API key was requested or used; tests used only fake local sentinels.

Security note: the local `.env` file was not manually opened or displayed. The original Task 2 test processes imported `src.config` before dotenv loading was disabled; because `.env` exists, `load_dotenv()` may have parsed it into those short-lived process environments. Provider mode was forced to `mock` and both API-key environment variables were explicitly blank, so no real provider call or credential use occurred. Those processes have ended. Task 3's authoritative full-suite rerun retested OpenAI and Anthropic with `PYTHON_DOTENV_DISABLED=1` to prevent dotenv loading.

The project still needs a real-provider run to verify the selected account's model access, live response compatibility, latency, rate limits, and model quality. Model availability and billing status have not been checked.

## Inspected implementation

- `src/llm_client.py`: `OpenAIClient` implements the shared `LLMClient` interface, passes the configured key only to the SDK, uses Chat Completions with JSON-object response format, applies the configured timeout and input/output limits, returns response content, and records the returned model identifier with the configured model as fallback.
- `src/config.py`: `OPENAI_API_KEY` is read from the process environment (with `python-dotenv` loading a local `.env`); OpenAI selection and per-critic OpenAI overrides require a non-empty key. Model selection uses `LLM_MODEL`, falling back to `OPENAI_MODEL` / the example default when unset.
- `src/workflow.py`: the configured client is shared by critics unless a per-critic override is selected; provider/model metadata flows into critic reports and adjudicator results.
- `src/critic_runner.py` and `src/adjudicator.py`: outer retry loops cover provider timeouts, transient provider errors, and invalid model output. The SDK's own retries are disabled so retry count remains controlled by `LLM_MAX_RETRIES`.
- `src/evaluation.py` and `scripts/evaluate.py`: evaluation reports record provider/model and prompt/dataset metadata, skip ambiguous cases, and do not persist evaluation arbitrations.
- `tests/test_llm_clients.py`, `tests/test_critic_runner.py`, `tests/test_adjudicator.py`, `tests/test_workflow.py`, `tests/test_evaluation.py`, and `tests/test_configuration.py`: offline SDK, retry, workflow, dataset, and configuration coverage.
- `.env.example` contains a blank `OPENAI_API_KEY`; `.gitignore` excludes `.env` and related private configuration files. No real `.env` values were inspected.

## Correction made

Provider errors were previously flattened into `LLMProviderError`, and the retry loops retried that base type. Authentication, permission, invalid-request, and missing-model responses cannot generally be corrected by repeating the same request. These are now represented by `LLMNonRetryableProviderError` and stop the outer retry loop. Timeouts, rate limits, connection failures, and malformed model output retain the configured retry behavior. Public error messages contain the provider and error class, not raw provider response text.

The behavior change is limited to permanent request rejections: these no longer consume the configured retry attempts. Transient errors and malformed outputs continue to retry as before. Rate-limit retries are immediate; the project does not currently implement exponential backoff.

## Offline tests and results

All OpenAI adapter tests use only fake keys and local stubs; the SDK-level HTTP integration tests use `httpx.MockTransport` with a `.invalid` mock host. No DNS lookup, external network request, API account, or billing access is involved.

Coverage includes:

- Successful Chat Completions request shape and JSON mode.
- Missing key rejection before request construction.
- Authentication, permission, malformed-request, and rate-limit responses.
- Timeout and connection failures.
- Empty content and malformed wire responses.
- Malformed model JSON and retry exhaustion.
- Secret-bearing error detail redaction.
- Returned model attribution and configured-model fallback.
- A complete three-critic plus adjudicator workflow through the mocked SDK transport.
- Non-retry of permanent provider rejections and retry of transient failures.
- Ambiguous dataset case exclusion from every scored metric.

Verification performed on 2026-11-03:

| Command / check | Result |
|---|---|
| Focused provider/retry/workflow modules (`test_llm_clients.py`, `test_critic_runner.py`, `test_adjudicator.py`, `test_workflow.py`) | 44 passed |
| Full offline test suite with `LLM_PROVIDER=mock`, provider overrides blank, and credentials blank | 106 passed, 0 failed, 4 warnings |
| Warnings | Four Streamlit/Pandas deprecation warnings in the UI history/analytics test; unrelated to OpenAI provider behavior |
| Dataset validator | 21 cases validated; dataset version 1.2.0; one case (`ambiguous_001`) remains ambiguous |
| Human review record | 20 `APPROVE`, 1 `AMBIGUOUS`, 0 corrections |
| Real OpenAI requests / spend | None / none |

The full suite was run in the existing `.qa-venv` with OpenAI and Anthropic credentials explicitly blank and the selected provider set to `mock`. The dedicated SDK tests route their requests exclusively through in-memory `MockTransport` handlers.

## Credential and model configuration for a future run

No credential is needed for offline tests. To prepare a future live run:

1. Copy `.env.example` to `.env` and edit `.env` with a local editor. Keep `.env` private and ignored by Git. Do not paste the key into chat, source code, command history, screenshots, or experiment logs.
2. Set `LLM_PROVIDER=openai`, `LLM_MODEL` to a model identifier currently available to the account, and `OPENAI_API_KEY` locally. The example value `gpt-4o-mini` is a configuration example only; this project has not verified that it is currently available to any particular account.
3. For a bounded first run, set `LLM_MAX_RETRIES=0`, choose conservative `OPENAI_MAX_OUTPUT_TOKENS` and `OPENAI_MAX_INPUT_CHARS`, and use a temporary, versioned pilot dataset containing only a small number of already-reviewed, non-ambiguous cases. Keep the canonical 21-case dataset unchanged.
4. Before running, check the provider account's current model availability, pricing, usage limits, and billing settings. This project does not know whether an account has free credits and does not query account billing.

The live evaluation command is:

```powershell
python -m scripts.evaluate --dataset tmp/openai-pilot.json --output tmp/openai-pilot-report.json
```

**This command will contact the configured OpenAI service and may incur charges.** It was documented only; it was not run as part of this task. The standard dataset has 21 cases, of which one ambiguous case is skipped. A full run therefore evaluates up to 20 cases: three critic requests per case (60 base requests), and up to one adjudicator request per case (20 more; unanimous-good cases can use a local shortcut). Configured retries can multiply attempted requests by as much as `LLM_MAX_RETRIES + 1`, so the rough upper bound is `80 × (LLM_MAX_RETRIES + 1)` requests for the current dataset. A one- or two-case pilot sharply reduces that bound.

## Usage and cost estimation limits

Before any future live run, estimate the sum of input and output tokens for each critic and adjudicator request using the chosen model's current tokenizer and current account pricing. A conceptual estimate is:

```text
estimated cost = Σ(input tokens × current input rate + output tokens × current output rate)
```

Apply this separately for each configured model/provider and include possible retries. The project enforces character budgets and output-token caps, but character counts are not tokenizer counts. It currently does not aggregate provider token usage or calculate cost in evaluation reports. Therefore, its report metadata is useful for reproducibility but is not a billing estimate. Consult the provider's current account/pricing interface before starting a run; no prices or free-credit assumptions are supplied here.

## Distinguishing mock and real results

- Keep `LLM_PROVIDER=mock` for offline wiring tests. Mock judgments are deterministic placeholders and are not model-quality measurements.
- A real evaluation requires an intentional local switch to `LLM_PROVIDER=openai`, a locally configured key, and an account-supported model. The generated report should identify provider `openai`, observed/configured model IDs, dataset version, prompt versions, and timestamp.
- After a real run, inspect every false positive, false negative, critic failure, low-confidence decision, and disagreement. Record the report path, exact model/prompt/dataset versions, settings, and manual findings in `docs/experiment-log.md`; never record the key.
- The `ambiguous_001` case remains skipped and contributes to no scored metric. Its schema-required `accept` value is only a placeholder, not a human-approved quality judgment.

## Remaining limitations

- No real provider request has verified account credentials, account model access, live response compatibility, provider-side rate limits, latency, or model quality.
- Rate-limit/network retries currently have no backoff; set `LLM_MAX_RETRIES=0` for a tightly bounded initial run and increase only after reviewing behavior.
- Exact tokens and costs are not captured by the evaluation report. Add usage accounting before relying on the application for per-run cost reporting.
- The evaluation set is small and cannot support broad benchmark claims. Mock outputs must never be reported as real OpenAI performance.
