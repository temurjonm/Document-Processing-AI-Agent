# Four tools the ReAct agent can use:
# 1. search_docs — find relevant chunks using hybrid search
# 2. extract_table — pull structured table data from a PDF page
# 3. compare_sections — compare two sets of text using LLM
# 4. summarize — condense chunks into a short summary

import json
import os
import tempfile
import fitz
import boto3
from openai import OpenAI
from src.config import AWS_REGION, OPENAI_API_KEY, SIMPLE_MODEL
from src.search.hybrid import hybrid_search
from src.storage.document_store import get_document_status, local_uploaded_file_path

_client = OpenAI(api_key=OPENAI_API_KEY)

def search_docs(query: str, vector_store, bm25_index, doc_id: str = None) -> list[dict]:
    """
    Search for relevant document chunks using hybrid search.
    This is the most-used tool — the agent calls it on almost every query.

    Args:
        query: what to search for
        vector_store: ChromaDB wrapper instance
        bm25_index: BM25 index instance
        doc_id: optional — restrict search to one document
    Returns:
        list of {text, page_num, score} — the top relevant chunks
    """
    results = hybrid_search(query, vector_store, bm25_index, top_k=5)
    if doc_id:
        # Filter results to only include chunks from the specified document
        results = [r for r in results if r['doc_id'] == doc_id]
    
    return [
        {
            "text": r["text"][:500],
            "page_num": r["page_num"],
            "score": round(r["score"], 3)
        }
        for r in results
    ]

def extract_table(doc_id: str, page_num: int) -> dict:
    """
    Extract table data from a specific page of a PDF.
    Uses PyMuPDF's built-in table detection — no ML models needed.

    Args:
        doc_id: which document to look in
        page_num: which page (1-indexed)
    Returns:
        {headers, rows} or {error} if no table found
    """
    status = get_document_status(doc_id)
    if "error" in status:
        return {"error": f"Document {doc_id} not found"}

    local_path = local_uploaded_file_path(doc_id, status.get("filename"))
    if local_path:
        return _extract_table_from_path(local_path, page_num)

    s3_bucket = status.get("s3_bucket")
    s3_key = status.get("s3_key")
    if not s3_bucket or not s3_key:
        return {"error": f"Document {doc_id} has no accessible source file"}

    kwargs = {}
    if AWS_REGION:
        kwargs["region_name"] = AWS_REGION

    with tempfile.TemporaryDirectory(prefix="doc-agent-table-") as tmp_dir:
        local_file = os.path.join(tmp_dir, os.path.basename(s3_key))
        boto3.client("s3", **kwargs).download_file(s3_bucket, s3_key, local_file)
        return _extract_table_from_path(local_file, page_num)


def _extract_table_from_path(file_path: str, page_num: int) -> dict:
    doc = fitz.open(file_path)
    try:
        page_index = page_num - 1

        if page_index < 0 or page_index >= len(doc):
            return {"error": f"Page {page_num} does not exist (document has {len(doc)} pages)"}

        page = doc.load_page(page_index)
        tables = page.find_tables()
        if not tables.tables:
            return {"error": f"No tables found on page {page_num}"}

        data = tables[0].extract()
        return {
            "headers": data[0] if data else [],
            "rows": data[1:] if len(data) > 1 else [],
            "page_num": page_num,
        }
    finally:
        doc.close()

def compare_sections(chunks_a: list[str], chunks_b: list[str]) -> dict:
    """
    Use an LLM to compare two sets of text and find similarities/differences.
    Used for: "Compare the liability clauses in Contract A vs Contract B"

    Args:
        chunks_a: text chunks from the first document/section
        chunks_b: text chunks from the second document/section
    Returns:
        {similarities, differences, summary}
    """
    # Build the prompt for comparison
    prompt = f"""Compare these two sections and provide a structured analysis.

Section A:
{chr(10).join(chunks_a)}

Section B:
{chr(10).join(chunks_b)}

Respond in JSON:
{{
    "similarities": ["list of things that are the same"],
    "differences": ["list of things that differ"],
    "summary": "one paragraph overall comparison"
}}"""

    # Call the LLM to perform the comparison
    response = _client.chat.completions.create(
        model=SIMPLE_MODEL,  # gpt-4o-mini is fine for comparison tasks
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,  # low creativity — we want accurate comparison
        response_format={"type": "json_object"}
    )

    # Parse the JSON response
    result = json.loads(response.choices[0].message.content)
    return result


def summarize(chunks: list[dict], max_words: int = 200) -> dict:
    """
    Summarize a set of chunks into a concise paragraph.
    Used for: "Summarize this document" or "Give me the key points"

    Args:
        chunks: list of {text, page_num} to summarize
        max_words: word limit for the summary
    Returns:
        {summary, source_pages}
    """
    # Combine all chunk texts
    combined = "\n\n".join(c["text"] for c in chunks)

    # Get the page numbers for source attribution
    source_pages = sorted(set(c["page_num"] for c in chunks))

    prompt = f"""Summarize the following content in {max_words} words or less.
            Be concise and focus on the key points.
            Content:
            {combined}
            Respond in JSON:
            {{
                "summary": "your summary here"
            }}"""

    response = _client.chat.completions.create(
        model=SIMPLE_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,  # slightly higher temp for more natural summary language
        response_format={"type": "json_object"}
    )

    result = json.loads(response.choices[0].message.content)
    result["source_pages"] = source_pages

    return result

# These JSON Schema definitions tell the LLM what tools are available,
# what arguments each tool accepts, and what each tool does.
# The LLM reads these to decide which tool to call.
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "search_docs",
            "description": "Search all indexed documents for relevant information. Documents are already uploaded and indexed — call this tool with your search query. You do NOT need a doc_id; omit it to search all documents.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query — be specific about what you're looking for"
                    },
                    "doc_id": {
                        "type": "string",
                        "description": "Optional: restrict search to a specific document ID"
                    }
                },
                "required": ["query"]  # query is required, doc_id is optional
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "extract_table",
            "description": "Extract a table from a specific page of a PDF document. Use when the user asks about tabular data.",
            "parameters": {
                "type": "object",
                "properties": {
                    "doc_id": {
                        "type": "string",
                        "description": "The document ID to extract the table from"
                    },
                    "page_num": {
                        "type": "integer",
                        "description": "The page number (1-indexed) containing the table"
                    }
                },
                "required": ["doc_id", "page_num"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "compare_sections",
            "description": "Compare two sections of text and identify similarities and differences. Use when asked to compare documents or sections.",
            "parameters": {
                "type": "object",
                "properties": {
                    "chunks_a": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Text chunks from the first section"
                    },
                    "chunks_b": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Text chunks from the second section"
                    }
                },
                "required": ["chunks_a", "chunks_b"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "summarize",
            "description": "Summarize a set of document chunks. Use when asked to summarize or give key points.",
            "parameters": {
                "type": "object",
                "properties": {
                    "chunk_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "IDs of chunks to summarize"
                    },
                    "max_words": {
                        "type": "integer",
                        "description": "Maximum words in the summary (default: 200)"
                    }
                },
                "required": ["chunk_ids"]
            }
        }
    }
]
