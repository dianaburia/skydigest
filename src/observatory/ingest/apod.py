"""Collector for NASA's Astronomy Picture of the Day (APOD).

Fetches today's APOD via the NASA API and upserts it into the articles table.
Idempotent: safe to run repeatedly, will not create duplicates.
"""

import logging
import sys
from datetime import date, datetime, timezone
from typing import Any

from observatory.config import get_settings
from observatory.infra.http import get_json
from observatory.infra.logging_setup import setup_logging
from observatory.repository import Article, insert_article

logger = logging.getLogger(__name__)

APOD_ENDPOINT = "https://api.nasa.gov/planetary/apod"


def _apod_page_url(day: date) -> str:
    """Build the canonical APOD permalink URL for a given date."""
    return f"https://apod.nasa.gov/apod/ap{day.strftime('%y%m%d')}.html"


def _to_utc_midnight(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=timezone.utc)


def fetch_apod() -> dict[str, Any] | None:
    """Fetch today's APOD and insert it into the articles table.

    Returns a dict with the parsed payload, the canonical page URL, and
    ``inserted`` (True if newly added, False if already present).
    Returns None on network or HTTP error.
    """
    settings = get_settings()
    data = get_json(APOD_ENDPOINT, params={"api_key": settings.nasa_api_key})
    if data is None:
        return None

    day = date.fromisoformat(data["date"])
    article_url = _apod_page_url(day)
    if data.get("media_type") == "image":
        image_url = data.get("hdurl") or data.get("url")
    else:
        image_url = None

    inserted = insert_article(
        Article(
            source="apod",
            url=article_url,
            title=data["title"],
            summary=data.get("explanation"),
            image_url=image_url,
            published_at=_to_utc_midnight(day),
        )
    )

    logger.info("APOD %s: %s (inserted=%s)", day, data["title"], inserted)
    return {"apod": data, "url": article_url, "inserted": inserted}


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
    print(f"Title:   {data['title']}")
    print(f"Media:   {data.get('media_type', 'unknown')}")
    print(f"URL:     {result['url']}")
    print(f"Preview: {preview}")
    print()
    print(f"Inserted new row: {'yes' if result['inserted'] else 'no (already in DB)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
