# Evaluation dataset review

## Review record

- Dataset: `tests/evaluation_dataset.json`, version `1.2.0`.
- Review date: 2026-11-02.
- Scope: all 21 cases, their prompts, candidate answers, issue labels, expected verdicts, and ambiguity flags.
- Method: inspect the human-authored examples and apply the structural dataset validator. No mock-model judgment was used to decide labels, and no provider call was made.
- Authorization: the user asked to complete Phase 3 after receiving the case-by-case review. The edits below are the review decisions applied under that instruction. They have not been checked by an independent subject-matter expert.
- Backup: `tests/evaluation_dataset.v1.1.1.pre-phase3-review.json` preserves the exact dataset before review edits.

## Verdict rubric used

- `accept`: no material issue is present and the answer satisfies the prompt.
- `revise`: at least one material issue is present, but the answer is locally correctable or contains useful correct content.
- `reject`: the central answer is materially false or unusable as a response to the prompt.

This rubric makes the existing `reject` versus `revise` distinction explicit. The evaluation loader verifies that `accept` corresponds to no issue and that an issue-bearing case is not `accept`; it does not independently judge severity or prove factual references.

## Case review decisions

| Case ID | Expected verdict | Issue labels | Review decision |
|---|---|---|---|
| `fact_false_001` | reject | `factual_error` | Retained: the direct answer gives the wrong capital; the central response is materially false. |
| `logic_001` | revise | `logical_contradiction` | Retained: the answer gives conflicting totals and an unsupported inference. |
| `incomplete_001` | revise | `incomplete_answer` | Retained: the requested currency is omitted. |
| `clean_001` | accept | none | Retained: arithmetic is correct. |
| `mixed_001` | revise | `factual_error` | Retained: the answer includes a false claim about Jupiter while its first claim is correct. |
| `ambiguous_001` | `accept` placeholder; ambiguous | none | The `accept` value is not a verified quality judgment. The human reviewer marked the case AMBIGUOUS and requested exclusion from every scored metric because the prompt gives no answer-quality criterion. |
| `fact_false_002` | reject | `factual_error` | Retained: the direct answer gives the wrong capital; the central response is materially false. |
| `fact_true_001` | accept | none | Retained: both requested facts are correct. |
| `logic_002` | revise | `logical_contradiction` | Retained: the conclusion contradicts the stated premise. |
| `logic_003` | revise | `calculation_error` | Changed from `logical_contradiction`: the specific defect is an arithmetic error in the final calculation. |
| `incomplete_002` | revise | `incomplete_answer` | Retained: only two of the three requested benefits are supplied. |
| `complete_001` | accept | none | Prompt clarified to specify the traditional RYB color model; the existing answer is valid under that convention and no longer requires a review skip. |
| `mixed_002` | revise | `factual_error` | Retained: the size comparison is false even though the largest-planet statement is correct. |
| `clean_002` | accept | none | Retained: the count is correct. |
| `clean_003` | accept | none | Retained: the multiplication is correct. |
| `fact_false_003` | reject | `factual_error` | Retained: the direct answer gives a materially incorrect boiling point. |
| `fact_true_002` | accept | none | Retained: the qualified freezing-point answer is correct. |
| `incomplete_003` | revise | `incomplete_answer` | Retained: the requested example is missing. |
| `logic_004` | revise | `logical_contradiction` | Retained: the answer contradicts the rule stated in the prompt. |
| `format_001` | accept | none | Retained: all three requested item types are present in a numbered list. |
| `format_002` | revise | `incomplete_answer`, `format_violation` | Expanded: the answer omits a requested item and violates the exact-three-item numbered-list requirement. |

## Validation and known limits

- The dataset contains 21 unique cases: 13 with issues, 8 without issues, and 1 explicitly ambiguous case.
- Every issue label belongs to the canonical category taxonomy. No duplicate labels or issue/verdict contradictions remain.
- `complete_001` no longer has `review_required`; it is now scored using an explicit color-model convention.
- `ambiguous_001` remains the single intentionally unscored ambiguous case.
- The dataset still has no per-case citation or authoritative reference field. Factual labels should be independently checked against suitable sources before publishing benchmark-quality claims.
- Category coverage remains limited: this 21-case set does not yet contain labeled examples for `unsupported_claim`, `invalid_inference`, or `other`.
- This review is not an independent scientific or domain-expert audit. The dataset is suitable for running the documented evaluation workflow, but results remain limited by its small size and reference coverage.

## Human approval ledger

The human reviewer completed the case-by-case review on 2026-11-02. The exact decisions were 20 `APPROVE` decisions and one `AMBIGUOUS` decision. No case was corrected. For approved cases, the listed reference fields were explicitly accepted by the reviewer; no labels or expected verdicts were changed as a result of this approval. The ambiguous case's placeholder reference is not a human-approved quality label.

| Review # | Case ID | Human decision | Approved fields / explanation | Status |
|---:|---|---|---|---|
| 1 | `logic_003` | APPROVE | `revise`; issue=true; `calculation_error`. Correct intermediate calculation, incorrect final result. | Approved |
| 2 | `complete_001` | APPROVE | `accept`; issue=false; no labels. Red and blue are primary colors in the specified traditional RYB model. | Approved |
| 3 | `format_002` | APPROVE | `revise`; issue=true; `incomplete_answer`, `format_violation`. Only two of exactly three required items are provided. | Approved |
| 4 | `fact_false_001` | APPROVE | `reject`; issue=true; `factual_error`. Sydney is not Australia's capital. | Approved |
| 5 | `logic_001` | APPROVE | `revise`; issue=true; `logical_contradiction`. The answer gives conflicting totals. | Approved |
| 6 | `ambiguous_001` | AMBIGUOUS | Ambiguity approved; the prompt lacks an answer-quality criterion. Its `accept` placeholder is not approved as a quality judgment and must be excluded from scored evaluation. | Ambiguous; exclude from scores |
| 7 | `fact_false_002` | APPROVE | `reject`; issue=true; `factual_error`. Lyon is not France's capital. | Approved |
| 8 | `fact_true_001` | APPROVE | `accept`; issue=false; no labels. Tokyo and the yen are correct. | Approved |
| 9 | `logic_002` | APPROVE | `revise`; issue=true; `logical_contradiction`. The conclusion contradicts the prompt's premises. | Approved |
| 10 | `incomplete_001` | APPROVE | `revise`; issue=true; `incomplete_answer`. The answer omits the requested currency. | Approved |
| 11 | `clean_001` | APPROVE | `accept`; issue=false; no labels. The arithmetic is correct and complete. | Approved |
| 12 | `mixed_001` | APPROVE | `revise`; issue=true; `factual_error`. Jupiter is not a rocky planet with a true solid surface. | Approved |
| 13 | `incomplete_002` | APPROVE | `revise`; issue=true; `incomplete_answer`. Only two of the requested three benefits are listed. | Approved |
| 14 | `mixed_002` | APPROVE | `revise`; issue=true; `factual_error`. Jupiter is larger, not smaller, than Earth. | Approved |
| 15 | `clean_002` | APPROVE | `accept`; issue=false; no labels. Two triangles have six sides in total. | Approved |
| 16 | `clean_003` | APPROVE | `accept`; issue=false; no labels. 17 × 6 = 102. | Approved |
| 17 | `fact_false_003` | APPROVE | `reject`; issue=true; `factual_error`. Water boils at approximately 100°C, not 50°C, at standard pressure. | Approved |
| 18 | `fact_true_002` | APPROVE | `accept`; issue=false; no labels. The stated approximate freezing point and pressure condition are correct. | Approved |
| 19 | `incomplete_003` | APPROVE | `revise`; issue=true; `incomplete_answer`. The requested example is missing. | Approved |
| 20 | `logic_004` | APPROVE | `revise`; issue=true; `logical_contradiction`. The answer contradicts the premises about squares and rectangles. | Approved |
| 21 | `format_001` | APPROVE | `accept`; issue=false; no labels. Exactly three numbered items satisfy the requested categories. | Approved |

### Ambiguous-case scoring rule

`ambiguous_001` is excluded from all scored evaluation metrics. In `src/evaluation.py`, ambiguous cases are marked `skipped_ambiguous` and skipped before arbitration or metric accumulation. Consequently, the case contributes to none of the confusion counts or precision, recall, false-positive-rate, verdict-agreement, or average-confidence denominators. It is counted only in dataset accounting (`dataset_cases` and `ambiguous_cases_skipped`). The report currently defines no separate composite aggregate-score field; any aggregate computed from the listed scored metrics uses only their non-ambiguous denominators.

## Reference sources consulted

These authoritative sources support the factual and context-dependent review decisions above:

- Australia’s capital: [Parliament of Australia](https://www.aph.gov.au/Parliamentary_Business/Committees/Joint/National_Capital_and_External_Territories/NationalCapital/A_Capital_for_All_Australians/Chapter_1_-_Introduction).
- France’s capital: [European Union country profile](https://european-union.europa.eu/principles-countries-history/eu-countries/france_en).
- Japan’s capital and currency: [Government of Japan](https://www.japan.go.jp/japan/index.html).
- Jupiter’s size and composition: [NASA Jupiter facts](https://science.nasa.gov/jupiter/jupiter-facts/) and [NASA Jupiter fact sheet](https://nssdc.gsfc.nasa.gov/planetary/factsheet/jupiterfact.html).
- Water’s approximate freezing and boiling points on the Celsius scale: [NIST temperature reference](https://www.nist.gov/pml/owm/si-units-temperature).
- Color-model convention: [Colour Literacy Project, primary colours](https://colourliteracy.org/primary-colours), describing RYB, CMY, and RGB as different color systems.

The logic, arithmetic, completeness, and format cases are checked directly against the prompt and candidate text. The references above are review support; they are not embedded per case in the JSON dataset.

## Reproduction

Run structural and semantic consistency validation without invoking any model:

```powershell
python -c "from src.evaluation import load_evaluation_dataset; from pathlib import Path; print(len(load_evaluation_dataset(Path('tests/evaluation_dataset.json'))))"
```

Run related tests:

```powershell
python -m pytest -q tests/test_evaluation.py
```
