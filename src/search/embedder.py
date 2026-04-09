from openai import OpenAI
from src.config import OPENAI_API_KEY, EMBEDDING_MODEL, EMBEDDING_BATCH_SIZE

_client = OpenAI(api_key=OPENAI_API_KEY)

def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a list of texts using OpenAI's embedding model."""
    embeddings = []
    for i in range(0, len(texts), EMBEDDING_BATCH_SIZE):
        batch = texts[i:i + EMBEDDING_BATCH_SIZE]
        response = _client.embeddings.create(input=batch, model=EMBEDDING_MODEL)
        batch_embeddings = [data.embedding for data in response.data]
        embeddings.extend(batch_embeddings)
    return embeddings

def embed_query(query: str) -> list[float]:
    """Embed a single query string."""
    response = _client.embeddings.create(input=query, model=EMBEDDING_MODEL)
    return response.data[0].embedding