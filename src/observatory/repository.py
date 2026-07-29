"""Repository layer: single source of truth for SQL against our tables.

Every module that reads or writes the database goes through functions here.
This keeps SQL in one place, makes typos loud (a missing keyword argument
raises TypeError at the call site rather than a silent bad insert), and
isolates a hypothetical future ORM swap to this single file — collectors
would not change.

Functions own their own connections; callers do not pass cursors.
"""

from dataclasses import asdict, dataclass
from datetime import datetime

from observatory.infra.db import get_conn


@dataclass
class Article:
    source: str
    url: str
    title: str
    summary: str | None = None
    content: str | None = None
    image_url: str | None = None
    published_at: datetime | None = None


_INSERT_ARTICLE_SQL = """
    INSERT INTO articles (source, url, title, summary, content, image_url, published_at)
    VALUES (%(source)s, %(url)s, %(title)s, %(summary)s, %(content)s, %(image_url)s, %(published_at)s)
    ON CONFLICT (url) DO NOTHING
"""


def insert_articles(articles: list[Article]) -> int:
    """Insert a batch of articles atomically. Returns the count of new rows.

    Rows whose URL already exists are silently skipped (per the UNIQUE
    constraint on articles.url and ON CONFLICT DO NOTHING). All inserts
    share a single connection and transaction.
    """
    if not articles:
        return 0
    total = 0
    with get_conn() as conn:
        with conn.cursor() as cur:
            for article in articles:
                cur.execute(_INSERT_ARTICLE_SQL, asdict(article))
                total += cur.rowcount
    return total


def insert_article(article: Article) -> bool:
    """Insert one article. Returns True if newly added, False on URL conflict."""
    return insert_articles([article]) == 1
