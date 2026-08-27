"""Tests for the /ask daily rate limiter."""

from datetime import date, timedelta

from fastapi.testclient import TestClient

from observatory.api.main import DailyIpRateLimiter, app, get_rate_limiter

client = TestClient(app)


def test_allows_up_to_limit_then_blocks():
    limiter = DailyIpRateLimiter(limit=3)
    assert [limiter.allow("1.2.3.4") for _ in range(4)] == [True, True, True, False]


def test_ips_counted_independently():
    limiter = DailyIpRateLimiter(limit=1)
    assert limiter.allow("1.1.1.1") is True
    assert limiter.allow("2.2.2.2") is True
    assert limiter.allow("1.1.1.1") is False


def test_new_day_resets_counts():
    limiter = DailyIpRateLimiter(limit=1)
    today = date(2026, 8, 26)
    assert limiter.allow("1.1.1.1", today=today) is True
    assert limiter.allow("1.1.1.1", today=today) is False
    assert limiter.allow("1.1.1.1", today=today + timedelta(days=1)) is True


def test_ask_returns_429_when_exhausted():
    # Exhaust the shared limiter for the test client's IP; the 429 must be
    # raised BEFORE any retrieval/LLM work, so no DB or network is touched.
    limiter = get_rate_limiter()
    ip = "testclient"
    limiter._counts[ip] = limiter.limit
    try:
        response = client.post("/ask", json={"question": "anything"})
        assert response.status_code == 429
        assert "limit" in response.json()["detail"].lower()
    finally:
        limiter._counts.pop(ip, None)
