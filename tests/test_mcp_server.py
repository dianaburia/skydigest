"""Tests for the MCP server's pure logic (no model, no client)."""

from observatory.mcp_server import ISSUE_TEXT_LIMIT, issue_html_to_text


def test_issue_text_strips_style_and_tags():
    html = (
        "<html><head><style>body { color: red; }</style></head>"
        "<body><h1>Top stories</h1><p>A comet<br/>appeared.</p></body></html>"
    )
    text = issue_html_to_text(html)
    assert text == "Top stories A comet appeared."
    assert "color" not in text


def test_issue_text_is_capped():
    html = "<p>" + "word " * 10_000 + "</p>"
    assert len(issue_html_to_text(html)) <= ISSUE_TEXT_LIMIT
