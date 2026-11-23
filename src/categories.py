"""Canonical issue-category names shared by arbitration and analytics."""

import re


CANONICAL_ISSUE_CATEGORIES = frozenset({
    "factual_error", "unsupported_claim", "logical_contradiction",
    "invalid_inference", "incomplete_answer", "format_violation",
    "calculation_error", "other",
})

_ALIASES = {
    "fact": "factual_error", "factual": "factual_error", "fact_error": "factual_error",
    "false_claim": "factual_error", "incorrect_fact": "factual_error",
    "factual_inaccuracy": "factual_error", "factual_error": "factual_error",
    "unsupported": "unsupported_claim", "unverified_claim": "unsupported_claim",
    "unsupported_claim": "unsupported_claim",
    "logic": "logical_contradiction", "contradiction": "logical_contradiction",
    "contradiciton": "logical_contradiction", "logical_inconsistency": "logical_contradiction",
    "logical_contradiction": "logical_contradiction",
    "reasoning_gap": "invalid_inference", "invalid_reasoning": "invalid_inference",
    "unsupported_conclusion": "invalid_inference", "invalid_inference": "invalid_inference",
    "incomplete": "incomplete_answer", "incompleteness": "incomplete_answer",
    "incompletness": "incomplete_answer", "omission": "incomplete_answer",
    "missing_requirement": "incomplete_answer", "incomplete_answer": "incomplete_answer",
    "format": "format_violation", "format_error": "format_violation",
    "formatting_violation": "format_violation", "format_violation": "format_violation",
    "math_error": "calculation_error", "arithmetic_error": "calculation_error",
    "calculation_error": "calculation_error", "other": "other",
}


def normalize_category_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")


def canonicalize_issue_category(value: str) -> str:
    """Map known aliases; preserve unknown values in an explicit namespace."""
    normalized = normalize_category_text(value)
    if not normalized:
        return "unknown:empty"
    if normalized.startswith("unknown_"):
        remainder = normalized.removeprefix("unknown_")
        return f"unknown:{remainder or 'empty'}"
    return _ALIASES.get(normalized, f"unknown:{normalized}")
