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


@dataclass
class Paper:
    arxiv_id: str
    title: str
    abstract: str
    authors: list[str]
    categories: list[str]
    url: str
    published_at: datetime
    pdf_url: str | None = None
    updated_at: datetime | None = None


_INSERT_PAPER_SQL = """
    INSERT INTO papers (arxiv_id, title, abstract, authors, categories, url, pdf_url, published_at, updated_at)
    VALUES (%(arxiv_id)s, %(title)s, %(abstract)s, %(authors)s, %(categories)s, %(url)s, %(pdf_url)s, %(published_at)s, %(updated_at)s)
    ON CONFLICT (arxiv_id) DO NOTHING
"""


def insert_papers(papers: list[Paper]) -> int:
    """Insert a batch of papers atomically. Returns the count of new rows.

    Rows whose arxiv_id already exists are silently skipped (per the
    PRIMARY KEY on papers.arxiv_id and ON CONFLICT DO NOTHING).
    """
    if not papers:
        return 0
    total = 0
    with get_conn() as conn:
        with conn.cursor() as cur:
            for paper in papers:
                cur.execute(_INSERT_PAPER_SQL, asdict(paper))
                total += cur.rowcount
    return total


def insert_paper(paper: Paper) -> bool:
    """Insert one paper. Returns True if newly added, False on arxiv_id conflict."""
    return insert_papers([paper]) == 1


@dataclass
class SpaceWeatherMeasurement:
    ts: datetime
    metric: str  # one of: 'kp', 'sw_speed', 'sw_density', 'bz' (CHECK in schema)
    value: float


_INSERT_MEASUREMENT_SQL = """
    INSERT INTO space_weather (ts, metric, value)
    VALUES (%(ts)s, %(metric)s, %(value)s)
    ON CONFLICT (ts, metric) DO NOTHING
"""


def insert_measurements(measurements: list[SpaceWeatherMeasurement]) -> int:
    """Insert a batch of space-weather measurements atomically.

    Returns the count of newly inserted rows. Rows whose (ts, metric) pair
    already exists are silently skipped (per the primary key on the table
    and ON CONFLICT DO NOTHING).
    """
    if not measurements:
        return 0
    total = 0
    with get_conn() as conn:
        with conn.cursor() as cur:
            for m in measurements:
                cur.execute(_INSERT_MEASUREMENT_SQL, asdict(m))
                total += cur.rowcount
    return total
