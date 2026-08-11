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
    id: int | None = None  # assigned by the database; None until inserted


_INSERT_ARTICLE_SQL = """
    INSERT INTO articles (source, url, title, summary, content, image_url, published_at)
    VALUES (%(source)s, %(url)s, %(title)s, %(summary)s, %(content)s, %(image_url)s, %(published_at)s)
    ON CONFLICT (url) DO NOTHING
"""

_ARTICLE_COLUMNS = "source, url, title, summary, content, image_url, published_at, id"


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


def list_recent_articles(days: int = 7) -> list[Article]:
    """Return articles published (or, lacking a date, ingested) in the last N days."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {_ARTICLE_COLUMNS}
                FROM articles
                WHERE COALESCE(published_at, created_at) >= NOW() - make_interval(days => %(days)s)
                ORDER BY COALESCE(published_at, created_at) DESC
                """,
                {"days": days},
            )
            return [Article(*row) for row in cur.fetchall()]


def list_recent_papers(days: int = 7) -> list[Paper]:
    """Return papers published in the last N days."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT arxiv_id, title, abstract, authors, categories, url,
                       published_at, pdf_url, updated_at
                FROM papers
                WHERE published_at >= NOW() - make_interval(days => %(days)s)
                ORDER BY published_at DESC
                """,
                {"days": days},
            )
            return [Paper(*row) for row in cur.fetchall()]


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


@dataclass
class SpaceWeatherSummary:
    """Weekly aggregate of space-weather metrics for the journal."""

    max_kp: float | None
    max_kp_at: datetime | None
    storm_intervals: int  # count of 3-hour Kp readings >= 5 (storm level G1+)
    avg_sw_speed: float | None
    max_sw_speed: float | None
    min_bz: float | None


def get_space_weather_summary(days: int = 7) -> SpaceWeatherSummary:
    """Aggregate the last N days of space-weather data for the journal."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    (SELECT max(value) FROM space_weather
                     WHERE metric = 'kp' AND ts >= NOW() - make_interval(days => %(days)s)),
                    (SELECT ts FROM space_weather
                     WHERE metric = 'kp' AND ts >= NOW() - make_interval(days => %(days)s)
                     ORDER BY value DESC, ts DESC LIMIT 1),
                    (SELECT count(*) FROM space_weather
                     WHERE metric = 'kp' AND value >= 5
                       AND ts >= NOW() - make_interval(days => %(days)s)),
                    (SELECT avg(value) FROM space_weather
                     WHERE metric = 'sw_speed' AND ts >= NOW() - make_interval(days => %(days)s)),
                    (SELECT max(value) FROM space_weather
                     WHERE metric = 'sw_speed' AND ts >= NOW() - make_interval(days => %(days)s)),
                    (SELECT min(value) FROM space_weather
                     WHERE metric = 'bz' AND ts >= NOW() - make_interval(days => %(days)s))
                """,
                {"days": days},
            )
            row = cur.fetchone()
            return SpaceWeatherSummary(
                max_kp=row[0],
                max_kp_at=row[1],
                storm_intervals=row[2] or 0,
                avg_sw_speed=row[3],
                max_sw_speed=row[4],
                min_bz=row[5],
            )


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


@dataclass
class Chunk:
    doc_type: str  # 'article' | 'paper'
    doc_id: str  # str(articles.id) or papers.arxiv_id
    chunk_index: int
    content: str
    embedding: list[float]


_INSERT_CHUNK_SQL = """
    INSERT INTO chunks (doc_type, doc_id, chunk_index, content, embedding)
    VALUES (%(doc_type)s, %(doc_id)s, %(chunk_index)s, %(content)s, %(embedding)s)
    ON CONFLICT (doc_type, doc_id, chunk_index) DO NOTHING
"""


def insert_chunks(chunks: list[Chunk]) -> int:
    """Insert a batch of chunks atomically. Returns the count of new rows."""
    if not chunks:
        return 0
    total = 0
    with get_conn() as conn:
        with conn.cursor() as cur:
            for chunk in chunks:
                params = asdict(chunk)
                # pgvector accepts a vector literal in its string form '[0.1, 0.2, ...]'
                params["embedding"] = str(chunk.embedding)
                cur.execute(_INSERT_CHUNK_SQL, params)
                total += cur.rowcount
    return total


def list_unindexed_articles() -> list[Article]:
    """Articles that do not have any chunks yet."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {_ARTICLE_COLUMNS}
                FROM articles a
                WHERE NOT EXISTS (
                    SELECT 1 FROM chunks c
                    WHERE c.doc_type = 'article' AND c.doc_id = a.id::text
                )
                """
            )
            return [Article(*row) for row in cur.fetchall()]


def list_unindexed_papers() -> list[Paper]:
    """Papers that do not have any chunks yet."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT arxiv_id, title, abstract, authors, categories, url,
                       published_at, pdf_url, updated_at
                FROM papers p
                WHERE NOT EXISTS (
                    SELECT 1 FROM chunks c
                    WHERE c.doc_type = 'paper' AND c.doc_id = p.arxiv_id
                )
                """
            )
            return [Paper(*row) for row in cur.fetchall()]
