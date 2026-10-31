"""Tests for the clustering algorithm and its journal integration (no DB)."""

from observatory.journal.generate import build_sources
from observatory.rag.clustering import cluster_ids, cosine_distance
from observatory.repository import Article

# Simple 2D directions: a and b point almost the same way, c is orthogonal.
VEC_A = [1.0, 0.0]
VEC_B = [0.98, 0.2]
VEC_C = [0.0, 1.0]


def test_near_vectors_merge_far_ones_do_not():
    clusters = cluster_ids({1: VEC_A, 2: VEC_B, 3: VEC_C}, threshold=0.26)
    as_sets = sorted(sorted(c) for c in clusters)
    assert as_sets == [[1, 2], [3]]


def test_identical_vectors_have_zero_distance():
    assert cosine_distance(VEC_A, VEC_A) < 1e-9


def test_threshold_zero_keeps_everything_apart():
    clusters = cluster_ids({1: VEC_A, 2: VEC_B}, threshold=0.0)
    assert len(clusters) == 2


def test_build_sources_merges_cluster_into_one_numbered_source():
    primary = Article(
        source="nasa",
        url="https://example.com/nasa",
        title="Big story",
        summary="A long detailed summary of the big story this week.",
        id=1,
    )
    reprint = Article(
        source="physorg",
        url="https://example.com/phys",
        title="Big story (reprint)",
        summary="Short.",
        id=2,
    )
    solo = Article(
        source="esa", url="https://example.com/esa", title="Other story", id=3
    )
    sources = build_sources([[reprint, primary], [solo]], papers=[])

    assert [s.number for s in sources] == [1, 2]
    # The member with the most text represents the event...
    assert sources[0].url == primary.url
    # ...and the reprint rides along as an alternative link.
    assert [a.url for a in sources[0].also_covered_by] == [reprint.url]
    assert sources[1].also_covered_by == []
