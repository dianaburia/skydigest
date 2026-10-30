"""Retrieval evaluation against the labeled set in tests/eval_questions.json.

Runs every retrieval question through retrieve(), checks whether the
expected documents show up in the top-K chunks, and prints Recall@5,
Recall@8 and MRR. Abstention questions are skipped on purpose: they test
generation, and running the LLM on every eval would be slow and paid.

Run locally (needs the embedding model and a populated database):

    uv run python -m observatory.rag.evaluate

Not wired into CI — the model alone is ~2 GB. Run before "release"
changes (chunking, embedding model, data cleanup) and record the numbers
in the private EVAL.md.
"""

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from observatory.infra.logging_setup import setup_logging
from observatory.rag.retrieve import retrieve
from observatory.repository import RetrievedChunk

EVAL_SET_PATH = Path("tests/eval_questions.json")
TOP_K = 8  # what the production chat retrieves
RECALL_CUTOFFS = (5, 8)

_ARXIV_VERSION = re.compile(r"v\d+$")


def _normalize_arxiv_id(arxiv_id: str) -> str:
    """Drop the version suffix: '2608.01621v2' and '2608.01621' are one paper."""
    return _ARXIV_VERSION.sub("", arxiv_id)


def _chunk_doc_key(chunk: RetrievedChunk) -> tuple[str, str]:
    if chunk.doc_type == "paper":
        return ("paper", _normalize_arxiv_id(chunk.doc_id))
    return ("article", chunk.url)


def _expected_doc_key(entry: dict) -> tuple[str, str]:
    if entry["doc_type"] == "paper":
        return ("paper", _normalize_arxiv_id(entry["arxiv_id"]))
    return ("article", entry["url"])


@dataclass
class QuestionResult:
    question_id: int
    question: str
    require: str  # 'any' | 'all'
    expected_total: int
    found_total: int  # expected docs present anywhere in the top-K
    first_rank: int | None  # 1-based rank of the first relevant chunk
    hit_at: dict[int, bool]  # cutoff -> did the question count as a hit

    @property
    def reciprocal_rank(self) -> float:
        return 0.0 if self.first_rank is None else 1.0 / self.first_rank


def evaluate_question(spec: dict, chunks: list[RetrievedChunk]) -> QuestionResult:
    """Score one labeled question against its retrieved chunks (pure logic).

    'require: any' counts a hit when at least one expected doc appears
    within the cutoff; 'require: all' demands every expected doc.
    """
    expected = {_expected_doc_key(e) for e in spec["expected"]}
    require = spec["require"]

    doc_keys = [_chunk_doc_key(c) for c in chunks]
    first_rank = next(
        (rank for rank, key in enumerate(doc_keys, start=1) if key in expected),
        None,
    )

    hit_at: dict[int, bool] = {}
    for cutoff in RECALL_CUTOFFS:
        seen = set(doc_keys[:cutoff])
        found = expected & seen
        hit_at[cutoff] = bool(found) if require == "any" else found == expected

    return QuestionResult(
        question_id=spec["id"],
        question=spec["question"],
        require=require,
        expected_total=len(expected),
        found_total=len(expected & set(doc_keys)),
        first_rank=first_rank,
        hit_at=hit_at,
    )


def evaluate_retrieval(specs: list[dict]) -> list[QuestionResult]:
    return [evaluate_question(spec, retrieve(spec["question"], TOP_K)) for spec in specs]


def main() -> int:
    setup_logging()

    if not EVAL_SET_PATH.exists():
        print(f"Eval set not found: {EVAL_SET_PATH} (run from the repo root)", file=sys.stderr)
        return 1
    eval_set = json.loads(EVAL_SET_PATH.read_text())

    specs = eval_set["retrieval"]
    results = evaluate_retrieval(specs)

    print()
    print(f"{'id':>3}  {'req':<4} {'found':>5}  {'rank':>4}  {'@5':>3} {'@8':>3}  question")
    for r in results:
        rank = str(r.first_rank) if r.first_rank else "-"
        print(
            f"{r.question_id:>3}  {r.require:<4} {r.found_total}/{r.expected_total:<3}"
            f"  {rank:>4}  {'✓' if r.hit_at[5] else '✗':>3} {'✓' if r.hit_at[8] else '✗':>3}"
            f"  {r.question[:60]}"
        )

    n = len(results)
    mrr = sum(r.reciprocal_rank for r in results) / n
    print()
    for cutoff in RECALL_CUTOFFS:
        hits = sum(r.hit_at[cutoff] for r in results)
        print(f"Recall@{cutoff}: {hits}/{n} = {hits / n:.0%}")
    print(f"MRR:      {mrr:.3f}")
    print(f"\n(abstention questions skipped: {len(eval_set.get('abstention', []))} — generation-side, evaluated manually)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
