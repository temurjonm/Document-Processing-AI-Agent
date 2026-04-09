from rank_bm25 import BM25Okapi
import numpy as np

class BM25Index:

    def __init__(self):
        """Initialize an empty index. Call build() to populate it."""
        self._bm25 = None       # the BM25 model — None until build() is called
        self._chunks = []        # stores chunk data for lookup after search
        self._tokenized = []     # tokenized versions of chunk texts

    def build(self, chunks: list[dict]):
        """Build the BM25 index from a list of text chunks."""
        if not chunks:
            self._bm25 = None
            self._chunks = []
            self._tokenized = []
            return

        self._chunks = chunks
        self._tokenized = [chunk["text"].lower().split() for chunk in chunks]
        self._bm25 = BM25Okapi(self._tokenized)

    def search(self, query: str, top_k: int = 20) -> list[dict]:
        if self._bm25 is None:
            return []
        
        query_tokens = query.lower().split()
        scores = self._bm25.get_scores(query_tokens)
        top_indices = np.argsort(scores)[::-1][:top_k]
        results = []
        for idx in top_indices:
            if scores[idx] == 0:
                continue

            results.append({
                "chunk_id": self._chunks[idx]["chunk_id"],
                "text": self._chunks[idx]["text"],
                "page_num": self._chunks[idx]["page_num"],
                "doc_id": self._chunks[idx]["doc_id"],
                "score": float(scores[idx])
            })

        return results
    
    def add_chunks(self, new_chunks: list[dict]) -> None:
        # Append new chunks to existing ones
        self._chunks.extend(new_chunks)
        # Rebuild the index from scratch with all chunks
        self.build(self._chunks)

    def delete_document(self, doc_id: str) -> None:
        self._chunks = [chunk for chunk in self._chunks if chunk["doc_id"] != doc_id]
        if self._chunks:
            self.build(self._chunks)
        else:
            self._bm25 = None
            self._tokenized = []
