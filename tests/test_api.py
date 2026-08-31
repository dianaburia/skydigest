"""Tests for the FastAPI app wiring (no DB, no model, no external calls)."""

from fastapi.testclient import TestClient

from observatory.api.main import app

client = TestClient(app)


def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_index_serves_journal_or_fallback():
    # / is the journal front page: either the latest issue or the
    # "no issue yet" placeholder — both are branded HTML. Issues generated
    # before the 2026-08-31 rebrand say "Observatory", newer ones "Skydigest".
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Skydigest" in response.text or "Observatory" in response.text


def test_chat_page_served_at_chat():
    response = client.get("/chat")
    assert response.status_code == 200
    assert "Ask the Archive" in response.text


def test_ask_rejects_empty_question():
    # pydantic validation (min_length=1) must reject before any RAG work happens
    response = client.post("/ask", json={"question": ""})
    assert response.status_code == 422
