import json
import os
import sys
from pathlib import Path

# Streamlit executes this file with the `ui` directory on sys.path. Add the
# project root explicitly so `streamlit run ui/app.py` works from a fresh clone.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import requests
import streamlit as st
import pandas as pd

from src.config import settings
from src.presentation import disagreement_topics_by_critic, render_answer_with_markers

st.set_page_config(page_title="Arbitration Verdict Explorer", layout="wide")
api_url = os.getenv("ARBITRATION_API_URL", "http://localhost:8000").rstrip("/")
st.title("LLM Output Arbitration")
default_provider = os.getenv("ARBITRATION_PROVIDER", settings.llm_provider).strip().lower()
factual_provider = os.getenv("ARBITRATION_FACTUAL_PROVIDER") or settings.factual_provider or default_provider
logical_provider = os.getenv("ARBITRATION_LOGICAL_PROVIDER") or settings.logical_provider or default_provider
completeness_provider = os.getenv("ARBITRATION_COMPLETENESS_PROVIDER") or settings.completeness_provider or default_provider
configured_providers = {
    default_provider,
    factual_provider,
    logical_provider,
    completeness_provider,
}
if configured_providers == {"mock"}:
    st.caption("Audit a candidate answer using specialist critics. Mock mode is deterministic and does not judge semantic correctness.")
else:
    st.caption(
        "Audit a candidate answer using specialist critics. Configured provider(s): "
        f"{', '.join(sorted(configured_providers))}. Per-critic provider overrides may apply."
    )

tab_run, tab_batch, tab_history, tab_analytics = st.tabs(["Arbitrate", "Batch", "History", "Analytics"])

def show_result(result: dict) -> None:
    verdict = result["final_verdict"]
    c1, c2, c3 = st.columns(3)
    c1.metric("Verdict", verdict["verdict"].upper())
    c2.metric("Score", f"{verdict['overall_score']}/10")
    c3.metric("Confidence", f"{verdict['confidence']:.0%}")
    st.write(verdict["summary"])
    if verdict.get("rationale"):
        st.caption(f"Adjudication rationale: {verdict['rationale']}")
    if verdict.get("recommended_revision"):
        st.info(verdict["recommended_revision"])
    attributions = {
        f"{report['provider']}/{report['model']}" if report.get("model") else report["provider"]
        for report in result["critic_reports"] if report.get("provider")
    }
    adjudicator_provider = verdict.get("adjudicator_provider")
    adjudicator_model = verdict.get("adjudicator_model")
    if adjudicator_provider:
        attributions.add(
            f"{adjudicator_provider}/{adjudicator_model}" if adjudicator_model else adjudicator_provider
        )
    attribution_text = ", ".join(sorted(attributions)) or result["provider"]
    st.caption(f"ID: {result['arbitration_id']} | Provider/model: {attribution_text} | Stored in audit history")
    with st.expander("Original prompt and candidate answer", expanded=True):
        st.markdown("**Original prompt**")
        st.text(result["original_prompt"])
        st.markdown("**Candidate answer · evidence markers**")
        st.markdown(
            "<style>.arb-confirmed{background:#ffd9d9;color:#8c1010}.arb-low-confidence{background:#fff0bd;color:#664b00}.arb-validated{background:#d7f5df;color:#145c27}.arb-answer{white-space:pre-wrap;border:1px solid #dddddd;border-radius:8px;padding:12px}</style>"
            f'<div class="arb-answer">{render_answer_with_markers(result["candidate_output"], result["critic_reports"], verdict)}</div>',
            unsafe_allow_html=True,
        )
        st.caption("Red: adjudicator-confirmed issue · Yellow: low-confidence critic flag · Green: evidence quote matched exactly but was not confirmed as a defect.")
    st.subheader("Side-by-side critic comparison")
    disagreement_topics = disagreement_topics_by_critic(result["disagreements"])
    critic_columns = st.columns(3)
    for column, report in zip(critic_columns, result["critic_reports"]):
        with column:
            st.markdown(f"**{report['critic_type'].replace('_', ' ').title()}**")
            st.metric("Score", f"{report['score']}/5")
            st.write(report["summary"])
            topics = disagreement_topics.get(report["critic_type"], [])
            if topics:
                st.warning("Disagreement: " + ", ".join(topics))
            else:
                st.caption("No pairwise disagreement detected")
            if report["issues"]:
                st.error(f"{len(report['issues'])} issue(s) flagged")
                for issue in report["issues"]:
                    st.markdown(f"**{issue['severity'].upper()} · {issue['category']}**")
                    st.write(issue["description"])
                    st.caption(f"Evidence: {issue['evidence']}")
            else:
                st.success("No issues reported")
    st.subheader("Disagreements and evidence")
    st.json(result["disagreements"])
    st.subheader("Confirmed issues")
    if verdict["confirmed_issues"]:
        for item in verdict["confirmed_issues"]:
            issue = item["issue"]
            st.error(f"{item['critic_type']} · {issue['severity'].upper()} · {issue['category']}: {issue['description']}\n\nEvidence: {issue['evidence']}")
    else:
        st.success("No issues were confirmed")
    if verdict["dismissed_flags"]:
        st.subheader("Dismissed flags")
        for item in verdict["dismissed_flags"]:
            issue = item["issue"]
            st.warning(f"{item['critic_type']} · {issue['category']}: {item['reason']}\n\nEvidence: {issue['evidence']}")
    if result["errors"]:
        st.warning("One or more critics failed; confidence was reduced.")
        st.json(result["errors"])


def show_count_chart(values: dict, label: str, value_label: str) -> None:
    if not values:
        st.info("No data recorded yet.")
        return
    chart_data = pd.DataFrame(list(values.items()), columns=[label, value_label]).set_index(label)
    st.bar_chart(chart_data)


def validate_result_payload(result: object) -> dict:
    required = {"arbitration_id", "original_prompt", "candidate_output", "critic_reports", "disagreements", "final_verdict", "errors", "provider"}
    if not isinstance(result, dict) or not required.issubset(result) or not isinstance(result.get("final_verdict"), dict):
        raise ValueError("The API returned a malformed arbitration result.")
    return result

with tab_run:
    with st.form("single"):
        prompt = st.text_area("Original prompt", height=130)
        answer = st.text_area("Candidate answer", height=200)
        submit = st.form_submit_button("Run arbitration", type="primary")
    if submit:
        try:
            response = requests.post(f"{api_url}/v1/arbitrate", json={"original_prompt": prompt, "candidate_answer": answer}, timeout=settings.single_request_timeout_seconds)
            response.raise_for_status()
            show_result(validate_result_payload(response.json()))
        except (ValueError, TypeError, KeyError, requests.RequestException) as exc:
            st.error(f"API request failed: {exc}")

with tab_batch:
    raw = st.text_area("Batch JSON (array of {original_prompt, candidate_answer})", value="[]", height=220)
    if st.button("Run batch"):
        try:
            items = json.loads(raw)
            if not isinstance(items, list):
                raise ValueError("Batch JSON must be an array of items.")
            response = requests.post(f"{api_url}/v1/arbitrate/batch", json={"items": items}, timeout=settings.batch_request_timeout_seconds)
            response.raise_for_status()
            batch_results = response.json()
            if not isinstance(batch_results, list):
                raise ValueError("The API returned a malformed batch response.")
            failed_count = sum(isinstance(result, dict) and bool(result.get("errors")) for result in batch_results)
            if failed_count:
                st.warning(f"{failed_count} batch item(s) completed with critic failures; expand each result to review its details.")
            for result in batch_results:
                result = validate_result_payload(result)
                with st.expander(f"{result['arbitration_id']} — {result['final_verdict']['verdict']}"):
                    show_result(result)
        except (ValueError, TypeError, KeyError, requests.RequestException) as exc:
            st.error(f"Batch request failed: {exc}")

with tab_history:
    history_page = int(st.number_input("History page", min_value=1, value=1, step=1))
    if st.button("Refresh history"):
        try:
            response = requests.get(f"{api_url}/v1/arbitrations", params={"limit": 50, "offset": (history_page - 1) * 50}, timeout=30)
            response.raise_for_status()
            history = response.json()
            if not isinstance(history, list):
                raise ValueError("The API returned malformed history data.")
            st.dataframe([{
                "id": r["arbitration_id"], "created": r["created_at"], "verdict": r["final_verdict"]["verdict"],
                "score": r["final_verdict"]["overall_score"], "confirmed issues": len(r["final_verdict"]["confirmed_issues"]),
                "confidence": r["final_verdict"]["confidence"], "answer excerpt": r["candidate_output"][:180],
            } for r in history], use_container_width=True)
        except (ValueError, TypeError, KeyError, requests.RequestException) as exc:
            st.error(f"Could not load history: {exc}")
    lookup = st.text_input("Load arbitration by ID")
    if st.button("Load verdict") and lookup:
        try:
            response = requests.get(f"{api_url}/v1/arbitrations/{lookup}", timeout=30)
            response.raise_for_status()
            show_result(validate_result_payload(response.json()))
        except (ValueError, TypeError, KeyError, requests.RequestException) as exc:
            st.error(f"Could not retrieve arbitration: {exc}")

with tab_analytics:
    if st.button("Refresh analytics"):
        try:
            response = requests.get(f"{api_url}/v1/analytics", timeout=30)
            response.raise_for_status()
            metrics = response.json()
            cols = st.columns(4)
            cols[0].metric("Arbitrations", metrics["total_arbitrations"])
            cols[1].metric("Critic-pair agreement", f"{metrics['agreement_rate']:.1%}")
            cols[2].metric("Critic-pair disagreement", f"{metrics['disagreement_rate']:.1%}")
            cols[3].metric("Avg latency", f"{metrics['average_latency_ms']:.0f} ms")
            st.subheader("Issues by critic")
            show_count_chart(metrics["issues_by_critic"], "critic", "issues")
            st.subheader("Common issue categories")
            show_count_chart(metrics["issues_by_category"], "category", "issues")
            st.subheader("Overruled flags by critic")
            show_count_chart(metrics["overruled_flags_by_critic"], "critic", "overruled")
            st.subheader("Average critic latency (ms)")
            show_count_chart(metrics["average_critic_latency_ms"], "critic", "milliseconds")
            st.subheader("Failure types")
            show_count_chart(metrics["failures_by_type"], "failure type", "count")
            st.subheader("Final score distribution")
            show_count_chart(metrics["final_scores"], "score (out of 10)", "arbitrations")
            st.subheader("Critic-pair agreement and disagreement")
            show_count_chart({"agreement": metrics["agreement_rate"], "disagreement": metrics["disagreement_rate"]}, "pair outcome", "rate")
        except requests.RequestException as exc:
            st.error(f"Could not load analytics: {exc}")
