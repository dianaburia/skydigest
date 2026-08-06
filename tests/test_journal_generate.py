"""Tests for the pure parts of journal generation."""

from datetime import datetime, timezone

import pytest

from observatory.journal.generate import (
    NumberedSource,
    _extract_json,
    build_sources,
    render_html,
)
from observatory.repository import Article, Paper


def _article(url: str) -> Article:
    return Article(source="nasa", url=url, title="T", summary="<p>Some  text</p>")


def _paper(arxiv_id: str) -> Paper:
    return Paper(
        arxiv_id=arxiv_id,
        title="P",
        abstract="A",
        authors=["X"],
        categories=["astro-ph.GA"],
        url=f"https://arxiv.org/abs/{arxiv_id}",
        published_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
    )


def test_build_sources_numbers_articles_then_papers():
    sources = build_sources(
        [_article("https://a/1"), _article("https://a/2")], [_paper("2608.00001")]
    )
    assert [s.number for s in sources] == [1, 2, 3]
    assert [s.kind for s in sources] == ["article", "article", "paper"]
    # HTML stripped and whitespace collapsed in snippets
    assert sources[0].snippet == "Some text"


def test_extract_json_plain():
    assert _extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_with_code_fences():
    assert _extract_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_extract_json_garbage_raises():
    with pytest.raises(Exception):
        _extract_json("not json at all")


FAKE_ISSUE = {
    "title": "Test Issue",
    "intro": "Welcome to the test.",
    "main_events": [{"heading": "Big event", "text": "It happened.", "source_ids": [1]}],
    "arxiv_picks": [{"heading": "Cool paper", "text": "Science.", "source_ids": [2]}],
    "space_weather_summary": "Quiet week.",
    "photo_of_week": {"source_id": 1, "caption": "Nice photo."},
}


def test_render_html_produces_page():
    result = {
        "issue": FAKE_ISSUE,
        "sources": [
            NumberedSource(
                number=1,
                kind="article",
                source="apod",
                title="APOD article",
                url="https://apod.nasa.gov/apod/ap260806.html",
                snippet="A photo.",
                image_url="https://apod.nasa.gov/image/helix.jpg",
            ),
            NumberedSource(
                number=2,
                kind="paper",
                source="arxiv",
                title="Some paper",
                url="https://arxiv.org/abs/2608.00001",
                snippet="An abstract.",
            ),
        ],
    }
    html = render_html(result)
    assert "Test Issue" in html
    assert "https://apod.nasa.gov/apod/ap260806.html" in html
    assert "<img" in html  # source 1 has an image_url, so the photo block renders
