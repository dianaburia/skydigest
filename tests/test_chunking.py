"""Tests for RAG text chunking."""

from observatory.rag.chunking import chunk_text


def _make_text(n_sentences: int) -> str:
    return " ".join(f"Sentence number {i} is right here." for i in range(n_sentences))


def test_empty_text_returns_no_chunks():
    assert chunk_text("") == []
    assert chunk_text("   \n  ") == []


def test_short_text_single_chunk():
    text = "One short sentence. And another one."
    assert chunk_text(text) == [text]


def test_long_text_multiple_chunks_within_limit():
    chunks = chunk_text(_make_text(60), chunk_size=1000, overlap=150)
    assert len(chunks) > 1
    assert all(len(chunk) <= 1000 for chunk in chunks)


def test_consecutive_chunks_overlap():
    chunks = chunk_text(_make_text(60), chunk_size=1000, overlap=150)
    for first, second in zip(chunks, chunks[1:]):
        # the last sentence of one chunk must reappear at the start of the next
        last_sentence = first.rsplit(". ", 1)[-1]
        assert last_sentence in second


def test_chunks_end_on_sentence_boundary():
    chunks = chunk_text(_make_text(60))
    for chunk in chunks[:-1]:
        assert chunk.endswith(".")


def test_sentence_longer_than_chunk_size_is_hard_split():
    # 3000 chars with no punctuation: must still be split, nothing lost
    text = "x" * 3000
    chunks = chunk_text(text, chunk_size=1000, overlap=150)
    assert all(len(chunk) <= 1000 for chunk in chunks)
    assert sum(len(chunk.replace(" ", "")) for chunk in chunks) == 3000
