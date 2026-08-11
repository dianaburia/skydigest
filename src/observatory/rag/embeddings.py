"""Text embeddings via sentence-transformers.

The single place in the project that touches the embedding model. The model
name comes from Settings.embedding_model (never hardcoded) so it can be
swapped via .env for the planned model-comparison experiment.
"""

from functools import lru_cache

from sentence_transformers import SentenceTransformer

from observatory.config import get_settings


@lru_cache
def get_model() -> SentenceTransformer:
    """Load the embedding model once per process. First call is slow
    (downloads ~2 GB to the HuggingFace cache on the very first run,
    then loads it into RAM); every later call returns the cached model."""
    return SentenceTransformer(get_settings().embedding_model)


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts into 1024-dim unit-length vectors.

    normalize_embeddings=True makes every vector length 1, which our HNSW
    index (vector_cosine_ops) expects for meaningful cosine distances.
    """
    if not texts:
        return []
    vectors = get_model().encode(texts, normalize_embeddings=True)
    return [vector.tolist() for vector in vectors]
