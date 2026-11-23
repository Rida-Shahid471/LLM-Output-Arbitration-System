# Ollama Local Model Evaluation

## Result summary

On 2026-11-06, the project ran the real arbitration workflow on the local Ollama model `qwen2.5:1.5b` against evaluation dataset version `1.2.0`. The runner processed all 20 approved/scorable cases and skipped `ambiguous_001` before arbitration. The model is genuinely connected to the application; this report describes a local model run, not a mock evaluation.

The run demonstrates working local provider selection, three-critic execution, adjudication, JSON output parsing, and result export. It also shows poor verdict quality on this small dataset: the clean-answer false-positive rate was high and only three of fourteen scored verdicts agreed with the approved reference. These results do not support a claim of general model accuracy.

## Hardware and Ollama

| Item | Verified value |
|---|---|
| Operating system | Windows 10 Pro |
| CPU | Intel Core i7-1255U, 12th generation |
| RAM | 15.7 GB installed; approximately 4–5 GB available before inference |
| GPU | Integrated Intel Iris Xe; inference used CPU (`size_vram=0`) |
| Free disk at model selection | More than 260 GB |
| Ollama version during evaluation | 0.40.14 |
| Model | `qwen2.5:1.5b`, Q4_K_M, 1.5B parameters |
| Model file size | 986,061,892 bytes (about 986 MB) |
| Model digest | `65ec06548149b04c096a120e4a6da9d4017ea809c91734ea5631e89f96ddc57b` |

The Ollama CLI was found at `%LOCALAPPDATA%\Programs\Ollama\ollama.exe`; after refreshing the verification shell from the existing user PATH, `where.exe ollama`, `ollama --version`, and `ollama list` succeeded. The full evaluation used Ollama 0.40.14. During a later check on 2026-11-11, the CLI temporarily reported `upgrade in progress` and the loopback endpoint refused connections while `OllamaSetup.exe` was active. The update then completed; Ollama 0.40.16, the local model inventory, and the loopback API were verified, and a local telemetry smoke test succeeded.

The initial plain-text and JSON smoke prompts returned local responses. Available memory declined from about 4.3 GB to 3.2 GB after inference; the model's process working set was around 1.2–1.6 GB. The laptop handled the run, but CPU inference was slow. Do not infer GPU acceleration from this test.

## Integration and safety

The application uses the `ollama` provider and sends requests to the local endpoint only. The verified evaluation used `http://127.0.0.1:11434/v1` configuration, with no OpenAI or Anthropic credentials. The model name was a local model tag, not a cloud tag. Ollama's device/account connection did not change the application's request destination: prompts went to loopback.

`src/llm_client.py` implements the Ollama client with native local structured-output requests, model attribution, token-usage parsing, request budgets, timeouts, and local-service error handling. The same client was used by all three critics and the adjudicator. `tests/test_llm_clients.py` and the workflow transport tests verify request construction and error behavior offline. The full real run verified that provider/model attribution appeared on critic and adjudicator outputs.

The local client rejects non-loopback hostnames except the configured Docker Desktop host name used by the container path. Do not use a cloud endpoint for this local evaluation. No OpenAI or Anthropic API call was made, and no paid API service or credit was used.

## Dataset and method

- Dataset: `tests/evaluation_dataset.json`, version `1.2.0`.
- Total cases: 21.
- Human-approved scorable cases: 20.
- Ambiguous cases skipped: 1 (`ambiguous_001`).
- Human review record: 20 `APPROVE`, 1 `AMBIGUOUS`; no approved semantic labels were changed for this run.
- Critic and adjudicator prompts: `critic-prompts-v3` and `adjudicator-prompt-v3`.
- Provider/model: Ollama / `qwen2.5:1.5b`.
- Temperature: 0.
- Output budget: 1,024 tokens per provider request.
- Persistence: the evaluation CLI exported a JSON report and used `persist=False`, so the application database was not changed by this run.

The full local report, including each case's critic findings, disagreements, adjudicator output, confidence, issue categories, and errors, is stored in the ignored local artifact `tmp/ollama-qwen2.5-1.5b-dataset-v1.2.0-20261103.json`. The temporary report is not tracked by Git. Its generated timestamp is 2026-11-06 08:54:10 +05:00.

## Measured results

Issue detection counts compare whether any of the three critics reported at least one issue with the human-reviewed `has_issue` value. They do not measure whether each issue category was exactly right.

| Metric | Result | Denominator / note |
|---|---:|---|
| Evaluated cases | 20 / 20 | 1 ambiguous case skipped before arbitration |
| Coverage | 1.0000 | 20 evaluated / 20 eligible |
| True positives | 13 | |
| False positives | 6 | Six of seven clean cases were flagged |
| False negatives | 0 | |
| True negatives | 1 | |
| Precision | 0.6842 | 13 / 19 predicted-positive cases |
| Recall | 1.0000 | 13 / 13 issue cases |
| F1 | 0.8125 | Derived from precision and recall |
| Clean-answer false-positive rate | 0.8571 | 6 / 7 clean cases |
| Verdict agreement | 0.2143 | 3 / 14; adjudication fallback cases excluded |
| Average confidence | 0.7321 | 14 verdicts; fallback cases excluded |
| Cases with adjudication fallback | 6 / 20 | Five local verdict/issue-resolution consistency failures and one local request timeout |
| Cases with critic failures | 0 / 20 | All 20 produced three critic reports |
| Reported error rate | 0.3000 | The implementation counts adjudication fallback cases as failed cases; interpret this as a combined fallback/error rate |

The model frequently over-reported `incomplete_answer` and `unsupported_claim`. It predicted an issue in 19 of 20 cases, including six of the seven clean cases. It returned `reject` for 19 scored cases and `accept` for one; only three of fourteen non-fallback verdicts matched the reference. This is poor calibration and excessive false-positive behavior for this dataset.

Per-case final verdicts (the full report contains each case's detailed critic and adjudicator payloads):

| Case | Expected | Local verdict | Issue predicted | Adjudication fallback |
|---|---|---|---:|---:|
| `fact_false_001` | reject | reject | yes | no |
| `logic_001` | revise | reject | yes | no |
| `incomplete_001` | revise | reject | yes | no |
| `clean_001` | accept | reject | yes | yes |
| `mixed_001` | revise | reject | yes | no |
| `ambiguous_001` | unscored | skipped | — | — |
| `fact_false_002` | reject | reject | yes | yes |
| `fact_true_001` | accept | reject | yes | yes |
| `logic_002` | revise | reject | yes | no |
| `logic_003` | revise | reject | yes | no |
| `incomplete_002` | revise | reject | yes | yes |
| `complete_001` | accept | reject | yes | no |
| `mixed_002` | revise | reject | yes | no |
| `clean_002` | accept | reject | yes | no |
| `clean_003` | accept | reject | yes | yes |
| `fact_false_003` | reject | reject | yes | no |
| `fact_true_002` | accept | accept | no | no |
| `incomplete_003` | revise | reject | yes | yes |
| `logic_004` | revise | reject | yes | no |
| `format_001` | accept | reject | yes | no |
| `format_002` | revise | reject | yes | no |

## Timing and usage limitations

The report recorded 226,622.013 seconds total and 11,331.1 seconds per case. One case (`logic_004`) alone recorded 221,162.298 seconds, far beyond the configured request timeout. The timer includes an anomalous interval and is not a credible measure of active inference latency. Do not use the reported total, mean, or that case duration as a performance benchmark. The other 19 recorded case durations total 5,459.709 seconds (mean 287.353 seconds), but these remain machine/session wall-clock measurements rather than controlled throughput measurements.

The stored aggregate request and token telemetry is incomplete. The evaluation wrapper was applied after LangGraph captured its critic client references, so the saved report counted adjudicator-client attempts but missed calls made by the three critics. Its recorded 28 requests, 26 successful requests, 2 failed requests, and 30,254 returned tokens are therefore not full-run totals and must not be cited as total evaluation usage. The evaluator instrumentation has since been fixed to rebuild the graph after wrapping clients. An offline regression test verifies that four calls (three critics plus adjudicator) are tracked. After Ollama's update completed, a real one-case local telemetry verification succeeded with four successful calls and 2,934 returned tokens. That smoke test verifies telemetry plumbing only; it does not repair the full-run report's missing critic usage or change its scored metrics.

Ollama returned token usage for successful responses during the original run, but because critic calls were missing from the tracker those totals cannot be reliably reconstructed from the saved aggregate. No total-token claim is made here.

## Setup and reproduction

Prerequisites: install Ollama from its official Windows installer, open a new PowerShell after PATH changes, ensure `ollama list` shows `qwen2.5:1.5b`, and confirm the local service responds at `http://127.0.0.1:11434`. Ollama normally runs from its Windows tray app; if it is not running, launch `ollama serve` in a terminal and leave that terminal open. Stop a manually launched server with Ctrl+C; stop the background app from its tray menu. The `.qa-venv` should contain the project's locked dependencies. The following PowerShell commands disable dotenv loading for the Python process, force local-only provider selection, blank cloud credentials, and save a new report to a unique output path:

```powershell
$env:PYTHON_DOTENV_DISABLED = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:LLM_PROVIDER = 'ollama'
$env:LLM_MODEL = 'qwen2.5:1.5b'
$env:OLLAMA_BASE_URL = 'http://127.0.0.1:11434/v1'
$env:OLLAMA_MODEL_DIGEST = '65ec06548149b04c096a120e4a6da9d4017ea809c91734ea5631e89f96ddc57b'
$env:LLM_TEMPERATURE = '0'
$env:LLM_TIMEOUT_SECONDS = '180'
$env:LLM_MAX_RETRIES = '1'
$env:OLLAMA_MAX_OUTPUT_TOKENS = '1024'
$env:OPENAI_API_KEY = ''
$env:ANTHROPIC_API_KEY = ''
& .\.qa-venv\Scripts\python.exe -m scripts.evaluate `
  --dataset tests/evaluation_dataset.json `
  --output tmp/ollama-qwen2.5-1.5b-dataset-v1.2.0-new.json
```

Before a long evaluation, check available RAM and disk space, confirm the local service with `ollama list`, and use a new report filename. Do not overwrite previous reports. The evaluation runner exports JSON and does not persist those evaluation cases to the SQLite arbitration history.

## Verification evidence and limitations

- Dataset validator: version 1.2.0; 21 cases; `ambiguous_001` is the sole ambiguous case; 20 eligible cases.
- Human review ledger: 20 `APPROVE`, 1 `AMBIGUOUS`; the backup file remains present.
- Offline suite after the telemetry fix: 134 passed, 0 failed, four existing Pandas/Streamlit deprecation warnings.
- Focused evaluation tests: 12 passed.
- Offline Ollama client and workflow transport tests use mocked HTTP responses; they are not real-model evidence.
- The original 20-case run is real local-model evidence. The local provider integration and JSON inference passed live smoke tests; after the telemetry fix, the one-case live smoke recorded three critic calls and one adjudicator call.
- OpenAI and Anthropic were not called. Docker deployment and Docker-to-Ollama networking were not tested.
- The 21-case dataset is small and synthetic, has limited category coverage, and cannot establish general model quality.

Before another live run, finish or close the active Ollama update and verify `ollama --version`, `ollama list`, and the loopback service. If the CLI still reports `upgrade in progress`, restart Ollama through its normal Windows app/tray workflow and retry only after the local API responds.
