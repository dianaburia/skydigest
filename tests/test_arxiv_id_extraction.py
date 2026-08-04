"""Tests for extracting arxiv_id from Atom entry URLs."""

from observatory.ingest.arxiv import extract_arxiv_id


def test_new_format_with_version():
    assert extract_arxiv_id("http://arxiv.org/abs/2408.12345v2") == "2408.12345"


def test_new_format_without_version():
    assert extract_arxiv_id("http://arxiv.org/abs/2408.12345") == "2408.12345"


def test_old_format_with_category():
    # Pre-2007 papers carry the primary category as part of the ID.
    assert extract_arxiv_id("http://arxiv.org/abs/astro-ph/0601001v1") == "astro-ph/0601001"


def test_multi_digit_version():
    assert extract_arxiv_id("http://arxiv.org/abs/2408.12345v42") == "2408.12345"
