"""Tests for the retry behavior of the shared HTTP helper.

httpx.get is stubbed with real httpx.Response objects (no network),
and retry_delay=0 so the tests never sleep.
"""

import httpx

from observatory.infra import http


def _stub_responses(monkeypatch, statuses: list[int]):
    """Make http's httpx.get return the given status codes in order.

    Returns the list of recorded calls so tests can assert how many
    attempts were made. The last status repeats if exhausted.
    """
    calls: list[int] = []

    def fake_get(url, *, params=None, timeout=None, follow_redirects=False):
        status = statuses[min(len(calls), len(statuses) - 1)]
        calls.append(status)
        request = httpx.Request("GET", url)
        return httpx.Response(status, json={"ok": True}, request=request)

    monkeypatch.setattr(http.httpx, "get", fake_get)
    return calls


def test_get_json_retries_transient_500_then_succeeds(monkeypatch):
    calls = _stub_responses(monkeypatch, [500, 200])
    result = http.get_json("https://example.com/api", retry_delay=0)
    assert result == {"ok": True}
    assert calls == [500, 200]


def test_get_json_gives_up_after_all_attempts(monkeypatch):
    calls = _stub_responses(monkeypatch, [500])
    result = http.get_json("https://example.com/api", attempts=3, retry_delay=0)
    assert result is None
    assert calls == [500, 500, 500]


def test_get_json_client_error_fails_immediately(monkeypatch):
    calls = _stub_responses(monkeypatch, [404])
    result = http.get_json("https://example.com/api", retry_delay=0)
    assert result is None
    assert calls == [404]
