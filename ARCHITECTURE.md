# LLM Output Arbitration System — Architecture

## 1. Purpose

The LLM Output Arbitration System is designed to audit an already-generated LLM response using multiple independent specialist critics and an evidence-based adjudication process.

The system does not primarily generate a replacement answer.

Instead, it evaluates a candidate answer against the original prompt, identifies potential problems, compares independent critic findings, detects disagreements, and produces a structured final verdict.

---

## 2. Architectural Goals

The architecture is designed around the following goals:

* Independent evaluation of different quality dimensions.
* Parallel execution of specialist critics.
* Structured and machine-readable critic outputs.
* Explicit disagreement detection.
* Evidence-based adjudication.
* Provider-independent critic implementation.
* Persistent audit history.
* API-based access.
* Interactive verdict exploration.
* Analytics for critic behavior.
* Graceful failure handling.
* Reproducible evaluation and deployment.

---

## 3. High-Level System Flow

The primary system flow is:

```text
┌─────────────────────────────────────┐
│ Original Prompt + Candidate Output  │
└──────────────────┬──────────────────┘
                   │
                   ▼
          ┌─────────────────┐
          │   Input Parser  │
          └────────┬────────┘
                   │
                   ▼
       ┌───────────────────────────┐
       │   Parallel Critic Layer   │
       └───────┬────────┬──────────┘
               │        │
        ┌──────▼───┐ ┌──▼────────┐ ┌───────────────▼┐
        │ Factual  │ │  Logical  │ │  Completeness │
        │  Critic  │ │  Critic   │ │     Critic    │
        └─────┬────┘ └────┬──────┘ └───────┬───────┘
              │           │                │
              └───────────┼────────────────┘
                          │
                          ▼
               ┌────────────────────┐
               │ Critique Collection│
               └─────────┬──────────┘
                         │
                         ▼
               ┌────────────────────┐
               │ Disagreement       │
               │ Detector           │
               └─────────┬──────────┘
                         │
                         ▼
               ┌────────────────────┐
               │    Adjudicator     │
               └─────────┬──────────┘
                         │
                         ▼
               ┌────────────────────┐
               │   Final Verdict    │
               └─────────┬──────────┘
                         │
              ┌──────────┼───────────┐
              ▼          ▼           ▼
         Persistence    API      Dashboard/UI
```

The architecture follows the project model of:

```text
Input
→ 3 Parallel Critics
→ Critique Collection
→ Disagreement Detection
→ Adjudication
→ Final Verdict
→ Persistence / API / Dashboard
```

---

## 4. Input Layer

## Responsibility

The Input Layer receives the information required to audit a candidate answer.

### Inputs

```text
Original Prompt
Candidate LLM Output
```

Conceptual input:

```json
{
  "prompt": "Original user question",
  "candidate_output": "Generated answer to audit"
}
```

## Responsibilities

The Input Layer should:

* Validate required fields.
* Normalize the input representation.
* Generate or attach an arbitration/request identifier.
* Pass the validated input into the orchestration layer.

The Input Layer should not perform critic evaluation.

---

## 5. Critic Layer

The Critic Layer contains three independent specialist evaluators.

```text
                  Critic Layer
                       │
       ┌───────────────┼────────────────┐
       ▼               ▼                ▼
   Factual           Logical       Completeness
   Critic            Critic           Critic
```

Each critic focuses on a different quality dimension.

---

## 5.1 Factual Accuracy Critic

### FA_Responsibility

Evaluate whether claims in the candidate answer are verifiable and internally consistent.

### Focus

* Factual claims.
* Unsupported claims.
* Contradictory statements.
* Evidence associated with claims.
* Severity.
* Confidence.

### Output

A structured critic report.

---

## 5.2 Logical Consistency Critic

### LC_Responsibility

Evaluate whether the reasoning and conclusions in the candidate answer are logically supported.

### LC_Focus

* Contradictions.
* Unsupported conclusions.
* Reasoning gaps.
* Invalid inference.
* Logical consistency.
* Severity.
* Confidence.

### LC_Output

A structured critic report.

---

## 5.3 Completeness Critic

## CC_Responsibility

Evaluate whether the candidate answer addresses the complete original request.

## CC_Focus

* Missing requested information.
* Unanswered parts.
* Important omissions.
* Coverage of requirements.
* Severity.
* Confidence.

## CC_Output

A structured critic report.

---

## 6. Why Three Critics?

The system deliberately separates evaluation into three specialist dimensions.

A single evaluator would combine factual, logical and completeness judgments into one reasoning process.

Separating the critics allows the system to:

* isolate evaluation responsibilities;
* compare independent findings;
* identify disagreements;
* measure critic-specific behavior;
* experiment with different models or prompts;
* determine which evaluator identifies particular failure types.

The architecture therefore treats the critics as independent evaluators rather than three stages of one sequential reasoning process.

---

## 7. Structured Critic Reports

Critics should return structured outputs rather than relying on arbitrary natural-language responses.

A critic report contains information such as:

```text
Critic
Score
Issues
Issue Type
Severity
Confidence
Quoted Evidence
Reasoning
```

Conceptually:

```json
{
  "critic": "factual_accuracy",
  "score": 4,
  "issues": [
    {
      "type": "factual_error",
      "severity": "high",
      "evidence": "Quoted candidate text",
      "reasoning": "Explanation of the finding"
    }
  ],
  "confidence": 0.91
}
```

The exact schema is implemented separately in the project's structured schema layer.

---

## 8. LLM Provider Abstraction

Critics should not directly depend on provider-specific SDK implementations.

The architecture therefore introduces a common LLM client abstraction.

```text
             Specialist Critic
                    │
                    ▼
            Common LLM Client
                    │
          ┌─────────┼─────────┐
          ▼         ▼         ▼
       OpenAI   Anthropic   Ollama
          │         │         │
          └─────────┼─────────┘
                    ▼
              Model Response
```

## Purpose

The abstraction allows:

* Different critics to use different providers.
* Provider implementations to change without rewriting critic logic.
* Local/mock implementations for development and testing.
* Provider-specific configuration to remain outside critic code.
* Future model experiments without changing the core arbitration architecture.

---

## 9. Orchestration Layer

The orchestration layer coordinates the complete arbitration workflow.

The planned orchestration technology is **LangGraph**.

The conceptual graph is:

```text
START
  │
  ▼
Input Validation
  │
  ▼
Parallel Critic Fan-Out
  │
  ├─────────────┬─────────────┐
  ▼             ▼             ▼
Factual       Logical     Completeness
Critic        Critic        Critic
  │             │             │
  └─────────────┴─────────────┘
                │
                ▼
        Critique Collection
                │
                ▼
      Disagreement Detection
                │
                ▼
           Adjudicator
                │
                ▼
          Final Verdict
                │
                ▼
          Persistence/API
                │
                ▼
              END
```

---

## 10. Parallel Fan-Out / Fan-In

The three critics are logically independent and therefore should execute in parallel where the orchestration implementation allows it.

```text
                    Input
                      │
                      ▼
                 Fan-Out
              ┌───────┼───────┐
              ▼       ▼       ▼
           Factual  Logical  Complete
              │       │       │
              └───────┼───────┘
                      ▼
                   Fan-In
                      │
                      ▼
             Critique Collection
```

## Benefits

Parallel execution can:

* Reduce unnecessary sequential waiting.
* Preserve critic independence.
* Make the architecture explicit.
* Provide a clear boundary between independent evaluation and downstream arbitration.

---

## 11. Critique Collection

After the critics complete, their structured reports are collected into a common arbitration state.

Conceptually:

```text
Factual Report
      +
Logical Report
      +
Completeness Report
      │
      ▼
Critique Collection
```

The collection layer should preserve:

* Each critic's identity.
* Each critic's score.
* Issues.
* Evidence.
* Severity.
* Confidence.
* Any provider/runtime metadata required for auditing.

---

## 12. Disagreement Detection Layer

The Disagreement Detector identifies meaningful conflicts between critic reports.

Disagreements may occur when critics differ on:

* Whether an issue exists.
* Issue type.
* Issue severity.
* Importance of an omission.
* Overall assessment.
* Confidence.

Example:

```text
Factual Critic:
Issue = Present
Severity = High

Logical Critic:
Related issue = Not Present
Severity = None

Completeness Critic:
Issue = Present
Severity = Medium
```

The disagreement detector records the conflict rather than silently averaging the outputs.

---

## 13. Adjudication Layer

The adjudicator receives the evidence required to resolve critic disagreements.

## AL_Inputs

```text
Original Prompt
Candidate Output
Critic Reports
Detected Disagreements
Supporting Evidence
```

Conceptually:

```text
Candidate Answer
      │
      ├───────────┐
      │           │
Critic Reports    │
      │           │
      └─────┬─────┘
            ▼
     Disagreements
            │
            ▼
       Adjudicator
            │
            ▼
     Final Structured
         Verdict
```

---

## 14. Final Verdict

The final verdict is structured around the following information:

```text
arbitration_id
prompt
candidate_output
critic_reports
disagreements
overall_score
confidence
confirmed_issues
dismissed_flags
summary
```

The final score is intended to be on a 1–10 scale.

Individual critic scores use a 1–5 scale.

The adjudicator should also explain why issues were confirmed or dismissed.

---

## 15. Persistence Layer

The Persistence Layer stores arbitration history.

The planned storage options are:

```text
SQLite
JSON
```

The audit trail should preserve enough information to inspect previous decisions.

A stored arbitration record conceptually contains:

```text
Arbitration ID
Original Prompt
Candidate Output
Critic Reports
Disagreements
Final Verdict
Confidence
Confirmed Issues
Dismissed Flags
Summary
```

Historical verdict retrieval should not require another LLM call.

---

## 16. API Layer

The API exposes the arbitration system to external clients.

The planned API endpoints are:

```http
POST /v1/arbitrate
POST /v1/arbitrate/batch
GET /v1/arbitrations/{id}
```

## `POST /v1/arbitrate`

Runs arbitration for a single candidate output.

### `POST /v1/arbitrate/batch`

Runs arbitration for multiple candidate outputs.

### `GET /v1/arbitrations/{id}`

Retrieves a stored arbitration result.

Optional endpoints may later include:

```http
GET /v1/analytics
GET /v1/health
```

---

## 17. UI Layer

The UI is responsible for making arbitration results understandable to a human reviewer.

The planned UI capabilities include:

* Verdict exploration.
* Candidate answer display.
* Critic comparison.
* Agreement/disagreement highlighting.
* Evidence inspection.
* Batch result exploration.
* History browsing.
* Analytics visualization.

The UI should display the underlying evidence chain rather than only the final score.

---

## 18. Analytics Layer

The Analytics Layer evaluates system behavior across arbitration runs.

Planned analytics include:

* Which critic identifies the most issues.
* Which critic is overruled most often.
* Common failure types.
* Critic agreement rates.
* Critic disagreement rates.
* Critic latency.
* Total arbitration latency.
* Scores.
* Overrides.

The purpose is to analyze the behavior of the arbitration system rather than simply display aggregate scores.

---

## 19. Configuration Layer

Configuration is kept separate from application logic.

Configuration includes:

```text
Environment
API Keys
Model Names
Timeouts
Retry Limits
Thresholds
Logging Level
```

Secrets must be supplied through environment variables rather than hard-coded into source files.

Example:

```text
.env
.env.example
```

The `.env` file is local and must not be committed to version control.

The `.env.example` file documents the required configuration without containing real secrets.

---

## 20. Logging and Request Identification

Each arbitration request should have a unique identifier.

Conceptually:

```text
Request
  │
  ▼
Request ID
  │
  ├── Input Logs
  ├── Critic Logs
  ├── Disagreement Logs
  ├── Adjudication Logs
  └── Final Result Logs
```

Request IDs make it possible to trace one arbitration request through the system.

Logs should provide useful operational information without exposing sensitive credentials.

---

## 21. Error Handling

The architecture treats expected failures explicitly.

Potential failure categories include:

```text
Provider Error
Timeout
Retry Exhaustion
Malformed LLM Output
Critic Failure
Validation Error
Database Error
API Error
```

The system should avoid silently converting a failed critic into an apparently valid result.

Where appropriate, the failure should be represented in the arbitration state and exposed through structured error handling.

---

## 22. Reliability Strategy

The system is designed around:

* Explicit timeouts.
* Controlled retries.
* Structured outputs.
* Input validation.
* Provider error handling.
* Malformed-output handling.
* Request IDs.
* Audit logging.
* Graceful degradation where appropriate.

Reliability behavior should be tested rather than assumed.

---

## 23. Security Architecture

Security responsibilities include:

## Secrets

API keys remain outside source code.

### Logging

Sensitive credentials must never be logged.

### Input Validation

API inputs should be validated using structured schemas.

### Size Limits

Safe limits should be applied to externally supplied content.

### Dependencies

Dependencies should be reviewed and unused packages removed.

---

## 24. Evaluation Architecture

The evaluation system is separate from the runtime arbitration pipeline.

```text
Evaluation Dataset
        │
        ▼
Evaluation Runner
        │
        ▼
Arbitration Pipeline
        │
        ▼
Predicted Results
        │
        ▼
Comparison with Reference Labels
        │
        ▼
Evaluation Metrics
        │
        ▼
Evaluation Report
```

The dataset is intended to contain:

* Factual errors.
* Logical contradictions.
* Incomplete answers.
* Correct answers.
* Mixed-quality answers.
* Ambiguous cases.

Reference labels must remain separate from model-generated outputs.

---

## 25. Portfolio Demonstration Architecture

The system will demonstrate four required scenarios:

```text
┌─────────────────────┐
│ 1. Factual Error    │
└──────────┬──────────┘
           │
┌──────────▼──────────┐
│ 2. Logical Flaw     │
└──────────┬──────────┘
           │
┌──────────▼──────────┐
│ 3. Incomplete Answer│
└──────────┬──────────┘
           │
┌──────────▼──────────┐
│ 4. Good Answer      │
└─────────────────────┘
```

Each demonstration should show the complete evidence chain:

```text
Candidate Output
      ↓
Factual Critic
Logical Critic
Completeness Critic
      ↓
Critic Reports
      ↓
Disagreement Detection
      ↓
Adjudicator
      ↓
Final Verdict
```

---

## 26. Deployment Architecture

The planned deployment uses Docker / Docker Compose.

The final deployment may contain components such as:

```text
                 Docker Compose
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
       API          Database       Local LLM
        │                              │
        └──────────────┬───────────────┘
                       ▼
                  Application
                       │
                       ▼
                      UI
```

The exact deployment configuration will depend on the final implementation.

---

## 27. Repository Architecture

The repository is organized to keep infrastructure, domain logic, orchestration and interfaces separated.

Planned structure:

```text
LLM Output Arbitration System/
│
├── docs/
│
├── src/
│   ├── __init__.py
│   ├── config.py
│   ├── errors.py
│   ├── llm_client.py
│   ├── logging_config.py
│   ├── main.py
│   │
│   ├── critics/
│   │   ├── __init__.py
│   │   ├── factual.py
│   │   ├── logical.py
│   │   └── completeness.py
│   │
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── issue.py
│   │   ├── critic_report.py
│   │   ├── disagreement.py
│   │   └── final_verdict.py
│   │
│   ├── prompts/
│   │   ├── __init__.py
│   │   ├── factual.py
│   │   ├── logical.py
│   │   └── completeness.py
│   │
│   ├── graph/
│   │   ├── __init__.py
│   │   ├── state.py
│   │   └── workflow.py
│   │
│   ├── adjudication/
│   │   ├── __init__.py
│   │   └── adjudicator.py
│   │
│   ├── persistence/
│   │   ├── __init__.py
│   │   └── repository.py
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes.py
│   │
│   └── utils/
│       ├── __init__.py
│       └── request_id.py
│
├── tests/
│
├── data/
│
├── .env.example
├── .gitignore
├── requirements.txt
├── ARCHITECTURE.md
├── SCOPE.md
└── README.md
```

The repository structure is expected to evolve as additional layers are implemented.

---

## 28. Design Decisions

## Separate Specialist Critics

The project uses three specialist critics because factual accuracy, logical consistency and completeness represent different evaluation dimensions.

## Parallel Critic Execution

The critics are independent evaluators, so their execution can be coordinated as a parallel fan-out/fan-in workflow.

## Structured Outputs

Structured schemas make critic results machine-readable and allow downstream disagreement detection and adjudication.

## Provider Abstraction

A common LLM client prevents provider-specific SDK details from leaking into critic logic.

## Explicit Disagreement Detection

Disagreements are preserved and analyzed rather than hidden through simple score averaging.

## Evidence-Based Adjudication

The adjudicator receives the original answer, critic reports and disagreement evidence so that final decisions can be traced back to the underlying findings.

## Persistent Audit Trail

Storing the complete arbitration record makes previous decisions inspectable and allows history to be retrieved without rerunning the LLM pipeline.

---

## 29. Architectural Data Flow

The complete data flow can be represented as:

```text
Prompt
  │
  ▼
Candidate Output
  │
  ▼
Input Validation
  │
  ▼
Arbitration State
  │
  ├───────────────────────────────────┐
  │                                   │
  ▼                                   ▼
Factual Critic                  Logical Critic
  │                                   │
  └───────────────┬───────────────────┘
                  │
                  ▼
         Completeness Critic
                  │
                  ▼
         Critique Collection
                  │
                  ▼
       Disagreement Detection
                  │
                  ▼
             Adjudicator
                  │
                  ▼
          Final Verdict
                  │
        ┌─────────┼──────────┐
        ▼         ▼          ▼
     SQLite      API         UI
        │         │          │
        └─────────┼──────────┘
                  ▼
              Analytics
```

---

## 30. Final Architecture

At completion, the intended system architecture is:

```text
                         ┌─────────────────────┐
                         │    Original Prompt   │
                         └──────────┬──────────┘
                                    │
                         ┌──────────▼──────────┐
                         │ Candidate LLM Output│
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │    Input Layer      │
                         └──────────┬──────────┘
                                    │
                                    ▼
                     ┌─────────────────────────────┐
                     │      LangGraph Workflow     │
                     │                             │
                     │   ┌────────┐ ┌────────┐    │
                     │   │Factual │ │Logical │    │
                     │   │Critic  │ │Critic  │    │
                     │   └───┬────┘ └────┬───┘    │
                     │       │           │        │
                     │       │  ┌────────▼──────┐ │
                     │       │  │ Completeness  │ │
                     │       │  │    Critic     │ │
                     │       │  └───────┬───────┘ │
                     │       └──────────┼─────────┘
                     │                  │
                     └──────────────────┼─────────┘
                                        ▼
                              ┌──────────────────┐
                              │ Critique Reports │
                              └────────┬─────────┘
                                       │
                                       ▼
                              ┌──────────────────┐
                              │  Disagreement    │
                              │    Detector      │
                              └────────┬─────────┘
                                       │
                                       ▼
                              ┌──────────────────┐
                              │   Adjudicator    │
                              └────────┬─────────┘
                                       │
                                       ▼
                              ┌──────────────────┐
                              │  Final Verdict   │
                              └────────┬─────────┘
                                       │
                   ┌───────────────────┼───────────────────┐
                   ▼                   ▼                   ▼
              ┌──────────┐       ┌──────────┐       ┌──────────┐
              │ SQLite / │       │ FastAPI  │       │    UI    │
              │   JSON   │       │          │       │Dashboard │
              └──────────┘       └──────────┘       └──────────┘
                                       │
                                       ▼
                                ┌──────────────┐
                                │  Analytics   │
                                └──────────────┘
```

---

## 31. Non-Functional Requirements

The completed system should aim for:

## Reliability

Expected provider and application failures should be handled explicitly.

### Traceability

An arbitration should be traceable through request IDs and stored evidence.

### Reproducibility

Evaluation and deployment should be repeatable.

### Maintainability

Provider integrations, critics, schemas, orchestration and interfaces should remain modular.

### Security

Secrets must remain outside source control and sensitive information must not be written to logs.

### Testability

Core schemas, critics, disagreement logic, adjudication, API behavior and failure paths should be testable independently.

---

## 32. Known Limitations

The architecture does not assume that LLM-based critics are perfect.

Important limitations include:

* Critics can produce incorrect judgments.
* Multiple critics may share the same blind spot.
* Different model outputs can vary between runs.
* Confidence values do not guarantee correctness.
* Some factual claims require external verification.
* Ambiguous questions can make evaluation difficult.
* The adjudicator can also make incorrect decisions.

Evaluation results must therefore be interpreted as measurements of the implemented system rather than guarantees of factual correctness.

---

## 33. Architecture Status

This document describes the target architecture and the incremental implementation plan.

Not every component is implemented at the same development stage.

The architecture will be refined as implementation, testing, evaluation and deployment reveal concrete requirements.

The final architecture must remain consistent with the actual codebase and deployed system.
