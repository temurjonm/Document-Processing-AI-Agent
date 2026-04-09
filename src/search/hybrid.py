from src.search.vector_store import VectorStore
from src.search.bm25_index import BM25Index
from src.config import DENSE_WEIGHT, BM25_WEIGHT

def hybrid_search(
    query: str,
    vector_store: VectorStore,
    bm25_index: BM25Index,
    top_k: int = 5
) -> list[dict]:
    dense_results = vector_store.search(query, top_k=20)
    bm25_results = bm25_index.search(query, top_k=20)
    
    dense_results = _normalize_scores(dense_results)
    bm25_results = _normalize_scores(bm25_results)

    merged = {}  # chunk_id → combined data

    for result in dense_results:
        cid = result["chunk_id"]
        merged[cid] = {
            "chunk_id": cid,
            "text": result["text"],
            "page_num": result["page_num"],
            "doc_id": result["doc_id"],
            "dense_score": result["score"],  # normalized dense score
            "bm25_score": 0.0                # default — will be updated if found in BM25 too
        }

    # Then, add/merge BM25 results
    for result in bm25_results:
        cid = result["chunk_id"]
        if cid in merged:
            merged[cid]["bm25_score"] = result["score"]  # update existing entry
        else:
            merged[cid] = {
                "chunk_id": cid,
                "text": result["text"],
                "page_num": result["page_num"],
                "doc_id": result["doc_id"],
                "dense_score": 0.0,             # default — not found in dense search
                "bm25_score": result["score"]   # BM25 score
            }

    for cid in merged:
        merged[cid]["score"] = (
            DENSE_WEIGHT * merged[cid]["dense_score"] +
            BM25_WEIGHT * merged[cid]["bm25_score"]
        )

    results = sorted(merged.values(), key=lambda x: x["score"], reverse=True)
    
    return results[:top_k]

def _normalize_scores(results: list[dict]) -> list[dict]:
    if not results:
        return results
    
    # Extract all scores
    scores = [r["score"] for r in results]
    min_score = min(scores)
    max_score = max(scores)

    if max_score == min_score:
        for r in results:
            r["score"] = 0.0
        return results
    
    # Apply min-max normalization to each result
    for r in results:
        r["score"] = (r["score"] - min_score) / (max_score - min_score)

    return results