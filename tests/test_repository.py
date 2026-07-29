"""Integration tests for the repository layer.

These tests hit the real local Postgres and clean up after themselves.
They require ``docker compose up -d`` to be running.
"""

import pytest

from observatory.infra.db import get_conn
from observatory.repository import Article, insert_article, insert_articles

TEST_SOURCE = "__test__"


@pytest.fixture(autouse=True)
def cleanup_test_rows():
    yield
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM articles WHERE source = %s", (TEST_SOURCE,))


def test_insert_article_new_returns_true():
    article = Article(
        source=TEST_SOURCE,
        url="https://example.com/test/new",
        title="Test article",
    )
    assert insert_article(article) is True


def test_insert_article_conflict_returns_false():
    article = Article(
        source=TEST_SOURCE,
        url="https://example.com/test/dup",
        title="Test article",
    )
    assert insert_article(article) is True
    assert insert_article(article) is False


def test_insert_articles_batch_returns_count():
    articles = [
        Article(
            source=TEST_SOURCE,
            url=f"https://example.com/test/batch/{i}",
            title=f"Batch {i}",
        )
        for i in range(5)
    ]
    assert insert_articles(articles) == 5


def test_insert_articles_partial_conflict_counts_only_new():
    """When some URLs already exist, only the new ones count as inserted."""
    first_batch = [
        Article(
            source=TEST_SOURCE,
            url=f"https://example.com/test/partial/{i}",
            title=f"P{i}",
        )
        for i in range(3)
    ]
    assert insert_articles(first_batch) == 3

    second_batch = first_batch[:2] + [
        Article(
            source=TEST_SOURCE,
            url=f"https://example.com/test/partial/{i}",
            title=f"P{i}",
        )
        for i in (3, 4)
    ]
    assert insert_articles(second_batch) == 2


def test_insert_articles_empty_returns_zero():
    assert insert_articles([]) == 0
