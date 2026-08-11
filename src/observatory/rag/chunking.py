"""Text chunking for the RAG index.

Splits documents into ~chunk_size character pieces on sentence boundaries,
with a ~overlap character tail carried over between consecutive chunks so
that a thought cut at a boundary survives intact in at least one chunk.

Pure logic: no database, no model, no network.
"""

import re

DEFAULT_CHUNK_SIZE = 1000
DEFAULT_OVERLAP = 150

# Split after sentence-ending punctuation followed by whitespace.
# Known limitation: abbreviations like "Dr. Smith" produce a false split;
# harmless for retrieval, so we keep the rule simple.
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def split_sentences(text: str) -> list[str]:
    """Split text into sentences. Empty/whitespace input yields []."""
    text = text.strip()
    if not text:
        return []
    return [part.strip() for part in _SENTENCE_END.split(text) if part.strip()]


def _overlap_tail(sentences: list[str], overlap: int) -> list[str]:
    """Last sentences from the end whose combined length fits in `overlap`."""
    tail: list[str] = []
    total = 0
    for sentence in reversed(sentences):
        if total + len(sentence) > overlap:
            break
        tail.insert(0, sentence)
        total += len(sentence)
    return tail


def chunk_text(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
) -> list[str]:
    """Split text into chunks of at most ~chunk_size chars on sentence boundaries.

    Consecutive chunks share a ~overlap character tail. Text shorter than
    chunk_size comes back as a single chunk. A single sentence longer than
    chunk_size (e.g. text without punctuation) is hard-split at chunk_size.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    sentences = split_sentences(text)
    if not sentences:
        return []

    # Guard against pathological input: a "sentence" longer than a whole
    # chunk gets hard-split so no chunk can exceed chunk_size.
    pieces: list[str] = []
    for sentence in sentences:
        if len(sentence) <= chunk_size:
            pieces.append(sentence)
        else:
            pieces.extend(
                sentence[i : i + chunk_size]
                for i in range(0, len(sentence), chunk_size)
            )

    chunks: list[str] = []
    current: list[str] = []
    length = 0
    for piece in pieces:
        if current and length + len(piece) + 1 > chunk_size:
            chunks.append(" ".join(current))
            current = _overlap_tail(current, overlap)
            length = sum(len(s) for s in current) + max(len(current) - 1, 0)
        current.append(piece)
        length += len(piece) + (1 if length else 0)
    if current:
        chunks.append(" ".join(current))
    return chunks
