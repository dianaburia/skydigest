"""MCP server: the Skydigest archive as tools for AI clients (step 2.8).

Exposes DATA ACCESS, not finished answers: the connecting client (Claude
Desktop, another agent) has its own LLM and does its own reasoning, so no
tool here ever spends our Anthropic credits. Tools mirror what the site's
own agent can reach: vector search over the archive, journal issues, and
current space-weather numbers.

Run (stdio transport, what Claude Desktop expects):

    uv run python -m observatory.mcp_server

Note: the first search_archive call loads the embedding model (~30 s cold);
later calls are instant.
"""

import re
import sys
from datetime import date
from typing import Any

from mcp.server.mcpserver import MCPServer

from observatory.infra.logging_setup import setup_logging
from observatory.repository import (
    get_issue,
    get_space_weather_stats,
    list_issues,
)

server = MCPServer(
    "skydigest",
    instructions=(
        "Skydigest is a weekly astronomy magazine with a searchable archive of "
        "news articles, arXiv papers, and NOAA space-weather measurements. "
        "Use search_archive for questions about astronomy news and research; "
        "cite the returned URLs. Use space_weather_current for present-day "
        "geomagnetic conditions (Kp, solar wind, Bz)."
    ),
)

# An issue's stored HTML has inline <style>; strip tags for a text payload.
_STYLE_OR_SCRIPT = re.compile(r"<(style|script)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
_TAGS = re.compile(r"<[^>]+>")
ISSUE_TEXT_LIMIT = 20_000


def issue_html_to_text(html: str) -> str:
    """Readable plain text of an issue page, capped for tool payloads."""
    text = _TAGS.sub(" ", _STYLE_OR_SCRIPT.sub(" ", html))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:ISSUE_TEXT_LIMIT]


@server.tool()
def search_archive(query: str, limit: int = 8) -> list[dict[str, Any]]:
    """Semantic search over the astronomy archive (news articles + arXiv papers).

    Returns the closest text chunks with their source document's title and
    URL, best match first. `score` is cosine distance: lower is closer;
    below 0.35 is a confident match, above 0.45 is weak.
    """
    from observatory.rag.retrieve import retrieve  # lazy: loads the 2 GB model

    chunks = retrieve(query, top_k=min(limit, 20))
    return [
        {
            "title": c.title,
            "url": c.url,
            "doc_type": c.doc_type,
            "snippet": c.content[:500],
            "score": round(c.score, 3),
        }
        for c in chunks
    ]


@server.tool()
def list_journal_issues() -> list[dict[str, str]]:
    """All published weekly issues of the Skydigest magazine, newest first."""
    return [
        {"issue_date": s.issue_date.isoformat(), "title": s.title}
        for s in list_issues()
    ]


@server.tool()
def get_journal_issue(issue_date: str) -> dict[str, Any]:
    """One weekly issue as plain text by its date (YYYY-MM-DD, see list_journal_issues)."""
    issue = get_issue(date.fromisoformat(issue_date))
    if issue is None:
        return {"error": f"No issue published on {issue_date}"}
    return {
        "issue_date": issue_date,
        "title": issue.title,
        "text": issue_html_to_text(issue.html),
        "suggested_questions": issue.suggested_questions,
    }


@server.tool()
def space_weather_current() -> list[dict[str, Any]]:
    """Current space weather: latest value and 7-day extremes per metric.

    Metrics: kp (geomagnetic index, 0-9, 5+ is a storm), sw_speed (solar wind,
    km/s), sw_density (protons/cm3), bz (IMF north-south component, nT;
    negative values are geoeffective). Data: NOAA SWPC real-time feeds.
    """
    return [
        {
            "metric": s.metric,
            "latest": s.latest,
            "measured_at": s.latest_ts.isoformat(),
            "min_7d": s.minimum,
            "max_7d": s.maximum,
        }
        for s in get_space_weather_stats()
    ]


def main() -> int:
    setup_logging()
    server.run(transport="stdio")
    return 0


if __name__ == "__main__":
    sys.exit(main())
