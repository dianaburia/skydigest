"""Agglomerative clustering of articles into events (step 2.3, ML-1).

The same story syndicated by several outlets (phys.org reprinting NASA,
universetoday covering the same paper) wastes journal space and retrieval
slots. Articles whose embeddings sit closer than CLUSTER_THRESHOLD are
merged into one event: average-linkage agglomerative clustering with
cosine distance.

Pure Python on ~150 vectors — no numpy/scipy, so the slim cron-journal
image (no ML extra) can run it: embeddings are NOT computed here, they
are read back from the chunks table where the indexer already stored them.

Threshold tuning: labeled pairs live in tests/eval_questions.json under
"duplicate_pairs"; `python -m observatory.rag.clustering` prints their
distances so the threshold is chosen from data, not vibes (history in
EVAL.md).
"""

import json
import math
import sys
from pathlib import Path

from observatory.infra.logging_setup import setup_logging
from observatory.repository import get_article_embeddings, get_article_ids_by_url

# Chosen from labeled duplicate/non-duplicate pairs (EVAL.md, 2026-10-31):
# measured duplicates span 0.141-0.223, distinct same-topic stories start at
# 0.293 (the Swift rescue-launched vs rescue-called-off hard negative), so the
# threshold sits mid-gap. Retune via `python -m observatory.rag.clustering`
# whenever the embedding model or the pair set changes.
CLUSTER_THRESHOLD = 0.26

EVAL_SET_PATH = Path("tests/eval_questions.json")


def cosine_distance(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 1.0
    return 1.0 - dot / (norm_a * norm_b)


def cluster_ids(
    embeddings: dict[int, list[float]], threshold: float = CLUSTER_THRESHOLD
) -> list[list[int]]:
    """Group ids whose vectors are closer than `threshold` (average linkage).

    Classic agglomerative loop: start with singletons, repeatedly merge the
    two closest clusters while their average pairwise distance is below the
    threshold. O(n^3) worst case — fine for a weekly batch of ~150 articles.
    """
    ids = list(embeddings)
    base = {
        (i, j): cosine_distance(embeddings[i], embeddings[j])
        for idx, i in enumerate(ids)
        for j in ids[idx + 1 :]
    }

    def pair_distance(i: int, j: int) -> float:
        return base[(i, j)] if (i, j) in base else base[(j, i)]

    def linkage(c1: list[int], c2: list[int]) -> float:
        pairs = [(i, j) for i in c1 for j in c2]
        return sum(pair_distance(i, j) for i, j in pairs) / len(pairs)

    clusters = [[i] for i in ids]
    while len(clusters) > 1:
        best = None
        best_dist = threshold
        for a in range(len(clusters)):
            for b in range(a + 1, len(clusters)):
                d = linkage(clusters[a], clusters[b])
                if d < best_dist:
                    best, best_dist = (a, b), d
        if best is None:
            break
        a, b = best
        clusters[a] = clusters[a] + clusters[b]
        del clusters[b]
    return clusters


def cluster_articles(articles, threshold: float = CLUSTER_THRESHOLD):
    """Group Article objects into events, preserving recency order.

    Articles whose embeddings are not in the chunks table yet (ingested
    after the last indexer run) become singleton clusters — better to show
    a possible duplicate than to drop a story.
    """
    by_id = {a.id: a for a in articles if a.id is not None}
    embeddings = get_article_embeddings(list(by_id))
    groups = cluster_ids(embeddings, threshold)

    clusters = [[by_id[i] for i in group] for group in groups]
    clusters += [[a] for a in articles if a.id not in embeddings]
    # Stable order: clusters sorted by their most recent member's position
    # in the input list (which list_recent_articles returns newest-first).
    position = {id(a): idx for idx, a in enumerate(articles)}
    clusters.sort(key=lambda c: min(position[id(a)] for a in c))
    return clusters


def main() -> int:
    """Print distances for the labeled duplicate pairs (threshold tuning)."""
    setup_logging()
    pairs = json.loads(EVAL_SET_PATH.read_text()).get("duplicate_pairs", [])
    if not pairs:
        print("No duplicate_pairs section in the eval set.", file=sys.stderr)
        return 1

    urls = {url for p in pairs for url in (p["url_a"], p["url_b"])}
    id_by_url = get_article_ids_by_url(sorted(urls))
    embeddings = get_article_embeddings(list(id_by_url.values()))

    print(f"\n{'dist':>6}  {'label':<9} pair")
    rows = []
    for p in pairs:
        id_a, id_b = id_by_url.get(p["url_a"]), id_by_url.get(p["url_b"])
        if id_a is None or id_b is None or id_a not in embeddings or id_b not in embeddings:
            print(f"{'skip':>6}  {p['label']:<9} {p['name']} (not in this database)")
            continue
        d = cosine_distance(embeddings[id_a], embeddings[id_b])
        rows.append((d, p["label"], p["name"]))
    for d, label, name in sorted(rows):
        marker = "✗ BAD" if (label == "duplicate") != (d < CLUSTER_THRESHOLD) else ""
        print(f"{d:>6.3f}  {label:<9} {name} {marker}")
    print(f"\nCLUSTER_THRESHOLD = {CLUSTER_THRESHOLD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
