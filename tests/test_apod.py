"""Tests for the APOD collector: page parsing and broken-API fallbacks.

Since October 2026 the NASA APOD API returns "NASA Science" / the NASA logo
in place of the real title and photo, so the collector scrapes the APOD page
and falls back to the API. No network: HTTP and DB calls are stubbed.
"""

from datetime import date

from observatory.ingest import apod
from observatory.ingest.apod import ApodPage, parse_apod_page

# Trimmed-down real markup from https://science.nasa.gov/apod/ (2026-10-31).
PAGE_HTML = """
<h1 class="display-48 smd-embed-post__heading">Astronomy Picture of the Day</h1>
<h2 class="heading-18 margin-top-0">Suggested Searches</h2>
<h2 class="display-48 margin-top-0 margin-bottom-3">Night &amp; a Spooky Planet</h2>
<a href="https://science.nasa.gov/image-article/apod-2026-october-31-night-on-a-spooky-planet/">
<img srcset="https://assets.science.nasa.gov/dynamicimage/assets/science/cds/apod/apod/Hverir_Vetter_1300.jpg?w=1280&amp;h=1280&amp;fit=crop 1280w">
</a>
"""

BROKEN_API_DATA = {
    "date": "2026-10-31",
    "title": "NASA Science",
    "hdurl": "https://science.nasa.gov/wp-content/themes/nasa-child/assets/images/nasa-logo@2x.png",
    "url": "https://science.nasa.gov/wp-content/themes/nasa-child/assets/images/nasa-logo@2x.png",
    "media_type": "image",
    "explanation": "What spooky planet is this?",
}


def test_parse_apod_page_extracts_all_fields():
    parsed = parse_apod_page(PAGE_HTML)
    assert parsed.title == "Night & a Spooky Planet"
    assert parsed.image_url == (
        "https://assets.science.nasa.gov/dynamicimage/assets/science/cds/apod/apod/Hverir_Vetter_1300.jpg"
    )
    assert parsed.page_url == (
        "https://science.nasa.gov/image-article/apod-2026-october-31-night-on-a-spooky-planet/"
    )
    assert parsed.page_date == date(2026, 10, 31)


def test_parse_apod_page_unrelated_html_yields_nothing():
    assert parse_apod_page("<html><h2>Other site</h2></html>") == ApodPage()


class _Settings:
    nasa_api_key = "test-key"


def _run_fetch(monkeypatch, api_data, page_html):
    """Run fetch_apod with stubbed HTTP and DB; return the inserted Article."""
    captured = {}

    def fake_insert(article):
        captured["article"] = article
        return True

    monkeypatch.setattr(apod, "get_settings", lambda: _Settings())
    monkeypatch.setattr(apod, "get_json", lambda url, **kw: api_data)
    monkeypatch.setattr(apod, "get_text", lambda url, **kw: page_html)
    monkeypatch.setattr(apod, "insert_article", fake_insert)
    result = apod.fetch_apod()
    assert result is not None
    return captured["article"]


def test_fetch_prefers_page_fields_over_broken_api(monkeypatch):
    article = _run_fetch(monkeypatch, BROKEN_API_DATA, PAGE_HTML)
    assert article.title == "Night & a Spooky Planet"
    assert "Hverir_Vetter_1300.jpg" in article.image_url
    # The classic dated URL, NOT the science.nasa.gov permalink: that one may
    # already be taken by the RSS collector, which would no-op this insert.
    assert article.url == "https://apod.nasa.gov/apod/ap261031.html"
    assert article.summary == "What spooky planet is this?"


def test_fetch_on_page_date_mismatch_drops_broken_api_junk(monkeypatch):
    # The page still shows October 31, but the API already moved to November 1:
    # page fields must not be used, and the API's junk title/logo are dropped.
    api_data = dict(BROKEN_API_DATA, date="2026-11-01")
    article = _run_fetch(monkeypatch, api_data, PAGE_HTML)
    assert article.title == "Astronomy Picture of the Day, 2026-11-01"
    assert article.image_url is None
    assert article.url == "https://apod.nasa.gov/apod/ap261101.html"
