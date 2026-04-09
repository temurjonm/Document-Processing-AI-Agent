import chromadb
from src.config import CHROMA_PATH
from src.search.embedder import embed_texts, embed_query

class VectorStore:

    def __init__(self):
        self._client = chromadb.PersistentClient(path=CHROMA_PATH)

        self._collection = self._client.get_or_create_collection(
            name="documents",
            metadata={"hnsw:space": "cosine"}  # explicitly set cosine similarity
        )

    def add_chunks(self, chunks: list[dict]):
        """Add text chunks to the vector store."""
        texts = [c["text"] for c in chunks]
        embeddings = embed_texts(texts)
        metadatas = [
            {
                "doc_id": c["doc_id"],
                "page_num": c["page_num"],
                "token_count": c["token_count"]
            }
            for c in chunks
        ]
        ids = [c["chunk_id"] for c in chunks]
        self._collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas
        )

    def search(self, query: str, top_k: int = 20, doc_id: str = None) -> list[dict]:
        """Search for relevant chunks based on a query."""
        query_embedding = embed_query(query)
        filters = {"doc_id": doc_id} if doc_id else None
        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=filters
        )
        parsed = []
        for i in range(len(results["ids"][0])):
            # Convert distance to similarity: similarity = 1 - distance
            # Distance 0.0 → Similarity 1.0 (perfect match)
            # Distance 1.0 → Similarity 0.0 (no match)
            distance = results["distances"][0][i]
            similarity = 1.0 - distance

            parsed.append({
                "chunk_id": results["ids"][0][i],
                "text": results["documents"][0][i],
                "page_num": results["metadatas"][0][i]["page_num"],
                "doc_id": results["metadatas"][0][i]["doc_id"],
                "score": similarity  # higher = more similar
            })

        return parsed

    def delete_document(self, doc_id: str):
        """Delete all chunks associated with a specific document ID."""
        self._collection.delete(where={"doc_id": doc_id})

    def get_stats(self) -> dict:
        """Get statistics about the vector store."""
        return {
            "total_chunks": self._collection.count(),
            "collection_name": "documents"
        }

    def get_all_chunks(self) -> list[dict]:
        results = self._collection.get()
        chunks = []
        for i in range(len(results["ids"])):
            chunks.append({
                "chunk_id": results["ids"][i],
                "text": results["documents"][i],
                "page_num": results["metadatas"][i]["page_num"],
                "doc_id": results["metadatas"][i]["doc_id"],
                "token_count": results["metadatas"][i].get("token_count", 0),
            })
        return chunks
