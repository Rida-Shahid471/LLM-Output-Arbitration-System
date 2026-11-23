from src.config import settings
from src.critic_response_parser import parse_critic_response
from src.errors import CriticResponseError, LLMNonRetryableProviderError, LLMProviderError
from src.input_parser import ArbitrationInput
from src.llm_client import LLMClient
from src.prompts.critic_prompts import SYSTEM_CRITIC_INSTRUCTIONS, get_critic_prompt
from src.categories import CANONICAL_ISSUE_CATEGORIES
from src.schemas import CriticReport, CriticType, Issue


def _issue_identity(issue: Issue) -> tuple[str, str, str, str]:
    """Return fields that identify a repeated finding independent of confidence."""
    description = " ".join(issue.description.casefold().split())
    return issue.category.casefold(), description, issue.evidence, issue.severity.value


class CriticRunner:
    """Run and validate one dimension-specific critic evaluation."""

    def __init__(self, llm_client: LLMClient, max_retries: int | None = None) -> None:
        self._llm_client = llm_client
        self._max_retries = settings.llm_max_retries if max_retries is None else max_retries

    def build_prompt(self, *, critic_type: CriticType, arbitration_input: ArbitrationInput) -> str:
        return get_critic_prompt(critic_type, arbitration_input.original_prompt, arbitration_input.candidate_answer)

    def run(self, *, critic_type: CriticType, arbitration_input: ArbitrationInput) -> CriticReport:
        prompt = self.build_prompt(critic_type=critic_type, arbitration_input=arbitration_input)
        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                generate_args = {"system_prompt": SYSTEM_CRITIC_INSTRUCTIONS, "prompt": prompt}
                if getattr(self._llm_client, "supports_json_schema", False):
                    schema = CriticReport.model_json_schema()
                    schema["$defs"]["Issue"]["properties"]["category"] = {
                        "type": "string", "enum": sorted(CANONICAL_ISSUE_CATEGORIES),
                    }
                    generate_args["json_schema"] = schema
                    generate_args["system_prompt"] += (
                        "\nFor each issue, evidence must be copied as a contiguous, exact substring of the candidate answer. "
                        "Do not add a lead-in, explanation, quotation marks, or correction to evidence."
                    )
                response = self._llm_client.generate(**generate_args)
                report = parse_critic_response(response.content)
                if report.critic_type != critic_type:
                    raise CriticResponseError(f"Expected {critic_type.value} report, received {report.critic_type.value}.")
                identities = [_issue_identity(issue) for issue in report.issues]
                if len(identities) != len(set(identities)):
                    raise CriticResponseError("Critic response contains duplicate issue entries.")
                for issue in report.issues:
                    if issue.evidence not in arbitration_input.candidate_answer:
                        raise CriticResponseError("Every issue's evidence must be an exact quote from the candidate answer.")
                return report.model_copy(update={"model": response.model, "provider": response.provider})
            except (CriticResponseError, LLMProviderError) as exc:
                last_error = exc
                if isinstance(exc, LLMNonRetryableProviderError):
                    break
                if attempt >= self._max_retries:
                    break
        if last_error:
            raise last_error
        raise CriticResponseError("Critic could not produce a valid report.")
