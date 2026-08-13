"""RAG indexer: turn unindexed documents into embedded chunks.

Pipeline per run: fetch documents that have no chunks yet -> split each into
~1000-char chunks -> embed in batches -> store. Idempotent: a second run
finds nothing unindexed and does zero embedding work.

Transaction boundary is THE DOCUMENT: all chunks of one document are inserted
in a single insert_chunks call (one transaction). A crash mid-run therefore
leaves every document either fully indexed or fully pending — never half-done,
which the unindexed-document query could not detect.
"""

import logging
import sys

from observatory.infra.logging_setup import setup_logging
from observatory.rag.chunking import chunk_text
from observatory.rag.embeddings import embed_texts
from observatory.text import clean_text
from observatory.repository import (
    Article,
    Chunk,
    Paper,
    insert_chunks,
    list_unindexed_articles,
    list_unindexed_papers,
)

logger = logging.getLogger(__name__)

# Embed roughly this many chunks per model call: one big call is far faster
# than many small ones, but groups stay small enough for steady progress.
EMBED_BATCH_SIZE = 64


def _article_text(article: Article) -> str:
    """Text to index for an article: title + best available body, HTML stripped."""
    body = clean_text(article.content or article.summary)
    return f"{article.title}\n\n{body}".strip()


def _paper_text(paper: Paper) -> str:
    """Text to index for a paper: title + abstract."""
    return f"{paper.title}\n\n{paper.abstract}".strip()


def _build_chunks(doc_type: str, doc_id: str, text: str) -> list[Chunk]:
    """Chunk one document. Embeddings are filled in later, per batch group."""
    return [
        Chunk(
            doc_type=doc_type,
            doc_id=doc_id,
            chunk_index=i,
            content=piece,
            embedding=[],  # placeholder until the embedding pass
        )
        for i, piece in enumerate(chunk_text(text))
    ]


def _embed_and_store(group: list[list[Chunk]]) -> int:
    """Embed one group of documents in a single model call, then insert
    each document in its own transaction. Returns count of new chunks."""
    texts = [chunk.content for document in group for chunk in document]
    vectors = embed_texts(texts)
    position = 0
    for document in group:
        for chunk in document:
            chunk.embedding = vectors[position]
            position += 1
    return sum(insert_chunks(document) for document in group)


def index_documents() -> dict[str, int]:
    """Index everything new. Returns counts for logging/CLI."""
    articles = list_unindexed_articles()
    papers = list_unindexed_papers()

    documents: list[list[Chunk]] = []
    for article in articles:
        chunks = _build_chunks("article", str(article.id), _article_text(article))
        if chunks:
            documents.append(chunks)
    for paper in papers:
        chunks = _build_chunks("paper", paper.arxiv_id, _paper_text(paper))
        if chunks:
            documents.append(chunks)

    total_chunks = sum(len(d) for d in documents)
    logger.info(
        "Indexing %d articles + %d papers -> %d chunks",
        len(articles),
        len(papers),
        total_chunks,
    )

    inserted = 0
    processed = 0
    group: list[list[Chunk]] = []
    group_size = 0
    for document in documents:
        group.append(document)
        group_size += len(document)
        if group_size >= EMBED_BATCH_SIZE:
            inserted += _embed_and_store(group)
            processed += group_size
            logger.info("Progress: %d/%d chunks", processed, total_chunks)
            group, group_size = [], 0
    if group:
        inserted += _embed_and_store(group)

    return {
        "articles": len(articles),
        "papers": len(papers),
        "chunks_new": inserted,
    }


def main() -> int:
    setup_logging()
    counts = index_documents()
    print()
    print(f"Documents indexed: {counts['articles']} articles, {counts['papers']} papers")
    print(f"New chunks stored: {counts['chunks_new']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
