# Evaluation and model experiment log

## Protocol

- Keep the versioned, human-authored reference labels fixed for each comparison.
- Use the same dataset version for every provider run. Set `LLM_TEMPERATURE=0` for OpenAI/Ollama. Anthropic requests omit temperature for compatibility with current Claude SDK/model behavior, so record its sampling configuration as provider default.
- The report records UTC timestamp, provider/model identifiers, dataset version, and critic/adjudicator prompt versions. Also record the output report path and any manual review notes here. Do not record API keys.
- Review every false positive, false negative, case with critic failures, and low-confidence verdict before changing prompts.
- `issue_detection_precision` and `issue_detection_recall` measure whether any critic report flags an issue, not whether the adjudicator confirms it.
- Mock mode is only a wiring check. Its metrics are never model-quality measurements.
- The first real Ollama evaluation recorded incomplete request/token telemetry because the evaluator wrapped clients after LangGraph captured the critic clients. Do not cite its request or token totals as full-run totals; this instrumentation was fixed afterward and regression-tested.

## Run records

| Date | Provider/model | Dataset | Temperature | Result | Interpretation |
|---|---|---|---:|---|---|
| 2026-11-02 | Mock / deterministic | 1.1.0; prompt versions v1/v1 | 0 | Precision 0.0000; recall 0.0000; clean-answer false-positive rate 0.0000; verdict agreement 0.5000; average confidence 0.2000; 0 critic failures | Offline harness smoke only. The mock deliberately does not judge semantics; these numbers must not be used to compare model quality. |
| 2026-11-02 11:30:54 UTC | Mock / `mock-evaluation` | 1.1.0; prompt versions v2/v2 | 0 (mock ignores sampling) | Precision 0.0000; recall 0.0000; clean-answer false-positive rate 0.0000; verdict agreement 0.5000; average confidence 0.2000; 0 critic failures | Re-run after evaluation denominator, prompt-version, and model-identity logging changes; wiring check only, never model-quality data. |
| Pending | OpenAI / exact model ID to record | 1.2.0; critic/adjudicator v3 | 0 | Not run | Requires a locally configured OpenAI API key and model ID. |
| Pending | Anthropic / exact model ID to record | 1.2.0; critic/adjudicator v3 | Provider default (temperature omitted) | Not run | Requires a locally configured Anthropic API key and model ID. |
| 2026-11-06 | Ollama / `qwen2.5:1.5b` (digest `65ec06548149b04c096a120e4a6da9d4017ea809c91734ea5631e89f96ddc57b`) | 1.2.0; critic/adjudicator v3 | 0 | Precision 0.6842; recall 1.0000; F1 0.8125; clean-answer FPR 0.8571; verdict agreement 0.2143 (3/14); mean confidence 0.7321 (14); 20/20 scorable cases; ambiguous case skipped | Real local CPU inference. Poor clean-answer specificity and verdict agreement. Six adjudication fallbacks; zero critic failures. Timing has one 221,162-second outlier and is not a valid latency benchmark. Saved aggregate request/token counts are under-counted because the evaluator initially missed LangGraph-captured critic clients. Full evidence and case-level verdicts: [`ollama-local-model-evaluation.md`](ollama-local-model-evaluation.md); raw report remains in ignored local `tmp/`. |

No real OpenAI or Anthropic result has been generated. The Ollama result above is actual local-model inference and is not a mock result. Do not replace pending cloud-provider rows with estimates.

## Controlled factual-critic prompt comparison (2026-11-13)

An isolated real Ollama comparison used `qwen2.5:1.5b` (digest `65ec06548149b04c096a120e4a6da9d4017ea809c91734ea5631e89f96ddc57b`) and dataset v1.2.0. The sole changed variable was the factual-accuracy critic prompt (`critic-prompts-v3` to `day16-factual-calibration-v1`); other prompts, adjudicator, model, temperature, output budget, timeout/retry configuration, and non-persistent mode were held fixed. `ambiguous_001` was skipped. Tracked raw comparison outputs and metadata are under `docs/experiments/prompt-comparison-qwen2.5-1.5b/`; the ignored `tmp/experiments/` copies remain as local provenance and are not required for the documented result.

The initial 20-case pass took 2,365.888 seconds wall time and checkpointed all cases. The logical critic failed on `format_002`; that initial output remains preserved. The case was retried once using identical model, factual prompt, and generation settings; all three critics completed in 85.376 seconds. A separate offline aggregation uses the 19 initial complete outcomes plus the successful retry, for 20/20 final coverage. Metrics: precision 0.7222 (13/18), recall 1.0000 (13/13), F1 0.8387, clean-answer FPR 0.7143 (5/7), verdict agreement 0.1765 (3/17), mean confidence 0.7765 (17 measured), confusion TP/FP/FN/TN 13/5/0/2, three adjudication fallbacks, zero critic failures in the selected final outcomes. The first attempt's one critic failure is retained separately. Baseline remains the earlier local run: precision 0.6842, recall 1.0000, F1 0.8125, FPR 0.8571, verdict agreement 0.2143 (3/14), six fallbacks, zero critic failures, and 20/20 coverage. This small synthetic dataset, unequal verdict denominators, and one explicit retry do not establish a general improvement. Token usage was not captured. Full historical raw attempts remain under ignored `tmp/experiments/`; tracked final artifacts and analysis are linked in [`prompt-comparison-evaluation.md`](prompt-comparison-evaluation.md). The full offline test suite passed 145 tests with four Pandas warnings on 2026-11-23.

On 2026-11-11, after the evaluator telemetry fix, a separate real local smoke evaluation of `fact_false_001` used `qwen2.5:1.5b` and completed all three critic calls plus adjudication: 4 successful local requests, 2,285 prompt tokens, 649 completion tokens, and 2,934 total returned tokens. This was a telemetry check, not a new dataset-quality result; it does not replace or augment the 20-case metrics above. Ollama was version 0.40.16 for this smoke test.

## Reproducible commands

Set the provider, exact model, and temperature in the local ignored `.env` file, then run:

```powershell
python -m scripts.evaluate --dataset tests/evaluation_dataset.json --output tmp/evaluation-report.json
```

For the default Ollama installation outside Docker, set `OLLAMA_BASE_URL=http://localhost:11434/v1`. In Docker Compose, use `OLLAMA_DOCKER_BASE_URL=http://host.docker.internal:11434/v1`. Report files may include case-level inputs; keep private reports outside Git.

## Docker deployment verification (2026-11-12)

Docker deployment was **runtime-verified** on 2026-11-12 with Docker 29.9.3, Compose v5.7.0, the Docker Desktop Linux Engine, and host Ollama `qwen2.5:1.5b`. Compose validation and sequential image builds succeeded. The isolated API/UI stack returned HTTP 200 for health, docs, and Streamlit; UI-to-API Compose networking returned 200. Two real local Docker workflow runs each returned all three Ollama critic reports and exercised adjudication; one had a valid model-attributed result and the dashboard run used the conservative fallback because the model's adjudication conflicted with its issue resolutions. The first run's record survived API container recreation. Both temporary records were removed by exact ID from the isolated verification volume, which now contains zero arbitration rows. The final full offline suite passed 140 tests with four existing Pandas/Streamlit deprecation warnings; host and container `pip check` found no broken requirements. Task 4 dataset and evaluation results were not changed; no dataset-wide evaluation or cloud provider call was made. See [`docker-deployment-verification.md`](docker-deployment-verification.md). The raw provider request count is not exposed by the runtime result, so only the three critic reports and adjudicator outcome are reported, not an inferred total request count.
