"""Semantic retrieval: question text in, relevant chunks out.

The bridge between human text and the vector index. The question MUST be
embedded by the same model and normalization as the indexed chunks —
comparing points from different embedding spaces yields silent nonsense.
Both paths go through embeddings.py, which guarantees that.
"""

from observatory.rag.embeddings import embed_texts
from observatory.repository import RetrievedChunk, search_chunks


def retrieve(question: str, top_k: int = 8) -> list[RetrievedChunk]:
    """Return the top_k chunks semantically closest to the question."""
    vector = embed_texts([question])[0]
    return search_chunks(vector, limit=top_k)
