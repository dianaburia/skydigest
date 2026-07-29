"""Tests for the RSS pubDate parser."""

from datetime import datetime, timezone

from observatory.ingest.rss import parse_pub_date


def test_parses_standard_rfc2822():
    dt = parse_pub_date("Mon, 18 Jul 2026 14:30:00 +0000")
    assert dt == datetime(2026, 7, 18, 14, 30, 0, tzinfo=timezone.utc)


def test_converts_non_utc_to_utc():
    # Eastern Daylight Time (-0400) → UTC = +4 hours
    dt = parse_pub_date("Mon, 18 Jul 2026 14:30:00 -0400")
    assert dt == datetime(2026, 7, 18, 18, 30, 0, tzinfo=timezone.utc)


def test_naive_date_assumed_utc():
    dt = parse_pub_date("Mon, 18 Jul 2026 14:30:00")
    assert dt == datetime(2026, 7, 18, 14, 30, 0, tzinfo=timezone.utc)


def test_none_or_empty_returns_none():
    assert parse_pub_date(None) is None
    assert parse_pub_date("") is None


def test_garbage_returns_none():
    assert parse_pub_date("not a date at all") is None
