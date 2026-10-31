"""Tests for the agent's deterministic logic (no LLM, no DB)."""

from datetime import datetime, timezone

from observatory.rag.agent import WEAK_SCORE, needs_reformulation
from observatory.rag.answer import build_weather_prompt
from observatory.repository import RetrievedChunk, SpaceWeatherStat


def _chunk(score: float) -> RetrievedChunk:
    return RetrievedChunk(
        doc_type="article", doc_id="1", content="...", score=score, title="t", url="u"
    )


def test_weak_scores_trigger_one_reformulation():
    weak = [_chunk(WEAK_SCORE + 0.05)]
    assert needs_reformulation(weak, reformulated=False) is True
    # ...but only once: a second rewrite is never attempted.
    assert needs_reformulation(weak, reformulated=True) is False


def test_confident_scores_skip_reformulation():
    assert needs_reformulation([_chunk(0.30)], reformulated=False) is False


def test_empty_retrieval_counts_as_weak():
    assert needs_reformulation([], reformulated=False) is True


def test_weather_prompt_carries_values_and_units():
    stats = [
        SpaceWeatherStat(
            metric="kp",
            latest=5.33,
            latest_ts=datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc),
            minimum=1.0,
            maximum=7.0,
        ),
        SpaceWeatherStat(
            metric="sw_speed",
            latest=612.0,
            latest_ts=datetime(2026, 10, 31, 12, 0, tzinfo=timezone.utc),
            minimum=380.0,
            maximum=905.0,
        ),
    ]
    prompt = build_weather_prompt("how stormy is it?", stats)
    assert "Kp index" in prompt
    assert "5.33" in prompt and "max 7" in prompt
    assert "612 km/s" in prompt
    assert "how stormy is it?" in prompt
