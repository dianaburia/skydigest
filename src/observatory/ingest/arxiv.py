"""Collector for arXiv astro-ph submissions via the Atom API."""

import logging
import re
import sys
import time
from datetime import datetime
from typing import Any
from urllib.parse import urlencode

import feedparser

from observatory.infra.logging_setup import setup_logging
from observatory.repository import Paper, insert_papers

logger = logging.getLogger(__name__)

ARXIV_API = "http://export.arxiv.org/api/query"
CATEGORY_QUERY = "cat:astro-ph.*"
PAGE_SIZE = 100
POLITE_DELAY = 3.0  # arXiv TOS asks for at least 3s between search_query requests

_VERSION_RE = re.compile(r"v\d+$")


def extract_arxiv_id(entry_id: str) -> str:
    """Extract the versionless arxiv_id from an entry id URL.

    Handles both the modern format ("2408.12345") and the pre-2007 format
    with a category prefix ("astro-ph/0601001"). Any trailing ``vN`` version
    suffix is stripped.
    """
    _, _, tail = entry_id.partition("/abs/")
    return _VERSION_RE.sub("", tail)


def _parse_arxiv_date(raw: str) -> datetime:
    """Parse an arXiv Atom timestamp (ISO 8601 with Z suffix) to UTC-aware datetime."""
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


def _pdf_url(entry: Any) -> str | None:
    """Find the PDF link in an entry's links list, if any."""
    for link in getattr(entry, "links", []):
        if link.get("type") == "application/pdf":
            return link.get("href")
    return None


def parse_arxiv_entries(entries: Any) -> list[Paper]:
    """Convert feedparser entries into Paper objects. Skips malformed entries."""
    papers: list[Paper] = []
    for entry in entries:
        entry_id = getattr(entry, "id", None)
        if not entry_id:
            continue
        try:
            papers.append(
                Paper(
                    arxiv_id=extract_arxiv_id(entry_id),
                    title=entry.title.strip(),
                    abstract=entry.summary.strip(),
                    authors=[a.name for a in entry.authors],
                    categories=[t.term for t in entry.tags],
                    url=entry.link,
                    pdf_url=_pdf_url(entry),
                    published_at=_parse_arxiv_date(entry.published),
                    updated_at=(
                        _parse_arxiv_date(entry.updated)
                        if hasattr(entry, "updated")
                        else None
                    ),
                )
            )
        except (AttributeError, KeyError, ValueError) as e:
            logger.warning("Skipping malformed arXiv entry %s: %s", entry_id, e)
    return papers


def fetch_arxiv_page(start: int) -> list[Paper]:
    """Fetch and parse one page of arXiv astro-ph submissions."""
    params = {
        "search_query": CATEGORY_QUERY,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
        "start": start,
        "max_results": PAGE_SIZE,
    }
    url = f"{ARXIV_API}?{urlencode(params)}"
    parsed = feedparser.parse(url)
    if parsed.bozo and not parsed.entries:
        logger.warning(
            "Failed to parse arXiv page start=%d: %s", start, parsed.bozo_exception
        )
        return []
    return parse_arxiv_entries(parsed.entries)


def fetch_arxiv_papers(pages: int = 1) -> int:
    """Fetch N pages of astro-ph submissions, insert new ones. Returns new count.

    Sleeps 3 seconds between pages per arXiv TOS. The first page has no
    leading sleep.
    """
    total_inserted = 0
    for page in range(pages):
        if page > 0:
            time.sleep(POLITE_DELAY)
        start = page * PAGE_SIZE
        papers = fetch_arxiv_page(start=start)
        inserted = insert_papers(papers)
        logger.info(
            "arXiv page %d/%d: %d new / %d parsed",
            page + 1,
            pages,
            inserted,
            len(papers),
        )
        total_inserted += inserted
    return total_inserted


def main() -> int:
    setup_logging()
    pages = 1
    if len(sys.argv) > 1:
        try:
            pages = int(sys.argv[1])
        except ValueError:
            print("Usage: python -m observatory.ingest.arxiv [pages]", file=sys.stderr)
            return 1
    if pages < 1:
        print("pages must be >= 1", file=sys.stderr)
        return 1

    inserted = fetch_arxiv_papers(pages=pages)
    print()
    print(f"Total inserted: {inserted} new papers across {pages} page(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
