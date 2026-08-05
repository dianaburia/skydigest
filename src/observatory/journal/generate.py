"""Weekly journal issue generation.

Collects the last 7 days of articles, papers, and space-weather aggregates,
builds a numbered source list, and asks Claude to write a magazine issue in
plain English as structured JSON. Every claim must cite source numbers, which
the HTML template (step 7b) later turns into links.
"""

import json
import logging
import re
import sys
from dataclasses import dataclass

import anthropic

from observatory.config import get_settings
from observatory.infra.logging_setup import setup_logging
from observatory.repository import (
    Article,
    Paper,
    SpaceWeatherSummary,
    get_space_weather_summary,
    list_recent_articles,
    list_recent_papers,
)

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 4096
SNIPPET_LEN = 400
MAX_ARTICLES = 150
MAX_PAPERS = 150

SYSTEM_PROMPT = """\
You are the editor of a popular astronomy magazine. You write for curious
readers with no scientific background: plain English, short sentences, no
jargon (or jargon explained in passing), a warm and slightly playful tone.
You never invent facts: every claim comes from the numbered sources you are
given, and you cite them by number. You respond with valid JSON only."""


@dataclass
class NumberedSource:
    number: int
    kind: str  # 'article' | 'paper'
    source: str  # feed name, 'apod', or 'arxiv'
    title: str
    url: str
    snippet: str


def _clean_text(raw: str | None, limit: int = SNIPPET_LEN) -> str:
    """Strip HTML tags and collapse whitespace, then truncate."""
    if not raw:
        return ""
    text = re.sub(r"<[^>]+>", " ", raw)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def build_sources(
    articles: list[Article], papers: list[Paper]
) -> list[NumberedSource]:
    """Number all sources sequentially: articles first, then papers."""
    sources: list[NumberedSource] = []
    for article in articles:
        sources.append(
            NumberedSource(
                number=len(sources) + 1,
                kind="article",
                source=article.source,
                title=article.title,
                url=article.url,
                snippet=_clean_text(article.summary or article.content),
            )
        )
    for paper in papers:
        sources.append(
            NumberedSource(
                number=len(sources) + 1,
                kind="paper",
                source="arxiv",
                title=paper.title,
                url=paper.url,
                snippet=_clean_text(paper.abstract),
            )
        )
    return sources


def _format_sources_block(sources: list[NumberedSource]) -> str:
    lines = []
    for s in sources:
        lines.append(f"[{s.number}] ({s.kind}/{s.source}) {s.title}\n    {s.snippet}")
    return "\n".join(lines)


def _format_space_weather_block(sw: SpaceWeatherSummary) -> str:
    def fmt(value: float | None, suffix: str = "") -> str:
        return f"{value:.1f}{suffix}" if value is not None else "no data"

    kp_line = f"- Max Kp index this week: {fmt(sw.max_kp)}"
    if sw.max_kp_at is not None:
        kp_line += f" (reached at {sw.max_kp_at:%Y-%m-%d %H:%M} UTC)"
    return "\n".join(
        [
            kp_line,
            f"- 3-hour intervals at storm level (Kp >= 5): {sw.storm_intervals}",
            f"- Solar wind speed: avg {fmt(sw.avg_sw_speed, ' km/s')},"
            f" max {fmt(sw.max_sw_speed, ' km/s')}",
            f"- Strongest southward IMF Bz: {fmt(sw.min_bz, ' nT')}"
            " (negative = magnetosphere 'opens', aurora chances rise)",
        ]
    )


def build_user_prompt(
    sources: list[NumberedSource], sw: SpaceWeatherSummary
) -> str:
    return f"""\
Here is everything collected this week.

=== NUMBERED SOURCES ===
{_format_sources_block(sources)}

=== SPACE WEATHER DATA (measured, not from sources) ===
{_format_space_weather_block(sw)}

=== TASK ===
Write this week's issue of the magazine. Respond with ONLY a JSON object,
no markdown fences, matching exactly this structure:

{{
  "title": "catchy issue title",
  "intro": "2-3 sentence welcome paragraph",
  "main_events": [
    {{"heading": "...", "text": "2-4 sentences", "source_ids": [1, 2]}}
  ],
  "arxiv_picks": [
    {{"heading": "...", "text": "2-4 sentences explaining the paper simply", "source_ids": [3]}}
  ],
  "space_weather_summary": "one paragraph based on the space weather data above",
  "photo_of_week": {{"source_id": 4, "caption": "1-2 sentences about the APOD image"}}
}}

Rules:
- main_events: pick the 3-4 most important stories of the week. Prefer stories
  covered by several sources; merge duplicates into one event citing all of them.
- arxiv_picks: pick 2-3 papers (kind=paper) that a general reader would find
  exciting, and explain each in plain words.
- photo_of_week: source_id must point to an APOD source (source=apod).
- Every source_id must exist in the numbered list above.
- Plain English, no jargon, friendly tone."""


def _extract_json(text: str) -> dict:
    """Parse the model response, tolerating optional markdown code fences."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return json.loads(cleaned)


def generate_issue(days: int = 7) -> dict | None:
    """Generate this week's issue. Returns dict with 'issue' and 'sources', or None."""
    articles = list_recent_articles(days)
    papers = list_recent_papers(days)
    sw = get_space_weather_summary(days)

    if len(articles) > MAX_ARTICLES:
        logger.warning("Capping articles %d -> %d", len(articles), MAX_ARTICLES)
        articles = articles[:MAX_ARTICLES]
    if len(papers) > MAX_PAPERS:
        logger.warning("Capping papers %d -> %d", len(papers), MAX_PAPERS)
        papers = papers[:MAX_PAPERS]

    if not articles and not papers:
        logger.error("Nothing to write about: no articles or papers in the last %d days", days)
        return None

    sources = build_sources(articles, papers)
    logger.info(
        "Generating issue from %d articles + %d papers", len(articles), len(papers)
    )

    client = anthropic.Anthropic(api_key=get_settings().anthropic_api_key)
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": build_user_prompt(sources, sw)}],
        )
    except anthropic.APIError as e:
        logger.error("Anthropic API call failed: %s", e)
        return None

    raw = response.content[0].text
    try:
        issue = _extract_json(raw)
    except json.JSONDecodeError as e:
        logger.error("Model did not return valid JSON: %s\nFirst 500 chars: %s", e, raw[:500])
        return None

    logger.info(
        "Issue generated: %s (input tokens=%d, output tokens=%d)",
        issue.get("title", "<untitled>"),
        response.usage.input_tokens,
        response.usage.output_tokens,
    )
    return {"issue": issue, "sources": sources}


def main() -> int:
    setup_logging()
    result = generate_issue()
    if result is None:
        print("Failed to generate the issue (see errors above).", file=sys.stderr)
        return 1

    issue = result["issue"]
    sources = {s.number: s for s in result["sources"]}

    def cite(ids: list[int]) -> str:
        return " ".join(f"[{i}]" for i in ids)

    print()
    print("=" * 72)
    print(issue["title"].upper())
    print("=" * 72)
    print()
    print(issue["intro"])
    print()
    print("--- TOP STORIES OF THE WEEK ---")
    for event in issue["main_events"]:
        print(f"\n## {event['heading']} {cite(event['source_ids'])}")
        print(event["text"])
    print()
    print("--- ARXIV IN PLAIN WORDS ---")
    for pick in issue["arxiv_picks"]:
        print(f"\n## {pick['heading']} {cite(pick['source_ids'])}")
        print(pick["text"])
    print()
    print("--- SPACE WEATHER ---")
    print(issue["space_weather_summary"])
    print()
    print("--- PHOTO OF THE WEEK ---")
    photo = issue["photo_of_week"]
    print(f"{photo['caption']} {cite([photo['source_id']])}")
    print()
    print("--- SOURCES CITED ---")
    cited: set[int] = set()
    for event in issue["main_events"] + issue["arxiv_picks"]:
        cited.update(event["source_ids"])
    cited.add(issue["photo_of_week"]["source_id"])
    for num in sorted(cited):
        if num in sources:
            print(f"[{num}] {sources[num].title}\n     {sources[num].url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
