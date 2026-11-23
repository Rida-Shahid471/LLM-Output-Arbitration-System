from html import escape
from typing import Any


_STYLE_BY_KIND = {
    "confirmed": (3, "arb-confirmed", "Confirmed issue"),
    "low_confidence": (2, "arb-low-confidence", "Low-confidence issue"),
    "validated": (1, "arb-validated", "Evidence quote validated; issue not confirmed"),
}


def disagreement_topics_by_critic(disagreements: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Group detected disagreement topics by each participating critic."""
    topics: dict[str, set[str]] = {}
    for disagreement in disagreements:
        topic = str(disagreement.get("topic", "unspecified"))
        for critic_key in ("critic_a", "critic_b"):
            critic = disagreement.get(critic_key)
            if critic:
                topics.setdefault(str(critic), set()).add(topic)
    return {critic: sorted(critic_topics) for critic, critic_topics in topics.items()}


def render_answer_with_markers(candidate: str, critic_reports: list[dict[str, Any]], final_verdict: dict[str, Any]) -> str:
    """Return escaped HTML that marks validated evidence excerpts in a candidate answer."""
    confirmed = {
        (item["critic_type"], item["issue"]["category"].casefold(), item["issue"]["evidence"])
        for item in final_verdict.get("confirmed_issues", [])
    }
    spans: list[tuple[int, int, str]] = []
    for report in critic_reports:
        for issue in report.get("issues", []):
            evidence = issue.get("evidence", "")
            if not evidence:
                continue
            key = (report.get("critic_type"), issue.get("category", "").casefold(), evidence)
            if key in confirmed:
                kind = "confirmed"
            elif float(issue.get("confidence", 0.0)) < 0.7:
                kind = "low_confidence"
            else:
                kind = "validated"
            start = 0
            while True:
                start = candidate.find(evidence, start)
                if start < 0:
                    break
                spans.append((start, start + len(evidence), kind))
                start += 1

    if not spans:
        return escape(candidate)
    boundaries = sorted({0, len(candidate), *(point for start, end, _ in spans for point in (start, end))})
    parts: list[str] = []
    for start, end in zip(boundaries, boundaries[1:]):
        active = [kind for span_start, span_end, kind in spans if span_start <= start and span_end >= end]
        segment = escape(candidate[start:end])
        if active:
            kind = max(active, key=lambda value: _STYLE_BY_KIND[value][0])
            _, css_class, label = _STYLE_BY_KIND[kind]
            parts.append(f'<span class="{css_class}" title="{escape(label)}">{segment}</span>')
        else:
            parts.append(segment)
    return "".join(parts)
