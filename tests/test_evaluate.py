"""Tests for the pure scoring logic of the retrieval eval (no DB, no model)."""

from observatory.rag.evaluate import evaluate_question
from observatory.repository import RetrievedChunk


def _chunk(doc_type: str, ident: str) -> RetrievedChunk:
    """Build a chunk whose document identity is `ident` (url or arxiv_id)."""
    return RetrievedChunk(
        doc_type=doc_type,
        doc_id=ident if doc_type == "paper" else "42",
        content="...",
        score=0.3,
        title="t",
        url=ident if doc_type == "article" else "https://arxiv.org/abs/x",
    )


def test_require_any_hits_on_first_match_and_ranks_it():
    spec = {
        "id": 1,
        "question": "q",
        "require": "any",
        "expected": [
            {"doc_type": "article", "url": "https://example.com/a"},
            {"doc_type": "article", "url": "https://example.com/never-found"},
        ],
    }
    chunks = [_chunk("article", "https://example.com/other")] * 2 + [
        _chunk("article", "https://example.com/a")
    ]
    result = evaluate_question(spec, chunks)
    assert result.hit_at == {5: True, 8: True}
    assert result.first_rank == 3
    assert result.found_total == 1


def test_require_all_needs_every_doc_within_cutoff():
    spec = {
        "id": 2,
        "question": "q",
        "require": "all",
        "expected": [
            {"doc_type": "article", "url": "https://example.com/a"},
            {"doc_type": "paper", "arxiv_id": "2608.02601"},
        ],
    }
    # Article at rank 1, paper only at rank 6: 'all' holds at @8 but not @5.
    chunks = (
        [_chunk("article", "https://example.com/a")]
        + [_chunk("article", "https://example.com/noise")] * 4
        + [_chunk("paper", "2608.02601")]
    )
    result = evaluate_question(spec, chunks)
    assert result.hit_at == {5: False, 8: True}
    assert result.first_rank == 1


def test_arxiv_version_suffix_is_ignored():
    spec = {
        "id": 3,
        "question": "q",
        "require": "any",
        "expected": [{"doc_type": "paper", "arxiv_id": "2608.01621"}],
    }
    result = evaluate_question(spec, [_chunk("paper", "2608.01621v2")])
    assert result.hit_at[8] is True


def test_miss_yields_zero_reciprocal_rank():
    spec = {
        "id": 4,
        "question": "q",
        "require": "any",
        "expected": [{"doc_type": "article", "url": "https://example.com/a"}],
    }
    result = evaluate_question(spec, [_chunk("article", "https://example.com/b")])
    assert result.hit_at == {5: False, 8: False}
    assert result.first_rank is None
    assert result.reciprocal_rank == 0.0
