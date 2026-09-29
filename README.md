# LLM Output Arbitration System

## Project Overview

LLM Output Arbitration System is an AI engineering project designed to audit an already-generated Large Language Model (LLM) answer.

Instead of generating another answer, the system evaluates the candidate answer using three independent specialist critics:

1. Factual Accuracy Critic
2. Logical Consistency Critic
3. Completeness Critic

The critic reports are collected, disagreements are detected, and an adjudicator produces a final structured verdict.

---

## Core System Flow

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

## Three Critics

### Factual Accuracy Critic

Checks whether claims in the candidate answer are factually correct and internally consistent.

### Logical Consistency Critic

Checks whether the reasoning is logically consistent and whether conclusions are supported.

### Completeness Critic

Checks whether the answer addresses all required parts of the original question.

---

## Main Features

- Multi-agent evaluation
- Three specialist critics
- Structured critic reports
- Parallel critic execution
- Disagreement detection
- Evidence-based adjudication
- Final structured verdict
- Persistence and audit history
- FastAPI API
- Verdict explorer UI
- Analytics
- Evaluation dataset
- Failure handling
- Docker deployment

---

## Technology Stack

- Python 3.11+
- LangGraph
- OpenAI / Anthropic / Ollama
- Pydantic
- Instructor
- SQLite
- JSON
- FastAPI
- Streamlit or React
- Docker
- Docker Compose

---

## Project Structure

```text
llm-output-arbitration/
│
├── docs/
│
├── src/
│
├── tests/
│   └── demo_cases.json
│
├── .gitignore
├── ARCHITECTURE.md
├── README.md
└── SCOPE.md
