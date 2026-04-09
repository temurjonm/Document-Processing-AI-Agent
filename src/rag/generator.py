import time
import json
from openai import OpenAI
from src.config import OPENAI_API_KEY, SIMPLE_MODEL

_client = OpenAI(api_key=OPENAI_API_KEY)

SYSTEM_PROMPT = """You are a document analysis assistant. Answer the question based ONLY on the provided context.

Rules:
- ONLY use information from the context below. Do NOT use your training knowledge.
- If the context doesn't contain enough information, say "I don't have enough information to answer this."
- Cite your sources using [Page X] format inline with your answer.
- Rate your confidence: high (directly stated), medium (inferred), low (partially supported).

You must respond in JSON format:
{
    "answer": "your answer with [Page X] citations",
    "confidence": "high|medium|low",
    "sources": [1, 4, 7]
}"""

def generate_answer(query: str, chunks: list[dict], model: str = None) -> dict:
    model = model or SIMPLE_MODEL
    context_parts = []
    for chunk in chunks:
        context_parts.append(f"[Page {chunk['page_num']}] {chunk['text']}")
    context = "\n\n".join(context_parts)

    user_message = f"""Context:\n{context}\n\nQuestion: {query}"""
    start_time = time.time()

    response = _client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},  # instructions
            {"role": "user", "content": user_message}       # context + question
        ],
        temperature=0.1,  # low temperature = more deterministic, less creative
        # 0.1 not 0.0 because 0.0 can cause repetition loops in some models
        response_format={"type": "json_object"}  # force JSON output
    )

    # Calculate how long the LLM call took
    latency_ms = int((time.time() - start_time) * 1000)

    raw_content = response.choices[0].message.content

    try:
        parsed = json.loads(raw_content)
    except json.JSONDecodeError:
        parsed = {
            "answer": raw_content,
            "confidence": "low",
            "sources": []
        }

    tokens_used = response.usage.total_tokens
    return {
        "answer": parsed.get("answer", ""),
        "confidence": parsed.get("confidence", "low"),
        "sources": parsed.get("sources", []),
        "tokens_used": tokens_used,
        "latency_ms": latency_ms,
        "model": model
    }