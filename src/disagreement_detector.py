from src.categories import canonicalize_issue_category
from src.schemas import CriticReport, CriticType, Disagreement, Issue, Severity

_SEVERITY = {Severity.LOW: 1, Severity.MEDIUM: 2, Severity.HIGH: 3, Severity.CRITICAL: 4}


def _normalize(value: str) -> str:
    return canonicalize_issue_category(value)


def detect_disagreements(reports: list[CriticReport], severity_gap: int = 2, score_gap: int = 2) -> list[Disagreement]:
    """Compare reports deterministically by scores, category presence and severity."""
    order = {critic: index for index, critic in enumerate(CriticType)}
    reports = sorted(reports, key=lambda report: order[report.critic_type])
    found: list[Disagreement] = []
    for i, left in enumerate(reports):
        for right in reports[i + 1:]:
            pair_disagreements: list[Disagreement] = []
            left_categories: dict[str, list[Issue]] = {}
            right_categories: dict[str, list[Issue]] = {}
            for issue in left.issues:
                left_categories.setdefault(_normalize(issue.category), []).append(issue)
            for issue in right.issues:
                right_categories.setdefault(_normalize(issue.category), []).append(issue)
            for category in sorted(left_categories.keys() | right_categories.keys()):
                left_issues, right_issues = left_categories.get(category, []), right_categories.get(category, [])
                if not left_issues or not right_issues:
                    reporter = left if left_issues else right
                    for issue in left_issues or right_issues:
                        pair_disagreements.append(Disagreement(
                            topic=category or "issue_presence", critic_a=left.critic_type, critic_b=right.critic_type,
                            description=f"{reporter.critic_type.value} identified '{category}' while the other critic did not.",
                            severity=issue.severity, confidence=issue.confidence,
                        ))
                    continue
                a = max(left_issues, key=lambda issue: _SEVERITY[issue.severity])
                b = max(right_issues, key=lambda issue: _SEVERITY[issue.severity])
                if {issue.evidence for issue in left_issues} != {issue.evidence for issue in right_issues}:
                    pair_disagreements.append(Disagreement(
                        topic=f"{category}_evidence", critic_a=left.critic_type, critic_b=right.critic_type,
                        description=f"Critics cited different evidence excerpts for {category}.",
                        severity=max((a.severity, b.severity), key=lambda s: _SEVERITY[s]),
                        confidence=min(a.confidence, b.confidence),
                    ))
                if abs(_SEVERITY[a.severity] - _SEVERITY[b.severity]) > severity_gap:
                    pair_disagreements.append(Disagreement(
                        topic=category, critic_a=left.critic_type, critic_b=right.critic_type,
                        description=f"Critics assigned different severity to {category}: {a.severity.value} vs {b.severity.value}.",
                        severity=max((a.severity, b.severity), key=lambda s: _SEVERITY[s]),
                        confidence=min(a.confidence, b.confidence),
                    ))
            if abs(left.score - right.score) >= score_gap:
                pair_disagreements.append(Disagreement(
                    topic="overall_score", critic_a=left.critic_type, critic_b=right.critic_type,
                    description=f"Critic scores differ by {abs(left.score - right.score)} points ({left.score} vs {right.score}).",
                    severity=Severity.HIGH if abs(left.score - right.score) >= 3 else Severity.MEDIUM,
                    confidence=min(left.overall_confidence, right.overall_confidence),
                ))
            found.extend(pair_disagreements)
    return found
