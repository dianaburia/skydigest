"""Collector for NASA's Astronomy Picture of the Day (APOD).

Fetches today's APOD via the NASA API and upserts it into the articles table.
Idempotent: safe to run repeatedly, will not create duplicates.
"""

import logging
import sys
from datetime import date, datetime, timezone
from typing import Any

import httpx

from observatory.config import get_settings
from observatory.db import get_conn

logger = logging.getLogger(__name__)

APOD_ENDPOINT = "https://api.nasa.gov/planetary/apod"
REQUEST_TIMEOUT = 10.0


def _apod_page_url(day: date) -> str:
    """Build the canonical APOD permalink URL for a given date."""
    return f"https://apod.nasa.gov/apod/ap{day.strftime('%y%m%d')}.html"


def _to_utc_midnight(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=timezone.utc)


def fetch_apod() -> dict[str, Any] | None:
    """Fetch today's APOD and insert it into the articles table.

    Returns a dict with the parsed payload, the canonical page URL, and
    ``inserted`` (0 if the entry was already present, 1 if newly added).
    Returns None on network or HTTP error.
    """
    settings = get_settings()
    try:
        response = httpx.get(
            APOD_ENDPOINT,
            params={"api_key": settings.nasa_api_key},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        logger.error(
            "APOD API returned HTTP %s: %s",
            e.response.status_code,
            e.response.text[:200],
        )
        return None
    except httpx.HTTPError as e:
        logger.error("APOD API request failed: %s", e)
        return None

    data = response.json()
    day = date.fromisoformat(data["date"])
    article_url = _apod_page_url(day)
    image_url = data.get("hdurl") or data.get("url")

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO articles (source, url, title, summary, image_url, published_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (url) DO NOTHING
                """,
                (
                    "apod",
                    article_url,
                    data["title"],
                    data.get("explanation"),
                    image_url,
                    _to_utc_midnight(day),
                ),
            )
            inserted = cur.rowcount

    logger.info("APOD %s: %s (inserted=%d)", day, data["title"], inserted)
    return {"apod": data, "url": article_url, "inserted": inserted}


def _main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    # httpx logs full request URLs at INFO level, which would leak the api_key
    # query parameter. Silence it — fetch_apod logs the events we care about.
    logging.getLogger("httpx").setLevel(logging.WARNING)
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
    sys.exit(_main())
