"""Collector for NASA's Astronomy Picture of the Day (APOD).

Fetches today's APOD and upserts it into the articles table.
Idempotent: safe to run repeatedly, will not create duplicates.

Since NASA moved APOD to science.nasa.gov (October 2026), the official API
keeps returning correct ``date``/``explanation`` but substitutes the site's
generic metadata for the real fields: ``title`` becomes "NASA Science" and
``hdurl``/``url`` point at the NASA logo. The real title and photo are
therefore scraped from the APOD page itself; the API supplies the text and
serves as a fallback when the page cannot be parsed.

The row's url stays the classic dated permalink (apod.nasa.gov/apod/apYYMMDD
.html): the RSS collector also ingests the new science.nasa.gov APOD pages,
so using their URL here would collide with that row (url is unique) and the
insert would silently no-op. Clustering later merges the two copies into one
event, with this row contributing the photo.
"""

import html
import logging
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from observatory.config import get_settings
from observatory.infra.http import get_json, get_text
from observatory.infra.logging_setup import setup_logging
from observatory.repository import Article, insert_article

logger = logging.getLogger(__name__)

APOD_ENDPOINT = "https://api.nasa.gov/planetary/apod"
APOD_PAGE = "https://science.nasa.gov/apod/"

# Values the broken API substitutes for the real title and image.
_BROKEN_TITLE = "NASA Science"
_BROKEN_IMAGE_MARKER = "/nasa-logo"

# The day's title is the only <h2 class="display-48 ..."> on the page
# (the page header "Astronomy Picture of the Day" is an <h1>).
_TITLE_RE = re.compile(r'<h2 class="display-48[^"]*">([^<]+)</h2>')
# Dated permalink, e.g. .../image-article/apod-2026-october-31-night-on-a-spooky-planet/
_PERMALINK_RE = re.compile(
    r"https://science\.nasa\.gov/image-article/apod-(\d{4})-([a-z]+)-(\d{1,2})-[a-z0-9-]+/?"
)
# The photo lives under the apod/apod asset path; the query string only
# carries resize parameters, so it is dropped.
_IMAGE_RE = re.compile(
    r'https://assets\.science\.nasa\.gov/dynamicimage/assets/science/cds/apod/apod/[^"\s?]+'
)
_MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


@dataclass
class ApodPage:
    """Fields scraped from the science.nasa.gov APOD page."""

    title: str | None = None
    image_url: str | None = None
    page_url: str | None = None
    page_date: date | None = None


def parse_apod_page(page_html: str) -> ApodPage:
    """Extract the day's title, photo URL, permalink, and date from page HTML.

    Every field is best-effort: anything the page does not yield stays None
    and the caller falls back to the API fields.
    """
    parsed = ApodPage()
    if m := _TITLE_RE.search(page_html):
        parsed.title = html.unescape(m.group(1)).strip()
    if m := _IMAGE_RE.search(page_html):
        parsed.image_url = m.group(0)
    if m := _PERMALINK_RE.search(page_html):
        parsed.page_url = m.group(0)
        month = _MONTHS.get(m.group(2))
        if month:
            parsed.page_date = date(int(m.group(1)), month, int(m.group(3)))
    return parsed


def _apod_page_url(day: date) -> str:
    """Build the classic APOD permalink URL for a given date (fallback)."""
    return f"https://apod.nasa.gov/apod/ap{day.strftime('%y%m%d')}.html"


def _to_utc_midnight(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=timezone.utc)


def fetch_apod() -> dict[str, Any] | None:
    """Fetch today's APOD and insert it into the articles table.

    Returns a dict with the resolved fields and ``inserted`` (True if newly
    added, False if already present). Returns None on network or HTTP error.
    """
    settings = get_settings()
    data = get_json(APOD_ENDPOINT, params={"api_key": settings.nasa_api_key})
    if data is None:
        return None

    day = date.fromisoformat(data["date"])
    page = parse_apod_page(get_text(APOD_PAGE) or "")
    if page.page_date != day:
        # Around midnight the page and the API can show different days;
        # never attach the wrong day's title or photo.
        if page.page_date is not None:
            logger.warning(
                "APOD page shows %s but API says %s; using API fields only",
                page.page_date,
                day,
            )
        page = ApodPage()

    api_title = data.get("title")
    if api_title == _BROKEN_TITLE:
        api_title = None
    title = page.title or api_title or f"Astronomy Picture of the Day, {day}"

    image_url = None
    if data.get("media_type") == "image":
        api_image = data.get("hdurl") or data.get("url")
        if api_image and _BROKEN_IMAGE_MARKER in api_image:
            api_image = None
        image_url = page.image_url or api_image

    # Never the science.nasa.gov permalink: the RSS collector may already
    # hold that URL, and a url conflict would silently drop this insert.
    article_url = _apod_page_url(day)

    inserted = insert_article(
        Article(
            source="apod",
            url=article_url,
            title=title,
            summary=data.get("explanation"),
            image_url=image_url,
            published_at=_to_utc_midnight(day),
        )
    )

    logger.info("APOD %s: %s (inserted=%s)", day, title, inserted)
    return {
        "apod": data,
        "title": title,
        "url": article_url,
        "image_url": image_url,
        "inserted": inserted,
    }


def main() -> int:
    setup_logging()
    result = fetch_apod()
    if result is None:
        print("Failed to fetch APOD (see errors above).", file=sys.stderr)
        return 1

    data = result["apod"]
    explanation = (data.get("explanation") or "").strip()
    preview = explanation[:200] + ("..." if len(explanation) > 200 else "")

    print()
    print(f"Date:    {data['date']}")
    print(f"Title:   {result['title']}")
    print(f"Media:   {data.get('media_type', 'unknown')}")
    print(f"URL:     {result['url']}")
    print(f"Image:   {result['image_url'] or '—'}")
    print(f"Preview: {preview}")
    print()
    print(f"Inserted new row: {'yes' if result['inserted'] else 'no (already in DB)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
