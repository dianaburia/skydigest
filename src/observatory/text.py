"""Shared plain-text helpers."""

import re

_TAG = re.compile(r"<[^>]+>")
_WHITESPACE = re.compile(r"\s+")


def clean_text(raw: str | None, limit: int | None = None) -> str:
    """Strip HTML tags, collapse whitespace, optionally truncate.

    Used by the journal (prompt snippets) and the RAG indexer (chunk text):
    embedding raw HTML dilutes vector semantics and wastes chunk budget.
    """
    if not raw:
        return ""
    text = _TAG.sub(" ", raw)
    text = _WHITESPACE.sub(" ", text).strip()
    return text[:limit] if limit is not None else text
