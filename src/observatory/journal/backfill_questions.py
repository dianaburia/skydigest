"""One-off backfill: suggested reader questions for pre-feature issues.

New issues get their questions in the same model call that writes the issue
(see generate.py). Issues generated before that only have rendered HTML, so
this module feeds the issue text back to Claude and stores 8-10 questions
per issue. Safe to re-run: only issues with an empty question list are
processed.

Run locally against the local DB, or against production via
``railway run`` (needs DATABASE_URL and ANTHROPIC_API_KEY in the env).
"""

import json
import logging
import re
import sys

import anthropic

from observatory.config import get_settings
from observatory.infra.logging_setup import setup_logging
from observatory.journal.generate import MODEL, _extract_json
from observatory.repository import (
    Issue,
    list_issues_without_questions,
    set_issue_suggested_questions,
)
from observatory.text import clean_text

logger = logging.getLogger(__name__)

# Enough for a whole issue's text; keeps the prompt (and cost) bounded.
ISSUE_TEXT_LIMIT = 8000

# clean_text strips tags but keeps tag CONTENT, and issue HTML starts with a
# big inline <style> block — drop style/script blocks entirely first.
_STYLE_OR_SCRIPT = re.compile(r"<(style|script)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)

SYSTEM_PROMPT = """\
You write short questions that a curious reader with no scientific background
might ask after reading an astronomy magazine issue. You respond with valid
JSON only."""


def build_questions_prompt(issue_text: str) -> str:
    return f"""\
Here is the text of one weekly issue of an astronomy magazine:

=== ISSUE TEXT ===
{issue_text}

=== TASK ===
Respond with ONLY a JSON array of 8-10 short questions (under 90 characters
each) that a curious reader might ask after reading this issue. Each question
must be answerable from the issue's stories. Vary the topics across the whole
issue. Plain English, no jargon."""


def generate_questions(client: anthropic.Anthropic, issue: Issue) -> list[str] | None:
    """Ask the model for reader questions about one issue; None on failure."""
    issue_text = clean_text(_STYLE_OR_SCRIPT.sub(" ", issue.html), limit=ISSUE_TEXT_LIMIT)
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": build_questions_prompt(issue_text)}],
        )
    except anthropic.APIError as e:
        logger.error("Anthropic API call failed for %s: %s", issue.issue_date, e)
        return None
    raw = response.content[0].text
    try:
        questions = _extract_json(raw)
    except json.JSONDecodeError as e:
        logger.error("Invalid JSON for %s: %s\nFirst 200 chars: %s", issue.issue_date, e, raw[:200])
        return None
    if not isinstance(questions, list) or not all(isinstance(q, str) for q in questions):
        logger.error("Expected a JSON array of strings for %s, got: %r", issue.issue_date, questions)
        return None
    return questions


def backfill() -> int:
    """Generate and store questions for every issue lacking them.

    Returns the number of issues updated."""
    issues = list_issues_without_questions()
    if not issues:
        logger.info("All issues already have suggested questions.")
        return 0
    client = anthropic.Anthropic(api_key=get_settings().anthropic_api_key)
    updated = 0
    for issue in issues:
        questions = generate_questions(client, issue)
        if questions is None:
            continue  # logged above; the rest of the issues still get theirs
        set_issue_suggested_questions(issue.issue_date, questions)
        logger.info("Stored %d questions for issue %s", len(questions), issue.issue_date)
        updated += 1
    return updated


def main() -> int:
    setup_logging()
    updated = backfill()
    print(f"Issues updated with suggested questions: {updated}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
