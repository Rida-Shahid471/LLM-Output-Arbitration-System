import json
import logging
import operator
import time
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph

from src.adjudicator import ADJUDICATOR_PROMPT_VERSION, adjudicate
from src.config import settings
from src.critic_runner import CriticRunner
from src.disagreement_detector import detect_disagreements
from src.input_parser import ArbitrationInput, parse_input
from src.llm_client import LLMClient, MockLLMClient, create_llm_client
from src.prompts.critic_prompts import CRITIC_PROMPT_VERSION, SYSTEM_CRITIC_INSTRUCTIONS
from src.schemas import ArbitrationResult, CriticReport, CriticType, FinalVerdict, Verdict
from src.storage import ArbitrationStore, utc_now
from src.utils.request_id import create_request_id


class WorkflowState(TypedDict, total=False):
    arbitration_id: str
    arbitration_input: ArbitrationInput
    reports: Annotated[list[CriticReport], operator.add]
    errors: Annotated[list[str], operator.add]
    timings_ms: Annotated[dict[str, float], operator.or_]
    disagreements: list
    final_verdict: FinalVerdict


def _mock_response(prompt: str, system_prompt: str | None) -> str:
    if system_prompt and "evidence-based adjudicator" in system_prompt.lower():
        return json.dumps({"verdict": "revise", "overall_score": 5, "confidence": 0.2, "confirmed_issues": [], "dismissed_flags": [], "summary": "Mock provider did not evaluate answer quality; configure a live provider for a real verdict.", "unresolved_disagreements": [], "rationale": "Deterministic mock response only."})
    text = prompt.lower()
    critic = next((ct for ct in CriticType if f"evaluate the candidate answer for {ct.value.replace('_', ' ')}" in text), CriticType.FACTUAL_ACCURACY)
    return json.dumps({"critic_type": critic.value, "score": 3, "summary": "Deterministic mock report; no semantic evaluation was performed.", "issues": [], "overall_confidence": 0.2})


class ArbitrationEngine:
    def __init__(self, *, llm_client: LLMClient | None = None, store: ArbitrationStore | None = None, persist: bool = True) -> None:
        injected_client = llm_client is not None
        self.llm_client = llm_client or self._configured_client(
            settings.llm_provider,
            api_key=(settings.openai_api_key if settings.llm_provider == "openai" else
                     settings.anthropic_api_key if settings.llm_provider == "anthropic" else None),
            model=settings.llm_model,
            base_url=settings.ollama_base_url if settings.llm_provider == "ollama" else None,
        )
        self.critic_clients: dict[CriticType, LLMClient] = {}
        for critic_type, provider_override, model_override in (
            (CriticType.FACTUAL_ACCURACY, settings.factual_provider, settings.factual_model),
            (CriticType.LOGICAL_CONSISTENCY, settings.logical_provider, settings.logical_model),
            (CriticType.COMPLETENESS, settings.completeness_provider, settings.completeness_model),
        ):
            if injected_client or not (provider_override or model_override):
                self.critic_clients[critic_type] = self.llm_client
            else:
                provider = provider_override or settings.llm_provider
                key = (settings.anthropic_api_key if provider == "anthropic" else
                       settings.openai_api_key if provider == "openai" else None)
                self.critic_clients[critic_type] = self._configured_client(
                    provider, api_key=key, model=model_override or settings.llm_model,
                    base_url=settings.ollama_base_url if provider == "ollama" else None,
                )
        provider_names = {self._client_provider(client) for client in self.critic_clients.values()} | {self._client_provider(self.llm_client)}
        self.provider = "mixed" if len(provider_names) > 1 else next(iter(provider_names))
        self.store = store or (ArbitrationStore(settings.database_path) if persist else None)
        self.graph = self._build_graph()

    @staticmethod
    def _configured_client(provider: str, *, api_key: str | None, model: str, base_url: str | None = None) -> LLMClient:
        client = create_llm_client(
            provider, api_key=api_key, model=model,
            timeout=settings.llm_timeout_seconds, base_url=base_url,
            temperature=settings.llm_temperature,
            max_input_chars=settings.provider_input_limit(provider),
            max_output_tokens=settings.provider_output_limit(provider),
        )
        # Provider-created mock clients must produce schema-valid responses for
        # both the critic and adjudicator paths. Preserve explicitly injected
        # clients so tests and callers can supply their own deterministic output.
        if isinstance(client, MockLLMClient):
            return MockLLMClient(response=_mock_response, model=model)
        return client

    def _build_graph(self):
        builder = StateGraph(WorkflowState)
        def critic_node(critic_type: CriticType):
            runner = CriticRunner(self.critic_clients[critic_type])
            def run(state: WorkflowState) -> dict:
                started = time.perf_counter()
                try:
                    report = runner.run(critic_type=critic_type, arbitration_input=state["arbitration_input"])
                    return {"reports": [report], "timings_ms": {f"{critic_type.value}_ms": (time.perf_counter() - started) * 1000}}
                except Exception as exc:
                    logging.getLogger("arbitration").warning(
                        "Critic failed | request_id=%s | critic=%s | error_type=%s",
                        state.get("arbitration_id", "unknown"), critic_type.value, type(exc).__name__,
                    )
                    return {"errors": [f"{critic_type.value}: {type(exc).__name__}: {exc}"], "timings_ms": {f"{critic_type.value}_ms": (time.perf_counter() - started) * 1000}}
            return run

        names = []
        for critic_type in CriticType:
            name = critic_type.value
            names.append(name)
            builder.add_node(name, critic_node(critic_type))
            builder.add_edge(START, name)
        builder.add_node("detect_disagreements", self._detect_node)
        for name in names:
            builder.add_edge(name, "detect_disagreements")
        builder.add_node("adjudicate", self._adjudicate_node)
        builder.add_edge("detect_disagreements", "adjudicate")
        builder.add_edge("adjudicate", END)
        return builder.compile()

    @staticmethod
    def _client_provider(client: LLMClient) -> str:
        if isinstance(client, MockLLMClient):
            return "mock"
        return getattr(client, "provider_name", client.__class__.__name__.removesuffix("Client").lower())

    @staticmethod
    def _detect_node(state: WorkflowState) -> dict:
        started = time.perf_counter()
        disagreements = detect_disagreements(state.get("reports", []))
        return {
            "disagreements": disagreements,
            "timings_ms": {"disagreement_detection_ms": (time.perf_counter() - started) * 1000},
        }

    def _adjudicate_node(self, state: WorkflowState) -> dict:
        started = time.perf_counter()
        order = {critic: index for index, critic in enumerate(CriticType)}
        reports = sorted(state.get("reports", []), key=lambda report: order[report.critic_type])
        disagreements = state.get("disagreements", [])
        errors = state.get("errors", [])
        # The roadmap's unanimous-good shortcut avoids an unnecessary adjudicator call.
        thresholds = {
            CriticType.FACTUAL_ACCURACY: settings.factual_threshold,
            CriticType.LOGICAL_CONSISTENCY: settings.logical_threshold,
            CriticType.COMPLETENESS: settings.completeness_threshold,
        }
        if len(reports) == 3 and not errors and not disagreements and all(
            not r.issues and r.score >= max(4, thresholds[r.critic_type]) and r.overall_confidence >= 0.7
            for r in reports
        ):
            verdict = FinalVerdict(
                verdict=Verdict.ACCEPT, overall_score=min(r.score for r in reports) * 2,
                confidence=min(r.overall_confidence for r in reports), confirmed_issues=[], dismissed_flags=[],
                summary="All three critics independently found no issues and assigned a high score.",
                unresolved_disagreements=[], rationale="Unanimous-good shortcut.",
                adjudicator_provider="system_shortcut", adjudicator_model=None,
            )
            return {"final_verdict": verdict, "timings_ms": {"adjudication_ms": (time.perf_counter() - started) * 1000}}
        verdict = adjudicate(
            llm_client=self.llm_client, arbitration_input=state["arbitration_input"], reports=reports,
            disagreements=disagreements, errors=errors, max_retries=settings.llm_max_retries,
        )
        return {"final_verdict": verdict, "timings_ms": {"adjudication_ms": (time.perf_counter() - started) * 1000}}

    def arbitrate(self, original_prompt: str, candidate_answer: str, *, persist: bool = True) -> ArbitrationResult:
        arbitration_input = parse_input(original_prompt, candidate_answer)
        self.validate_provider_input(arbitration_input)
        arbitration_id = create_request_id()
        started = time.perf_counter()
        logging.getLogger("arbitration").info("Arbitration started | request_id=%s", arbitration_id)
        state = self.graph.invoke({"arbitration_id": arbitration_id, "arbitration_input": arbitration_input, "reports": [], "errors": [], "timings_ms": {}})
        timings = dict(state.get("timings_ms", {}))
        timings["total"] = (time.perf_counter() - started) * 1000
        result = ArbitrationResult(
            arbitration_id=arbitration_id, original_prompt=arbitration_input.original_prompt,
            candidate_output=arbitration_input.candidate_answer,
            critic_reports=sorted(state.get("reports", []), key=lambda report: list(CriticType).index(report.critic_type)),
            disagreements=state.get("disagreements", []), final_verdict=state["final_verdict"],
            errors=state.get("errors", []), timings_ms=timings,
            provider=self.provider,
            critic_prompt_version=CRITIC_PROMPT_VERSION,
            adjudicator_prompt_version=ADJUDICATOR_PROMPT_VERSION,
            created_at=utc_now(),
        )
        if persist and self.store:
            self.store.save(result)
        logging.getLogger("arbitration").info("Arbitration finished | request_id=%s | verdict=%s", arbitration_id, result.final_verdict.verdict.value)
        return result

    def validate_provider_input(self, arbitration_input: ArbitrationInput) -> None:
        """Reject an oversized critic request before any provider call is made."""
        for critic_type, client in self.critic_clients.items():
            prompt = CriticRunner(client).build_prompt(critic_type=critic_type, arbitration_input=arbitration_input)
            limit = getattr(client, "max_input_chars", settings.max_provider_input_chars)
            size = len(prompt) + len(SYSTEM_CRITIC_INSTRUCTIONS)
            if size > limit:
                raise ValueError(f"{critic_type.value} provider input exceeds configured character budget ({size} > {limit}); no provider request was sent.")
