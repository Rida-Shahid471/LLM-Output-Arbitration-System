# Portfolio materials

These descriptions use implemented features and verified evidence. The Docker deployment and local Ollama evaluation have been verified; OpenAI and Anthropic have only offline-mocked verification. Do not imply that mock results establish model accuracy or that the local evaluation generalizes beyond its small dataset.

## Short project description

An LLM answer auditing service that runs parallel factual, logical, and completeness critics, validates quoted evidence, records disagreements, and produces an adjudicated verdict with persistent history and analytics.

## CV project entry

**LLM Output Arbitration System** — Python, LangGraph, FastAPI, SQLite, Streamlit

- Built a structured audit pipeline that evaluates an existing answer with three parallel critic dimensions and an evidence-checked adjudication step.
- Added single and batch API workflows, persistent audit history, a Streamlit verdict explorer, and analytics for critic findings and failures.
- Added a human-reviewed v1.2.0 evaluation set and a reproducible local Ollama evaluation; the 20-case prompt comparison recorded precision 0.7222, recall 1.0000, F1 0.8387, clean-answer false-positive rate 0.7143, and verdict agreement 0.1765. The small synthetic set and clean-answer over-flagging limit any quality conclusion.
- Verified a local Docker Compose deployment with FastAPI, Streamlit, SQLite persistence, and real host-Ollama inference; this remains a local/demo deployment without API authentication or rate limiting.

Before publishing a CV claim about passing test counts, provider quality, deployment, or performance, rerun the associated verification and state exactly which environment was tested.

## LinkedIn draft

I built an LLM Output Arbitration System that audits an already-generated answer through parallel factual, logical, and completeness critics. It validates evidence excerpts, surfaces critic disagreements, records audit history, and exposes results through a FastAPI service and Streamlit interface. I verified a Docker Compose deployment with local Ollama inference and ran a controlled 20-case prompt comparison on a human-reviewed synthetic dataset. The model produced a high clean-answer false-positive rate and low verdict agreement, so these results are limited evidence rather than a broad quality claim. OpenAI and Anthropic integrations have offline-mocked tests only.

## Short demo script

1. Explain the input: an original prompt and candidate answer to audit.
2. Submit the safe Australia-capital example through the local Ollama-configured demo.
3. Show the actual result, evidence markers, three critic cards, disagreements, and final verdict; explain that a model result can be wrong.
4. Open history and analytics, clarifying that operational analytics are not evaluation metrics.
5. Describe the separate v1.2.0 experiment and its clean-answer false positives; do not claim general accuracy.

## Interview topics

- Why separate factual, logical, and completeness critics?
- How do independent parallel reports help expose disagreement?
- How does the detector count pairwise agreement and preserve disagreement evidence?
- How does adjudication validate evidence and resolve every reported issue?
- What happens after one critic times out or returns malformed JSON?
- How do the labeled dataset and evaluation metrics distinguish issue detection from final-verdict agreement?
- What did the provider experiments actually show? (Answer only after real runs have been recorded.)
- What are the system's limits, privacy boundaries, and deployment controls?

## Demo assets

The verified public screenshots are in [`screenshots/`](screenshots/); the genuine local application walkthrough is in [`demo/llm-output-arbitration-demo.mp4`](demo/llm-output-arbitration-demo.mp4). The original high-bitrate recording remains local and is excluded from ordinary Git tracking because it is 124.4 MiB. See [`demo-recording-guide.md`](demo-recording-guide.md) for what each asset shows and the review limitations.
