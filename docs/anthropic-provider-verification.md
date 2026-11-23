# Anthropic provider verification and future evaluation guide

## Status and scope

The Anthropic integration is **implemented and offline-verified**. The application uses the Anthropic Python SDK's Messages API, with a distinct system field and user message, a configured output-token limit, and text-block extraction. The offline checks exercise the installed SDK through its required `httpx2.MockTransport`, including the complete three-critic and adjudicator workflow.

These checks verify local request construction, response handling, error classification, attribution, and workflow compatibility. They do not verify a real Anthropic account, model availability, live service behavior, or model quality. No real Anthropic API request was made, and no money or API credits were spent. No real credential was requested or used; transport tests used only the fake `offline-test-key` sentinel.

Security note: the local `.env` file was not manually opened or displayed. Preliminary test processes imported `src.config` before dotenv loading was disabled; because `.env` exists, `load_dotenv()` may have parsed it into those short-lived process environments. Provider mode was forced to `mock` and both API-key environment variables were explicitly blank, so no real provider call or credential use occurred. Those processes have ended. The authoritative full-suite and dataset checks were rerun with `PYTHON_DOTENV_DISABLED=1` to prevent dotenv loading.

## Implementation inspected

- `src/llm_client.py`: `AnthropicClient` implements the shared `LLMClient` contract. It constructs the SDK `Anthropic` client with the configured timeout and `max_retries=0`, sends `system_prompt` through the Anthropic `system` field and the candidate request as a user message, sets `max_tokens`, and deliberately omits `temperature`. It joins text content blocks, rejects an empty text response, and returns the provider-reported model ID with the configured model as fallback.
- `src/config.py`: `ANTHROPIC_API_KEY` is read from process configuration after normal dotenv loading. Selecting Anthropic globally or for an individual critic requires a non-empty key. `LLM_MODEL` selects the model; critic-specific models use `FACTUAL_MODEL`, `LOGICAL_MODEL`, and `COMPLETENESS_MODEL`.
- `src/workflow.py`: the selected client is used by all three critics and the adjudicator unless per-critic overrides are configured. Provider and observed model metadata flow into critic reports and the final verdict.
- `src/critic_runner.py` and `src/adjudicator.py`: the application retry loop controls retry attempts; SDK-level retries are disabled. Permanent authentication, permission, invalid-request, and missing-model errors stop retries. Rate-limit, timeout, network, and invalid model-output failures retain configured retries.
- `src/evaluation.py` and `scripts/evaluate.py`: evaluation records provider/model, prompt, dataset, and timestamp metadata; it skips ambiguous cases before arbitration and does not persist evaluation arbitrations.
- `.env.example` contains a blank `ANTHROPIC_API_KEY`; `.gitignore` excludes `.env` and private credential files. The example `LLM_MODEL=gpt-4o-mini` is an OpenAI-oriented example and must be replaced with a model identifier currently supported by the user's Anthropic account before a live Anthropic run. This verification did not check model availability.

## Correction made

The Anthropic adapter did not expose the SDK's injectable `http_client`, unlike the OpenAI adapter. The installed Anthropic SDK uses `httpx2` and rejects a standard `httpx.Client`; therefore, the earlier SDK-method stubs could not verify actual Anthropic request construction through an offline HTTP transport. `AnthropicClient` and `create_llm_client` now accept and pass through an optional HTTP client. Normal construction remains unchanged when the argument is omitted. Tests use the SDK-compatible `httpx2.MockTransport`; no network fallback is used by those tests.

No change was made to Anthropic request temperature behavior, dataset content, model defaults, retry counts, or existing provider response semantics. A test suite failure initially came from passing `httpx.Client` to the Anthropic SDK; it was corrected by using its installed `httpx2` dependency. A subsequent test-only input-budget mismatch was fixed by setting the mock harness limit above the actual specialist prompt size.

## Offline verification

Anthropic HTTP tests use a fake key and `httpx2.MockTransport`. The transport handler constructs SDK responses locally and prevents socket/network access. The suite explicitly blanks provider credentials and selects mock mode for the full run.

Coverage includes:

- Successful Messages API request shape, including separate system/user fields, model, and output-token cap.
- Omission of temperature and extraction/concatenation of multiple text blocks.
- Missing API key and configuration-time key validation for global and per-critic use.
- Authentication, permission, invalid-request, missing-model, and rate-limit responses.
- Timeout and connection failures, empty content, malformed wire response, and malformed model JSON.
- Secret-detail redaction and provider/model attribution, including configured-model fallback.
- Rate-limit retry and stopping retries for authentication failure.
- Complete mocked execution of all three critics followed by Anthropic adjudication.
- Dataset validation and ambiguous-case exclusion from scored evaluation.

Verification performed on 2026-11-03:

| Command/check | Result |
|---|---|
| Focused Anthropic adapter, workflow, and configuration selection (`pytest -q tests/test_llm_clients.py -k anthropic ...`) | 19 passed, 19 deselected |
| Full offline project suite with provider set to `mock` and both provider credentials blank | 124 passed, 0 failed, 4 warnings |
| Warnings | Four Streamlit/Pandas deprecation warnings in UI history/analytics tests; unrelated to Anthropic |
| Dataset validator | Dataset v1.2.0 valid: 21 cases |
| Offline fake-engine dataset check | 20 cases evaluated; `ambiguous_001` marked `skipped_ambiguous` |
| Human review record | 20 `APPROVE`, 1 `AMBIGUOUS`, 0 corrections |
| Real Anthropic requests / spend | None / none |

The full suite used the existing `.qa-venv`. A fake-engine dataset run emitted only case counts and the skipped status; its outputs are not model-quality results. The canonical dataset and human review record were not modified. The preserved backup remains present with SHA-256 `008629AE66FF8ECD19EE379A205D861968440C921D648753B0005B1F4129A45E`.

### Final safe offline verification procedure

For any future offline verification, set these variables in PowerShell **before** starting Python. The disabled flag makes `load_dotenv()` return before it searches for or opens `.env`; provider selection is forced to mock and both credential variables are blank:

```powershell
$env:PYTHON_DOTENV_DISABLED = '1'
$env:LLM_PROVIDER = 'mock'
$env:LLM_MODEL = 'offline-test-model'
$env:FACTUAL_PROVIDER = ''
$env:LOGICAL_PROVIDER = ''
$env:COMPLETENESS_PROVIDER = ''
$env:OPENAI_API_KEY = ''
$env:ANTHROPIC_API_KEY = ''
```

From the project directory, run:

```powershell
& .\.qa-venv\Scripts\python.exe -m pytest -q -k anthropic tests/test_llm_clients.py tests/test_workflow.py::test_anthropic_sdk_transport_completes_arbitration_offline tests/test_configuration.py::test_anthropic_configuration_requires_key_for_global_or_critic_provider
& .\.qa-venv\Scripts\python.exe -m pytest -q
& .\.qa-venv\Scripts\python.exe -c "from src.evaluation import load_evaluation_dataset; from pathlib import Path; print(len(load_evaluation_dataset(Path('tests/evaluation_dataset.json'))))"
```

The final safety audit used this launch setup and obtained 19 focused Anthropic tests passed (19 deselected), 124 full-suite tests passed (four existing UI deprecation warnings), and 21 dataset cases validated. A separate fake-engine evaluation of the actual dataset scored 20 cases and reported `ambiguous_001` as `skipped_ambiguous`; it used no provider client.

## Local configuration for a future real evaluation

No API key is needed for offline verification. For a future live run:

1. Copy `.env.example` to `.env` and edit it locally. Keep `.env` ignored by Git. Never paste the key into chat, source files, command history, screenshots, or experiment records.
2. Set `LLM_PROVIDER=anthropic`, `ANTHROPIC_API_KEY` locally, and `LLM_MODEL` to a model identifier currently available to the account. Replace the example `gpt-4o-mini` value; this project has not established which model IDs the account can use.
3. For an initial bounded pilot, use a temporary versioned dataset with one or two already-reviewed, non-ambiguous cases. Keep `tests/evaluation_dataset.json` unchanged. Set `LLM_MAX_RETRIES=0` and conservative `ANTHROPIC_MAX_OUTPUT_TOKENS` and `ANTHROPIC_MAX_INPUT_CHARS` values.
4. Check current account model access, pricing, usage limits, and billing controls before executing. The project does not determine whether free credits or free access are available.

The documented live command is:

```powershell
python -m scripts.evaluate --dataset tmp/anthropic-pilot.json --output tmp/anthropic-pilot-report.json
```

**This command will contact the configured Anthropic service and may incur charges.** It is documented for future use only and was not executed. The canonical dataset has 21 cases, with one ambiguous case skipped and 20 eligible for scoring. A full run uses 60 base critic requests and up to 20 base adjudicator requests (some unanimous-good cases use a local shortcut). With `LLM_MAX_RETRIES=R`, the rough upper bound is `80 × (R + 1)` attempted requests. For the default `R=2`, that is up to 240 attempts. A one- or two-case pilot reduces this bound.

## Usage and cost controls

Estimate the total input and output tokens for each critic and adjudicator using the selected model's tokenizer, then apply the current account pricing to those token totals. Include configured retries and any provider/model overrides. The conceptual estimate is:

```text
estimated cost = Σ(input tokens × current input rate + output tokens × current output rate)
```

The project limits input characters and output tokens, but character counts are not tokenizer counts. The evaluation report does not currently aggregate Anthropic usage tokens or calculate cost, so it is not a billing estimate. Consult the account's current usage/pricing interface before a live run. No price or free-credit claim is made here.

## Distinguishing mock and real results

- `LLM_PROVIDER=mock` runs are deterministic wiring checks and do not judge semantics. Do not present their metrics as Anthropic quality results.
- A future real run requires an intentional local switch to Anthropic, a locally configured key, and a currently supported model ID. The report records configured and observed provider/model IDs, dataset version, prompt versions, and UTC timestamp.
- Review false positives, false negatives, critic failures, low-confidence verdicts, and disagreements. Record the report path, exact model/prompt/dataset versions, settings, and manual findings in `docs/experiment-log.md`; never record the key.
- `ambiguous_001` remains `AMBIGUOUS` and is skipped before arbitration and all scored metrics. The schema's neutral `accept` value is not a verified judgment.

## Remaining limitations

- No real Anthropic account, key, model access, response, latency, or model-quality behavior was verified.
- The SDK uses `httpx2`; the pinned environment includes it through the Anthropic dependency. The offline tests use this SDK-compatible transport rather than standard `httpx`.
- Rate-limit and network retries have no backoff. For a bounded first run, use `LLM_MAX_RETRIES=0` and increase only after reviewing results.
- Token usage and cost are not recorded by the evaluation report. Add usage accounting before relying on the application for cost reporting.
- The 21-case dataset is small and cannot support broad benchmark claims.
