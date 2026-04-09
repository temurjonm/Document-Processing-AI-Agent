# Routes queries to the right LLM model based on complexity.
# Simple queries (70%) → GPT-4o-mini at $0.15/M tokens
# Complex queries (30%) → GPT-4o at $2.50/M tokens
# Result: ~60% cost savings compared to always using GPT-4o.
# Interviewers LOVE this — always mention model routing when asked about cost.

import json
from openai import OpenAI
from src.config import OPENAI_API_KEY, SIMPLE_MODEL, COMPLEX_MODEL

_client = OpenAI(api_key=OPENAI_API_KEY)


def classify_intent(query: str) -> str:
    """
    Classify the user's query into an intent category.
    Uses GPT-4o-mini — costs ~100 tokens (~$0.00001) per classification.
    That's essentially free, and it saves dollars on downstream model selection.

    Intent categories:
    - simple_lookup: "What is the effective date?" → just find one fact
    - summarize: "Summarize section 3" → condense content
    - compare: "Compare Contract A vs B" → multi-document analysis
    - extract: "Extract all dates from this document" → structured extraction
    - analyze: "What are the risks in this contract?" → deep reasoning

    Returns: one of the intent strings above
    """
    prompt = f"""Classify this query into exactly one category.

Categories:
- simple_lookup: finding a specific fact or data point
- summarize: condensing or summarizing content
- compare: comparing two or more things
- extract: extracting structured data (dates, names, tables)
- analyze: deep analysis requiring reasoning

Query: "{query}"

Respond with just the category name, nothing else."""

    response = _client.chat.completions.create(
        model=SIMPLE_MODEL,  # use the cheap model for classification
        messages=[{"role": "user", "content": prompt}],
        temperature=0,  # 0 = completely deterministic — we want consistent classification
        max_tokens=20   # the answer is one word, we don't need more
    )

    # Get the classification and clean it up
    intent = response.choices[0].message.content.strip().lower()

    # Validate — if the LLM returned something unexpected, default to simple_lookup
    valid_intents = ["simple_lookup", "summarize", "compare", "extract", "analyze"]
    if intent not in valid_intents:
        intent = "simple_lookup"  # safe default — uses the cheap model

    return intent


def select_model(intent: str) -> str:
    """
    Choose the LLM model based on query intent.
    Simple tasks → cheap model. Complex tasks → powerful model.

    This is the actual cost savings logic:
    - 70% of real-world queries are simple_lookup or summarize
    - Those go to GPT-4o-mini ($0.15/M tokens)
    - Only 30% need GPT-4o ($2.50/M tokens)
    - Weighted average: 0.7 × $0.15 + 0.3 × $2.50 = $0.855/M
    - vs always GPT-4o: $2.50/M → that's a 66% savings
    """
    # Map intents to models
    # Simple tasks don't need the expensive model
    if intent in ["simple_lookup", "summarize"]:
        return SIMPLE_MODEL   # "gpt-4o-mini" — fast and cheap

    # Complex tasks need stronger reasoning
    # compare, extract, analyze → GPT-4o
    return COMPLEX_MODEL  # "gpt-4o" — slower but much smarter