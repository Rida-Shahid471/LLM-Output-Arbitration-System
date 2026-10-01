from textwrap import dedent

from src.schemas import CriticType


SYSTEM_CRITIC_INSTRUCTIONS = dedent(
    """
    You are a specialist evaluator in an LLM output arbitration system.

    Your task is to evaluate a candidate LLM response against the original
    user request.

    Evaluation must be evidence-based and limited to the assigned critic
    responsibility.

    Do not rewrite the candidate answer.

    Do not introduce unsupported claims.

    Identify concrete issues and assign:
    - severity
    - confidence

    Confidence must be represented as a value between 0.0 and 1.0.

    Return structured information compatible with the arbitration system's
    critic report schema.
    """
).strip()


FACTUAL_ACCURACY_PROMPT = dedent(
    """
    Evaluate the candidate answer for factual accuracy.

    Focus on:
    - incorrect factual claims
    - unsupported factual assertions
    - contradictions with information provided in the prompt
    - internally inconsistent factual statements
    - claims that require verification

    Do not evaluate writing style unless it affects factual correctness.

    Original prompt:
    {original_prompt}

    Candidate answer:
    {candidate_answer}
    """
).strip()


LOGICAL_CONSISTENCY_PROMPT = dedent(
    """
    Evaluate the candidate answer for logical consistency.

    Focus on:
    - contradictions
    - unsupported conclusions
    - reasoning gaps
    - invalid inferences
    - conclusions that do not follow from the stated premises
    - internally inconsistent reasoning

    Do not evaluate factual accuracy unless it directly creates a logical
    inconsistency.

    Original prompt:
    {original_prompt}

    Candidate answer:
    {candidate_answer}
    """
).strip()


COMPLETENESS_PROMPT = dedent(
    """
    Evaluate the candidate answer for completeness.

    Focus on:
    - unanswered parts of the original request
    - missing required information
    - important omissions
    - incomplete coverage of explicit requirements
    - failure to satisfy requested output constraints

    Do not penalize the candidate for information that was not requested.

    Original prompt:
    {original_prompt}

    Candidate answer:
    {candidate_answer}
    """
).strip()


def get_critic_prompt(
    critic_type: CriticType,
    original_prompt: str,
    candidate_answer: str,
) -> str:
    """Build the evaluation prompt for a specialist critic."""

    templates = {
        CriticType.FACTUAL_ACCURACY: FACTUAL_ACCURACY_PROMPT,
        CriticType.LOGICAL_CONSISTENCY: LOGICAL_CONSISTENCY_PROMPT,
        CriticType.COMPLETENESS: COMPLETENESS_PROMPT,
    }

    template = templates[critic_type]

    return (
    SYSTEM_CRITIC_INSTRUCTIONS
    + "\n\n"
    + template.format(
        original_prompt=original_prompt,
        candidate_answer=candidate_answer,
    )
)