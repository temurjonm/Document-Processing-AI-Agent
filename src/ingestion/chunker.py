import tiktoken  # OpenAI's tokenizer — counts tokens the same way the LLM does
import uuid  # for generating unique chunk IDs
from src.config import CHUNK_SIZE, CHUNK_OVERLAP, SEPARATORS  # our settings

_encoder = tiktoken.get_encoding("cl100k_base")

def count_tokens(text: str) -> int:
    return len(_encoder.encode(text))

def chunk_document(pages: list[dict], doc_id: str) -> list[dict]:
    all_chunks = []
    for page in pages:
        page_num = page["page"]
        text = page["text"]

        pieces = _recursive_split(text, SEPARATORS, CHUNK_SIZE)

        for piece in pieces:
            chunk = {
                "chunk_id": str(uuid.uuid4()),  # unique ID for this chunk
                "doc_id": doc_id,                # which document this came from
                "text": piece,                   # the actual text content
                "page_num": page_num,            # which page (for citations)
                "token_count": count_tokens(piece)  # how many tokens (for monitoring)
            }
            all_chunks.append(chunk)
    all_chunks = _add_overlap(all_chunks)
    return all_chunks

def _recursive_split(text: str, separators: list[str], max_tokens: int) -> list[str]:
    if count_tokens(text) <= max_tokens:
        return [text]
    if not separators:
        return _force_split(text, max_tokens)
    
    separator = separators[0]
    remaining_separators = separators[1:]
    parts = text.split(separator)

    result = []  
    current = "" 

    for part in parts:
        candidate = current + separator + part if current else part

        if count_tokens(candidate) <= max_tokens:
            current = candidate
        else:
            if current:
                result.append(current)
            if count_tokens(part) > max_tokens:
                result.extend(_recursive_split(part, remaining_separators, max_tokens))
                current = ""
            else:
                current = part

    if current:
        result.append(current)

    return result

def _force_split(text: str, max_tokens: int) -> list[str]:
    tokens = _encoder.encode(text)
    chunks = []
    for i in range(0, len(tokens), max_tokens):
        chunk_tokens = tokens[i:i + max_tokens]
        chunk_text = _encoder.decode(chunk_tokens)
        chunks.append(chunk_text)
    return chunks

def _add_overlap(chunks: list[dict]) -> list[dict]:
    if len(chunks) <= 1:
        return chunks
    
    for i in range(1, len(chunks)):
        prev_chunk = chunks[i - 1]
        curr_chunk = chunks[i]

        if prev_chunk["doc_id"] != curr_chunk["doc_id"]:
            continue

        prev_tokens = _encoder.encode(prev_chunk["text"])
        overlap_tokens = prev_tokens[-CHUNK_OVERLAP:]
        overlap_text = _encoder.decode(overlap_tokens)
        curr_chunk["text"] = overlap_text + curr_chunk["text"]
        curr_chunk["token_count"] = count_tokens(curr_chunk["text"])
    return chunks