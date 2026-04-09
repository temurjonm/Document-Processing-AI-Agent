# Post-generation grounding check: verifies every claim in the answer
# is actually supported by the source documents.
#
# Three-layer hallucination prevention:
# 1. Prompt: "ONLY from the provided context" (generator.py)
# 2. Self-assessment: confidence rating in the response (generator.py)
# 3. Automated check: this file — independent verification
# No single layer catches everything. Together they're very reliable.

import json
from openai import OpenAI
from src.config import OPENAI_API_KEY, SIMPLE_MODEL

_client = OpenAI(api_key=OPENAI_API_KEY)


def check_grounding(answer: str, source_chunks: list[str]) -> dict:
    """
    Check if every claim in the answer is supported by the source chunks.
    Uses a separate LLM call — independent from the one that generated the answer.

    Why a separate call? The same LLM that generated the answer might be biased
    to think its own answer is correct. A fresh call is more objective.

    Args:
        answer: the generated answer text
        source_chunks: list of source texts the answer was based on
    Returns:
        {grounded: bool, unsupported_claims: list[str], score: float}
    """
    # Combine source chunks into one block of text
    # Number them so the LLM can reference specific sources
    sources_text = ""
    for i, chunk in enumerate(source_chunks):
        sources_text += f"[Source {i + 1}] {chunk}\n\n"

    prompt = f"""You are a fact-checking assistant. Check if every claim in the Answer is supported by the Sources.

Answer:
{answer}

Sources:
{sources_text}

For each claim in the answer, check if it appears in or can be directly inferred from the sources.

Respond in JSON:
{{
    "grounded": true or false,
    "score": 0.0 to 1.0 (what fraction of claims are supported),
    "unsupported_claims": ["list of claims not found in sources"],
    "explanation": "brief explanation"
}}"""

    response = _client.chat.completions.create(
        model=SIMPLE_MODEL,  # gpt-4o-mini is good enough for fact-checking
        messages=[{"role": "user", "content": prompt}],
        temperature=0,  # deterministic — we want consistent fact-checking
        response_format={"type": "json_object"}
    )

    try:
        result = json.loads(response.choices[0].message.content)
    except json.JSONDecodeError:
        # If parsing fails, assume not grounded (fail safe, not fail open)
        result = {
            "grounded": False,
            "score": 0.0,
            "unsupported_claims": ["Could not verify — parsing error"],
            "explanation": "Grounding check failed to parse"
        }

    return result


def apply_grounding_result(answer_dict: dict, grounding: dict) -> dict:
    """
    Modify the answer based on the grounding check result.
    If not grounded: lower confidence and add a warning.

    Args:
        answer_dict: the original answer from generator.py
        grounding: the result from check_grounding()
    Returns:
        the modified answer dict
    """
    if not grounding.get("grounded", True):
        # The answer contains unsupported claims
        # Downgrade confidence to "low" so the user knows to verify
        answer_dict["confidence"] = "low"

        # Add a warning with the specific unsupported claims
        claims = grounding.get("unsupported_claims", [])
        if claims:
            warning = f"Warning: These claims could not be verified in the source documents: {'; '.join(claims)}"
            answer_dict["warning"] = warning

        # Add the grounding score (e.g., 0.7 means 70% of claims verified)
        answer_dict["grounding_score"] = grounding.get("score", 0.0)
    else:
        # Answer is grounded — add the score for transparency
        answer_dict["grounding_score"] = grounding.get("score", 1.0)

    return answer_dict