# ReAct (Reason + Act) agent loop:
# 1. Think: "What do I need to find out?"
# 2. Act: Call a tool (search, extract, compare, summarize)
# 3. Observe: Read the tool's result
# 4. Repeat until enough info gathered, then generate final answer
#
# This is more powerful than single-hop RAG because it can:
# - Search multiple documents separately, then compare
# - Extract a table, then search for context about that table
# - Iteratively refine its search based on what it finds

import time
import json
from openai import OpenAI
from src.config import OPENAI_API_KEY, COMPLEX_MODEL, MAX_AGENT_ITERATIONS, AGENT_TIMEOUT_SECONDS
from src.agent.tools import search_docs, extract_table, compare_sections, summarize, TOOL_DEFINITIONS

_client = OpenAI(api_key=OPENAI_API_KEY)

# ── Agent System Prompt ──
# Tells the LLM it's an agent that should think step by step
AGENT_SYSTEM_PROMPT = """You are a document analysis agent. Documents have already been uploaded and indexed — you MUST use the search_docs tool to find information. Never say "please provide a document" — the documents are already in the system.

Think step by step:
1. Understand what the user is asking
2. ALWAYS call search_docs first to find relevant content
3. Call additional tools if needed (extract_table, compare_sections, summarize)
4. When you have enough information, provide your final answer

Rules:
- ALWAYS use search_docs before answering — never skip this step
- The documents are already indexed and searchable
- Cite sources with [Page X] format
- If search returns no results, say "I couldn't find relevant information in the indexed documents"
- Be concise but thorough"""

def run_agent(
    query: str,
    vector_store,
    bm25_index,
    model: str = None
) -> dict:
    """
    Run the ReAct agent loop.

    Args:
        query: the user's question
        vector_store: ChromaDB wrapper
        bm25_index: BM25 index
        model: LLM model to use (defaults to COMPLEX_MODEL)
    Returns:
        {answer, confidence, sources, steps, total_tokens, latency_ms}
    """
    model = model or COMPLEX_MODEL
    start_time = time.time()
    
    messages = [
        {"role": "system", "content": AGENT_SYSTEM_PROMPT},
        {"role": "user", "content": query}
    ]

    steps = []
    gathered_chunks = []   # Store search results so summarize can use them later
    total_tokens = 0
    iteration = 0

    # The ReAct Loop
    while iteration < MAX_AGENT_ITERATIONS:
        iteration += 1

        elapsed = time.time() - start_time

        if elapsed > AGENT_TIMEOUT_SECONDS:
            # Add a message telling the agent to wrap up
            messages.append({
                "role": "user",
                "content": "You have run out of time. Please provide your best answer now with what you've found so far."
            })

        # ── Call the LLM ──
        # First iteration: FORCE the agent to call search_docs
        # Later iterations: let it decide (auto)
        if iteration == 1:
            # Force the agent to search first — it must gather evidence before answering
            current_tool_choice = {
                "type": "function",
                "function": {"name": "search_docs"}
            }
        else:
            # After the first search, let the agent decide: call more tools or answer
            current_tool_choice = "auto"

        response = _client.chat.completions.create(
            model=model,
            messages=messages,
            tools=TOOL_DEFINITIONS,     # available tools the agent can call
            tool_choice=current_tool_choice,  # forced on iter 1, auto after
            temperature=0.1
        )

        # Track token usage
        total_tokens += response.usage.total_tokens

        # Get the assistant's message
        assistant_message = response.choices[0].message

        # Add the assistant's response to the conversation history
        # This preserves the full chain of thought
        messages.append(assistant_message)

        # ── Check if the agent wants to call a tool ──
        if assistant_message.tool_calls:
            # The agent chose to call one or more tools
            for tool_call in assistant_message.tool_calls:
                tool_name = tool_call.function.name
                tool_args = json.loads(tool_call.function.arguments)

                # Execute the tool and get the result
                tool_result = _execute_tool(
                    tool_name, tool_args, vector_store, bm25_index,
                    gathered_chunks=gathered_chunks
                )

                # If search_docs returned results, save them for later tools
                if tool_name == "search_docs" and isinstance(tool_result, list):
                    gathered_chunks.extend(tool_result)

                # Record this step for the user to see the agent's reasoning
                steps.append({
                    "iteration": iteration,
                    "tool": tool_name,
                    "args": tool_args,
                    "result_summary": _summarize_tool_result(tool_result)
                })

                # Add the tool result back to the conversation
                # The LLM will read this on the next iteration
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,  # links result to the specific call
                    "content": json.dumps(tool_result)  # tool results must be strings
                })
        else:
            # ── No tool call = agent is ready to give final answer ──
            # The agent's response IS the final answer
            final_answer = _parse_final_answer(assistant_message.content)

            latency_ms = int((time.time() - start_time) * 1000)

            return {
                "answer": final_answer.get("answer", assistant_message.content),
                "confidence": final_answer.get("confidence", "medium"),
                "sources": final_answer.get("sources", []),
                "steps": steps,             # the agent's reasoning trace
                "total_tokens": total_tokens,
                "latency_ms": latency_ms,
                "iterations": iteration,
                "model": model
            }

    # ── Max iterations reached ──
    # Force the agent to answer with what it has
    latency_ms = int((time.time() - start_time) * 1000)
    return {
        "answer": "I reached the maximum number of reasoning steps. Based on what I found: " + (steps[-1]["result_summary"] if steps else "No results found."),
        "confidence": "low",
        "sources": [],
        "steps": steps,
        "total_tokens": total_tokens,
        "latency_ms": latency_ms,
        "iterations": iteration,
        "model": model
    }


def _execute_tool(
    tool_name: str,
    tool_args: dict,
    vector_store,
    bm25_index,
    gathered_chunks: list = None
) -> dict:
    """
    Dispatch a tool call to the correct function.
    This is basically a switch statement mapping tool names to functions.
    gathered_chunks: search results from earlier iterations, used by summarize.
    """
    if tool_name == "search_docs":
        return search_docs(
            query=tool_args["query"],
            vector_store=vector_store,
            bm25_index=bm25_index,
            doc_id=tool_args.get("doc_id")  # optional argument
        )
    elif tool_name == "extract_table":
        return extract_table(
            doc_id=tool_args["doc_id"],
            page_num=tool_args["page_num"]
        )
    elif tool_name == "compare_sections":
        return compare_sections(
            chunks_a=tool_args["chunks_a"],
            chunks_b=tool_args["chunks_b"]
        )
    elif tool_name == "summarize":
        # Use chunks gathered from previous search_docs calls.
        # The LLM sends chunk_ids (strings), but summarize() needs list[dict]
        # with "text" and "page_num" keys — so we use gathered_chunks instead.
        chunks_for_summary = gathered_chunks if gathered_chunks else []

        # Fallback: if no chunks were gathered yet, do a quick search
        if not chunks_for_summary:
            fallback_query = " ".join(tool_args.get("chunk_ids", ["document summary"]))
            chunks_for_summary = search_docs(
                query=fallback_query,
                vector_store=vector_store,
                bm25_index=bm25_index
            )

        return summarize(
            chunks=chunks_for_summary,
            max_words=tool_args.get("max_words", 200)
        )
    else:
        return {"error": f"Unknown tool: {tool_name}"}


def _summarize_tool_result(result) -> str:
    """
    Create a short summary of a tool result for the agent's step trace.
    We don't want to dump the full result into the steps — too verbose.
    """
    if isinstance(result, list):
        return f"Found {len(result)} results"
    elif isinstance(result, dict):
        if "error" in result:
            return f"Error: {result['error']}"
        elif "summary" in result:
            return result["summary"][:100]  # first 100 chars of summary
        elif "similarities" in result:
            return f"{len(result.get('differences', []))} differences found"
        else:
            return f"Result with {len(result)} fields"
    return str(result)[:100]


def _parse_final_answer(content: str) -> dict:
    """
    Try to parse the agent's final answer as JSON.
    If it's not JSON, wrap the raw text as the answer.
    """
    try:
        return json.loads(content)
    except (json.JSONDecodeError, TypeError):
        # Agent gave a plain text answer instead of JSON — that's fine
        return {
            "answer": content,
            "confidence": "medium",
            "sources": []
        }