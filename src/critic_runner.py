from src.input_parser import ArbitrationInput
from src.llm_client import LLMClient
from src.prompts.critic_prompts import get_critic_prompt
from src.schemas import CriticReport, CriticType


class CriticRunner:
    """Executes a specialist critic against an arbitration input."""

    def __init__(self, llm_client: LLMClient) -> None:
        self._llm_client = llm_client

    def build_prompt(
        self,
        *,
        critic_type: CriticType,
        arbitration_input: ArbitrationInput,
    ) -> str:
        """Build the prompt assigned to a specialist critic."""

        return get_critic_prompt(
            critic_type=critic_type,
            original_prompt=arbitration_input.original_prompt,
            candidate_answer=arbitration_input.candidate_answer,
        )

    def run(
        self,
        *,
        critic_type: CriticType,
        arbitration_input: ArbitrationInput,
    ) -> CriticReport:
        """Run a specialist critic and validate its structured report."""

        prompt = self.build_prompt(
            critic_type=critic_type,
            arbitration_input=arbitration_input,
        )

        response = self._llm_client.generate(
            system_prompt=(
                "You are a specialist critic in an LLM output "
                "arbitration system."
            ),
            prompt=prompt,
        )

        raise NotImplementedError(
            "Structured critic response parsing will be implemented "
            "in the next stage."
        )