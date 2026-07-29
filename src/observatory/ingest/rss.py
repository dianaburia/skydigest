"""Collector for RSS/Atom feeds from space-news sites."""

import logging
import socket
import sys
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import feedparser

from observatory.repository import Article, insert_articles

logger = logging.getLogger(__name__)


FEEDS: dict[str, str] = {
    "universetoday": "https://www.universetoday.com/feed/",
    "physorg": "https://phys.org/rss-feed/space-news/",
    "esa": "https://www.esa.int/rssfeed/Our_Activities/Space_News",
    "nasa": "https://www.nasa.gov/feed/",
    "skyandtelescope": "https://skyandtelescope.org/feed/",
}


def parse_pub_date(raw: str | None) -> datetime | None:
    """Parse an RFC 2822 pubDate string to a UTC-aware datetime.

    Returns None for missing, empty, or unparseable input.
    Naive datetimes (no timezone) are assumed to be UTC.
    """
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _entry_summary(entry: Any) -> str | None:
    return getattr(entry, "summary", None) or getattr(entry, "description", None)


def _entry_content(entry: Any) -> str | None:
    try:
        return entry.content[0].value
    except (AttributeError, IndexError):
        return None


def fetch_feed(source: str, url: str) -> int:
    """Fetch one feed and insert new entries. Returns count of new rows."""
    parsed = feedparser.parse(url)
    if parsed.bozo and not parsed.entries:
        logger.warning("Failed to parse feed %s: %s", source, parsed.bozo_exception)
        return 0

    articles: list[Article] = []
    for entry in parsed.entries:
        link = getattr(entry, "link", None)
        title = getattr(entry, "title", None)
        if not link or not title:
            continue
        articles.append(
            Article(
                source=source,
                url=link,
                title=title,
                summary=_entry_summary(entry),
                content=_entry_content(entry),
                published_at=parse_pub_date(getattr(entry, "published", None)),
            )
        )

    inserted = insert_articles(articles)
    logger.info(
        "Feed %s: %d new / %d total in feed", source, inserted, len(parsed.entries)
    )
    return inserted


def fetch_all_feeds() -> dict[str, int]:
    """Fetch every configured feed. Errors on one feed do not stop the others."""
    counts: dict[str, int] = {}
    for source, url in FEEDS.items():
        try:
            counts[source] = fetch_feed(source, url)
        except Exception:
            logger.exception("Unexpected error fetching feed %s", source)
            counts[source] = 0
    return counts


def _main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    # feedparser has no timeout parameter; set a global socket timeout so a
    # single stalled feed cannot block the whole run indefinitely.
    socket.setdefaulttimeout(30)

    counts = fetch_all_feeds()
    total = sum(counts.values())

    print()
    print("New articles per source:")
    for source, n in counts.items():
        print(f"  {source:20s} {n}")
    print()
    print(f"Total new: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
