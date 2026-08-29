"""Integration tests for the repository layer.

These tests hit the real local Postgres and clean up after themselves.
They require ``docker compose up -d`` to be running.
"""

from datetime import date

import pytest

from observatory.infra.db import get_conn
from observatory.repository import (
    Article,
    Issue,
    get_issue,
    insert_article,
    insert_articles,
    insert_issue,
    list_issues,
)

TEST_SOURCE = "__test__"
# Dates far in the past so test issues never collide with real weekly issues.
TEST_ISSUE_DATES = (date(1999, 1, 2), date(1999, 1, 9))


@pytest.fixture(autouse=True)
def cleanup_test_rows():
    yield
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM articles WHERE source = %s", (TEST_SOURCE,))
        cur.execute(
            "DELETE FROM issues WHERE issue_date = ANY(%s)", (list(TEST_ISSUE_DATES),)
        )


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


def test_list_issues_newest_first_without_html():
    older, newer = TEST_ISSUE_DATES
    insert_issue(Issue(issue_date=older, title="Older test issue", html="<p>old</p>"))
    insert_issue(Issue(issue_date=newer, title="Newer test issue", html="<p>new</p>"))

    ours = [s for s in list_issues() if s.issue_date in TEST_ISSUE_DATES]
    assert [s.issue_date for s in ours] == [newer, older]
    assert not hasattr(ours[0], "html")


def test_get_issue_returns_full_issue():
    issue = Issue(
        issue_date=TEST_ISSUE_DATES[0], title="Test issue", html="<p>body</p>"
    )
    insert_issue(issue)
    assert get_issue(issue.issue_date) == issue


def test_get_issue_missing_date_returns_none():
    assert get_issue(date(1999, 12, 31)) is None
