# LLM Output Arbitration System Architecture

## High-Level Flow

The system follows this pipeline:

Candidate LLM Output
        ↓
Input Parser
        ↓
Parallel Critics
        ↓
Critique Collection
        ↓
Disagreement Detector
        ↓
Adjudicator
        ↓
Final Verdict
        ↓
Database / API / Dashboard

---

## 1. Input Layer

The input layer receives:

- Original prompt
- Candidate LLM output

The input is validated before entering the arbitration pipeline.

---

## 2. Critic Layer

The critic layer contains three independent specialist critics:

### Factual Accuracy Critic

Evaluates factual correctness and internal consistency.

### Logical Consistency Critic

Evaluates reasoning, contradictions and unsupported conclusions.

### Completeness Critic

Evaluates whether all requirements of the original prompt are addressed.

---

## 3. Orchestration Layer

LangGraph will be used to orchestrate the arbitration workflow.

The three critics should run independently and in parallel where possible.

Their reports are collected before disagreement detection.

---

## 4. Disagreement Layer

The disagreement detector compares critic reports.

It examines:

- Issue presence
- Severity
- Scores
- Issue categories
- Evidence

The detector produces a structured disagreement report.

---

## 5. Adjudication Layer

The adjudicator receives:

- Original prompt
- Candidate output
- Critic reports
- Disagreements

The adjudicator evaluates the evidence and resolves conflicts.

---

## 6. Final Verdict Layer

The adjudicator produces:

- Overall score from 1 to 10
- Confidence
- Confirmed issues
- Dismissed flags
- Reasons
- Final summary

---

## 7. Persistence Layer

Arbitration results will be stored so previous verdicts can be retrieved without running another LLM evaluation.

SQLite and JSON-based storage are planned.

---

## 8. API Layer

FastAPI will expose the arbitration pipeline.

Main endpoints:

- POST /v1/arbitrate
- POST /v1/arbitrate/batch
- GET /v1/arbitrations/{id}

---

## 9. UI Layer

The UI will provide a verdict explorer where users can view:

- Candidate answer
- Final score
- Confidence
- Critic reports
- Disagreements
- Evidence
- Final summary

---

## 10. Analytics Layer

Analytics will track:

- Critic issue counts
- Critic overrides
- Agreement rates
- Disagreement rates
- Issue types
- Critic latency
- Total latency

---

## Overall Architecture

Input
→ 3 Parallel Critics
→ Critique Collection
→ Disagreement Detector
→ Adjudicator
→ Final Verdict
→ Database / API / Dashboard
