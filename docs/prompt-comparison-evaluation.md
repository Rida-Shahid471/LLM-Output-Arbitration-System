# Controlled Prompt Comparison

**Status: COMPLETE — all 20 approved cases have a valid final outcome; one failed case was explicitly retried and both attempts are preserved.**

## Objective and experimental design

This was a one-variable prompt comparison using the local Ollama model `qwen2.5:1.5b` and the human-reviewed v1.2.0 dataset. The only changed variable was the factual-accuracy critic prompt (`critic-prompts-v3` baseline versus `day16-factual-calibration-v1` comparison). The logic and completeness prompts, adjudicator prompt v3, model digest, temperature (0), output budget (1,024 tokens), retry count (2), timeout (60 seconds), and non-persistent evaluation mode were held fixed. `ambiguous_001` was excluded. No cloud provider was contacted.

The comparison prompt asks the critic to distinguish false, unsupported, and incomplete claims and to lower confidence when a fact cannot be reliably verified. This was the existing documented comparison condition; no new experiment design was substituted.

## Why the previous run produced no report

The interrupted run in `tmp/experiments/day16-qwen2.5-1.5b-factual-calibration-v1/` remains unchanged and marked `interrupted`. The earlier runner wrote its final report only after the full evaluator returned and offered no case-level checkpoint/progress report. Consequently, interruption before finalization left no report even though inference may have been in progress. The local model itself was responsive in the verified smoke test. In this controlled run, 20 arbitration requests took 2,365.519 seconds (39m 25.5s), averaging 118.276 seconds per case; slow CPU inference is therefore a material runtime factor. The exact duration and completion point of the earlier interrupted process cannot be independently reconstructed from its metadata.

The comparison runner prints progress and persists completed case outputs atomically. A post-run accounting guard exposed one incomplete critic set. Rather than hide it, the failed attempt was retained, `format_002` was retried once with the same model, prompt, and generation settings, and its successful result was saved separately. Offline aggregation then used the 19 original complete outcomes plus that successful retry. The original failed attempt, retry record, and earlier 19-case aggregation remain preserved.

## Run evidence

- Provider/model: local Ollama / `qwen2.5:1.5b`
- Model digest: `65ec06548149b04c096a120e4a6da9d4017ea809c91734ea5631e89f96ddc57b`
- Ollama runtime: 0.40.16
- Dataset: version 1.2.0; 21 total, 20 approved/scorable; `ambiguous_001` skipped
- Actual inference: all 20 approved cases have a valid final three-critic result; `ambiguous_001` was skipped. There were 21 case attempts because one recorded failure was retried.
- Initial failed case: `format_002`; `logical_consistency` raised `CriticResponseError: Every issue's evidence must be an exact quote from the candidate answer.` The first attempt (two critic reports and an adjudication fallback) remains in the initial checkpoint and is not counted as a successful outcome.
- Retry: the same case and settings completed with three critic reports and no errors in 85.376 seconds. The standalone retry record is `tmp/experiments/day16_retry_format002_20261113-1530/retry_result.json`.
- Started: 2026-11-13 08:40:00 UTC
- Initial 20-case pass completed: 2026-11-13 09:19:26 UTC (2,365.888 seconds wall time; 2,365.519 seconds summed case execution time)
- `format_002` retry completed: 2026-11-13 09:59:17 UTC (85.376 seconds)
- Total recorded wall time across the first pass and retry: 2,451.264 seconds; summed case-attempt execution time: 2,450.895 seconds. The final selected 20 successful case outputs sum to 2,261.267 seconds (113.063 seconds average per case).
- Interrupted/failed execution and per-case checkpoints: `tmp/experiments/day16_final_20261113-133725/`
- Offline metric aggregation from the first pass (19 scored; no provider calls): `tmp/experiments/day16_final_reaggregated_20261113-1430/`
- Full-coverage final aggregation (19 original successes plus the successful same-condition retry; no provider calls): `tmp/experiments/day16_final_reaggregated_retry_20261113-1545/`
- Tracked machine-readable baseline: [`experiments/ollama-qwen2.5-1.5b-v1.2.0-baseline.json`](experiments/ollama-qwen2.5-1.5b-v1.2.0-baseline.json)
- Tracked comparison results and metadata: [`experiments/prompt-comparison-qwen2.5-1.5b/`](experiments/prompt-comparison-qwen2.5-1.5b/)
- Baseline: `tmp/ollama-qwen2.5-1.5b-dataset-v1.2.0-20261103.json`, SHA-256 `b3ecd3357ddb856e644aea8c36be80770f3b929839d5e1fd7af043435289348d`
- Dataset SHA-256: `5986dc2ca1a2e09a03a00daa2c0386287d34f671f27fdcded9ab739d82b24e82`

## Results

| Metric | Historical baseline | Prompt comparison | Notes |
|---|---:|---:|---|
| Issue precision | 0.6842 (13/19 predicted-positive) | 0.7222 (13/18 predicted-positive) | 20 final outcomes; issue detection uses critic reports. |
| Issue recall | 1.0000 (13/13 actual-positive) | 1.0000 (13/13 actual-positive) | All approved cases scored. |
| Issue F1 | 0.8125 | 0.8387 | Same 20 approved cases; one comparison case was retried. |
| Clean-answer false-positive rate | 0.8571 (6/7) | 0.7143 (5/7) | Still high; only seven clean examples. |
| Verdict agreement | 0.2143 (3/14) | 0.1765 (3/17) | Agreement denominator excludes adjudication fallbacks. |
| Average confidence | 0.7321 (14 measured) | 0.7765 (17 measured) | Confidence is not correctness; fallback cases excluded. |
| Evaluation coverage | 1.0000 (20/20) | 1.0000 (20/20) | `ambiguous_001` excluded; all approved cases have a final complete critic set. |
| Critic failures in selected final outcomes | 0 | 0 | The first `format_002` attempt had one failure; its retry succeeded. |
| Adjudication fallbacks | 6 | 3 | Fallbacks are not counted as successful verdict-agreement cases. |
| Confusion counts (TP/FP/FN/TN) | 13 / 6 / 0 / 1 | 13 / 5 / 0 / 2 | Ambiguous case excluded. |
| Workflow error/fallback rate | 0.3000 (6/20) | 0.1500 (3/20) | Evaluator definition counts critic-error or adjudication-fallback cases. |

The comparison shows fewer clean-answer false positives in this run, but this is **not evidence of a reliable improvement**: there are only 20 synthetic cases, one case required a second attempt, verdict agreement is lower, and the small sample does not support broad conclusions. Metric denominators are reported above. These results support only a narrow observation about this prompt/model/run. Token usage was not captured reliably and is reported as unavailable, not zero.

## Reproduction and verification

Use `.qa-venv\Scripts\python.exe` with `PYTHON_DOTENV_DISABLED=1`, the same local Ollama model/digest, and the runner in `scripts/run_prompt_comparison.py`. The runner refuses to reuse prior outputs. The exact commands for a future fresh run and offline finalization are:

```powershell
$env:PYTHON_DOTENV_DISABLED = '1'
$env:LLM_PROVIDER = 'ollama'
$env:LLM_MODEL = 'qwen2.5:1.5b'
$env:OLLAMA_BASE_URL = 'http://127.0.0.1:11434/v1'
& '.qa-venv\Scripts\python.exe' scripts\run_prompt_comparison.py --output-dir 'tmp\experiments\day16_retry_<unique-id>'

# Reaggregate an existing checkpoint offline; choose a different, new output folder.
& '.qa-venv\Scripts\python.exe' scripts\run_prompt_comparison.py --output-dir 'tmp\experiments\day16_reaggregate_<unique-id>' --finalize-checkpoint 'tmp\experiments\day16_final_20261113-133725'
```

The environment variables above are set before Python starts. The first command makes local Ollama requests; the second only reads the recorded checkpoint and makes no provider calls. Both commands require a new, unused output directory.

Focused runner/evaluation tests previously passed: **17 passed**. On 2026-11-23, the renamed runner's complete offline suite passed **145 tests, 0 failed, 0 skipped**, with **4 Pandas deprecation warnings** (`.qa-venv`, `PYTHON_DOTENV_DISABLED=1`); `pip check` reported no broken requirements. The project dataset is version 1.2.0 with 21 cases, 20 approved/scorable and only `ambiguous_001` ambiguous; the evaluator excludes that case before arbitration and metric accumulation. All eight screenshots were visually inspected during this final audit.

## Case-level error review

The baseline produced six false-positive issue detections and no false negatives. The comparison produced five false positives and no false negatives. Reviewing each affected approved case against its prompt and answer shows a repeated over-flagging pattern: the model labels correct arithmetic or complete answers as `unsupported_claim`, `incomplete_answer`, or (in a few cases) `factual_error`.

| Case | Expected clean answer | Baseline finding | Comparison finding |
|---|---|---|---|
| `clean_001` | `2 + 2 = 4` | `unsupported_claim` | `incomplete_answer` |
| `fact_true_001` | Tokyo and yen correctly answer the Japan question | `incomplete_answer`, `unsupported_claim` | `incomplete_answer` |
| `complete_001` | Red and blue satisfy the specified traditional RYB model | `incomplete_answer`, `unsupported_claim` | `factual_error`, `incomplete_answer`, `unsupported_claim` (fallback) |
| `clean_002` | Two triangles have six sides | `unsupported_claim` | `factual_error`, `unsupported_claim` |
| `clean_003` | `17 × 6 = 102` | `factual_error` | no issue flagged |
| `format_001` | Three requested fruit/vegetable/grain items are present | `incomplete_answer`, `unsupported_claim` | `incomplete_answer`, `unsupported_claim` |

The comparison resolved only the `clean_003` false positive while retaining five other clean-answer false positives. There were no false negatives in either run. This case review is a qualitative analysis of the recorded outputs, not independent evidence that the model generalizes beyond this synthetic dataset.

## Limitations and acceptance

- Only one factual critic prompt was changed; the model, dataset, adjudicator, and other critics were held fixed.
- The dataset is small and synthetic, and results may vary with local runtime and model generation behavior.
- The first `format_002` attempt failed its logical critic; the same case was retried once under unchanged conditions. Both attempts are preserved, and the final aggregate uses the successful retry. This per-case retry is disclosed because it may affect comparability with the one-pass baseline.
- No reliable token usage was recorded.
- The original Task 4 baseline, dataset, and human review ledger were not modified.

The controlled comparison is **COMPLETE**: a real one-variable prompt comparison produced valid final results for all 20 approved cases, excluded the ambiguous case, recorded the initial failure and successful retry separately, calculated metrics from actual local outputs, passed the focused and full offline tests, and preserved the original baseline and dataset.
