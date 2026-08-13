"""Tests for grouping retrieved chunks into numbered sources."""

from observatory.rag.answer import group_sources
from observatory.repository import RetrievedChunk


def _chunk(doc_id: str, score: float, content: str = "text") -> RetrievedChunk:
    return RetrievedChunk(
        doc_type="article",
        doc_id=doc_id,
        content=content,
        score=score,
        title=f"Title {doc_id}",
        url=f"https://example.com/{doc_id}",
    )


def test_same_document_chunks_share_one_number():
    grouped = group_sources(
        [_chunk("42", 0.30, "first piece"), _chunk("42", 0.35, "second piece")]
    )
    assert len(grouped) == 1
    assert grouped[0].number == 1
    assert grouped[0].contents == ["first piece", "second piece"]
    assert grouped[0].best_score == 0.30  # score of the first (best) chunk


def test_different_documents_get_sequential_numbers():
    grouped = group_sources([_chunk("a", 0.30), _chunk("b", 0.35), _chunk("c", 0.40)])
    assert [g.number for g in grouped] == [1, 2, 3]
    assert [g.doc_id for g in grouped] == ["a", "b", "c"]


def test_numbering_follows_best_chunk_rank():
    # doc "b" appears between two chunks of doc "a": "a" keeps number 1
    grouped = group_sources([_chunk("a", 0.30), _chunk("b", 0.35), _chunk("a", 0.40)])
    assert len(grouped) == 2
    assert grouped[0].doc_id == "a"
    assert grouped[0].number == 1
    assert len(grouped[0].contents) == 2
    assert grouped[1].doc_id == "b"
    assert grouped[1].number == 2
